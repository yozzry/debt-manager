import io
import re
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user

from app.models import db, Product, Category, StockMovement
from app.utils import update_stock, log_activity
from app.products.forms import ProductForm, CategoryForm, StockAdjustForm

products_bp = Blueprint('products', __name__)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _category_choices():
    return [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]


def _barcode_code(product):
    code = (product.barcode or '').strip() or (product.sku or '').strip()
    code = re.sub(r'[^\x20-\x7e]', '', code)
    if not code:
        code = str(product.id or '')
    if not code:
        code = '0'
    return code


def generate_barcode_svg(product):
    """توليد SVG باركود (Code128) للمنتج. تُرجع نص SVG أو None عند الفشل."""
    try:
        import barcode
        from barcode.writer import SVGWriter
    except Exception:
        return None
    try:
        writer = SVGWriter()
        bc = barcode.get('code128', _barcode_code(product), writer=writer)
        buf = io.BytesIO()
        bc.write(buf, options={
            'module_width': 0.22,
            'module_height': 15,
            'font_size': 11,
            'text_distance': 1,
            'quiet_zone': 6.5,
        })
        return buf.getvalue().decode('utf-8')
    except Exception:
        return None


def generate_barcode_png(product):
    """توليد PNG باركود (Code128) للمنتج — مناسب للطباعة الحرارية/المباشرة."""
    try:
        import barcode
        from barcode.writer import ImageWriter
    except Exception:
        return None
    try:
        writer = ImageWriter()
        bc = barcode.get('code128', _barcode_code(product), writer=writer)
        buf = io.BytesIO()
        bc.write(buf, options={
            'module_width': 0.25,
            'module_height': 12,
            'font_size': 10,
            'text_distance': 2,
            'quiet_zone': 6,
            'dpi': 300,
        })
        return buf.getvalue()
    except Exception:
        return None


@products_bp.route('/')
@login_required
def index():
    search = request.args.get('q', '').strip()
    category_id = request.args.get('category', '', type=int) or None
    stock_filter = request.args.get('stock', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    q = Product.query
    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(Product.name.ilike(like),
                            Product.sku.ilike(like),
                            Product.barcode.ilike(like)))
    if category_id:
        q = q.filter_by(category_id=category_id)
    if stock_filter == 'low':
        q = q.filter(Product.current_stock > 0, Product.current_stock <= Product.min_stock)
    elif stock_filter == 'out':
        q = q.filter(Product.current_stock <= 0)
    elif stock_filter == 'ok':
        q = q.filter(Product.current_stock > Product.min_stock)

    pagination = q.order_by(Product.name).paginate(
        page=page, per_page=per_page, error_out=False)

    filtered_ids = [p.id for p in pagination.items]
    stock_value = sum(float(p.cost_price or 0) * float(p.current_stock or 0)
                      for p in pagination.items)
    total_qty = sum(float(p.current_stock or 0) for p in pagination.items)

    stats = {
        'total_products': Product.query.count(),
        'filtered_count': pagination.total,
        'total_qty': total_qty,
        'stock_value': stock_value,
        'low_count': Product.query.filter(Product.current_stock > 0,
                                          Product.current_stock <= Product.min_stock).count(),
        'out_count': Product.query.filter(Product.current_stock <= 0).count(),
    }
    categories = Category.query.order_by(Category.name).all()
    return render_template('products/index.html',
                           products=pagination.items,
                           pagination=pagination, stats=stats,
                           categories=categories,
                           search=search, category_id=category_id,
                           stock_filter=stock_filter)


@products_bp.route('/low-stock')
@login_required
def low_stock():
    low = Product.query.filter_by(is_active=True).all()
    low = [p for p in low if p.stock_status != 'ok']
    low.sort(key=lambda p: (p.stock_status == 'out', float(p.current_stock)))
    categories = Category.query.order_by(Category.name).all()
    return render_template('products/low_stock.html', products=low,
                           categories=categories)


@products_bp.route('/movements')
@login_required
def movements():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    pagination = StockMovement.query.order_by(StockMovement.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    return render_template('products/stock_movements.html', pagination=pagination)


@products_bp.route('/add', methods=['GET', 'POST'])
@login_required
def product_add():
    if not current_user.can_edit:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('products.index'))
    form = ProductForm()
    form.category_id.choices = [(0, 'بدون تصنيف')] + _category_choices()
    if request.method == 'POST' and form.validate():
        try:
            p = Product(
                name=form.name.data.strip(),
                sku=(form.sku.data or '').strip() or None,
                barcode=(form.barcode.data or '').strip() or None,
                category_id=form.category_id.data or None,
                unit=(form.unit.data or '').strip() or 'قطعة',
                cost_price=form.get_field_decimal('cost_price'),
                selling_price=form.get_field_decimal('selling_price'),
                min_stock=form.get_field_decimal('min_stock'),
                current_stock=0,
                description=(form.description.data or '').strip() or None,
                is_active=('is_active' in request.form),
            )
            db.session.add(p)
            db.session.commit()
            log_activity(current_user.id, 'add', 'product', p.id,
                         f'إضافة منتج: {p.name}', request.remote_addr)
            flash(f'تم إضافة المنتج "{p.name}" بنجاح', 'success')
            return redirect(url_for('products.product_detail', pid=p.id))
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ أثناء الحفظ: {e}', 'danger')
    elif request.method == 'POST':
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
    return render_template('products/product_edit.html', product=None, form=form,
                           categories=_category_choices())


@products_bp.route('/<int:pid>')
@login_required
def product_detail(pid):
    p = db.session.get(Product, pid)
    if not p:
        from flask import abort
        abort(404)
    movements_list = StockMovement.query.filter_by(product_id=pid) \
        .order_by(StockMovement.id.desc()).limit(50).all()
    return render_template('products/product_detail.html', product=p,
                           movements=movements_list)


@products_bp.route('/<int:pid>/edit', methods=['GET', 'POST'])
@login_required
def product_edit(pid):
    if not current_user.can_edit:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('products.index'))
    p = db.session.get(Product, pid)
    if not p:
        from flask import abort
        abort(404)
    form = ProductForm()
    form.category_id.choices = [(0, 'بدون تصنيف')] + _category_choices()
    if request.method == 'POST' and form.validate():
        p.name = form.name.data.strip()
        p.sku = (form.sku.data or '').strip() or None
        p.barcode = (form.barcode.data or '').strip() or None
        p.category_id = form.category_id.data or None
        p.unit = (form.unit.data or '').strip() or 'قطعة'
        p.cost_price = form.get_field_decimal('cost_price')
        p.selling_price = form.get_field_decimal('selling_price')
        p.min_stock = form.get_field_decimal('min_stock')
        p.description = (form.description.data or '').strip() or None
        p.is_active = ('is_active' in request.form)
        p.updated_at = _now()
        db.session.commit()
        log_activity(current_user.id, 'edit', 'product', p.id,
                     f'تعديل منتج: {p.name}', request.remote_addr)
        flash('تم تحديث بيانات المنتج', 'success')
        return redirect(url_for('products.product_detail', pid=pid))
    elif request.method == 'POST':
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
    return render_template('products/product_edit.html', product=p, form=form,
                           categories=_category_choices())


@products_bp.route('/<int:pid>/delete', methods=['POST'])
@login_required
def product_delete(pid):
    if not current_user.is_admin:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('products.index'))
    p = db.session.get(Product, pid)
    if not p:
        from flask import abort
        abort(404)
    name = p.name
    log_activity(current_user.id, 'delete', 'product', pid,
                 f'حذف منتج: {name}', request.remote_addr)
    db.session.delete(p)
    db.session.commit()
    flash(f'تم حذف المنتج "{name}"', 'success')
    return redirect(url_for('products.index'))


@products_bp.route('/<int:pid>/stock', methods=['GET', 'POST'])
@login_required
def stock_adjust(pid):
    if not current_user.can_edit:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('products.index'))
    p = db.session.get(Product, pid)
    if not p:
        from flask import abort
        abort(404)
    form = StockAdjustForm()
    if request.method == 'POST' and form.validate():
        qty = form.get_quantity_decimal()
        mtype = form.movement_type.data
        ok, msg = update_stock(p, qty, mtype,
                               reference=f'manual-{mtype}',
                               notes=(form.notes.data or '').strip() or None,
                               user_id=current_user.id)
        if ok:
            db.session.commit()
            log_activity(current_user.id, 'edit', 'product', p.id,
                         f'تسوية مخزون {p.name} ({mtype} {qty})',
                         request.remote_addr)
            flash(f'تم تحديث المخزون: {msg}', 'success')
            return redirect(url_for('products.product_detail', pid=pid))
        db.session.rollback()
        flash(msg, 'danger')
    elif request.method == 'POST':
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
    return render_template('products/stock_adjust.html', product=p, form=form)


@products_bp.route('/barcode/<int:pid>')
@login_required
def barcode_label(pid):
    p = db.session.get(Product, pid)
    if not p:
        from flask import abort
        abort(404)
    return render_template('products/barcode_label.html', product=p,
                           barcode_code=_barcode_code(p))


@products_bp.route('/barcode/<int:pid>/image')
@login_required
def barcode_image(pid):
    p = db.session.get(Product, pid)
    if not p:
        from flask import abort
        abort(404)
    svg = generate_barcode_svg(p)
    if not svg:
        from flask import jsonify
        return jsonify({'ok': False, 'msg': 'تعذر توليد الباركود'}), 500
    return Response(svg, mimetype='image/svg+xml')


@products_bp.route('/barcode/<int:pid>/image.png')
@login_required
def barcode_image_png(pid):
    p = db.session.get(Product, pid)
    if not p:
        from flask import abort
        abort(404)
    png = generate_barcode_png(p)
    if not png:
        from flask import jsonify
        return jsonify({'ok': False, 'msg': 'تعذر توليد الباركود'}), 500
    return Response(png, mimetype='image/png')


@products_bp.route('/categories', methods=['GET', 'POST'])
@login_required
def categories():
    if request.method == 'POST':
        if not current_user.can_edit:
            flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
            return redirect(url_for('products.categories'))
        form = CategoryForm()
        if form.validate():
            name = form.name.data.strip()
            existing = Category.query.filter_by(name=name).first()
            if existing:
                flash('يوجد تصنيف بنفس الاسم', 'danger')
            else:
                c = Category(name=name,
                             description=(form.description.data or '').strip() or None)
                db.session.add(c)
                db.session.commit()
                log_activity(current_user.id, 'add', 'category', c.id,
                             f'إضافة تصنيف: {name}', request.remote_addr)
                flash(f'تم إضافة التصنيف "{name}"', 'success')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(error, 'danger')
        return redirect(url_for('products.categories'))
    cats = Category.query.order_by(Category.name).all()
    return render_template('products/categories.html', categories=cats)


@products_bp.route('/categories/<int:cid>/delete', methods=['POST'])
@login_required
def category_delete(cid):
    if not current_user.is_admin:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('products.categories'))
    c = db.session.get(Category, cid)
    if not c:
        from flask import abort
        abort(404)
    name = c.name
    products_count = Product.query.filter_by(category_id=cid).count()
    if products_count:
        flash(f'لا يمكن حذف التصنيف — يوجد {products_count} منتج مرتبط به', 'danger')
        return redirect(url_for('products.categories'))
    log_activity(current_user.id, 'delete', 'category', cid,
                 f'حذف تصنيف: {name}', request.remote_addr)
    db.session.delete(c)
    db.session.commit()
    flash(f'تم حذف التصنيف "{name}"', 'success')
    return redirect(url_for('products.categories'))

