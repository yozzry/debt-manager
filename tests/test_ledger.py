"""اختبارات دفتر الأستاذ (ledger_entries) — الرصيد الجاري لكل حساب."""
from app.models import db, Account, JournalEntry, JournalEntryLine, LedgerEntry, Settings


def _seed_accounts(auth_client):
    auth_client.post('/accounts/seed', follow_redirects=True)


def _account_id(auth_client, code):
    with auth_client.application.app_context():
        return Account.query.filter_by(code=code).first().id


def _add_entry(auth_client, lines, desc='قيد اختبار', date='2026-01-20'):
    """lines: list of (account_id, debit, credit)"""
    data = {'date': date, 'description': desc,
            'account_id': [str(aid) for aid, _, _ in lines],
            'debit': [str(d) for _, d, _ in lines],
            'credit': [str(c) for _, _, c in lines]}
    return auth_client.post('/accounts/entries/add', data=data, follow_redirects=True)


def _ledger(account_id):
    return [(float(l.debit or 0), float(l.credit or 0), float(l.running_balance or 0))
            for l in LedgerEntry.query.filter_by(account_id=account_id)
                                     .order_by(LedgerEntry.id).all()]


def test_ledger_populated_on_entry_add(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    bank = _account_id(auth_client, '1102')
    resp = _add_entry(auth_client, [(cash, '500', ''), (bank, '', '500')])
    assert resp.status_code == 200
    with auth_client.application.app_context():
        assert LedgerEntry.query.count() == 2
        assert _ledger(cash) == [(500.0, 0.0, 500.0)]
        assert _ledger(bank) == [(0.0, 500.0, -500.0)]


def test_ledger_running_balance_accumulates(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    bank = _account_id(auth_client, '1102')
    _add_entry(auth_client, [(cash, '300', ''), (bank, '', '300')], date='2026-01-20')
    _add_entry(auth_client, [(cash, '200', ''), (bank, '', '200')], date='2026-01-21')
    with auth_client.application.app_context():
        assert _ledger(cash) == [(300.0, 0.0, 300.0), (200.0, 0.0, 500.0)]
        assert _ledger(bank) == [(0.0, 300.0, -300.0), (0.0, 200.0, -500.0)]


def test_ledger_honors_opening_balance(auth_client):
    _seed_accounts(auth_client)
    with auth_client.application.app_context():
        a = Account(code='1105', name='نقدية افتتاحية', account_type='asset',
                    opening_balance=1000)
        db.session.add(a)
        db.session.commit()
        cash_id = a.id
    bank = _account_id(auth_client, '1102')
    _add_entry(auth_client, [(cash_id, '150', ''), (bank, '', '150')])
    with auth_client.application.app_context():
        assert _ledger(cash_id) == [(150.0, 0.0, 1150.0)]


def test_ledger_rebuilt_on_delete(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    bank = _account_id(auth_client, '1102')
    _add_entry(auth_client, [(cash, '500', ''), (bank, '', '500')])
    with auth_client.application.app_context():
        e = JournalEntry.query.order_by(JournalEntry.id.desc()).first()
        eid = e.id
    auth_client.post(f'/accounts/entries/{eid}/delete', follow_redirects=True)
    with auth_client.application.app_context():
        assert LedgerEntry.query.count() == 0


def test_ledger_line_unique_constraint(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    bank = _account_id(auth_client, '1102')
    _add_entry(auth_client, [(cash, '500', ''), (bank, '', '500')])
    with auth_client.application.app_context():
        assert len({l.line_id for l in LedgerEntry.query.all()}) == LedgerEntry.query.count()


def test_ledger_matches_account_balance(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    bank = _account_id(auth_client, '1102')
    _add_entry(auth_client, [(cash, '300', ''), (bank, '', '300')], date='2026-01-20')
    _add_entry(auth_client, [(cash, '200', ''), (bank, '', '200')], date='2026-01-21')
    with auth_client.application.app_context():
        cash_acc = db.session.get(Account, cash)
        bank_acc = db.session.get(Account, bank)
        assert float(cash_acc.balance()) == _ledger(cash)[-1][2]
        assert float(bank_acc.balance()) == _ledger(bank)[-1][2]


def test_auto_accounting_writes_ledger(auth_client):
    with auth_client.application.app_context():
        Settings.set('auto_accounting_enabled', True, value_type='bool')
    _seed_accounts(auth_client)
    auth_client.post('/products/add', data={
        'name': 'قهوة', 'sku': 'SKU-قهوة', 'barcode': '', 'unit': 'قطعة',
        'cost_price': '5', 'selling_price': '10', 'min_stock': '1', 'is_active': 'on',
    }, follow_redirects=True)
    with auth_client.application.app_context():
        from app.models import Product
        pid = Product.query.filter_by(name='قهوة').first().id
    auth_client.post(f'/products/{pid}/stock', data={
        'movement_type': 'IN', 'quantity': '10'}, follow_redirects=True)
    auth_client.post('/pos/complete', data={
        'client_id': '', 'payment_method': 'cash', 'discount_type': 'amount',
        'discount_value': '0', 'date': '2026-01-20',
        'product_id': [str(pid)], 'quantity': ['1'], 'unit_price': ['10'],
    }, follow_redirects=True)
    with auth_client.application.app_context():
        # بيع نقدي: مدين نقدية 10 + مدين تكلفة 5، دائن مبيعات 10 + دائن مخزون 5
        assert LedgerEntry.query.count() == 4
        cash_id = Account.query.filter_by(code='1101').first().id
        assert _ledger(cash_id)[-1] == (10.0, 0.0, 10.0)


# ── صفحة دفتر الأستاذ ──

def test_ledger_page_empty(auth_client):
    resp = auth_client.get('/accounts/ledger')
    assert resp.status_code == 200
    assert 'دفتر الأستاذ'.encode() in resp.data or 'دفتر الأستاذ' in resp.get_data(as_text=True)


def test_ledger_page_shows_entries(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    bank = _account_id(auth_client, '1102')
    _add_entry(auth_client, [(cash, '500', ''), (bank, '', '500')])
    resp = auth_client.get('/accounts/ledger')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert '1101' in text
    assert '500.00' in text


def test_ledger_page_filter_by_account(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    bank = _account_id(auth_client, '1102')
    _add_entry(auth_client, [(cash, '500', ''), (bank, '', '500')])
    resp = auth_client.get(f'/accounts/ledger?account_id={cash}')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    # خلية الحساب في صفوف الجدول تعرض كود الحساب فقط؛ خلية القيد تعرض رقم القيد
    assert '1101' in text
    # 1102 لن يظهر كصف حركة (يظهر فقط ضمن قائمة الترشيح)
    rows = [line for line in text.splitlines() if '1102' in line and 'option' not in line]
    assert rows == []


def test_ledger_page_date_filter(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    bank = _account_id(auth_client, '1102')
    _add_entry(auth_client, [(cash, '300', ''), (bank, '', '300')], date='2026-01-20')
    _add_entry(auth_client, [(cash, '200', ''), (bank, '', '200')], date='2026-01-21')
    resp = auth_client.get('/accounts/ledger?from=2026-01-21')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert '200.00' in text
    # الرصيد الجاري بعد نطاق 21 يناير = 300 (قبل النطاق) + 200 = 500
    assert '500.00' in text


# ── أقسام دفتر الأستاذ ──

def test_ledger_sections_grouped_by_account(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    bank = _account_id(auth_client, '1102')
    _add_entry(auth_client, [(cash, '500', ''), (bank, '', '500')])
    with auth_client.application.app_context():
        from app.accounts.ledger import ledger_sections
        sections = ledger_sections()
        assert len(sections) == 2
        by_code = {s['account'].code: s for s in sections}
        assert by_code['1101']['closing'] == 500.0
        assert by_code['1102']['closing'] == -500.0
        assert by_code['1101']['rows'][0]['running'] == 500.0


def test_ledger_sections_date_filter_running(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    bank = _account_id(auth_client, '1102')
    _add_entry(auth_client, [(cash, '300', ''), (bank, '', '300')], date='2026-01-20')
    _add_entry(auth_client, [(cash, '200', ''), (bank, '', '200')], date='2026-01-21')
    with auth_client.application.app_context():
        from app.accounts.ledger import ledger_sections
        sections = ledger_sections(date_from='2026-01-21')
        cash_sec = next(s for s in sections if s['account'].code == '1101')
        # الرصيد الافتتاحي للنطاق = 300 (قبل 21 يناير)، ثم حركة 200 → رصيد 500
        assert cash_sec['opening'] == 300.0
        assert cash_sec['closing'] == 500.0


# ── طباعة PDF ──

def test_ledger_pdf_empty(auth_client):
    resp = auth_client.get('/accounts/ledger/pdf')
    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data[:4] == b'%PDF'


def test_ledger_pdf_with_data(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    bank = _account_id(auth_client, '1102')
    _add_entry(auth_client, [(cash, '500', ''), (bank, '', '500')])
    resp = auth_client.get('/accounts/ledger/pdf')
    assert resp.status_code == 200
    assert resp.data[:4] == b'%PDF'


def test_ledger_pdf_account_filter(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    bank = _account_id(auth_client, '1102')
    _add_entry(auth_client, [(cash, '500', ''), (bank, '', '500')])
    resp = auth_client.get(f'/accounts/ledger/pdf?account_id={cash}')
    assert resp.status_code == 200
    assert resp.data[:4] == b'%PDF'


# ── القوائم المالية ──

def test_balance_sheet_page_empty(auth_client):
    resp = auth_client.get('/accounts/balance-sheet')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'الميزانية العمومية' in text
    assert 'متوازنة' in text


def test_balance_sheet_matches_identity(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    # بيع نقدي: مدين نقدية 1000، دائن مبيعات 1000 → أصول 1000، إيرادات 1000
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')])
    resp = auth_client.get('/accounts/balance-sheet')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert '1,000.00' in text
    assert 'متوازنة' in text


def test_balance_sheet_as_of_date(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')],
               date='2026-01-20')
    resp = auth_client.get('/accounts/balance-sheet?to=2026-01-19')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert '1,000.00' not in text
    resp2 = auth_client.get('/accounts/balance-sheet?to=2026-01-20')
    assert '1,000.00' in resp2.get_data(as_text=True)


def test_income_statement_period(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')],
               date='2026-01-20')
    resp = auth_client.get('/accounts/income-statement')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert '1,000.00' in text
    assert 'صافي الدخل' in text


def test_income_statement_date_filter(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')],
               date='2026-01-20')
    # فترة بعد القيد → صافي دخل صفر
    resp = auth_client.get('/accounts/income-statement?from=2026-01-21')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert '0.00' in text
    assert '1,000.00' not in text


def test_balance_sheet_pdf(auth_client):
    resp = auth_client.get('/accounts/balance-sheet/pdf')
    assert resp.status_code == 200
    assert resp.data[:4] == b'%PDF'


def test_income_statement_pdf(auth_client):
    resp = auth_client.get('/accounts/income-statement/pdf')
    assert resp.status_code == 200
    assert resp.data[:4] == b'%PDF'


# ── مقارنة الفترات في القوائم المالية ──

def test_balance_sheet_start_end_columns(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')],
               date='2026-01-20')
    # من 2026-01-21: بداية الفترة 1000 (قبلها)، نهاية الفترة 1000 (لا حركة لاحقة)
    resp = auth_client.get('/accounts/balance-sheet?from=2026-01-21')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'بداية الفترة' in text
    assert 'نهاية الفترة' in text
    # حركة داخل الفترة 2026-01-21..22 تعكس تغيّر الرصيد
    _add_entry(auth_client, [(cash, '500', ''), (sales, '', '500')],
               date='2026-01-22')
    resp2 = auth_client.get('/accounts/balance-sheet?from=2026-01-21&to=2026-01-31')
    text2 = resp2.get_data(as_text=True)
    assert '1,500.00' in text2
    assert '1,000.00' in text2


def test_income_statement_compare_previous_period(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    # الفترة السابقة: 1000
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')],
               date='2026-01-20')
    # الفترة الحالية: 500
    _add_entry(auth_client, [(cash, '500', ''), (sales, '', '500')],
               date='2026-01-27')
    resp = auth_client.get(
        '/accounts/income-statement?from=2026-01-26&to=2026-01-31&compare=1')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'الفترة السابقة' in text
    assert '500.00' in text
    assert '1,000.00' in text


def test_income_statement_compare_pdf(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')],
               date='2026-01-20')
    resp = auth_client.get(
        '/accounts/income-statement/pdf?from=2026-01-26&to=2026-01-31&compare=1')
    assert resp.status_code == 200
    assert resp.data[:4] == b'%PDF'


def test_balance_sheet_pdf_with_period(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')],
               date='2026-01-20')
    resp = auth_client.get('/accounts/balance-sheet/pdf?from=2026-01-21&to=2026-01-31')
    assert resp.status_code == 200
    assert resp.data[:4] == b'%PDF'


# ── الرسوم البيانية للقوائم المالية ──

def test_analytics_page_empty(auth_client):
    resp = auth_client.get('/accounts/analytics')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'الرسوم البيانية' in text
    assert 'netIncomeChart' in text


def test_analytics_monthly_trend(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')],
               date='2026-01-20')
    resp = auth_client.get('/accounts/analytics')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'incomeExpenseChart' in text
    assert '1,000' in text or '1000' in text


def test_analytics_requires_login(client):
    resp = client.get('/accounts/analytics')
    assert resp.status_code in (302, 401, 403)


# ── بيان التدفقات النقدية ──

def test_cash_flow_page_empty(auth_client):
    resp = auth_client.get('/accounts/cash-flow')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'التدفقات النقدية' in text


def test_cash_flow_cash_sale(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')])
    resp = auth_client.get('/accounts/cash-flow')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'متسق' in text
    assert '1,000.00' in text


def test_cash_flow_credit_sale_reduces_operating(auth_client):
    _seed_accounts(auth_client)
    ar = _account_id(auth_client, '1301')
    sales = _account_id(auth_client, '4101')
    # بيع آجل: مدين ذمم مدينة 1000، دائن مبيعات 1000 → تدفق تشغيلي صفر
    _add_entry(auth_client, [(ar, '1000', ''), (sales, '', '1000')])
    resp = auth_client.get('/accounts/cash-flow')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'متسق' in text
    assert '0.00' in text


def test_cash_flow_pdf(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')])
    resp = auth_client.get('/accounts/cash-flow/pdf')
    assert resp.status_code == 200
    assert resp.data[:4] == b'%PDF'


# ── التقرير المالي الشامل ──

def test_overview_page_empty(auth_client):
    resp = auth_client.get('/accounts/overview')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'التقرير المالي الشامل' in text


def test_overview_shows_kpis(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')])
    resp = auth_client.get('/accounts/overview')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'إجمالي الأصول' in text
    assert 'النقدية والبنك' in text
    assert 'صافي التدفق النقدي' in text


def test_overview_pdf(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')])
    resp = auth_client.get('/accounts/overview/pdf')
    assert resp.status_code == 200
    assert resp.data[:4] == b'%PDF'


def test_overview_pdf_compare(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')],
               date='2026-01-20')
    resp = auth_client.get('/accounts/overview/pdf?compare=1')
    assert resp.status_code == 200
    assert resp.data[:4] == b'%PDF'


# ── الإقفال السنوي ──

def _retained_id(auth_client):
    with auth_client.application.app_context():
        from app.models import Account
        a = Account.query.filter_by(code='3102').first()
        return a.id if a else None


def test_close_period_page(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')])
    resp = auth_client.get('/accounts/close-period?date=2026-12-31')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'الإقفال السنوي' in text
    assert 'تنفيذ الإقفال السنوي' in text


def test_close_period_transfers_net_income(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')])
    resp = auth_client.post('/accounts/close-period?date=2026-12-31',
                            data={'date': '2026-12-31'})
    assert resp.status_code in (302, 303)
    with auth_client.application.app_context():
        from app.models import JournalEntry, Account
        entry = JournalEntry.query.filter_by(source_type='closing').first()
        assert entry is not None
        assert entry.is_balanced
        re = Account.query.filter_by(code='3102').first()
        assert re is not None
        assert re.balance() == 1000.0
        sales = Account.query.filter_by(code='4101').first()
        assert sales.balance() == 0.0
        cash = Account.query.filter_by(code='1101').first()
        assert cash.balance() == 1000.0


def test_close_period_once_per_date(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')])
    auth_client.post('/accounts/close-period', data={'date': '2026-12-31'})
    auth_client.post('/accounts/close-period', data={'date': '2026-12-31'})
    with auth_client.application.app_context():
        from app.models import JournalEntry
        count = JournalEntry.query.filter_by(source_type='closing').count()
        assert count == 1


def test_close_period_reverse(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')])
    auth_client.post('/accounts/close-period', data={'date': '2026-12-31'})
    resp = auth_client.post('/accounts/close-period/reverse',
                            data={'date': '2026-12-31'})
    assert resp.status_code in (302, 303)
    with auth_client.application.app_context():
        from app.models import JournalEntry, Account
        assert JournalEntry.query.filter_by(source_type='closing').count() == 0
        assert Account.query.filter_by(code='4101').first().balance() == 1000.0
        assert Account.query.filter_by(code='3102').first().balance() == 0.0


def test_close_period_no_data(auth_client):
    _seed_accounts(auth_client)
    resp = auth_client.post('/accounts/close-period',
                            data={'date': '2026-12-31'})
    assert resp.status_code in (302, 303)
    with auth_client.application.app_context():
        from app.models import JournalEntry
        assert JournalEntry.query.filter_by(source_type='closing').count() == 0


# ── الإعدادات المالية (اسم المنشأة) ──

def _set_company_name(auth_client, name='مؤسسة النور التجارية'):
    auth_client.post('/settings', data={'tab': 'general',
                                        'company_name': name},
                     follow_redirects=True)


def test_company_name_shown_on_statements(auth_client):
    _seed_accounts(auth_client)
    _set_company_name(auth_client)
    for path in ('/accounts/balance-sheet', '/accounts/income-statement',
                 '/accounts/cash-flow', '/accounts/overview'):
        resp = auth_client.get(path)
        assert resp.status_code == 200
        assert 'مؤسسة النور التجارية' in resp.get_data(as_text=True)


def test_company_name_in_pdfs(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')])
    _set_company_name(auth_client)
    for path in ('/accounts/balance-sheet/pdf', '/accounts/income-statement/pdf',
                 '/accounts/cash-flow/pdf', '/accounts/overview/pdf',
                 '/accounts/ledger/pdf'):
        resp = auth_client.get(path)
        assert resp.status_code == 200
        assert resp.data[:4] == b'%PDF'


def test_company_name_setting_saved(auth_client):
    _set_company_name(auth_client, 'شركة الاختبار')
    with auth_client.application.app_context():
        from app.models import Settings
        assert Settings.get('company_name', '') == 'شركة الاختبار'


# ── عرض العملة على القوائم المالية ──

def _set_currency(auth_client, short='ج.م'):
    auth_client.post('/settings', data={'tab': 'general',
                                        'app_currency_short': short},
                     follow_redirects=True)


def test_currency_shown_on_statement_headers(auth_client):
    _seed_accounts(auth_client)
    _set_currency(auth_client, 'ر.س')
    for path in ('/accounts/balance-sheet', '/accounts/income-statement',
                 '/accounts/cash-flow', '/accounts/overview'):
        resp = auth_client.get(path)
        assert resp.status_code == 200
        text = resp.get_data(as_text=True)
        assert 'ر.س' in text


def test_currency_in_statement_pdfs(auth_client):
    _seed_accounts(auth_client)
    cash = _account_id(auth_client, '1101')
    sales = _account_id(auth_client, '4101')
    _add_entry(auth_client, [(cash, '1000', ''), (sales, '', '1000')])
    _set_currency(auth_client, 'د.إ')
    for path in ('/accounts/balance-sheet/pdf', '/accounts/income-statement/pdf',
                 '/accounts/cash-flow/pdf', '/accounts/overview/pdf',
                 '/accounts/ledger/pdf'):
        resp = auth_client.get(path)
        assert resp.status_code == 200
        assert resp.data[:4] == b'%PDF'
