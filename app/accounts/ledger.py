"""دفتر الأستاذ (Ledger) — بناء/إعادة بناء أرصدة الحسابات الجارية.

يُبنى جدول ledger_entries من journal_entry_lines بالترتيب
(تاريخ القيد، رقم القيد، رقم السطر) لكل حساب، بدءاً من الرصيد الافتتاحي.
يُعاد الحساب كاملاً عند أي إضافة/حذف قيد يمسّ الحساب لضمان الاتساق.
"""
from app.models import db, Account, JournalEntry, JournalEntryLine, LedgerEntry


def _ordered_lines(account_id):
    """سطور الحساب مرتبة بترتيب الأثر المحاسبي (تاريخ/قيد/سطر)."""
    return (
        db.session.query(JournalEntryLine)
        .join(JournalEntry, JournalEntryLine.entry_id == JournalEntry.id)
        .filter(JournalEntryLine.account_id == account_id)
        .order_by(JournalEntry.date, JournalEntry.id, JournalEntryLine.id)
        .all()
    )


def rebuild_account(account_id):
    """حذف صفوف ledger لحساب وإعادة بنائها مع الرصيد الجاري الصحيح."""
    account = db.session.get(Account, account_id)
    if not account:
        return
    LedgerEntry.query.filter_by(account_id=account_id).delete()
    db.session.flush()

    normal = account.normal_balance
    running = float(account.opening_balance or 0)
    for line in _ordered_lines(account_id):
        debit = float(line.debit or 0)
        credit = float(line.credit or 0)
        if normal == 'debit':
            running = running + debit - credit
        else:
            running = running + credit - debit
        db.session.add(LedgerEntry(
            account_id=account_id,
            entry_id=line.entry_id,
            line_id=line.id,
            date=line.entry.date,
            debit=line.debit,
            credit=line.credit,
            running_balance=round(running, 2),
        ))
    db.session.flush()


def rebuild_all():
    """إعادة بناء دفتر الأستاذ لكل الحسابات النشطة (وغير النشطة أيضاً)."""
    for aid, in db.session.query(Account.id).all():
        rebuild_account(aid)


def sync_entry(entry):
    """إعادة بناء ledger لكل الحسابات المتأثرة بقيد (إضافة أو تعديل)."""
    account_ids = {line.account_id for line in entry.lines}
    for aid in account_ids:
        rebuild_account(aid)


def remove_entry(entry):
    """إعادة بناء ledger للحسابات المتأثرة بقيد محذوف (يُستدعى بعد الحذف)."""
    account_ids = {line.account_id for line in entry.lines}
    for aid in account_ids:
        rebuild_account(aid)


def _opening_before(account, date_from):
    """رصيد الحساب قبل نطاق التاريخ (الرصيد الافتتاحي + حركات ما قبل النطاق)."""
    if not date_from:
        return float(account.opening_balance or 0)
    last = (LedgerEntry.query
            .filter(LedgerEntry.account_id == account.id,
                    LedgerEntry.date < date_from)
            .order_by(LedgerEntry.date.desc(), LedgerEntry.entry_id.desc(),
                      LedgerEntry.id.desc()).first())
    if last:
        return float(last.running_balance or 0)
    return float(account.opening_balance or 0)


def ledger_sections(account_id=None, date_from=None, date_to=None):
    """أقسام دفتر الأستاذ (قسم لكل حساب) للطباعة/التقارير.

    يعيد قائمة: [{account, opening, closing, rows: [...]}]
    rows: [{entry_number, entry_id, date, description, debit, credit, running}]
    """
    q = LedgerEntry.query
    if account_id:
        q = q.filter(LedgerEntry.account_id == account_id)
    if date_from:
        q = q.filter(LedgerEntry.date >= date_from)
    if date_to:
        q = q.filter(LedgerEntry.date <= date_to)
    entries = q.order_by(LedgerEntry.date, LedgerEntry.entry_id,
                         LedgerEntry.id).all()

    sections = []
    current = None
    running = 0.0
    for le in entries:
        if current is None or le.account_id != current['account'].id:
            opening = _opening_before(le.account, date_from)
            current = {'account': le.account, 'opening': opening,
                       'closing': opening, 'rows': []}
            sections.append(current)
            running = opening
        debit = float(le.debit or 0)
        credit = float(le.credit or 0)
        if le.account.normal_balance == 'debit':
            running = running + debit - credit
        else:
            running = running + credit - debit
        current['rows'].append({
            'entry_number': le.entry.entry_number if le.entry else '',
            'entry_id': le.entry_id,
            'date': le.date,
            'description': le.entry.description if le.entry else '',
            'debit': debit,
            'credit': credit,
            'running': round(running, 2),
        })
        current['closing'] = round(running, 2)
    return sections
