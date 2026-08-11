from decimal import Decimal

from app.models import db, PurchaseOrder, PurchaseItem, Product, StockMovement


def _make_supplier(auth_client, name='مورد النور'):
    auth_client.post('/client/add', data={'name': name, 'type': 'supplier'},
                     follow_redirects=True)
    with auth_client.application.app_context():
        from app.models import Client
        c = Client.query.filter_by(name=name).first()
        return c.id if c else None


def _make_product(auth_client, name='كرتون'):
    data = {
        'name': name,
        'sku': 'SKU-C',
        'barcode': '999999999999',
        'unit': 'كرتون',
        'cost_price': '100',
        'selling_price': '150',
        'min_stock': '2',
        'is_active': 'on',
    }
    auth_client.post('/products/add', data=data, follow_redirects=True)
    with auth_client.application.app_context():
        p = Product.query.filter_by(name=name).first()
        return p.id if p else None


def _make_order(auth_client, supplier_id, product_ids, quantities, costs, date='2026-01-15'):
    if not isinstance(product_ids, list):
        product_ids = [product_ids]
        quantities = [quantities]
        costs = [costs]
    data = {
        'supplier_id': str(supplier_id),
        'date': date,
        'product_id': [str(p) for p in product_ids],
        'quantity': [str(q) for q in quantities],
        'unit_cost': [str(c) for c in costs],
    }
    auth_client.post('/purchases/new', data=data, follow_redirects=True)
    with auth_client.application.app_context():
        o = PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).first()
        return o.id if o else None


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

def test_purchases_index_page(auth_client):
    resp = auth_client.get('/purchases/')
    assert resp.status_code == 200


def test_purchases_new_page(auth_client):
    _make_supplier(auth_client)
    resp = auth_client.get('/purchases/new')
    assert resp.status_code == 200


# ── Create order ──

def test_create_order_draft(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    oid = _make_order(auth_client, sid, pid, 10, 100)
    assert oid is not None
    with auth_client.application.app_context():
        o = db.session.get(PurchaseOrder, oid)
        assert o.status == 'draft'
        assert o.order_number.startswith('PO-')
        assert len(o.items) == 1
        assert float(o.total_amount) == 1000.0


def test_create_order_multiple_items(auth_client):
    sid = _make_supplier(auth_client)
    p1 = _make_product(auth_client, 'كرتون')
    p2 = _make_product(auth_client, 'زجاجة')
    oid = _make_order(auth_client, sid, [p1, p2], [10, 5], [100, 50])
    with auth_client.application.app_context():
        o = db.session.get(PurchaseOrder, oid)
        assert len(o.items) == 2
        assert float(o.total_amount) == 1250.0


def test_create_order_requires_items(auth_client):
    sid = _make_supplier(auth_client)
    auth_client.post('/purchases/new', data={'supplier_id': str(sid), 'date': '2026-01-15'},
                     follow_redirects=True)
    with auth_client.application.app_context():
        assert PurchaseOrder.query.count() == 0


def test_create_order_requires_supplier(auth_client):
    pid = _make_product(auth_client)
    auth_client.post('/purchases/new', data={
        'supplier_id': '',
        'date': '2026-01-15',
        'product_id': [str(pid)],
        'quantity': ['5'],
        'unit_cost': ['100'],
    }, follow_redirects=True)
    with auth_client.application.app_context():
        assert PurchaseOrder.query.count() == 0


def test_create_order_bad_product_rejected(auth_client):
    sid = _make_supplier(auth_client)
    auth_client.post('/purchases/new', data={
        'supplier_id': str(sid),
        'date': '2026-01-15',
        'product_id': ['999999'],
        'quantity': ['5'],
        'unit_cost': ['100'],
    }, follow_redirects=True)
    with auth_client.application.app_context():
        assert PurchaseOrder.query.count() == 0


# ── Detail / Edit ──

def test_order_detail_page(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    oid = _make_order(auth_client, sid, pid, 10, 100)
    resp = auth_client.get(f'/purchases/{oid}')
    assert resp.status_code == 200
    assert 'كرتون'.encode('utf-8') in resp.data


def test_edit_draft_order(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    oid = _make_order(auth_client, sid, pid, 10, 100)
    resp = auth_client.post(f'/purchases/{oid}/edit', data={
        'supplier_id': str(sid),
        'date': '2026-02-01',
        'product_id': [str(pid)],
        'quantity': ['20'],
        'unit_cost': ['90'],
    }, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        o = db.session.get(PurchaseOrder, oid)
        assert len(o.items) == 1
        assert float(o.items[0].quantity) == 20.0
        assert float(o.total_amount) == 1800.0


def test_edit_received_blocked(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    oid = _make_order(auth_client, sid, pid, 10, 100)
    auth_client.post(f'/purchases/{oid}/receive', follow_redirects=True)
    resp = auth_client.post(f'/purchases/{oid}/edit', data={
        'supplier_id': str(sid), 'date': '2026-02-01',
        'product_id': [str(pid)], 'quantity': ['99'], 'unit_cost': ['1'],
    }, follow_redirects=True)
    with auth_client.application.app_context():
        o = db.session.get(PurchaseOrder, oid)
        assert o.status == 'received'
        assert float(o.items[0].quantity) == 10.0


# ── Receive ──

def test_receive_order_increases_stock(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    oid = _make_order(auth_client, sid, pid, 10, 100)
    resp = auth_client.post(f'/purchases/{oid}/receive', follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        o = db.session.get(PurchaseOrder, oid)
        assert o.status == 'received'
        p = db.session.get(Product, pid)
        assert float(p.current_stock) == 10.0
        mv = StockMovement.query.filter_by(product_id=pid).all()
        assert len(mv) == 1
        assert mv[0].movement_type == 'IN'
        assert mv[0].reference == o.order_number


def test_receive_order_twice_blocked(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    oid = _make_order(auth_client, sid, pid, 10, 100)
    auth_client.post(f'/purchases/{oid}/receive', follow_redirects=True)
    auth_client.post(f'/purchases/{oid}/receive', follow_redirects=True)
    with auth_client.application.app_context():
        p = db.session.get(Product, pid)
        assert float(p.current_stock) == 10.0


def test_receive_without_items_blocked(auth_client):
    sid = _make_supplier(auth_client)
    with auth_client.application.app_context():
        o = PurchaseOrder(order_number='PO-TEST-001', supplier_id=sid, status='draft')
        db.session.add(o)
        db.session.commit()
        oid = o.id
    auth_client.post(f'/purchases/{oid}/receive', follow_redirects=True)
    with auth_client.application.app_context():
        o = db.session.get(PurchaseOrder, oid)
        assert o.status == 'draft'


# ── Cancel / Delete ──

def test_cancel_draft_order(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    oid = _make_order(auth_client, sid, pid, 10, 100)
    auth_client.post(f'/purchases/{oid}/cancel', follow_redirects=True)
    with auth_client.application.app_context():
        o = db.session.get(PurchaseOrder, oid)
        assert o.status == 'cancelled'


def test_cancel_received_blocked(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    oid = _make_order(auth_client, sid, pid, 10, 100)
    auth_client.post(f'/purchases/{oid}/receive', follow_redirects=True)
    auth_client.post(f'/purchases/{oid}/cancel', follow_redirects=True)
    with auth_client.application.app_context():
        o = db.session.get(PurchaseOrder, oid)
        assert o.status == 'received'


def test_delete_draft_order(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    oid = _make_order(auth_client, sid, pid, 10, 100)
    resp = auth_client.post(f'/purchases/{oid}/delete', follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        assert db.session.get(PurchaseOrder, oid) is None
        assert PurchaseItem.query.count() == 0


def test_delete_received_blocked(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    oid = _make_order(auth_client, sid, pid, 10, 100)
    auth_client.post(f'/purchases/{oid}/receive', follow_redirects=True)
    auth_client.post(f'/purchases/{oid}/delete', follow_redirects=True)
    with auth_client.application.app_context():
        assert db.session.get(PurchaseOrder, oid) is not None


# ── Permissions ──

def test_viewer_cannot_create_order(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    _login_user(auth_client, 'viewer1', 'viewer')
    resp = auth_client.post('/purchases/new', data={
        'supplier_id': str(sid), 'date': '2026-01-15',
        'product_id': [str(pid)], 'quantity': ['5'], 'unit_cost': ['100'],
    }, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        assert PurchaseOrder.query.count() == 0


def test_viewer_cannot_receive_order(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    oid = _make_order(auth_client, sid, pid, 10, 100)
    _login_user(auth_client, 'viewer2', 'viewer')
    auth_client.post(f'/purchases/{oid}/receive', follow_redirects=True)
    with auth_client.application.app_context():
        o = db.session.get(PurchaseOrder, oid)
        assert o.status == 'draft'
        assert float(db.session.get(Product, pid).current_stock) == 0.0


def test_editor_cannot_delete_order(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    oid = _make_order(auth_client, sid, pid, 10, 100)
    _login_user(auth_client, 'editor1', 'editor')
    auth_client.post(f'/purchases/{oid}/delete', follow_redirects=True)
    with auth_client.application.app_context():
        assert db.session.get(PurchaseOrder, oid) is not None


def test_editor_can_create_and_receive(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    _login_user(auth_client, 'editor2', 'editor')
    oid = _make_order(auth_client, sid, pid, 4, 50)
    assert oid is not None
    auth_client.post(f'/purchases/{oid}/receive', follow_redirects=True)
    with auth_client.application.app_context():
        o = db.session.get(PurchaseOrder, oid)
        assert o.status == 'received'
        assert float(db.session.get(Product, pid).current_stock) == 4.0


# ── Filters ──

def test_index_filter_by_status(auth_client):
    sid = _make_supplier(auth_client)
    pid = _make_product(auth_client)
    oid = _make_order(auth_client, sid, pid, 10, 100)
    resp = auth_client.get('/purchases/?status=draft')
    assert resp.status_code == 200
    resp2 = auth_client.get('/purchases/?status=received')
    assert resp2.status_code == 200
    with auth_client.application.app_context():
        o = db.session.get(PurchaseOrder, oid)
        assert o is not None
