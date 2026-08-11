from decimal import Decimal

from app.models import db, Sale, SaleItem, Invoice, Product


def _make_product(auth_client, name='قهوة', price='10', stock=0):
    auth_client.post('/products/add', data={
        'name': name,
        'sku': 'SKU-' + name,
        'barcode': '',
        'unit': 'قطعة',
        'cost_price': '5',
        'selling_price': price,
        'min_stock': '1',
        'is_active': 'on',
    }, follow_redirects=True)
    with auth_client.application.app_context():
        p = Product.query.filter_by(name=name).first()
        pid = p.id
    if stock:
        auth_client.post(f'/products/{pid}/stock', data={
            'movement_type': 'IN', 'quantity': str(stock)}, follow_redirects=True)
    return pid


def _make_customer(auth_client, name='أحمد'):
    auth_client.post('/client/add', data={'name': name, 'type': 'customer'},
                     follow_redirects=True)
    with auth_client.application.app_context():
        from app.models import Client
        c = Client.query.filter_by(name=name).first()
        return c.id if c else None


def _complete_sale(auth_client, pid, qty='1', price=None, client_id='',
                   method='cash', discount_type='amount', discount_value='0',
                   date='2026-01-20'):
    data = {
        'client_id': str(client_id),
        'payment_method': method,
        'discount_type': discount_type,
        'discount_value': discount_value,
        'date': date,
        'product_id': [str(pid)],
        'quantity': [qty],
        'unit_price': [str(price) if price is not None else ''],
    }
    return auth_client.post('/pos/complete', data=data, follow_redirects=True)


def _last_sale():
    return Sale.query.order_by(Sale.id.desc()).first()


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

def test_pos_page(auth_client):
    resp = auth_client.get('/pos/')
    assert resp.status_code == 200


def test_history_page(auth_client):
    resp = auth_client.get('/pos/history')
    assert resp.status_code == 200


# ── Cash sales ──

def test_cash_sale_complete(auth_client):
    pid = _make_product(auth_client, stock=10)
    resp = _complete_sale(auth_client, pid, qty='2', price='10')
    assert resp.status_code == 200
    with auth_client.application.app_context():
        s = _last_sale()
        assert s is not None
        assert s.status == 'completed'
        assert s.payment_method == 'cash'
        assert float(s.total) == 20.0
        assert float(db.session.get(Product, pid).current_stock) == 8.0
        assert Invoice.query.count() == 0


def test_cash_sale_price_defaults_to_empty_rejected(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='1', price=None)
    with auth_client.application.app_context():
        assert Sale.query.count() == 0


def test_sale_without_items_rejected(auth_client):
    resp = auth_client.post('/pos/complete', data={
        'client_id': '', 'payment_method': 'cash',
        'discount_type': 'amount', 'discount_value': '0',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        assert Sale.query.count() == 0


def test_sale_overdraw_rejected(auth_client):
    pid = _make_product(auth_client, stock=3)
    _complete_sale(auth_client, pid, qty='10', price='10')
    with auth_client.application.app_context():
        assert Sale.query.count() == 0
        assert float(db.session.get(Product, pid).current_stock) == 3.0


def test_sale_invalid_quantity_rejected(auth_client):
    pid = _make_product(auth_client, stock=3)
    _complete_sale(auth_client, pid, qty='0', price='10')
    with auth_client.application.app_context():
        assert Sale.query.count() == 0


# ── Credit sales ──

def test_credit_sale_creates_invoice(auth_client):
    cid = _make_customer(auth_client)
    pid = _make_product(auth_client, stock=5)
    _complete_sale(auth_client, pid, qty='2', price='15', client_id=cid, method='credit')
    with auth_client.application.app_context():
        s = _last_sale()
        assert s is not None
        assert s.client_id == cid
        inv = Invoice.query.filter_by(sale_id=s.id).first()
        assert inv is not None
        assert float(inv.amount) == 30.0
        assert float(s.client.balance) == 30.0


def test_credit_without_client_rejected(auth_client):
    pid = _make_product(auth_client, stock=5)
    _complete_sale(auth_client, pid, qty='1', price='10', method='credit')
    with auth_client.application.app_context():
        assert Sale.query.count() == 0
        assert float(db.session.get(Product, pid).current_stock) == 5.0


# ── Discounts ──

def test_amount_discount(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='2', price='10',
                   discount_type='amount', discount_value='5')
    with auth_client.application.app_context():
        s = _last_sale()
        assert float(s.subtotal) == 20.0
        assert float(s.discount) == 5.0
        assert float(s.total) == 15.0


def test_amount_discount_capped_at_subtotal(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='2', price='10',
                   discount_type='amount', discount_value='999')
    with auth_client.application.app_context():
        s = _last_sale()
        assert float(s.total) == 0.0


def test_percent_discount(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='4', price='50',
                   discount_type='percent', discount_value='10')
    with auth_client.application.app_context():
        s = _last_sale()
        assert float(s.subtotal) == 200.0
        assert float(s.discount) == 20.0
        assert float(s.total) == 180.0


# ── Pages: detail / receipt ──

def test_sale_detail_page(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='1', price='10')
    with auth_client.application.app_context():
        sid = _last_sale().id
    resp = auth_client.get(f'/pos/{sid}')
    assert resp.status_code == 200
    assert 'قهوة'.encode('utf-8') in resp.data


def test_receipt_page(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='1', price='10')
    with auth_client.application.app_context():
        sid = _last_sale().id
    resp = auth_client.get(f'/pos/{sid}/receipt')
    assert resp.status_code == 200


# ── Cancel ──

def test_cancel_cash_sale_restores_stock(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='3', price='10')
    with auth_client.application.app_context():
        sid = _last_sale().id
        assert float(db.session.get(Product, pid).current_stock) == 7.0
    resp = auth_client.post(f'/pos/{sid}/cancel', follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        s = db.session.get(Sale, sid)
        assert s.status == 'cancelled'
        assert float(db.session.get(Product, pid).current_stock) == 10.0


def test_cancel_credit_sale_removes_invoice(auth_client):
    cid = _make_customer(auth_client)
    pid = _make_product(auth_client, stock=5)
    _complete_sale(auth_client, pid, qty='2', price='15', client_id=cid, method='credit')
    with auth_client.application.app_context():
        sid = _last_sale().id
        assert float(db.session.get(Sale, sid).client.balance) == 30.0
    auth_client.post(f'/pos/{sid}/cancel', follow_redirects=True)
    with auth_client.application.app_context():
        s = db.session.get(Sale, sid)
        assert s.status == 'cancelled'
        assert Invoice.query.filter_by(sale_id=sid).count() == 0
        assert float(s.client.balance) == 0.0


def test_cancel_twice_blocked(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='2', price='10')
    with auth_client.application.app_context():
        sid = _last_sale().id
    auth_client.post(f'/pos/{sid}/cancel', follow_redirects=True)
    auth_client.post(f'/pos/{sid}/cancel', follow_redirects=True)
    with auth_client.application.app_context():
        assert float(db.session.get(Product, pid).current_stock) == 10.0


# ── History filters ──

def test_history_filter_status(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='1', price='10')
    resp = auth_client.get('/pos/history?status=completed')
    assert resp.status_code == 200
    resp2 = auth_client.get('/pos/history?q=قهوة')
    assert resp2.status_code == 200


# ── Permissions ──

def test_viewer_cannot_complete_sale(auth_client):
    pid = _make_product(auth_client, stock=10)
    _login_user(auth_client, 'viewer1', 'viewer')
    _complete_sale(auth_client, pid, qty='1', price='10')
    with auth_client.application.app_context():
        assert Sale.query.count() == 0
        assert float(db.session.get(Product, pid).current_stock) == 10.0


def test_editor_cannot_cancel_sale(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='1', price='10')
    with auth_client.application.app_context():
        sid = _last_sale().id
    _login_user(auth_client, 'editor1', 'editor')
    auth_client.post(f'/pos/{sid}/cancel', follow_redirects=True)
    with auth_client.application.app_context():
        s = db.session.get(Sale, sid)
        assert s.status == 'completed'
        assert float(db.session.get(Product, pid).current_stock) == 9.0


def test_editor_can_complete_sale(auth_client):
    pid = _make_product(auth_client, stock=10)
    _login_user(auth_client, 'editor2', 'editor')
    _complete_sale(auth_client, pid, qty='4', price='10')
    with auth_client.application.app_context():
        assert Sale.query.count() == 1
        assert float(db.session.get(Product, pid).current_stock) == 6.0


# ── Thermal printing (ESC/POS) ──

def test_build_receipt_bytes(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='2', price='10', date='2026-01-20')
    with auth_client.application.app_context():
        s = _last_sale()
        from app.pos.printer import build_receipt_bytes
        data = build_receipt_bytes(s)
        assert isinstance(data, bytes)
        assert len(data) > 0
        text = data.decode('cp1256', errors='replace')
        assert 'DEBT MANAGER' in text
        assert s.invoice_number in text
        assert 'شكراً' in text


def test_print_receipt_disabled_when_no_printer(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='1', price='10')
    with auth_client.application.app_context():
        s = _last_sale()
        from app.pos.printer import print_receipt
        from app.models import Settings
        Settings.set('pos_printer_name', '')
        ok, msg = print_receipt(s)
        assert ok is False
        assert 'معطلة' in msg


def test_print_route_returns_message_without_printer(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='1', price='10')
    with auth_client.application.app_context():
        sid = _last_sale().id
    resp = auth_client.post(f'/pos/{sid}/print', follow_redirects=True)
    assert resp.status_code == 200
    assert 'الطباعة الحرارية'.encode('utf-8') in resp.data


# ── عميل «نقدي» الافتراضي ──

def test_cash_sale_attaches_cash_client(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='1', price='10')
    with auth_client.application.app_context():
        from app.models import Client
        s = _last_sale()
        c = db.session.get(Client, s.client_id)
        assert c is not None
        assert c.name == 'نقدي'
        assert c.type == 'customer'
        assert float(s.total) == 10.0


def test_cash_client_reused_across_sales(auth_client):
    pid = _make_product(auth_client, stock=10)
    _complete_sale(auth_client, pid, qty='1', price='10')
    _complete_sale(auth_client, pid, qty='1', price='10')
    with auth_client.application.app_context():
        from app.models import Client
        assert Client.query.filter_by(name='نقدي').count() == 1
        assert Sale.query.count() == 2


def test_credit_sale_keeps_selected_client(auth_client):
    cid = _make_customer(auth_client)
    pid = _make_product(auth_client, stock=5)
    _complete_sale(auth_client, pid, qty='1', price='15', client_id=cid, method='credit')
    with auth_client.application.app_context():
        from app.models import Client
        s = _last_sale()
        assert s.client_id == cid
        assert Client.query.filter_by(name='نقدي').count() == 0


def test_cash_client_appears_in_dropdown(auth_client):
    pid = _make_product(auth_client, stock=5)
    _complete_sale(auth_client, pid, qty='1', price='10')
    resp = auth_client.get('/pos/')
    assert resp.status_code == 200
    assert 'نقدي'.encode('utf-8') in resp.data


# ── الماسح الضوئي (بحث فوري بالباركود/SKU/الاسم) ──

def _make_scannable_product(auth_client, name='شاي', barcode='6291041500213',
                            sku='SKU-SCAN'):
    auth_client.post('/products/add', data={
        'name': name, 'sku': sku, 'barcode': barcode, 'unit': 'قطعة',
        'cost_price': '3', 'selling_price': '7', 'min_stock': '1', 'is_active': 'on',
    }, follow_redirects=True)
    with auth_client.application.app_context():
        return Product.query.filter_by(name=name).first().id


def test_product_lookup_by_barcode(auth_client):
    pid = _make_scannable_product(auth_client)
    resp = auth_client.get('/pos/api/product?q=6291041500213')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['id'] == pid
    assert data['name'] == 'شاي'
    assert data['selling_price'] == 7.0


def test_product_lookup_by_sku(auth_client):
    _make_scannable_product(auth_client)
    resp = auth_client.get('/pos/api/product?q=SKU-SCAN')
    assert resp.status_code == 200
    assert resp.get_json()['name'] == 'شاي'


def test_product_lookup_by_name(auth_client):
    _make_scannable_product(auth_client)
    resp = auth_client.get('/pos/api/product?q=شاي')
    assert resp.status_code == 200
    assert resp.get_json()['id'] is not None


def test_product_lookup_not_found(auth_client):
    resp = auth_client.get('/pos/api/product?q=XXXX-NOT-FOUND')
    assert resp.status_code == 404
    assert resp.get_json()['error']


def test_product_lookup_inactive_excluded(auth_client):
    _make_scannable_product(auth_client, name='منتج معطل')
    with auth_client.application.app_context():
        p = Product.query.filter_by(name='منتج معطل').first()
        p.is_active = False
        db.session.commit()
    resp = auth_client.get('/pos/api/product?q=6291041500213')
    assert resp.status_code == 404
