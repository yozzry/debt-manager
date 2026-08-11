import csv
import io
from datetime import date, timedelta

from flask import Blueprint, render_template, request, send_file
from flask_login import login_required
from sqlalchemy import func

from app.models import (db, Client, Payment, Product, PurchaseOrder,
                        Sale, SaleItem, Account)

dashboard_bp = Blueprint('dashboard', __name__)


# ── Helpers ──

def _parse_date(value, default):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return default


def _first_of_month():
    return date.today().replace(day=1)


def _completed_sales(date_from=None, date_to=None, method=None):
    q = Sale.query.filter_by(status='completed')
    if date_from:
        q = q.filter(Sale.date >= date_from)
    if date_to:
        q = q.filter(Sale.date <= date_to)
    if method in ('cash', 'credit'):
        q = q.filter_by(payment_method=method)
    return q.order_by(Sale.date.desc(), Sale.id.desc()).all()


def _sum_cents(rows, key):
    return sum(float(getattr(r, key) or 0) for r in rows)


def _product_stock_status():
    low = []
    out = []
    for p in Product.query.filter_by(is_active=True).all():
        if p.stock_status == 'out':
            out.append(p)
        elif p.stock_status == 'low':
            low.append(p)
    return low, out


def _inventory_value(products):
    return sum(float(p.current_stock or 0) * float(p.cost_price or 0) for p in products)


def _account_summary():
    """إجمالي أرصدة الحسابات التفصيلية حسب النوع."""
    from app.accounts import _leaf_accounts
    totals = {'asset': 0.0, 'liability': 0.0, 'equity': 0.0,
              'income': 0.0, 'expense': 0.0}
    for a in _leaf_accounts():
        totals[a.account_type] += a.balance()
    return totals


def _csv_response(filename, header, rows):
    buf = io.BytesIO()
    wrapper = io.TextIOWrapper(buf, encoding='utf-8-sig', newline='')
    writer = csv.writer(wrapper)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    wrapper.flush()
    wrapper.detach()
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=filename,
                     mimetype='text/csv')


# ── Dashboard ──

@dashboard_bp.route('/')
@login_required
def index():
    today = date.today()
    first = _first_of_month()
    week_ago = today - timedelta(days=6)

    sales_today = Sale.query.filter_by(status='completed', date=today).all()
    sales_month = Sale.query.filter_by(status='completed').filter(Sale.date >= first).all()
    sales_all = Sale.query.filter_by(status='completed').all()

    payments_month = Payment.query.filter(Payment.date >= first).all()
    payments_today = Payment.query.filter_by(date=today).all()

    low_products, out_products = _product_stock_status()
    active_products = Product.query.filter_by(is_active=True).all()
    inventory_value = _inventory_value(active_products)

    pending_orders = PurchaseOrder.query.filter_by(status='draft').count()
    received_orders = PurchaseOrder.query.filter_by(status='received').all()

    cash_month = sum(float(s.total or 0) for s in sales_month if s.payment_method == 'cash')
    credit_month = sum(float(s.total or 0) for s in sales_month if s.payment_method == 'credit')

    # سلسلة آخر 7 أيام
    trend = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        s_tot = sum(float(s.total or 0) for s in
                    Sale.query.filter_by(status='completed', date=d).all())
        p_tot = sum(float(p.amount or 0) for p in Payment.query.filter_by(date=d).all())
        trend.append({'label': d.strftime('%d/%m'), 'sales': s_tot, 'payments': p_tot})

    # أعلى المنتجات مبيعاً (إجمالي)
    top_products = db.session.query(
        SaleItem.product_id,
        func.sum(SaleItem.quantity).label('qty'),
        func.sum(SaleItem.quantity * SaleItem.unit_price).label('rev')
    ).join(Sale, SaleItem.sale_id == Sale.id) \
        .filter(Sale.status == 'completed') \
        .group_by(SaleItem.product_id) \
        .order_by(func.sum(SaleItem.quantity).desc()) \
        .limit(8).all()
    top_products_list = []
    for row in top_products:
        p = db.session.get(Product, row.product_id)
        top_products_list.append({
            'name': p.name if p else '—',
            'qty': float(row.qty or 0),
            'rev': float(row.rev or 0),
        })

    # أحدث المبيعات وأوامر الشراء المعلقة
    latest_sales = Sale.query.filter_by(status='completed') \
        .order_by(Sale.id.desc()).limit(8).all()
    pending_list = PurchaseOrder.query.filter_by(status='draft') \
        .order_by(PurchaseOrder.id.desc()).limit(8).all()

    low_list = (out_products + low_products)[:8]

    accounts = _account_summary()
    has_accounts = Account.query.count() > 0
    cash_balance = sum(
        float(a.balance()) for a in Account.query.all()
        if a.is_leaf and (a.code == '1101' or a.code == '1102'
                          or a.code.startswith('11')))
    acct = {
        'assets': accounts['asset'],
        'liabilities': accounts['liability'],
        'equity': accounts['equity'],
        'net_income': accounts['income'] - accounts['expense'],
        'cash': cash_balance,
    }

    kpis = {
        'sales_today_count': len(sales_today),
        'sales_today_total': _sum_cents(sales_today, 'total'),
        'sales_month_count': len(sales_month),
        'sales_month_total': _sum_cents(sales_month, 'total'),
        'cash_month': cash_month,
        'credit_month': credit_month,
        'sales_all_total': _sum_cents(sales_all, 'total'),
        'payments_today': _sum_cents(payments_today, 'amount'),
        'payments_month': _sum_cents(payments_month, 'amount'),
        'purchases_month': sum(float(o.total_amount or 0) for o in received_orders
                               if o.date and o.date >= first),
        'purchases_all': sum(float(o.total_amount or 0) for o in received_orders),
        'pending_orders': pending_orders,
        'low_stock_count': len(low_products) + len(out_products),
        'products_count': len(active_products),
        'inventory_value': inventory_value,
        'clients_total': Client.query.count(),
        'outstanding': sum(float(c.total_debt or 0) - float(c.total_paid or 0)
                           for c in Client.query.all()),
    }

    return render_template('dashboard/index.html', kpis=kpis, trend=trend,
                           top_products=top_products_list,
                           latest_sales=latest_sales, pending_list=pending_list,
                           low_list=low_list, accounts=accounts,
                           acct=acct, has_accounts=has_accounts)


# ── Sales report ──

@dashboard_bp.route('/sales-report')
@login_required
def sales_report():
    date_from = _parse_date(request.args.get('from'), None)
    date_to = _parse_date(request.args.get('to'), None)
    method = request.args.get('method', '')

    sales = _completed_sales(date_from, date_to, method or None)

    cash = [s for s in sales if s.payment_method == 'cash']
    credit = [s for s in sales if s.payment_method == 'credit']

    totals = {
        'count': len(sales),
        'subtotal': sum(float(s.subtotal or 0) for s in sales),
        'discount': sum(float(s.discount or 0) for s in sales),
        'total': sum(float(s.total or 0) for s in sales),
        'cash': sum(float(s.total or 0) for s in cash),
        'credit': sum(float(s.total or 0) for s in credit),
    }
    return render_template('dashboard/sales_report.html', sales=sales,
                           totals=totals, date_from=date_from, date_to=date_to,
                           method=method)


@dashboard_bp.route('/sales-report/export')
@login_required
def sales_report_export():
    date_from = _parse_date(request.args.get('from'), None)
    date_to = _parse_date(request.args.get('to'), None)
    method = request.args.get('method', '')
    sales = _completed_sales(date_from, date_to, method or None)
    rows = [[s.invoice_number, s.date.isoformat() if s.date else '',
             s.client.name if s.client else '', s.payment_method_label,
             s.status_label, '{:.2f}'.format(s.subtotal or 0),
             '{:.2f}'.format(s.discount or 0), '{:.2f}'.format(s.total or 0)]
            for s in sales]
    return _csv_response('sales_report.csv',
                         ['رقم الفاتورة', 'التاريخ', 'العميل', 'طريقة الدفع',
                          'الحالة', 'المجموع الفرعي', 'الخصم', 'الإجمالي'],
                         rows)


# ── Purchases report ──

@dashboard_bp.route('/purchases-report')
@login_required
def purchases_report():
    date_from = _parse_date(request.args.get('from'), None)
    date_to = _parse_date(request.args.get('to'), None)
    status = request.args.get('status', '')

    q = PurchaseOrder.query
    if date_from:
        q = q.filter(PurchaseOrder.date >= date_from)
    if date_to:
        q = q.filter(PurchaseOrder.date <= date_to)
    if status in ('draft', 'received', 'cancelled'):
        q = q.filter_by(status=status)
    orders = q.order_by(PurchaseOrder.date.desc(), PurchaseOrder.id.desc()).all()

    received = [o for o in orders if o.status == 'received']
    totals = {
        'count': len(orders),
        'total': sum(float(o.total_amount or 0) for o in orders),
        'received': sum(float(o.total_amount or 0) for o in received),
        'received_count': len(received),
    }
    return render_template('dashboard/purchases_report.html', orders=orders,
                           totals=totals, date_from=date_from, date_to=date_to,
                           status=status)


@dashboard_bp.route('/purchases-report/export')
@login_required
def purchases_report_export():
    date_from = _parse_date(request.args.get('from'), None)
    date_to = _parse_date(request.args.get('to'), None)
    status = request.args.get('status', '')
    q = PurchaseOrder.query
    if date_from:
        q = q.filter(PurchaseOrder.date >= date_from)
    if date_to:
        q = q.filter(PurchaseOrder.date <= date_to)
    if status in ('draft', 'received', 'cancelled'):
        q = q.filter_by(status=status)
    orders = q.order_by(PurchaseOrder.date.desc(), PurchaseOrder.id.desc()).all()
    rows = [[o.order_number, o.date.isoformat() if o.date else '',
             o.supplier.name if o.supplier else '', o.status_label,
             '{:.2f}'.format(o.total_amount or 0), o.notes or '']
            for o in orders]
    return _csv_response('purchases_report.csv',
                         ['رقم الأمر', 'التاريخ', 'المورد', 'الحالة',
                          'الإجمالي', 'ملاحظات'], rows)


# ── Inventory report ──

@dashboard_bp.route('/inventory-report')
@login_required
def inventory_report():
    stock_filter = request.args.get('filter', '')
    products = Product.query.filter_by(is_active=True).all()
    if stock_filter == 'low':
        products = [p for p in products if p.stock_status in ('low', 'out')]
    products.sort(key=lambda p: (p.stock_status != 'out', p.stock_status != 'low', p.name))

    stock_value = _inventory_value(products)
    potential_revenue = sum(float(p.current_stock or 0) * float(p.selling_price or 0)
                            for p in products)
    units = sum(float(p.current_stock or 0) for p in products)
    return render_template('dashboard/inventory_report.html', products=products,
                           stock_filter=stock_filter, stock_value=stock_value,
                           potential_revenue=potential_revenue, units=units)


@dashboard_bp.route('/inventory-report/export')
@login_required
def inventory_report_export():
    products = Product.query.filter_by(is_active=True).all()
    rows = [[p.name, p.sku or '', p.category.name if p.category else '',
             p.unit or '', '{:.2f}'.format(p.current_stock or 0),
             '{:.2f}'.format(p.min_stock or 0), '{:.2f}'.format(p.cost_price or 0),
             '{:.2f}'.format(p.selling_price or 0),
             '{:.2f}'.format(float(p.current_stock or 0) * float(p.cost_price or 0)),
             p.stock_status_label]
            for p in products]
    return _csv_response('inventory_report.csv',
                         ['المنتج', 'SKU', 'التصنيف', 'الوحدة', 'الكمية',
                          'الحد الأدنى', 'سعر التكلفة', 'سعر البيع',
                          'قيمة المخزون', 'الحالة'], rows)


# ── Profit report ──

def _profit_for_range(date_from, date_to):
    sales = Sale.query.filter_by(status='completed')
    if date_from:
        sales = sales.filter(Sale.date >= date_from)
    if date_to:
        sales = sales.filter(Sale.date <= date_to)
    sales = sales.all()

    revenue = sum(float(s.total or 0) for s in sales)
    sale_ids = [s.id for s in sales]
    cogs = 0.0
    if sale_ids:
        for (pid, qty) in db.session.query(SaleItem.product_id, SaleItem.quantity) \
                .filter(SaleItem.sale_id.in_(sale_ids)).all():
            p = db.session.get(Product, pid)
            if p:
                cogs += float(qty or 0) * float(p.cost_price or 0)
    gross = revenue - cogs
    margin = (gross / revenue * 100) if revenue else 0.0

    purchases = PurchaseOrder.query.filter_by(status='received')
    if date_from:
        purchases = purchases.filter(PurchaseOrder.date >= date_from)
    if date_to:
        purchases = purchases.filter(PurchaseOrder.date <= date_to)
    purchase_cost = sum(float(o.total_amount or 0) for o in purchases.all())

    payments = Payment.query
    if date_from:
        payments = payments.filter(Payment.date >= date_from)
    if date_to:
        payments = payments.filter(Payment.date <= date_to)
    collected = sum(float(p.amount or 0) for p in payments.all())

    return {
        'revenue': revenue,
        'cogs': cogs,
        'gross': gross,
        'margin': margin,
        'purchases': purchase_cost,
        'collected': collected,
        'count': len(sales),
    }


@dashboard_bp.route('/profit-report')
@login_required
def profit_report():
    date_from = _parse_date(request.args.get('from'), None)
    date_to = _parse_date(request.args.get('to'), None)
    totals = _profit_for_range(date_from, date_to)

    months = []
    today = date.today()
    for i in range(5, -1, -1):
        first = today.replace(day=1) - timedelta(days=30 * i)
        m_start = first.replace(day=1)
        nxt = (m_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        m_end = nxt - timedelta(days=1)
        m = _profit_for_range(m_start, m_end)
        m['label'] = m_start.strftime('%Y-%m')
        months.append(m)
    return render_template('dashboard/profit_report.html', totals=totals,
                           months=months, date_from=date_from, date_to=date_to)


@dashboard_bp.route('/profit-report/export')
@login_required
def profit_report_export():
    date_from = _parse_date(request.args.get('from'), None)
    date_to = _parse_date(request.args.get('to'), None)
    t = _profit_for_range(date_from, date_to)
    rows = [[
        'الإيرادات (مبيعات مكتملة)', '{:.2f}'.format(t['revenue'])],
        ['تكلفة البضاعة المباعة', '{:.2f}'.format(t['cogs'])],
        ['إجمالي الربح', '{:.2f}'.format(t['gross'])],
        ['هامش الربح %', '{:.2f}'.format(t['margin'])],
        ['المشتريات المستلمة', '{:.2f}'.format(t['purchases'])],
        ['المدفوعات المحصلة', '{:.2f}'.format(t['collected'])],
    ]
    return _csv_response('profit_report.csv', ['البند', 'القيمة'], rows)
