import json
from app.models import db, Client


def test_login_page(client):
    resp = client.get('/login')
    assert resp.status_code == 200


def test_login_success(auth_client):
    resp = auth_client.get('/')
    assert resp.status_code == 200


def test_login_fail(client):
    resp = client.post('/login', data={'username': 'wrong', 'password': 'wrong'}, follow_redirects=True)
    assert resp.status_code == 200


def test_add_client(auth_client):
    resp = auth_client.post('/client/add', data={
        'name': 'أحمد محمد',
        'phone': '201012345678',
        'notes': 'عميل تجريبي'
    }, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        c = Client.query.filter_by(name='أحمد محمد').first()
        assert c is not None
        assert c.phone == '201012345678'


def test_client_detail(auth_client):
    with auth_client.application.app_context():
        c = Client(name='-test', phone='123', status='due')
        db.session.add(c)
        db.session.commit()
        cid = c.id
    resp = auth_client.get(f'/client/{cid}')
    assert resp.status_code == 200


def test_edit_client(auth_client):
    with auth_client.application.app_context():
        c = Client(name='old-name', phone='000', status='due')
        db.session.add(c)
        db.session.commit()
        cid = c.id
    resp = auth_client.post(f'/client/{cid}/edit', data={
        'name': 'new-name',
        'phone': '111',
        'notes': 'updated'
    }, follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        c = Client.query.get(cid)
        assert c.name == 'new-name'


def test_delete_client(auth_client):
    with auth_client.application.app_context():
        c = Client(name='to-delete', status='due')
        db.session.add(c)
        db.session.commit()
        cid = c.id
    resp = auth_client.post(f'/client/{cid}/delete', follow_redirects=True)
    assert resp.status_code == 200
    with auth_client.application.app_context():
        assert Client.query.get(cid) is None


def test_add_invoice_api(auth_client):
    with auth_client.application.app_context():
        c = Client(name='inv-test', status='due')
        db.session.add(c)
        db.session.commit()
        cid = c.id
    resp = auth_client.post(f'/client/{cid}/invoice/add', data={
        'amount': '5000',
        'description': 'فاتورة تجريبية',
        'date': '2025-01-15'
    })
    data = json.loads(resp.data)
    assert data['ok'] is True
    assert resp.status_code == 200


def test_add_payment_api(auth_client):
    with auth_client.application.app_context():
        c = Client(name='pay-test', status='due')
        db.session.add(c)
        db.session.commit()
        cid = c.id
    resp = auth_client.post(f'/client/{cid}/payment/add', data={
        'amount': '2500',
        'date': '2025-01-15',
        'notes': 'دفعة تجريبية'
    })
    data = json.loads(resp.data)
    assert data['ok'] is True


def test_search(auth_client):
    with auth_client.application.app_context():
        db.session.add(Client(name='searchable', phone='999', status='due'))
        db.session.commit()
    resp = auth_client.get('/?q=searchable')
    assert resp.status_code == 200


def test_report_page(auth_client):
    resp = auth_client.get('/report')
    assert resp.status_code == 200


def test_advanced_report_page(auth_client):
    resp = auth_client.get('/advanced-report')
    assert resp.status_code == 200


def test_export_excel(auth_client):
    resp = auth_client.get('/export')
    assert resp.status_code == 200
    assert resp.content_type.startswith('application/vnd')


def test_api_list_clients(auth_client):
    resp = auth_client.get('/api/v1/clients')
    data = json.loads(resp.data)
    assert 'clients' in data
    assert 'total' in data


def test_api_create_client(auth_client):
    resp = auth_client.post('/api/v1/clients',
                            data=json.dumps({'name': 'API Client', 'phone': '123'}),
                            content_type='application/json')
    assert resp.status_code == 201
    data = json.loads(resp.data)
    assert data['client']['name'] == 'API Client'


def test_api_summary(auth_client):
    resp = auth_client.get('/api/v1/reports/summary')
    data = json.loads(resp.data)
    assert 'total_clients' in data
    assert 'total_debt' in data


def test_api_trends(auth_client):
    resp = auth_client.get('/api/v1/reports/trends')
    data = json.loads(resp.data)
    assert 'trends' in data
    assert len(data['trends']) == 6


# ── كشف حساب العميل ──

def test_client_statement_page(auth_client):
    with auth_client.application.app_context():
        c = Client(name='stmt-test', status='due')
        db.session.add(c)
        db.session.commit()
        cid = c.id
    resp = auth_client.get(f'/client/{cid}/statement')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'كشف حساب' in text
    assert 'stmt-test' in text


def test_client_statement_running_balance(auth_client):
    with auth_client.application.app_context():
        c = Client(name='stmt-bal', status='due')
        db.session.add(c)
        db.session.commit()
        cid = c.id
    auth_client.post(f'/client/{cid}/invoice/add', data={
        'amount': '1000', 'description': 'فاتورة 1', 'date': '2026-01-10'})
    auth_client.post(f'/client/{cid}/invoice/add', data={
        'amount': '500', 'description': 'فاتورة 2', 'date': '2026-01-20'})
    auth_client.post(f'/client/{cid}/payment/add', data={
        'amount': '300', 'date': '2026-01-25', 'notes': 'دفعة 1'})
    resp = auth_client.get(f'/client/{cid}/statement')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    # 1000 ثم 1500 ثم 1200
    assert '1,000.00' in text
    assert '1,500.00' in text
    assert '1,200.00' in text


def test_client_statement_date_filter_opening(auth_client):
    with auth_client.application.app_context():
        c = Client(name='stmt-open', status='due')
        db.session.add(c)
        db.session.commit()
        cid = c.id
    auth_client.post(f'/client/{cid}/invoice/add', data={
        'amount': '1000', 'description': 'فاتورة قبل', 'date': '2026-01-10'})
    auth_client.post(f'/client/{cid}/invoice/add', data={
        'amount': '500', 'description': 'فاتورة داخل', 'date': '2026-01-20'})
    resp = auth_client.get(f'/client/{cid}/statement?from=2026-01-15')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    # الرصيد الافتتاحي = 1000 (قبل 15 يناير)، ثم 500 → 1500
    assert '1,000.00' in text
    assert '1,500.00' in text


def test_client_statement_pdf(auth_client):
    with auth_client.application.app_context():
        c = Client(name='stmt-pdf', status='due')
        db.session.add(c)
        db.session.commit()
        cid = c.id
    auth_client.post(f'/client/{cid}/invoice/add', data={
        'amount': '1000', 'description': 'فاتورة', 'date': '2026-01-10'})
    resp = auth_client.get(f'/client/{cid}/statement/pdf')
    assert resp.status_code == 200
    assert resp.data[:4] == b'%PDF'


# ── تقرير تقادم الديون (Aging) ──

def _make_due_client(auth_client, name, total_debt, total_paid, invoice_date):
    from app.models import Invoice
    from datetime import date as _d
    with auth_client.application.app_context():
        c = Client(name=name, type='customer', status='due',
                   total_debt=total_debt, total_paid=total_paid)
        db.session.add(c)
        db.session.flush()
        db.session.add(Invoice(client_id=c.id, amount=total_debt,
                               date=invoice_date, description='فاتورة'))
        db.session.commit()
        return c.id


def test_aging_report_buckets(auth_client):
    from datetime import date, timedelta
    asof = date(2026, 1, 31)
    _make_due_client(auth_client, 'عميل حديث', 1000, 0,
                     asof - timedelta(days=10))
    _make_due_client(auth_client, 'عميل قديم جدا', 2000, 0,
                     asof - timedelta(days=120))
    resp = auth_client.get(f'/aging?to={asof.isoformat()}')
    assert resp.status_code == 200
    assert 'عميل حديث'.encode('utf-8') in resp.data
    assert 'عميل قديم جدا'.encode('utf-8') in resp.data
    assert 'أكثر من 90 يوم'.encode('utf-8') in resp.data


def test_aging_pdf(auth_client):
    from datetime import date, timedelta
    asof = date(2026, 1, 31)
    _make_due_client(auth_client, 'عميل PDF تقادم', 500, 0,
                     asof - timedelta(days=45))
    resp = auth_client.get(f'/aging/pdf?to={asof.isoformat()}')
    assert resp.status_code == 200
    assert resp.data[:4] == b'%PDF'
