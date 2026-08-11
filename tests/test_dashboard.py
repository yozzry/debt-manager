from app.models import db, Sale, Payment, PurchaseOrder, Product


def _make_product(auth_client, name='قهوة', cost='400', price='1000', stock=10):
    auth_client.post('/products/add', data={
        'name': name,
        'sku': 'SKU-' + name,
        'barcode': '',
        'unit': 'قطعة',
        'cost_price': cost,
        'selling_price': price,
        'min_stock': '2',
        'is_active': 'on',
    }, follow_redirects=True)
    with auth_client.application.app_context():
        p = Product.query.filter_by(name=name).first()
        pid = p.id
    if stock:
        auth_client.post(f'/products/{pid}/stock', data={
            'movement_type': 'IN', 'quantity': str(stock)}, follow_redirects=True)
    return pid


def _make_customer(auth_client, name='أحمد', ctype='customer'):
    auth_client.post('/client/add', data={'name': name, 'type': ctype},
                     follow_redirects=True)
    with auth_client.application.app_context():
        from app.models import Client
        c = Client.query.filter_by(name=name).first()
        return c.id if c else None


def _make_supplier(auth_client, name='مورد النور'):
    return _make_customer(auth_client, name, ctype='supplier')


def _complete_sale(auth_client, pid, qty='1', price='1000', client_id='',
                   method='cash', date='2026-01-20'):
    data = {
        'client_id': str(client_id),
        'payment_method': method,
        'discount_type': 'amount',
        'discount_value': '0',
        'date': date,
        'product_id': [str(pid)],
        'quantity': [qty],
        'unit_price': [price],
    }
    return auth_client.post('/pos/complete', data=data, follow_redirects=True)


def _make_purchase(auth_client, supplier_id, pid, qty, cost, date='2026-01-15'):
    auth_client.post('/purchases/new', data={
        'supplier_id': str(supplier_id),
        'date': date,
        'product_id': [str(pid)],
        'quantity': [str(qty)],
        'unit_cost': [str(cost)],
    }, follow_redirects=True)
    with auth_client.application.app_context():
        o = PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).first()
        oid = o.id
    auth_client.post(f'/purchases/{oid}/receive', follow_redirects=True)
    return oid


def _make_payment(auth_client, cid, amount, date='2026-01-20'):
    auth_client.post(f'/client/{cid}/payment/add', data={
        'amount': amount, 'date': date, 'payment_method': 'cash',
    })


def _login_user(auth_client, username, role):
    with auth_client.application.app_context():
        from app.models import User
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role=role)
            u.set_password('pass123')
            db.session.add(u)
            db.session.commit()
    auth_client.get('/logout')
    auth_client.post('/login', data={'username': username, 'password': 'pass123'})


# ── Pages ──

def test_dashboard_page(auth_client):
    resp = auth_client.get('/dashboard/')
    assert resp.status_code == 200
    assert 'لوحة العمليات'.encode('utf-8') in resp.data


def test_sales_report_page(auth_client):
    resp = auth_client.get('/dashboard/sales-report')
    assert resp.status_code == 200
    assert 'تقرير المبيعات'.encode('utf-8') in resp.data


def test_purchases_report_page(auth_client):
    resp = auth_client.get('/dashboard/purchases-report')
    assert resp.status_code == 200
    assert 'تقرير المشتريات'.encode('utf-8') in resp.data


def test_inventory_report_page(auth_client):
    resp = auth_client.get('/dashboard/inventory-report')
    assert resp.status_code == 200
    assert 'تقرير المخزون'.encode('utf-8') in resp.data


def test_profit_report_page(auth_client):
    resp = auth_client.get('/dashboard/profit-report')
    assert resp.status_code == 200
    assert 'تقرير الأرباح'.encode('utf-8') in resp.data


# ── KPIs correctness ──

def test_dashboard_kpis_reflect_sales(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='2', price='1000')
    resp = auth_client.get('/dashboard/')
    assert resp.status_code == 200
    assert b'2,000' in resp.data  # مبيعات اليوم


def test_dashboard_low_stock_alert(auth_client):
    _make_product(auth_client, name='نافذ', stock=0)
    resp = auth_client.get('/dashboard/')
    assert resp.status_code == 200
    assert 'نافذ'.encode('utf-8') in resp.data


def test_dashboard_pending_orders_count(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client, stock=0)
    auth_client.post('/purchases/new', data={
        'supplier_id': str(sid),
        'date': '2026-01-15',
        'product_id': [str(pid)],
        'quantity': ['5'],
        'unit_cost': ['100'],
    }, follow_redirects=True)
    with auth_client.application.app_context():
        number = PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).first().order_number
    resp = auth_client.get('/dashboard/')
    assert resp.status_code == 200
    assert number.encode('utf-8') in resp.data  # يظهر في قائمة الأوامر المعلقة


# ── Sales report filters ──

def test_sales_report_shows_invoice(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='1', price='1000')
    resp = auth_client.get('/dashboard/sales-report')
    assert resp.status_code == 200
    with auth_client.application.app_context():
        inv = Sale.query.order_by(Sale.id.desc()).first().invoice_number
    assert inv.encode('utf-8') in resp.data


def test_sales_report_filter_cash(auth_client):
    pid = _make_product(auth_client, stock=20)
    _complete_sale(auth_client, pid, qty='1', price='1000', method='cash')
    _complete_sale(auth_client, pid, qty='1', price='1000', method='credit',
                   client_id=_make_customer(auth_client))
    resp = auth_client.get('/dashboard/sales-report?method=cash')
    assert resp.status_code == 200
    assert b'1,000' in resp.data
    assert b'2,000' not in resp.data


def test_sales_report_date_filter(auth_client):
    pid = _make_product(auth_client, stock=20)
    _complete_sale(auth_client, pid, qty='1', price='1000', date='2026-01-20')
    _complete_sale(auth_client, pid, qty='1', price='1000', date='2026-01-21')
    resp = auth_client.get('/dashboard/sales-report?from=2026-01-21')
    assert resp.status_code == 200
    assert b'2,000' not in resp.data


def test_sales_report_export(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='1', price='1000')
    resp = auth_client.get('/dashboard/sales-report/export')
    assert resp.status_code == 200
    assert 'text/csv' in resp.content_type
    assert resp.data.startswith(b'\xef\xbb\xbf')  # utf-8 BOM


# ── Purchases report ──

def test_purchases_report_received_total(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client, stock=0)
    _make_purchase(auth_client, sid, pid, 5, 100)
    resp = auth_client.get('/dashboard/purchases-report')
    assert resp.status_code == 200
    assert b'500' in resp.data


def test_purchases_report_status_filter(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client, stock=0)
    _make_purchase(auth_client, sid, pid, 5, 100)
    with auth_client.application.app_context():
        assert PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).first().status == 'received'
    resp = auth_client.get('/dashboard/purchases-report?status=draft')
    assert resp.status_code == 200
    assert 'لا توجد أوامر شراء مطابقة'.encode('utf-8') in resp.data


# ── Inventory report ──

def test_inventory_value_and_export(auth_client):
    _make_product(auth_client, name='شاي', cost='400', price='1000', stock=10)
    resp = auth_client.get('/dashboard/inventory-report')
    assert resp.status_code == 200
    assert b'4,000' in resp.data  # 10 * 400
    exp = auth_client.get('/dashboard/inventory-report/export')
    assert exp.status_code == 200
    assert 'text/csv' in exp.content_type


def test_inventory_low_filter(auth_client):
    _make_product(auth_client, name='منخفض', cost='100', price='200', stock=1)
    resp = auth_client.get('/dashboard/inventory-report?filter=low')
    assert resp.status_code == 200
    assert 'منخفض'.encode('utf-8') in resp.data


# ── Profit report ──

def test_profit_calculation(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='2', price='1000')
    resp = auth_client.get('/dashboard/profit-report')
    assert resp.status_code == 200
    assert b'2,000' in resp.data  # الإيرادات
    assert b'800' in resp.data    # تكلفة المبيعات 2*400
    assert b'1,200' in resp.data  # إجمالي الربح


def test_profit_report_export(auth_client):
    resp = auth_client.get('/dashboard/profit-report/export')
    assert resp.status_code == 200
    assert 'text/csv' in resp.content_type


# ── Accounting KPIs ──

def test_dashboard_accounting_kpis(auth_client):
    with auth_client.application.app_context():
        from app.accounts import seed_default_accounts
        from app.models import Settings
        seed_default_accounts()
        Settings.set('auto_accounting_enabled', True, value_type='bool')
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client, stock=0)
    _make_purchase(auth_client, sid, pid, 5, 100)   # مخزون +500 / موردون +500
    _complete_sale(auth_client, pid, qty='2', price='1000')
    resp = auth_client.get('/dashboard/')
    assert resp.status_code == 200
    assert 'ملخص المحاسبة'.encode('utf-8') in resp.data
    assert 'صافي الدخل'.encode('utf-8') in resp.data
    assert b'1,700.00' in resp.data   # الأصول: نقدية 2000 + مخزون (500-800)
    assert b'500.00' in resp.data     # الخصوم: موردون
    assert b'1,200.00' in resp.data   # صافي الدخل: إيرادات 2000 - تكلفة 800
    assert b'2,000.00' in resp.data   # النقدية والبنك


def test_dashboard_hides_accounting_without_accounts(auth_client):
    resp = auth_client.get('/dashboard/')
    assert resp.status_code == 200
    assert 'ملخص المحاسبة'.encode('utf-8') not in resp.data


# ── Permissions ──

def test_viewer_can_view_dashboard(auth_client):
    _login_user(auth_client, 'viewer_dash', 'viewer')
    resp = auth_client.get('/dashboard/')
    assert resp.status_code == 200


def test_reports_need_login(client):
    resp = client.get('/dashboard/')
    assert resp.status_code in (302, 403)
