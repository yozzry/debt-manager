from datetime import datetime, timezone

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.models import db, Client, Product, PurchaseOrder, PurchaseItem
from app.utils import update_stock, log_activity
from app.purchases.forms import PurchaseOrderForm

purchases_bp = Blueprint('purchases', __name__)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _supplier_choices():
    return [(c.id, c.name) for c in Client.query.filter_by(type='supplier')
            .order_by(Client.name).all()]


def _get_order_or_404(oid):
    order = db.session.get(PurchaseOrder, oid)
    if not order:
        from flask import abort
        abort(404)
    return order


def _next_order_number():
    today = _now().strftime('%Y%m%d')
    prefix = f'PO-{today}-'
    count = PurchaseOrder.query.filter(PurchaseOrder.order_number.like(prefix + '%')).count()
    for seq in range(count + 1, count + 100):
        number = f'{prefix}{seq:03d}'
        if not PurchaseOrder.query.filter_by(order_number=number).first():
            return number
    return f'{prefix}{_now().timestamp():.0f}'


@purchases_bp.route('/')
@login_required
def index():
    search = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    q = PurchaseOrder.query
    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(PurchaseOrder.order_number.ilike(like),
                            PurchaseOrder.supplier.has(Client.name.ilike(like))))
    if status_filter in ('draft', 'received', 'cancelled'):
        q = q.filter_by(status=status_filter)

    pagination = q.order_by(PurchaseOrder.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False)

    stats = {
        'total_orders': PurchaseOrder.query.count(),
        'draft_count': PurchaseOrder.query.filter_by(status='draft').count(),
        'received_count': PurchaseOrder.query.filter_by(status='received').count(),
        'total_value': sum(float(o.total_amount or 0)
                           for o in PurchaseOrder.query.filter_by(status='received').all()),
    }
    return render_template('purchases/index.html',
                           orders=pagination.items,
                           pagination=pagination, stats=stats,
                           search=search, status_filter=status_filter)


@purchases_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_order():
    if not current_user.can_edit:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('purchases.index'))
    form = PurchaseOrderForm()
    form.supplier_id.choices = _supplier_choices()
    suppliers = Client.query.filter_by(type='supplier').order_by(Client.name).all()
    products = Product.query.order_by(Product.name).all()
    if not suppliers:
        flash('أضف مورداً أولاً من صفحة العملاء (نوع: مورد)', 'warning')

    if request.method == 'POST' and form.validate():
        items, errors = form.get_items_from_request(request)
        if errors:
            for e in errors:
                flash(e, 'danger')
        else:
            try:
                order = PurchaseOrder(
                    order_number=_next_order_number(),
                    supplier_id=form.supplier_id.data,
                    date=form.date.data,
                    status='draft',
                    notes=(form.notes.data or '').strip() or None,
                    created_by=current_user.id,
                )
                db.session.add(order)
                db.session.flush()
                for it in items:
                    db.session.add(PurchaseItem(
                        order_id=order.id,
                        product_id=it['product'].id,
                        quantity=it['quantity'],
                        unit_cost=it['unit_cost'],
                    ))
                order.total_amount = sum(float(it['quantity']) * float(it['unit_cost']) for it in items)
                db.session.commit()
                log_activity(current_user.id, 'add', 'purchase_order', order.id,
                             f'إنشاء أمر شراء: {order.order_number}', request.remote_addr)
                flash(f'تم إنشاء أمر الشراء "{order.order_number}"', 'success')
                return redirect(url_for('purchases.order_detail', oid=order.id))
            except Exception as e:
                db.session.rollback()
                flash(f'حدث خطأ أثناء الحفظ: {e}', 'danger')
    elif request.method == 'POST':
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
    return render_template('purchases/order_form.html', form=form,
                           order=None, suppliers=suppliers, products=products)


@purchases_bp.route('/<int:oid>')
@login_required
def order_detail(oid):
    order = _get_order_or_404(oid)
    return render_template('purchases/order_detail.html', order=order)


@purchases_bp.route('/<int:oid>/edit', methods=['GET', 'POST'])
@login_required
def edit_order(oid):
    if not current_user.can_edit:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('purchases.index'))
    order = _get_order_or_404(oid)
    if order.status != 'draft':
        flash('يمكن تعديل أوامر الشراء المسودة فقط', 'danger')
        return redirect(url_for('purchases.order_detail', oid=oid))
    form = PurchaseOrderForm(obj=order)
    form.supplier_id.choices = _supplier_choices()
    suppliers = Client.query.filter_by(type='supplier').order_by(Client.name).all()
    products = Product.query.order_by(Product.name).all()

    if request.method == 'POST' and form.validate():
        items, errors = form.get_items_from_request(request)
        if errors:
            for e in errors:
                flash(e, 'danger')
        else:
            try:
                order.supplier_id = form.supplier_id.data
                order.date = form.date.data
                order.notes = (form.notes.data or '').strip() or None
                for old in list(order.items):
                    db.session.delete(old)
                db.session.flush()
                for it in items:
                    db.session.add(PurchaseItem(
                        order_id=order.id,
                        product_id=it['product'].id,
                        quantity=it['quantity'],
                        unit_cost=it['unit_cost'],
                    ))
                order.total_amount = sum(float(it['quantity']) * float(it['unit_cost']) for it in items)
                order.updated_at = _now()
                db.session.commit()
                log_activity(current_user.id, 'edit', 'purchase_order', order.id,
                             f'تعديل أمر شراء: {order.order_number}', request.remote_addr)
                flash('تم تحديث أمر الشراء', 'success')
                return redirect(url_for('purchases.order_detail', oid=order.id))
            except Exception as e:
                db.session.rollback()
                flash(f'حدث خطأ أثناء الحفظ: {e}', 'danger')
    elif request.method == 'POST':
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
    return render_template('purchases/order_form.html', form=form,
                           order=order, suppliers=suppliers, products=products)


@purchases_bp.route('/<int:oid>/receive', methods=['POST'])
@login_required
def receive_order(oid):
    if not current_user.can_edit:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('purchases.index'))
    order = _get_order_or_404(oid)
    if order.status != 'draft':
        flash('لا يمكن استلام هذا الأمر — الحالة الحالية: ' + order.status_label, 'danger')
        return redirect(url_for('purchases.order_detail', oid=oid))
    if not order.items:
        flash('الأمر لا يحتوي على بنود — لا يمكن استلامه', 'danger')
        return redirect(url_for('purchases.order_detail', oid=oid))

    for it in order.items:
        ok, msg = update_stock(it.product, it.quantity, 'IN',
                               reference=order.order_number,
                               notes=f'استلام أمر شراء {order.order_number}',
                               user_id=current_user.id)
        if not ok:
            db.session.rollback()
            flash(f'فشل استلام بند "{it.product.name}": {msg}', 'danger')
            return redirect(url_for('purchases.order_detail', oid=oid))

    order.status = 'received'
    order.recalc_total()
    order.updated_at = _now()
    try:
        with db.session.begin_nested():
            from app.accounts.auto import post_purchase_entries
            post_purchase_entries(order, current_user.id)
    except Exception:
        pass
    db.session.commit()
    log_activity(current_user.id, 'edit', 'purchase_order', order.id,
                 f'استلام أمر شراء: {order.order_number}', request.remote_addr)
    flash(f'تم استلام الأمر "{order.order_number}" وتحديث المخزون', 'success')
    return redirect(url_for('purchases.order_detail', oid=oid))


@purchases_bp.route('/<int:oid>/cancel', methods=['POST'])
@login_required
def cancel_order(oid):
    if not current_user.can_edit:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('purchases.index'))
    order = _get_order_or_404(oid)
    if order.status != 'draft':
        flash('يمكن إلغاء أوامر الشراء المسودة فقط', 'danger')
        return redirect(url_for('purchases.order_detail', oid=oid))
    order.status = 'cancelled'
    order.updated_at = _now()
    db.session.commit()
    log_activity(current_user.id, 'edit', 'purchase_order', order.id,
                 f'إلغاء أمر شراء: {order.order_number}', request.remote_addr)
    flash(f'تم إلغاء الأمر "{order.order_number}"', 'warning')
    return redirect(url_for('purchases.order_detail', oid=oid))


@purchases_bp.route('/<int:oid>/delete', methods=['POST'])
@login_required
def delete_order(oid):
    if not current_user.is_admin:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('purchases.index'))
    order = _get_order_or_404(oid)
    if order.status == 'received':
        flash('لا يمكن حذف أمر مستلم — استخدم تسوية المخزون لتصحيح الكميات', 'danger')
        return redirect(url_for('purchases.order_detail', oid=oid))
    number = order.order_number
    log_activity(current_user.id, 'delete', 'purchase_order', oid,
                 f'حذف أمر شراء: {number}', request.remote_addr)
    db.session.delete(order)
    db.session.commit()
    flash(f'تم حذف الأمر "{number}"', 'success')
    return redirect(url_for('purchases.index'))
