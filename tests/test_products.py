import json
from decimal import Decimal
from app.models import db, Product, Category, StockMovement


def _make_category(auth_client, name='إلكترونيات'):
    auth_client.post('/products/categories', data={'name': name}, follow_redirects=True)
    with auth_client.application.app_context():
        c = Category.query.filter_by(name=name).first()
        return c.id if c else None


def _make_product(auth_client, name='لابتوب', **kw):
    data = {
        'name': name,
        'sku': 'SKU-X',
        'barcode': '123456789012',
        'unit': 'قطعة',
        'cost_price': '1000',
        'selling_price': '1500',
        'min_stock': '2',
        'is_active': 'on',
    }
    data.update(kw)
    auth_client.post('/products/add', data=data, follow_redirects=True)
    with auth_client.application.app_context():
        p = Product.query.filter_by(name=name).first()
        return p.id if p else None


# ── Categories ──

def test_categories_page(auth_client):
    resp = auth_client.get('/products/categories')
    assert resp.status_code == 200


def test_add_category(auth_client):
    cid = _make_category(auth_client)
    assert cid is not None
    with auth_client.application.app_context():
        c = db.session.get(Category, cid)
        assert c.name == 'إلكترونيات'


def test_duplicate_category_rejected(auth_client):
    _make_category(auth_client)
    _make_category(auth_client)
    with auth_client.application.app_context():
        assert Category.query.filter_by(name='إلكترونيات').count() == 1


def test_delete_empty_category(auth_client):
    cid = _make_category(auth_client)
    resp = auth_client.post(f'/products/categories/{cid}/delete', follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        assert db.session.get(Category, cid) is None


def test_delete_category_with_products_blocked(auth_client):
    cid = _make_category(auth_client)
    with auth_client.application.app_context():
        p = Product(name='منتج', category_id=cid)
        db.session.add(p)
        db.session.commit()
    resp = auth_client.post(f'/products/categories/{cid}/delete', follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        assert db.session.get(Category, cid) is not None


# ── Products CRUD ──

def test_products_index(auth_client):
    resp = auth_client.get('/products/')
    assert resp.status_code == 200


def test_add_product(auth_client):
    pid = _make_product(auth_client)
    assert pid is not None
    with auth_client.application.app_context():
        p = db.session.get(Product, pid)
        assert p.selling_price == Decimal('1500')
        assert p.current_stock == Decimal('0')


def test_add_product_with_category(auth_client):
    cid = _make_category(auth_client)
    pid = _make_product(auth_client, category_id=str(cid))
    with auth_client.application.app_context():
        p = db.session.get(Product, pid)
        assert p.category_id == cid


def test_add_product_missing_name(auth_client):
    resp = auth_client.post('/products/add', data={'name': ''}, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        assert Product.query.count() == 0


def test_product_detail(auth_client):
    pid = _make_product(auth_client)
    resp = auth_client.get(f'/products/{pid}')
    assert resp.status_code == 200


def test_edit_product(auth_client):
    pid = _make_product(auth_client)
    resp = auth_client.post(f'/products/{pid}/edit', data={
        'name': 'لابتوب معدل',
        'sku': 'SKU-Y',
        'barcode': '111111111111',
        'unit': 'حبة',
        'cost_price': '1200',
        'selling_price': '1800',
        'min_stock': '5',
        'description': 'وصف جديد',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        p = db.session.get(Product, pid)
        assert p.name == 'لابتوب معدل'
        assert p.selling_price == Decimal('1800')


def test_delete_product(auth_client):
    pid = _make_product(auth_client)
    resp = auth_client.post(f'/products/{pid}/delete', follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        assert db.session.get(Product, pid) is None


# ── Stock adjustments ──

def test_stock_adjust_in(auth_client):
    pid = _make_product(auth_client)
    resp = auth_client.post(f'/products/{pid}/stock', data={
        'movement_type': 'IN',
        'quantity': '10',
        'notes': 'شحنة جديدة',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        p = db.session.get(Product, pid)
        assert float(p.current_stock) == 10.0
        mv = StockMovement.query.filter_by(product_id=pid).all()
        assert len(mv) == 1 and mv[0].movement_type == 'IN'


def test_stock_adjust_out(auth_client):
    pid = _make_product(auth_client)
    auth_client.post(f'/products/{pid}/stock', data={
        'movement_type': 'IN', 'quantity': '5'}, follow_redirects=True)
    resp = auth_client.post(f'/products/{pid}/stock', data={
        'movement_type': 'OUT', 'quantity': '3'}, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        p = db.session.get(Product, pid)
        assert float(p.current_stock) == 2.0


def test_stock_adjust_overdraw_rejected(auth_client):
    pid = _make_product(auth_client)
    auth_client.post(f'/products/{pid}/stock', data={
        'movement_type': 'IN', 'quantity': '2'}, follow_redirects=True)
    resp = auth_client.post(f'/products/{pid}/stock', data={
        'movement_type': 'OUT', 'quantity': '10'}, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        p = db.session.get(Product, pid)
        assert float(p.current_stock) == 2.0


def test_stock_adjust_direct(auth_client):
    pid = _make_product(auth_client)
    auth_client.post(f'/products/{pid}/stock', data={
        'movement_type': 'IN', 'quantity': '5'}, follow_redirects=True)
    resp = auth_client.post(f'/products/{pid}/stock', data={
        'movement_type': 'ADJUST', 'quantity': '7'}, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        p = db.session.get(Product, pid)
        assert float(p.current_stock) == 7.0


def test_stock_adjust_invalid_quantity(auth_client):
    pid = _make_product(auth_client)
    resp = auth_client.post(f'/products/{pid}/stock', data={
        'movement_type': 'IN', 'quantity': '-5'}, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        p = db.session.get(Product, pid)
        assert float(p.current_stock) == 0.0


# ── Pages ──

def test_stock_movements_page(auth_client):
    pid = _make_product(auth_client)
    auth_client.post(f'/products/{pid}/stock', data={
        'movement_type': 'IN', 'quantity': '3'}, follow_redirects=True)
    resp = auth_client.get('/products/movements')
    assert resp.status_code == 200


def test_low_stock_page(auth_client):
    pid = _make_product(auth_client)
    auth_client.post(f'/products/{pid}/stock', data={
        'movement_type': 'IN', 'quantity': '1'}, follow_redirects=True)
    resp = auth_client.get('/products/low-stock')
    assert resp.status_code == 200
    assert 'لابتوب'.encode('utf-8') in resp.data


def test_low_stock_filter(auth_client):
    pid = _make_product(auth_client)
    auth_client.post(f'/products/{pid}/stock', data={
        'movement_type': 'IN', 'quantity': '1'}, follow_redirects=True)
    resp = auth_client.get('/products/?stock=low')
    assert resp.status_code == 200


# ── Barcode ──

def test_barcode_label_page(auth_client):
    pid = _make_product(auth_client)
    resp = auth_client.get(f'/products/barcode/{pid}')
    assert resp.status_code == 200


def test_barcode_image_svg(auth_client):
    pid = _make_product(auth_client)
    resp = auth_client.get(f'/products/barcode/{pid}/image')
    assert resp.status_code == 200
    assert resp.mimetype == 'image/svg+xml'
    assert b'<svg' in resp.data


def test_barcode_image_fallback_no_code(auth_client):
    auth_client.post('/products/add', data={
        'name': 'بلا باركود',
        'selling_price': '10',
    }, follow_redirects=True)
    with auth_client.application.app_context():
        p = Product.query.filter_by(name='بلا باركود').first()
        pid = p.id
    resp = auth_client.get(f'/products/barcode/{pid}/image')
    assert resp.status_code == 200


def test_barcode_image_png(auth_client):
    pid = _make_product(auth_client)
    resp = auth_client.get(f'/products/barcode/{pid}/image.png')
    assert resp.status_code == 200
    assert resp.mimetype == 'image/png'
    assert resp.data[:8] == b'\x89PNG\r\n\x1a\n'


# ── Permissions ──

def test_editor_cannot_delete_product(auth_client):
    pid = _make_product(auth_client)
    with auth_client.application.app_context():
        from app.models import User
        editor = User(username='editor1', role='editor')
        editor.set_password('pass123')
        db.session.add(editor)
        db.session.commit()
        user_id = editor.id
    auth_client.get('/logout')
    auth_client.post('/login', data={'username': 'editor1', 'password': 'pass123'})
    resp = auth_client.post(f'/products/{pid}/delete', follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        assert db.session.get(Product, pid) is not None
