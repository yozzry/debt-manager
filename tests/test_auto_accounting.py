"""اختبارات الربط التلقائي بين العمليات والمحاسبة (قيد مزدوج) — المرحلة 6d."""
from app.models import db, Account, JournalEntry, JournalEntryLine, Settings, Sale, Product, PurchaseOrder


def _enable(auth_client):
    with auth_client.application.app_context():
        Settings.set('auto_accounting_enabled', True, value_type='bool')


def _seed_accounts(auth_client):
    auth_client.post('/accounts/seed', follow_redirects=True)


def _make_product(auth_client, name, cost='5', price='10', stock=0):
    auth_client.post('/products/add', data={
        'name': name,
        'sku': 'SKU-' + name,
        'barcode': '',
        'unit': 'قطعة',
        'cost_price': cost,
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
        return Client.query.filter_by(name=name).first().id


def _make_supplier(auth_client, name='مورد النور'):
    auth_client.post('/client/add', data={'name': name, 'type': 'supplier'},
                     follow_redirects=True)
    with auth_client.application.app_context():
        from app.models import Client
        return Client.query.filter_by(name=name).first().id


def _complete_sale(auth_client, pid, qty='1', price='10', client_id='',
                   method='cash', date='2026-01-20'):
    return auth_client.post('/pos/complete', data={
        'client_id': str(client_id),
        'payment_method': method,
        'discount_type': 'amount',
        'discount_value': '0',
        'date': date,
        'product_id': [str(pid)],
        'quantity': [qty],
        'unit_price': [str(price)],
    }, follow_redirects=True)


def _make_order(auth_client, supplier_id, pid, qty='1', cost='100', date='2026-01-15'):
    auth_client.post('/purchases/new', data={
        'supplier_id': str(supplier_id),
        'date': date,
        'product_id': [str(pid)],
        'quantity': [str(qty)],
        'unit_cost': [str(cost)],
    }, follow_redirects=True)
    with auth_client.application.app_context():
        return PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).first().id


def _receive_order(auth_client, oid):
    return auth_client.post(f'/purchases/{oid}/receive', follow_redirects=True)


def _add_payment(auth_client, cid, amount, method='نقدي', date='2026-01-21'):
    return auth_client.post(f'/client/{cid}/payment/add', data={
        'amount': str(amount), 'payment_method': method, 'date': date, 'notes': ''})


def _edit_payment(auth_client, pid, amount, method='نقدي', date='2026-01-21'):
    return auth_client.post(f'/payment/{pid}/edit', data={
        'amount': str(amount), 'payment_method': method, 'date': date, 'notes': ''})


def _delete_payment(auth_client, pid):
    return auth_client.post(f'/payment/{pid}/delete')


def _last_entry():
    return JournalEntry.query.order_by(JournalEntry.id.desc()).first()


def _entry_for(source_type, source_id):
    return JournalEntry.query.filter_by(source_type=source_type,
                                        source_id=source_id).first()


def _lines(entry):
    return [(l.account.code, float(l.debit or 0), float(l.credit or 0))
            for l in entry.lines]


def _balance(code):
    return float(db.session.get(Account, Account.query.filter_by(code=code).first().id).balance())


def _client_code(cid):
    from app.models import Client
    return db.session.get(Client, cid).account.code


# ── المبيعات ──

def test_cash_sale_creates_balanced_entry(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    pid = _make_product(auth_client, 'بند قهوة', cost='5', price='10', stock=5)
    _complete_sale(auth_client, pid, qty='2', price='10')

    with auth_client.application.app_context():
        sale = Sale.query.order_by(Sale.id.desc()).first()
        entry = _entry_for('sale', sale.id)
        assert entry is not None
        assert entry.is_balanced
        assert _lines(entry) == [
            ('1101', 20.0, 0.0),
            ('5101', 10.0, 0.0),
            ('4101', 0.0, 20.0),
            ('1201', 0.0, 10.0),
        ]
        assert _balance('1101') == 20.0
        assert _balance('4101') == 20.0
        assert _balance('5101') == 10.0
        assert _balance('1201') == -10.0


def test_credit_sale_debits_ar(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client)
    pid = _make_product(auth_client, 'بند آجل', cost='5', price='10', stock=5)
    _complete_sale(auth_client, pid, qty='1', price='10', client_id=cid, method='credit')

    with auth_client.application.app_context():
        sale = Sale.query.order_by(Sale.id.desc()).first()
        entry = _entry_for('sale', sale.id)
        assert entry is not None
        lines = _lines(entry)
        assert (_client_code(cid), 10.0, 0.0) in lines
        assert ('4101', 0.0, 10.0) in lines
        assert _balance(_client_code(cid)) == 10.0


def test_cancel_sale_reverses_entry(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    pid = _make_product(auth_client, 'بند إلغاء', cost='5', price='10', stock=5)
    _complete_sale(auth_client, pid, qty='2', price='10')

    with auth_client.application.app_context():
        sale = Sale.query.order_by(Sale.id.desc()).first()
        sid = sale.id
    auth_client.post(f'/pos/{sid}/cancel', follow_redirects=True)

    with auth_client.application.app_context():
        assert _entry_for('sale', sid) is None
        assert _balance('1101') == 0.0
        assert _balance('4101') == 0.0
        assert _balance('1201') == 0.0


# ── المشتريات ──

def test_receive_purchase_creates_entry(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    supplier_id = _make_supplier(auth_client)
    pid = _make_product(auth_client, 'بند شراء', stock=0)
    oid = _make_order(auth_client, supplier_id, pid, qty='3', cost='100')
    _receive_order(auth_client, oid)

    with auth_client.application.app_context():
        entry = _entry_for('purchase', oid)
        assert entry is not None
        assert entry.is_balanced
        assert _lines(entry) == [('1201', 300.0, 0.0), ('2101', 0.0, 300.0)]
        assert _balance('1201') == 300.0
        assert _balance('2101') == 300.0


# ── الدفعات ──

def test_customer_payment_debits_cash(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client)
    _add_payment(auth_client, cid, '50', method='نقدي')

    with auth_client.application.app_context():
        from app.models import Payment
        p = Payment.query.order_by(Payment.id.desc()).first()
        entry = _entry_for('payment', p.id)
        assert entry is not None
        assert _lines(entry) == [('1101', 50.0, 0.0), (_client_code(cid), 0.0, 50.0)]
        assert _balance('1101') == 50.0
        assert _balance(_client_code(cid)) == -50.0


def test_bank_payment_uses_bank_account(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client)
    _add_payment(auth_client, cid, '80', method='تحويل بنكي')

    with auth_client.application.app_context():
        from app.models import Payment
        p = Payment.query.order_by(Payment.id.desc()).first()
        entry = _entry_for('payment', p.id)
        assert ('1102', 80.0, 0.0) in _lines(entry)
        assert _balance('1102') == 80.0


def test_supplier_payment_debits_ap(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    sid = _make_supplier(auth_client)
    _add_payment(auth_client, sid, '200', method='نقدي')

    with auth_client.application.app_context():
        from app.models import Payment
        p = Payment.query.order_by(Payment.id.desc()).first()
        entry = _entry_for('payment', p.id)
        assert _lines(entry) == [(_client_code(sid), 200.0, 0.0), ('1101', 0.0, 200.0)]
        assert _balance(_client_code(sid)) == -200.0
        assert _balance('1101') == -200.0


def test_edit_payment_replaces_entry(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client)
    _add_payment(auth_client, cid, '50', method='نقدي')

    with auth_client.application.app_context():
        from app.models import Payment
        p = Payment.query.order_by(Payment.id.desc()).first()
        pid = p.id
    _edit_payment(auth_client, pid, '30', method='نقدي')

    with auth_client.application.app_context():
        assert JournalEntry.query.filter_by(source_type='payment',
                                            source_id=pid).count() == 1
        assert _balance('1101') == 30.0
        assert _balance(_client_code(cid)) == -30.0


def test_delete_payment_removes_entry(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client)
    _add_payment(auth_client, cid, '50', method='نقدي')

    with auth_client.application.app_context():
        from app.models import Payment
        p = Payment.query.order_by(Payment.id.desc()).first()
        pid = p.id
    _delete_payment(auth_client, pid)

    with auth_client.application.app_context():
        assert _entry_for('payment', pid) is None
        assert _balance('1101') == 0.0


# ── فواتير العملاء اليدوية ──

def _add_invoice(auth_client, cid, amount, desc='فاتورة يدوية', date='2026-01-15'):
    return auth_client.post(f'/client/{cid}/invoice/add', data={
        'amount': str(amount), 'description': desc, 'date': date})


def _edit_invoice(auth_client, iid, amount, desc='فاتورة معدلة', date='2026-01-15'):
    return auth_client.post(f'/invoice/{iid}/edit', data={
        'amount': str(amount), 'description': desc, 'date': date})


def _delete_invoice(auth_client, iid):
    return auth_client.post(f'/invoice/{iid}/delete')


def test_customer_invoice_debits_ar(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client)
    _add_invoice(auth_client, cid, '500')

    with auth_client.application.app_context():
        from app.models import Invoice
        inv = Invoice.query.order_by(Invoice.id.desc()).first()
        entry = _entry_for('invoice', inv.id)
        assert entry is not None
        assert entry.is_balanced
        assert _lines(entry) == [(_client_code(cid), 500.0, 0.0), ('4101', 0.0, 500.0)]
        assert _balance(_client_code(cid)) == 500.0
        assert _balance('4101') == 500.0


def test_edit_invoice_replaces_entry(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client)
    _add_invoice(auth_client, cid, '500')

    with auth_client.application.app_context():
        from app.models import Invoice
        inv = Invoice.query.order_by(Invoice.id.desc()).first()
        iid = inv.id
    _edit_invoice(auth_client, iid, '300')

    with auth_client.application.app_context():
        assert JournalEntry.query.filter_by(source_type='invoice',
                                            source_id=iid).count() == 1
        assert _balance(_client_code(cid)) == 300.0
        assert _balance('4101') == 300.0


def test_delete_invoice_removes_entry(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client)
    _add_invoice(auth_client, cid, '500')

    with auth_client.application.app_context():
        from app.models import Invoice
        inv = Invoice.query.order_by(Invoice.id.desc()).first()
        iid = inv.id
    _delete_invoice(auth_client, iid)

    with auth_client.application.app_context():
        assert _entry_for('invoice', iid) is None
        assert _balance('1301') == 0.0
        assert _balance('4101') == 0.0


def test_supplier_invoice_skipped(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    sid = _make_supplier(auth_client)
    _add_invoice(auth_client, sid, '700')

    with auth_client.application.app_context():
        assert JournalEntry.query.count() == 0


def test_invoice_disabled_no_entries(auth_client):
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client)
    _add_invoice(auth_client, cid, '500')

    with auth_client.application.app_context():
        assert JournalEntry.query.count() == 0


# ── سلوك التفعيل ──

def test_disabled_creates_no_entries(auth_client):
    _seed_accounts(auth_client)
    pid = _make_product(auth_client, 'بند معطل', stock=5)
    _complete_sale(auth_client, pid, qty='1', price='10')

    with auth_client.application.app_context():
        assert JournalEntry.query.count() == 0


def test_missing_accounts_no_crash(auth_client):
    _enable(auth_client)
    pid = _make_product(auth_client, 'بند بلا حسابات', stock=5)
    resp = _complete_sale(auth_client, pid, qty='1', price='10')
    assert resp.status_code == 200

    with auth_client.application.app_context():
        assert JournalEntry.query.count() == 0
        assert Sale.query.order_by(Sale.id.desc()).first().status == 'completed'


def test_auto_functions_idempotent(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client)
    pid = _make_product(auth_client, 'بند استدعاء', cost='5', price='10', stock=5)
    _complete_sale(auth_client, pid, qty='1', price='10', client_id=cid, method='credit')

    with auth_client.application.app_context():
        from app.accounts.auto import post_sale_entries
        sale = Sale.query.order_by(Sale.id.desc()).first()
        post_sale_entries(sale, 1)
        post_sale_entries(sale, 1)
        db.session.commit()
        assert JournalEntry.query.filter_by(source_type='sale',
                                            source_id=sale.id).count() == 1


def test_settings_toggle_saves(auth_client):
    resp = auth_client.post('/settings', data={
        'tab': 'general',
        'auto_accounting_enabled': '1',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        assert Settings.get('auto_accounting_enabled', False) is True


# ── عدم كسر صفحات المحاسبة ──

def test_entries_and_detail_pages_render(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    pid = _make_product(auth_client, 'بند صفحات', cost='5', price='10', stock=5)
    _complete_sale(auth_client, pid, qty='1', price='10')

    with auth_client.application.app_context():
        eid = _last_entry().id
        assert _last_entry().to_dict()['source_type'] == 'sale'
    assert auth_client.get('/accounts/entries').status_code == 200
    assert auth_client.get(f'/accounts/entries/{eid}').status_code == 200
    assert auth_client.get('/accounts/trial-balance').status_code == 200


# ── حسابات العملاء الفرعية ──

def test_client_gets_sub_account(auth_client):
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client, name='عميل تلقائي')
    with auth_client.application.app_context():
        from app.models import Client
        c = db.session.get(Client, cid)
        assert c.account_id is not None
        acc = db.session.get(Account, c.account_id)
        assert acc.parent_id == Account.query.filter_by(code='1301').first().id
        assert acc.code == f'1301{cid}'
        assert acc.account_type == 'asset'
        assert acc.is_active


def test_supplier_gets_sub_account_under_ap(auth_client):
    _seed_accounts(auth_client)
    sid = _make_supplier(auth_client, name='مورد فرعي')
    with auth_client.application.app_context():
        from app.models import Client
        s = db.session.get(Client, sid)
        assert s.account_id is not None
        acc = db.session.get(Account, s.account_id)
        assert acc.parent_id == Account.query.filter_by(code='2101').first().id
        assert acc.code == f'2101{sid}'
        assert acc.account_type == 'liability'


def test_invoice_posts_to_client_subaccount(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client, name='عميل فاتورة')
    auth_client.post(f'/client/{cid}/invoice/add', data={
        'description': 'فاتورة سلع',
        'amount': '500', 'date': '2026-01-22',
    }, follow_redirects=True)
    with auth_client.application.app_context():
        from app.models import Client, Invoice
        c = db.session.get(Client, cid)
        inv = Invoice.query.order_by(Invoice.id.desc()).first()
        entry = _entry_for('invoice', inv.id)
        assert entry is not None
        lines = _lines(entry)
        assert (c.account.code, 500.0, 0.0) in lines
        assert ('1301', 500.0, 0.0) not in lines


def test_payment_credits_client_subaccount(auth_client):
    _enable(auth_client)
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client, name='عميل دفع')
    _add_payment(auth_client, cid, '300', method='نقدي', date='2026-01-23')
    with auth_client.application.app_context():
        from app.models import Client, Payment
        c = db.session.get(Client, cid)
        pay = Payment.query.order_by(Payment.id.desc()).first()
        entry = _entry_for('payment', pay.id)
        assert entry is not None
        lines = _lines(entry)
        assert (c.account.code, 0.0, 300.0) in lines


def test_delete_client_deactivates_account(auth_client):
    _seed_accounts(auth_client)
    cid = _make_customer(auth_client, name='عميل للحذف')
    with auth_client.application.app_context():
        from app.models import Client
        c = db.session.get(Client, cid)
        acc_id = c.account_id
        assert db.session.get(Account, acc_id).is_active
    auth_client.post(f'/client/{cid}/delete', follow_redirects=True)
    with auth_client.application.app_context():
        assert db.session.get(Account, acc_id).is_active is False
