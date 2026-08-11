"""اختبارات الأدوار الجديدة: cashier (نقطة البيع فقط) و accountant (المحاسبة فقط)."""

from app.models import db, Sale, Product, User, JournalEntry, Account


def _make_product(auth_client, name='قهوة', price='10', stock=10):
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


def _complete_sale(auth_client, pid, qty='1', price='10', method='cash'):
    return auth_client.post('/pos/complete', data={
        'client_id': '',
        'payment_method': method,
        'discount_type': 'amount',
        'discount_value': '0',
        'date': '2026-01-20',
        'product_id': [str(pid)],
        'quantity': [qty],
        'unit_price': [price],
    }, follow_redirects=True)


def _login_user(auth_client, username, role):
    with auth_client.application.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, role=role)
            u.set_password('pass123')
            db.session.add(u)
            db.session.commit()
    auth_client.get('/logout')
    auth_client.post('/login', data={'username': username, 'password': 'pass123'})


def _last_sale_id():
    return Sale.query.order_by(Sale.id.desc()).first().id


# ── خصائص الصلاحيات في النموذج ──

def test_role_permission_flags(app):
    with app.app_context():
        def flags(role):
            u = User(username=role + '_x', role=role)
            return (u.is_admin, u.is_cashier, u.is_accountant,
                    u.can_edit, u.can_pos, u.can_accounting)
        assert flags('admin') == (True, False, False, True, True, True)
        assert flags('editor') == (False, False, False, True, False, False)
        assert flags('cashier') == (False, True, False, False, True, False)
        assert flags('accountant') == (False, False, True, False, False, True)
        assert flags('viewer') == (False, False, False, False, False, False)


# ── أمين الصندوق: POS فقط ──

def test_cashier_can_view_pos_pages(auth_client):
    _login_user(auth_client, 'cash1', 'cashier')
    assert auth_client.get('/pos/').status_code == 200
    assert auth_client.get('/pos/history').status_code == 200


def test_cashier_can_complete_cash_sale(auth_client):
    pid = _make_product(auth_client)
    _login_user(auth_client, 'cash1', 'cashier')
    resp = _complete_sale(auth_client, pid)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        sale = Sale.query.first()
        assert sale is not None
        assert sale.payment_method == 'cash'
        assert sale.status == 'completed'


def test_cashier_can_print_receipt(auth_client):
    pid = _make_product(auth_client)
    _complete_sale(auth_client, pid)
    _login_user(auth_client, 'cash1', 'cashier')
    with auth_client.application.app_context():
        sid = _last_sale_id()
    resp = auth_client.post(f'/pos/{sid}/print', follow_redirects=True)
    assert 'الطباعة الحرارية معطلة' in resp.get_data(as_text=True)


def test_cashier_cannot_edit_products_or_clients(auth_client):
    _login_user(auth_client, 'cash1', 'cashier')
    auth_client.post('/products/add', data={
        'name': 'ممنوع', 'sku': 'NO', 'selling_price': '1',
    }, follow_redirects=True)
    with auth_client.application.app_context():
        assert Product.query.filter_by(name='ممنوع').first() is None
    auth_client.post('/client/add', data={'name': 'عميل ممنوع', 'type': 'customer'},
                     follow_redirects=True)
    with auth_client.application.app_context():
        from app.models import Client
        assert Client.query.filter_by(name='عميل ممنوع').first() is None


def test_cashier_cannot_access_admin_pages(auth_client):
    _login_user(auth_client, 'cash1', 'cashier')
    assert auth_client.get('/users').status_code == 302
    assert auth_client.get('/settings').status_code == 302


def test_cashier_cannot_manage_accounting(auth_client):
    _login_user(auth_client, 'cash1', 'cashier')
    assert auth_client.get('/accounts/').status_code == 200
    assert auth_client.post('/accounts/seed').status_code == 302
    with auth_client.application.app_context():
        assert Account.query.count() == 0


def test_cashier_cannot_cancel_sale(auth_client):
    pid = _make_product(auth_client)
    _complete_sale(auth_client, pid)
    _login_user(auth_client, 'cash1', 'cashier')
    with auth_client.application.app_context():
        sid = _last_sale_id()
    auth_client.post(f'/pos/{sid}/cancel')
    with auth_client.application.app_context():
        assert db.session.get(Sale, sid).status == 'completed'


# ── المحاسب: المحاسبة فقط ──

def test_accountant_can_view_accounting(auth_client):
    _login_user(auth_client, 'acc1', 'accountant')
    assert auth_client.get('/accounts/').status_code == 200
    assert auth_client.get('/accounts/entries').status_code == 200
    assert auth_client.get('/accounts/trial-balance').status_code == 200


def test_accountant_can_seed_and_add_account(auth_client):
    _login_user(auth_client, 'acc1', 'accountant')
    assert auth_client.post('/accounts/seed').status_code == 302
    with auth_client.application.app_context():
        assert Account.query.count() > 0
    resp = auth_client.post('/accounts/add', data={
        'code': '6101', 'name': 'مصروف اختبار', 'account_type': 'expense',
        'opening_balance': '0',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        assert Account.query.filter_by(code='6101').first() is not None


def test_accountant_can_add_and_delete_journal_entry(auth_client):
    _login_user(auth_client, 'acc1', 'accountant')
    for code, name, atype in [('6101', 'مصروف', 'expense'), ('4101', 'إيراد', 'income')]:
        auth_client.post('/accounts/add', data={
            'code': code, 'name': name, 'account_type': atype, 'opening_balance': '0',
        })
    with auth_client.application.app_context():
        d = Account.query.filter_by(code='6101').first()
        c = Account.query.filter_by(code='4101').first()
    resp = auth_client.post('/accounts/entries/add', data={
        'date': '2026-01-20',
        'description': 'قيد اختبار من محاسب',
        'account_id': [str(d.id), str(c.id)],
        'debit': ['100', '0'],
        'credit': ['0', '100'],
    }, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        entry = JournalEntry.query.first()
        assert entry is not None
        eid = entry.id
    assert auth_client.post(f'/accounts/entries/{eid}/delete').status_code == 302
    with auth_client.application.app_context():
        assert JournalEntry.query.first() is None


def test_accountant_cannot_run_pos(auth_client):
    pid = _make_product(auth_client)
    _login_user(auth_client, 'acc1', 'accountant')
    _complete_sale(auth_client, pid)
    with auth_client.application.app_context():
        assert Sale.query.first() is None


def test_accountant_cannot_edit_products_or_admin_pages(auth_client):
    _login_user(auth_client, 'acc1', 'accountant')
    auth_client.post('/products/add', data={
        'name': 'ممنوع', 'sku': 'NO', 'selling_price': '1',
    }, follow_redirects=True)
    with auth_client.application.app_context():
        assert Product.query.filter_by(name='ممنوع').first() is None
    assert auth_client.get('/users').status_code == 302
    assert auth_client.get('/settings').status_code == 302


# ── المشاهد: لا كتابة على الإطلاق ──

def test_viewer_cannot_complete_sale_or_print(auth_client):
    pid = _make_product(auth_client)
    _complete_sale(auth_client, pid)
    _login_user(auth_client, 'view1', 'viewer')
    with auth_client.application.app_context():
        sid = _last_sale_id()
    resp = auth_client.post(f'/pos/{sid}/print', follow_redirects=True)
    assert 'ليس لديك صلاحية' in resp.get_data(as_text=True)


# ── النافبار حسب الدور ──

def _navbar_html(body):
    start = body.find('<nav')
    end = body.find('</nav>', start)
    return body[start:end] if start != -1 and end != -1 else ''


def test_cashier_navbar_shows_pos_only(auth_client):
    _login_user(auth_client, 'cash1', 'cashier')
    auth_client.get('/mode/commerce')
    nav = _navbar_html(auth_client.get('/dashboard/').get_data(as_text=True))
    assert 'href="/pos/"' in nav
    assert 'href="/pos/history"' in nav
    assert 'href="/products/' not in nav
    assert 'href="/purchases/' not in nav
    assert 'href="/accounts/' not in nav
    assert 'href="/users"' not in nav
    assert 'href="/settings"' not in nav


def test_accountant_navbar_shows_accounting_only(auth_client):
    _login_user(auth_client, 'acc1', 'accountant')
    auth_client.get('/mode/commerce')
    nav = _navbar_html(auth_client.get('/dashboard/').get_data(as_text=True))
    assert 'href="/accounts/"' in nav
    assert 'href="/pos/"' not in nav
    assert 'href="/products/' not in nav
    assert 'href="/purchases/' not in nav
