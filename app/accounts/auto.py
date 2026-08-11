"""قيود اليومية التلقائية (قيد مزدوج) للعمليات التشغيلية.

تُنشئ قيداً واحداً لكل مصدر (بيع/استلام شراء/دفعة) عند تفعيل
الإعداد auto_accounting_enabled، مع ضمان عدم التكرار عبر
source_type/source_id، وعكس القيد عند إلغاء العملية.
"""
from datetime import date

from app.models import db, Account, JournalEntry, JournalEntryLine, Settings, Client
from app.utils import log_activity

SETTING_ENABLED = 'auto_accounting_enabled'

# أرقام الحسابات الافتراضية المستخدمة في الربط التلقائي
CASH_CODE = '1101'
BANK_CODE = '1102'
INVENTORY_CODE = '1201'
AR_CODE = '1301'
AP_CODE = '2101'
REVENUE_CODE = '4101'
COGS_CODE = '5101'


def _enabled():
    val = Settings.get(SETTING_ENABLED, False)
    if isinstance(val, str):
        return val.strip().lower() in ('true', '1', 'yes')
    return bool(val)


def _account_by_code(code):
    a = Account.query.filter_by(code=code, is_active=True).first()
    if a:
        return a
    return Account.query.filter_by(code=code).first()


def _client_account(client):
    """حساب العميل الفرعي (ذمم) إن وُجد ونشط."""
    if client and client.account_id:
        acc = db.session.get(Account, client.account_id)
        if acc and acc.is_active:
            return acc
    return None


def _client_parent_code(client):
    if client and client.type == 'supplier':
        return AP_CODE
    return AR_CODE


def create_client_account(client):
    """إنشاء حساب فرعي للعميل تحت حساب الذمم (1301 عملاء / 2101 موردون).

    الكود يُشتق من كود الأب + معرف العميل (مثال: 13011)، والرصيد الافتتاحي
    يعكس الديون الأساسية للعميل (base_debt - base_paid)."""
    if not client or not client.id:
        return None
    if _client_account(client):
        return _client_account(client)
    if client.account_id:
        acc = db.session.get(Account, client.account_id)
        if acc:
            return acc
    parent_code = _client_parent_code(client)
    parent = _account_by_code(parent_code)
    if not parent:
        return None
    code = f'{parent.code}{client.id}'
    acc = Account.query.filter_by(code=code).first()
    if not acc:
        acc = Account(code=code,
                      name=client.name or f'عميل #{client.id}',
                      account_type=parent.account_type,
                      parent_id=parent.id,
                      opening_balance=round(
                          float(client.base_debt or 0) - float(client.base_paid or 0),
                          2))
        db.session.add(acc)
        db.session.flush()
    client.account_id = acc.id
    db.session.flush()
    return acc


def sync_client_account(client):
    """مزامنة اسم/نوع حساب العميل عند تعديل بيانات العميل."""
    acc = _client_account(client) or create_client_account(client)
    if not acc:
        return None
    if acc.name != (client.name or ''):
        acc.name = client.name
    expected_parent_code = _client_parent_code(client)
    parent = _account_by_code(expected_parent_code)
    if parent and acc.parent_id != parent.id:
        acc.account_type = parent.account_type
        acc.parent_id = parent.id
    db.session.flush()
    return acc


def deactivate_client_account(client):
    """تعطيل حساب العميل عند الحذف مع الإبقاء على السجل المحاسبي."""
    acc = _client_account(client)
    if acc:
        acc.is_active = False
        db.session.flush()
    return acc


def _next_entry_number():
    from app.accounts import _next_entry_number as _gen
    return _gen()


def _find(source_type, source_id):
    return JournalEntry.query.filter_by(source_type=source_type,
                                        source_id=source_id).first()


def _log(user_id, entry, action, label):
    try:
        log_activity(user_id, action, 'journal_entry', entry.id,
                     f'{label}: {entry.entry_number}', None)
    except Exception:
        pass


def _create(source_type, source_id, entry_date, description, lines, user_id):
    """lines: list of (account, debit, credit). يعيد القيد أو None."""
    if _find(source_type, source_id):
        return None
    cleaned = [(acc, round(float(d or 0), 2), round(float(c or 0), 2))
               for acc, d, c in lines if acc is not None]
    cleaned = [(acc, d, c) for acc, d, c in cleaned if d or c]
    if not cleaned:
        return None
    total_debit = sum(d for _, d, _ in cleaned)
    total_credit = sum(c for _, _, c in cleaned)
    if abs(total_debit - total_credit) > 0.005:
        return None

    entry = JournalEntry(
        entry_number=_next_entry_number(),
        date=entry_date or date.today(),
        description=description,
        created_by=user_id,
        source_type=source_type,
        source_id=source_id,
    )
    db.session.add(entry)
    db.session.flush()
    for acc, d, c in cleaned:
        db.session.add(JournalEntryLine(
            entry_id=entry.id,
            account_id=acc.id,
            debit=d,
            credit=c,
        ))
    db.session.flush()
    from app.accounts.ledger import sync_entry
    sync_entry(entry)
    _log(user_id, entry, 'add', 'قيد تلقائي')
    return entry


def _delete(source_type, source_id, user_id):
    entry = _find(source_type, source_id)
    if not entry:
        return None
    account_ids = [line.account_id for line in entry.lines]
    _log(user_id, entry, 'delete', 'عكس قيد تلقائي')
    from app.models import LedgerEntry
    LedgerEntry.query.filter(LedgerEntry.entry_id == entry.id).delete()
    db.session.flush()
    db.session.delete(entry)
    db.session.flush()
    from app.accounts.ledger import rebuild_account
    for aid in set(account_ids):
        rebuild_account(aid)
    return entry


def _sale_cogs(sale):
    return round(sum(float(i.quantity or 0) * float(i.product.cost_price or 0)
                     for i in sale.items), 2)


def _cash_or_bank(payment_method):
    method = (payment_method or '').strip().lower()
    if 'bank' in method or 'بنك' in method:
        return _account_by_code(BANK_CODE), 'البنك'
    return _account_by_code(CASH_CODE), 'النقدية'


# ── المبيعات ──

def post_sale_entries(sale, user_id=None):
    """قيود بيع: (مدين نقدية/عملاء، مدين تكلفة، دائن مبيعات، دائن مخزون)."""
    if not _enabled():
        return None
    total = round(float(sale.total or 0), 2)
    cogs = _sale_cogs(sale)
    revenue = _account_by_code(REVENUE_CODE)
    inventory = _account_by_code(INVENTORY_CODE)
    if not revenue or not inventory:
        return None

    if sale.payment_method == 'credit':
        client = db.session.get(Client, sale.client_id) if sale.client_id else None
        counterpart = _client_account(client) or _account_by_code(AR_CODE)
        lines = [(counterpart, total, 0.0),
                 (_account_by_code(COGS_CODE), cogs, 0.0),
                 (revenue, 0.0, total),
                 (inventory, 0.0, cogs)]
        cname = 'ذمم مدينة'
    else:
        counterpart, cname = _cash_or_bank(sale.payment_method)
        lines = [(counterpart, total, 0.0),
                 (_account_by_code(COGS_CODE), cogs, 0.0),
                 (revenue, 0.0, total),
                 (inventory, 0.0, cogs)]
    return _create('sale', sale.id, sale.date,
                   f'تسجيل بيع {sale.invoice_number}', lines, user_id)


def reverse_sale_entries(sale, user_id=None):
    return _delete('sale', sale.id, user_id)


# ── أوامر الشراء ──

def post_purchase_entries(order, user_id=None):
    """قيود استلام: (مدين مخزون، دائن موردون)."""
    if not _enabled():
        return None
    total = round(float(order.total_amount or 0), 2)
    inventory = _account_by_code(INVENTORY_CODE)
    ap = _account_by_code(AP_CODE)
    if not inventory or not ap:
        return None
    return _create('purchase', order.id, order.date,
                   f'استلام أمر شراء {order.order_number}',
                   [(inventory, total, 0.0), (ap, 0.0, total)], user_id)


def reverse_purchase_entries(order, user_id=None):
    return _delete('purchase', order.id, user_id)


# ── فواتير العملاء اليدوية ──

def post_invoice_entries(invoice, user_id=None):
    """فاتورة عميل يدوية: (مدين عملاء، دائن مبيعات)."""
    if not _enabled():
        return None
    client = db.session.get(Client, invoice.client_id)
    if not client or client.type == 'supplier':
        return None
    ar = _client_account(client) or _account_by_code(AR_CODE)
    revenue = _account_by_code(REVENUE_CODE)
    if not ar or not revenue:
        return None
    amount = round(float(invoice.amount or 0), 2)
    if amount <= 0:
        return None
    return _create('invoice', invoice.id, invoice.date,
                   f'فاتورة للعميل {client.name}',
                   [(ar, amount, 0.0), (revenue, 0.0, amount)], user_id)


def reverse_invoice_entries(invoice, user_id=None):
    return _delete('invoice', invoice.id, user_id)


# ── الدفعات ──

def post_payment_entries(payment, user_id=None):
    """دفعة عميل: (مدين نقدية/بنك، دائن عملاء) — دفعة مورد: عكسها."""
    if not _enabled():
        return None
    amount = round(float(payment.amount or 0), 2)
    client = db.session.get(Client, payment.client_id)
    if not client:
        return None
    cash_or_bank, cname = _cash_or_bank(payment.payment_method)
    if not cash_or_bank:
        return None
    if client.type == 'supplier':
        ap = _client_account(client) or _account_by_code(AP_CODE)
        if not ap:
            return None
        lines = [(ap, amount, 0.0), (cash_or_bank, 0.0, amount)]
        desc = f'دفع للمورد {client.name}'
    else:
        ar = _client_account(client) or _account_by_code(AR_CODE)
        if not ar:
            return None
        lines = [(cash_or_bank, amount, 0.0), (ar, 0.0, amount)]
        desc = f'تحصيل من {client.name}'
    return _create('payment', payment.id, payment.date, desc, lines, user_id)


def reverse_payment_entries(payment, user_id=None):
    return _delete('payment', payment.id, user_id)


# ── الإقفال السنوي ──

RETAINED_EARNINGS_CODE = '3102'
CLOSING_TYPE = 'closing'


def _retained_earnings_account():
    re = _account_by_code(RETAINED_EARNINGS_CODE)
    if not re:
        parent = _account_by_code('31') or _account_by_code('3')
        re = Account(code=RETAINED_EARNINGS_CODE,
                     name='الأرباح المحتجزة', account_type='equity',
                     parent_id=parent.id if parent else None)
        db.session.add(re)
        db.session.flush()
    return re


def _closing_lines():
    """سطور الإقفال المقترحة: إقفال الإيرادات والمصروفات ونقل الصافي."""
    from app.accounts import _leaf_accounts
    lines = []
    total_income = 0.0
    total_expense = 0.0
    for a in _leaf_accounts():
        bal = a.balance()
        if a.account_type == 'income' and abs(bal) > 0.005:
            lines.append((a, round(float(bal), 2), 0.0))
            total_income += bal
        elif a.account_type == 'expense' and abs(bal) > 0.005:
            lines.append((a, 0.0, round(float(bal), 2)))
            total_expense += bal
    net = round(total_income - total_expense, 2)
    return lines, net


def preview_close():
    """بيانات معاينة الإقفال دون تنفيذ."""
    lines, net = _closing_lines()
    income = [l for l in lines if l[1] > 0]
    expenses = [l for l in lines if l[2] > 0]
    return {'income': income, 'expenses': expenses, 'net': net,
            'can_close': bool(lines) or abs(net) > 0.005}


def close_period(entry_date, user_id=None):
    """تنفيذ الإقفال: نقل صافي الدخل إلى الأرباح المحتجزة.

    يرجع القيد المنشأ أو None إذا لم يوجد ما يُقفل أو كان التاريخ مقفلاً.
    """
    if entry_date is None:
        entry_date = date.today()
    if _find(CLOSING_TYPE, str(entry_date)):
        return None
    lines, net = _closing_lines()
    if not lines and abs(net) < 0.005:
        return None
    re = _retained_earnings_account()
    if net >= 0:
        lines.append((re, 0.0, net))
    else:
        lines.append((re, -net, 0.0))
    return _create(CLOSING_TYPE, str(entry_date), entry_date,
                   f'الإقفال السنوي {entry_date}', lines, user_id)


def is_closed(entry_date):
    if entry_date is None:
        return False
    return _find(CLOSING_TYPE, str(entry_date)) is not None


def delete_closing(entry_date, user_id=None):
    return _delete(CLOSING_TYPE, str(entry_date), user_id)
