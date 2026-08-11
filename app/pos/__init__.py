from datetime import datetime, timezone

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from app.models import (db, Client, Product, Sale, SaleItem, Invoice, StockMovement)
from app.utils import update_stock, log_activity, recalc_client
from app.pos.forms import SaleForm

pos_bp = Blueprint('pos', __name__)

CASH_CLIENT_NAME = 'نقدي'


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _customer_choices():
    return [(c.id, c.name) for c in Client.query.filter_by(type='customer')
            .order_by(Client.name).all()]


def _cash_client():
    """عميل افتراضي «نقدي» للمبيعات النقدية الفورية — يُنشأ مرة واحدة ويعاد استخدامه."""
    c = Client.query.filter_by(name=CASH_CLIENT_NAME, type='customer').first()
    if not c:
        c = Client(name=CASH_CLIENT_NAME, type='customer', phone='0000000000',
                   notes='عميل افتراضي للمبيعات النقدية الفورية')
        db.session.add(c)
        db.session.flush()
    return c


def _get_sale_or_404(sid):
    sale = db.session.get(Sale, sid)
    if not sale:
        from flask import abort
        abort(404)
    return sale


def _next_invoice_number():
    today = _now().strftime('%Y%m%d')
    prefix = f'POS-{today}-'
    count = Sale.query.filter(Sale.invoice_number.like(prefix + '%')).count()
    for seq in range(count + 1, count + 100):
        number = f'{prefix}{seq:03d}'
        if not Sale.query.filter_by(invoice_number=number).first():
            return number
    return f'{prefix}{_now().timestamp():.0f}'


def _compute_totals(items, discount_type, discount_value):
    subtotal = sum(float(it['quantity']) * float(it['unit_price']) for it in items)
    disc = float(discount_value or 0)
    if discount_type == 'percent':
        disc = subtotal * disc / 100.0
    if disc < 0:
        disc = 0
    if disc > subtotal:
        disc = subtotal
    return subtotal, disc, subtotal - disc


@pos_bp.route('/')
@login_required
def index():
    search = request.args.get('q', '').strip()
    products_q = Product.query.filter_by(is_active=True)
    if search:
        like = f'%{search}%'
        products_q = products_q.filter(db.or_(Product.name.ilike(like),
                                              Product.sku.ilike(like),
                                              Product.barcode.ilike(like)))
    products = products_q.order_by(Product.name).limit(60).all()
    customers = Client.query.filter_by(type='customer').order_by(Client.name).all()
    return render_template('pos/index.html', products=products, search=search,
                           customers=customers)


@pos_bp.route('/api/product')
@login_required
def product_lookup():
    """بحث فوري لمنتج واحد (للماسح الضوئي): الباركود ثم SKU ثم الاسم."""
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'error': 'أدخل باركود أو SKU أو اسم'}), 400
    p = Product.query.filter_by(barcode=q, is_active=True).first()
    if not p:
        p = Product.query.filter_by(sku=q, is_active=True).first()
    if not p:
        p = (Product.query
             .filter(Product.name.ilike(f'%{q}%'), Product.is_active.is_(True))
             .order_by(Product.name).first())
    if not p:
        return jsonify({'error': 'لا يوجد منتج مطابق'}), 404
    return jsonify({
        'id': p.id,
        'name': p.name,
        'sku': p.sku,
        'barcode': p.barcode,
        'selling_price': float(p.selling_price or 0),
        'current_stock': float(p.current_stock or 0),
        'unit': p.unit,
    })


@pos_bp.route('/complete', methods=['POST'])
@login_required
def complete():
    if not (current_user.can_edit or current_user.can_pos):
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('pos.index'))
    form = SaleForm()
    form.client_id.choices = _customer_choices()
    if not form.validate():
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
        return redirect(url_for('pos.index'))

    items, errors = form.get_items_from_request(request)
    if errors:
        for e in errors:
            flash(e, 'danger')
        return redirect(url_for('pos.index'))

    payment_method = form.payment_method.data
    client_id = form.client_id.data or None
    if payment_method == 'credit' and not client_id:
        flash('يجب اختيار عميل للبيع الآجل', 'danger')
        return redirect(url_for('pos.index'))
    if payment_method != 'credit' and not client_id:
        client_id = _cash_client().id

    subtotal, discount, total = _compute_totals(items, form.discount_type.data,
                                                form.get_discount_decimal())
    date_val = form.date.data or _now().date()

    try:
        sale = Sale(
            invoice_number=_next_invoice_number(),
            client_id=client_id,
            date=date_val,
            subtotal=subtotal,
            discount=discount,
            total=total,
            payment_method=payment_method,
            status='completed',
            notes=(form.notes.data or '').strip() or None,
            created_by=current_user.id,
        )
        db.session.add(sale)
        db.session.flush()
        for it in items:
            db.session.add(SaleItem(
                sale_id=sale.id,
                product_id=it['product'].id,
                quantity=it['quantity'],
                unit_price=it['unit_price'],
            ))
        for it in items:
            ok, msg = update_stock(it['product'], it['quantity'], 'OUT',
                                   reference=sale.invoice_number,
                                   notes=f'بيع {sale.invoice_number}',
                                   user_id=current_user.id)
            if not ok:
                db.session.rollback()
                flash(f'لا يمكن بيع "{it["product"].name}": {msg}', 'danger')
                return redirect(url_for('pos.index'))

        if payment_method == 'credit' and client_id:
            db.session.add(Invoice(
                client_id=client_id,
                description=f'بيع آجل - {sale.invoice_number}',
                amount=total,
                sale_id=sale.id,
                date=date_val,
            ))
        try:
            with db.session.begin_nested():
                from app.accounts.auto import post_sale_entries
                post_sale_entries(sale, current_user.id)
        except Exception:
            pass
        db.session.commit()
        if payment_method == 'credit' and client_id:
            recalc_client(client_id)
        log_activity(current_user.id, 'add', 'sale', sale.id,
                     f'بيع {sale.invoice_number} ({payment_method})',
                     request.remote_addr)
        flash(f'تم إتمام البيع "{sale.invoice_number}"', 'success')
        return redirect(url_for('pos.sale_detail', sid=sale.id))
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ أثناء إتمام البيع: {e}', 'danger')
        return redirect(url_for('pos.index'))


@pos_bp.route('/history')
@login_required
def history():
    search = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')
    date_from = request.args.get('from', '').strip()
    date_to = request.args.get('to', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    q = Sale.query
    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(Sale.invoice_number.ilike(like),
                            Sale.client.has(Client.name.ilike(like))))
    if status_filter in ('completed', 'cancelled'):
        q = q.filter_by(status=status_filter)
    if date_from:
        q = q.filter(Sale.date >= date_from)
    if date_to:
        q = q.filter(Sale.date <= date_to)

    pagination = q.order_by(Sale.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False)

    stats = {
        'today_count': Sale.query.filter_by(date=_now().date(), status='completed').count(),
        'today_total': sum(float(s.total or 0) for s in
                           Sale.query.filter_by(date=_now().date(), status='completed').all()),
        'total_sales': Sale.query.filter_by(status='completed').count(),
        'cash_count': Sale.query.filter_by(status='completed', payment_method='cash').count(),
    }
    return render_template('pos/history.html', sales=pagination.items,
                           pagination=pagination, stats=stats,
                           search=search, status_filter=status_filter,
                           date_from=date_from, date_to=date_to)


@pos_bp.route('/<int:sid>')
@login_required
def sale_detail(sid):
    sale = _get_sale_or_404(sid)
    return render_template('pos/sale_detail.html', sale=sale)


@pos_bp.route('/<int:sid>/receipt')
@login_required
def receipt(sid):
    sale = _get_sale_or_404(sid)
    return render_template('pos/receipt.html', sale=sale)


@pos_bp.route('/<int:sid>/print', methods=['POST'])
@login_required
def print_sale(sid):
    if not (current_user.can_edit or current_user.can_pos):
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('pos.sale_detail', sid=sid))
    sale = _get_sale_or_404(sid)
    from app.pos.printer import print_receipt
    ok, msg = print_receipt(sale)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('pos.sale_detail', sid=sid))


@pos_bp.route('/<int:sid>/cancel', methods=['POST'])
@login_required
def cancel_sale(sid):
    if not current_user.is_admin:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('pos.history'))
    sale = _get_sale_or_404(sid)
    if sale.status != 'completed':
        flash('البيع ملغى بالفعل', 'warning')
        return redirect(url_for('pos.sale_detail', sid=sid))

    try:
        for it in sale.items:
            ok, msg = update_stock(it.product, it.quantity, 'IN',
                                   reference=sale.invoice_number,
                                   notes=f'إلغاء بيع {sale.invoice_number}',
                                   user_id=current_user.id)
            if not ok:
                db.session.rollback()
                flash(f'فشل إلغاء البند "{it.product.name}": {msg}', 'danger')
                return redirect(url_for('pos.sale_detail', sid=sid))
        linked_invoice = sale.invoice
        if linked_invoice:
            client_id = linked_invoice.client_id
            db.session.delete(linked_invoice)
        sale.status = 'cancelled'
        try:
            with db.session.begin_nested():
                from app.accounts.auto import reverse_sale_entries
                reverse_sale_entries(sale, current_user.id)
        except Exception:
            pass
        db.session.commit()
        if linked_invoice:
            recalc_client(client_id)
        log_activity(current_user.id, 'edit', 'sale', sale.id,
                     f'إلغاء بيع {sale.invoice_number}', request.remote_addr)
        flash(f'تم إلغاء البيع "{sale.invoice_number}" وعكس المخزون', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ أثناء الإلغاء: {e}', 'danger')
    return redirect(url_for('pos.sale_detail', sid=sid))
