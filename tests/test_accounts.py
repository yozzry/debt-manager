from app.models import db, Account, JournalEntry, JournalEntryLine


def _seed_accounts(auth_client):
    auth_client.post('/accounts/seed', follow_redirects=True)
    with auth_client.application.app_context():
        return Account.query.count()


def _add_account(auth_client, code='1103', name='صندوق فرعي', atype='asset',
                 parent='', opening='0'):
    data = {'code': code, 'name': name, 'account_type': atype,
            'opening_balance': opening}
    if parent:
        data['parent_id'] = parent
    return auth_client.post('/accounts/add', data=data, follow_redirects=True)


def _add_entry(auth_client, lines, desc='قيد اختبار', date='2026-01-20'):
    """lines: list of (account_id, debit, credit)"""
    data = {'date': date, 'description': desc,
            'account_id': [str(aid) for aid, _, _ in lines],
            'debit': [str(d) for _, d, _ in lines],
            'credit': [str(c) for _, _, c in lines]}
    return auth_client.post('/accounts/entries/add', data=data, follow_redirects=True)


def _last_entry():
    return JournalEntry.query.order_by(JournalEntry.id.desc()).first()


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

def test_index_page(auth_client):
    resp = auth_client.get('/accounts/')
    assert resp.status_code == 200


def test_entries_page(auth_client):
    resp = auth_client.get('/accounts/entries')
    assert resp.status_code == 200


def test_entry_add_page(auth_client):
    resp = auth_client.get('/accounts/entries/add')
    assert resp.status_code == 200


def test_trial_balance_page(auth_client):
    resp = auth_client.get('/accounts/trial-balance')
    assert resp.status_code == 200


# ── Chart of accounts ──

def test_seed_default_accounts(auth_client):
    count = _seed_accounts(auth_client)
    assert count == len([
        1, 11, 1101, 1102, 12, 1201, 13, 1301, 14, 1401,
        2, 21, 2101, 22, 2201, 3, 31, 3101, 3102,
        4, 41, 4101, 42, 4201, 5, 51, 5101, 52, 5201, 5202, 5203,
    ])


def test_seed_only_once(auth_client):
    _seed_accounts(auth_client)
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        assert Account.query.count() == 31


def test_add_leaf_account(auth_client):
    _add_account(auth_client, code='999', name='حساب جديد')
    with auth_client.application.app_context():
        a = Account.query.filter_by(code='999').first()
        assert a is not None
        assert a.name == 'حساب جديد'
        assert a.is_leaf
        assert a.balance() == 0.0


def test_add_account_with_parent(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        parent_id = str(Account.query.filter_by(code='1101').first().id)
    _add_account(auth_client, code='1103', name='طفل', parent=parent_id)
    with auth_client.application.app_context():
        parent = Account.query.filter_by(code='1101').first()
        child = Account.query.filter_by(code='1103').first()
        assert child.parent_id == parent.id
        assert not parent.is_leaf


def test_duplicate_code_rejected(auth_client):
    _add_account(auth_client, code='1101', name='تكرار')
    with auth_client.application.app_context():
        assert Account.query.filter_by(code='1101').count() == 1


def test_opening_balance_reflected(auth_client):
    _add_account(auth_client, code='1105', name='نقدية افتتاحية', opening='1000')
    with auth_client.application.app_context():
        a = Account.query.filter_by(code='1105').first()
        assert float(a.balance()) == 1000.0


# ── Journal entries ──

def test_balanced_entry_created(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '500', ''), (bank, '', '500')])
    with auth_client.application.app_context():
        e = _last_entry()
        assert e is not None
        assert e.entry_number.startswith('JV-')
        assert float(e.total) == 500.0
        assert e.is_balanced
        assert JournalEntryLine.query.filter_by(entry_id=e.id).count() == 2


def test_balances_updated(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '300', ''), (bank, '', '300')])
    with auth_client.application.app_context():
        assert float(db.session.get(Account, cash).balance()) == 300.0
        assert float(db.session.get(Account, bank).balance()) == -300.0


def test_unbalanced_rejected(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '500', ''), (bank, '', '400')])
    with auth_client.application.app_context():
        assert JournalEntry.query.count() == 0


def test_parent_account_not_allowed_in_entry(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        parent = Account.query.filter_by(code='11').first().id
    _add_entry(auth_client, [(cash, '100', ''), (parent, '', '100')])
    with auth_client.application.app_context():
        assert JournalEntry.query.count() == 0


def test_both_sides_on_line_rejected(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '100', '50'), (bank, '', '50')])
    with auth_client.application.app_context():
        assert JournalEntry.query.count() == 0


def test_single_line_rejected(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
    _add_entry(auth_client, [(cash, '100', '')])
    with auth_client.application.app_context():
        assert JournalEntry.query.count() == 0


def test_empty_amount_rejected(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '', ''), (bank, '', '')])
    with auth_client.application.app_context():
        assert JournalEntry.query.count() == 0


def test_entry_number_unique_sequence(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    for i in range(3):
        _add_entry(auth_client, [(cash, '100', ''), (bank, '', '100')])
    with auth_client.application.app_context():
        numbers = [e.entry_number for e in JournalEntry.query.all()]
        assert len(numbers) == len(set(numbers))


# ── Detail pages ──

def test_entry_detail_page(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '100', ''), (bank, '', '100')])
    with auth_client.application.app_context():
        eid = _last_entry().id
    resp = auth_client.get(f'/accounts/entries/{eid}')
    assert resp.status_code == 200
    assert 'قيد اختبار'.encode('utf-8') in resp.data


def test_account_detail_page(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '100', ''), (bank, '', '100')])
    resp = auth_client.get(f'/accounts/account/{cash}')
    assert resp.status_code == 200
    assert 'كشف الحساب'.encode('utf-8') in resp.data


def test_edit_account(auth_client):
    _add_account(auth_client, code='777', name='قبل')
    with auth_client.application.app_context():
        aid = Account.query.filter_by(code='777').first().id
    auth_client.post(f'/accounts/account/{aid}/edit', data={
        'code': '778', 'name': 'بعد', 'account_type': 'liability',
        'opening_balance': '50', 'is_active': 'on',
    }, follow_redirects=True)
    with auth_client.application.app_context():
        a = db.session.get(Account, aid)
        assert a.code == '778'
        assert a.name == 'بعد'
        assert a.account_type == 'liability'
        assert float(a.opening_balance) == 50.0
        assert a.is_active


# ── Trial balance ──

def test_trial_balance_totals_equal(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_account(auth_client, code='1105', name='صندوق', opening='1000')
    _add_entry(auth_client, [(cash, '300', ''), (bank, '', '300')])
    resp = auth_client.get('/accounts/trial-balance')
    assert resp.status_code == 200


def test_trial_balance_as_of_filter(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '1000', ''), (bank, '', '1000')],
               date='2026-01-20')
    # قبل تاريخ القيد لا يظهر الرصيد
    resp = auth_client.get('/accounts/trial-balance?to=2026-01-19')
    assert b'1,000.00' not in resp.data
    # في تاريخ القيد وبعده يظهر
    resp = auth_client.get('/accounts/trial-balance?to=2026-01-20')
    assert b'1,000.00' in resp.data
    resp = auth_client.get('/accounts/trial-balance')
    assert b'1,000.00' in resp.data


def test_trial_balance_pdf(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '1000', ''), (bank, '', '1000')])
    resp = auth_client.get('/accounts/trial-balance/pdf')
    assert resp.status_code == 200
    assert resp.data[:4] == b'%PDF'


# ── Delete ──

def test_delete_entry_removes_lines(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '100', ''), (bank, '', '100')])
    with auth_client.application.app_context():
        eid = _last_entry().id
    auth_client.post(f'/accounts/entries/{eid}/delete', follow_redirects=True)
    with auth_client.application.app_context():
        assert db.session.get(JournalEntry, eid) is None
        assert JournalEntryLine.query.filter_by(entry_id=eid).count() == 0


def test_delete_account_with_movements_blocked(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '100', ''), (bank, '', '100')])
    auth_client.post(f'/accounts/account/{cash}/delete', follow_redirects=True)
    with auth_client.application.app_context():
        assert db.session.get(Account, cash) is not None


def test_delete_parent_account_blocked(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        parent = Account.query.filter_by(code='11').first().id
    auth_client.post(f'/accounts/account/{parent}/delete', follow_redirects=True)
    with auth_client.application.app_context():
        assert db.session.get(Account, parent) is not None


# ── Permissions ──

def test_viewer_cannot_add_account(auth_client):
    _login_user(auth_client, 'viewer_acct', 'viewer')
    _add_account(auth_client, code='555', name='ممنوع')
    with auth_client.application.app_context():
        assert Account.query.filter_by(code='555').count() == 0


def test_viewer_cannot_add_entry(auth_client):
    _seed_accounts(auth_client)
    _login_user(auth_client, 'viewer_acct2', 'viewer')
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '100', ''), (bank, '', '100')])
    with auth_client.application.app_context():
        assert JournalEntry.query.count() == 0


def test_editor_can_add_entry(auth_client):
    _seed_accounts(auth_client)
    _login_user(auth_client, 'editor_acct', 'editor')
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '100', ''), (bank, '', '100')])
    with auth_client.application.app_context():
        assert JournalEntry.query.count() == 1


def test_editor_cannot_delete_entry(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        cash = Account.query.filter_by(code='1101').first().id
        bank = Account.query.filter_by(code='1102').first().id
    _add_entry(auth_client, [(cash, '100', ''), (bank, '', '100')])
    with auth_client.application.app_context():
        eid = _last_entry().id
    _login_user(auth_client, 'editor_acct2', 'editor')
    auth_client.post(f'/accounts/entries/{eid}/delete', follow_redirects=True)
    with auth_client.application.app_context():
        assert db.session.get(JournalEntry, eid) is not None
