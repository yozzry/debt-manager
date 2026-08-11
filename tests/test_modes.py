"""اختبارات وضعي التشغيل: المديونية (debt) والتجارة (commerce)."""


def test_default_mode_is_debt(auth_client):
    resp = auth_client.get('/')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'الرئيسية' in body
    assert 'التقارير' in body
    assert 'نقطة البيع' not in body
    assert 'المنتجات والمخازن' not in body
    assert 'المديونيات' in body


def test_switch_to_commerce(auth_client):
    resp = auth_client.get('/mode/commerce')
    assert resp.status_code == 302
    assert '/dashboard/' in resp.headers['Location']
    with auth_client.session_transaction() as sess:
        assert sess['app_mode'] == 'commerce'

    body = auth_client.get('/dashboard/').get_data(as_text=True)
    assert 'نقطة البيع' in body
    assert 'سجل المبيعات' in body
    assert 'المنتجات والمخازن' in body
    assert 'المشتريات' in body
    assert 'المحاسبة' in body
    assert 'لوحة العمليات' in body
    assert 'الرئيسية' not in body
    assert 'إدارة التجارة' in body


def test_switch_back_to_debt(auth_client):
    auth_client.get('/mode/commerce')
    resp = auth_client.get('/mode/debt')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/')
    with auth_client.session_transaction() as sess:
        assert sess['app_mode'] == 'debt'


def test_invalid_mode_falls_back_to_debt(auth_client):
    resp = auth_client.get('/mode/somewhere')
    assert resp.status_code == 302
    with auth_client.session_transaction() as sess:
        assert sess['app_mode'] == 'debt'


def test_mode_switch_requires_login(client):
    resp = client.get('/mode/commerce')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_landing_url_helper(auth_client):
    from app.utils import landing_url
    auth_client.get('/mode/commerce')
    with auth_client.application.test_request_context():
        from flask import session
        session['app_mode'] = 'commerce'
        assert landing_url().endswith('/dashboard/')
        session['app_mode'] = 'debt'
        assert landing_url() == '/'


def test_commerce_pages_still_accessible_from_debt_mode(auth_client):
    resp = auth_client.get('/products/')
    assert resp.status_code == 200
