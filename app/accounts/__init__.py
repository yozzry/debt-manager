from datetime import datetime, timezone

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user

from app.models import db, Account, JournalEntry, JournalEntryLine, LedgerEntry
from app.utils import log_activity
from app.accounts.forms import AccountForm, JournalEntryForm

accounts_bp = Blueprint('accounts', __name__)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _leaf_accounts():
    """الأوراق الفعلية: حسابات تفصيلية، أو حسابات تجميعية تحمل رصيداً مباشراً
    (مثل حساب العملاء 1301 عند وجود حسابات فرعية لكل عميل وقيود قديمة فيه)."""
    accounts = Account.query.order_by(Account.code).all()
    return [a for a in accounts if a.is_active and (
        a.is_leaf or abs(float(a.opening_balance or 0)) >= 0.005
        or a.lines.count() > 0)]


def _account_choices(include_ids=()):
    include = set(include_ids)
    choices = []
    for a in Account.query.order_by(Account.code).all():
        if a.id in include or (a.is_active and not a.children):
            choices.append((a.id, f'{a.code} - {a.name}'))
    return choices


def _parent_choices(exclude_ids=()):
    excluded = set(exclude_ids)
    return [(a.id, f'{a.code} - {a.name}')
            for a in Account.query.order_by(Account.code).all()
            if a.id not in excluded]


def _descendant_ids(aid):
    ids = set()
    stack = list(Account.query.filter_by(parent_id=aid).all())
    while stack:
        a = stack.pop()
        if a.id in ids:
            continue
        ids.add(a.id)
        stack.extend(Account.query.filter_by(parent_id=a.id).all())
    return ids


def _next_entry_number():
    today = _now().strftime('%Y%m%d')
    prefix = f'JV-{today}-'
    count = JournalEntry.query.filter(JournalEntry.entry_number.like(prefix + '%')).count()
    for seq in range(count + 1, count + 100):
        number = f'{prefix}{seq:03d}'
        if not JournalEntry.query.filter_by(entry_number=number).first():
            return number
    return f'{prefix}{_now().timestamp():.0f}'


def _get_entry_or_404(eid):
    entry = db.session.get(JournalEntry, eid)
    if not entry:
        from flask import abort
        abort(404)
    return entry


def _get_account_or_404(aid):
    account = db.session.get(Account, aid)
    if not account:
        from flask import abort
        abort(404)
    return account


def _build_tree(accounts):
    nodes = {a.id: {'account': a, 'children': []} for a in accounts}
    roots = []
    for a in accounts:
        node = nodes[a.id]
        if a.parent_id and a.parent_id in nodes:
            nodes[a.parent_id]['children'].append(node)
        else:
            roots.append(node)
    roots.sort(key=lambda n: n['account'].code)
    for n in nodes.values():
        n['children'].sort(key=lambda c: c['account'].code)
    return roots


def _flatten_tree(roots):
    """تحويل الشجرة إلى قائمة مسطحة (account, depth) لعرض أسهل في القالب."""
    flat = []
    def walk(nodes, depth):
        for node in nodes:
            flat.append((node['account'], depth))
            walk(node['children'], depth + 1)
    walk(roots, 0)
    return flat


def _summary():
    totals = {t: 0.0 for t in ('asset', 'liability', 'equity', 'income', 'expense')}
    for a in _leaf_accounts():
        totals[a.account_type] += a.balance()
    return totals


# ── Default accounts ──

DEFAULT_ACCOUNTS = [
    # (code, name, type, parent_code or None)
    ('1', 'الأصول', 'asset', None),
    ('11', 'نقدية وما في حكمها', 'asset', '1'),
    ('1101', 'النقدية (الخزينة)', 'asset', '11'),
    ('1102', 'البنك', 'asset', '11'),
    ('12', 'المخزون', 'asset', '1'),
    ('1201', 'بضاعة في المخزون', 'asset', '12'),
    ('13', 'ذمم مدينة', 'asset', '1'),
    ('1301', 'العملاء', 'asset', '13'),
    ('14', 'أصول ثابتة', 'asset', '1'),
    ('1401', 'الأثاث والمعدات', 'asset', '14'),
    ('2', 'الخصوم', 'liability', None),
    ('21', 'ذمم دائنة', 'liability', '2'),
    ('2101', 'الموردون', 'liability', '21'),
    ('22', 'قروض والتزامات', 'liability', '2'),
    ('2201', 'القروض', 'liability', '22'),
    ('3', 'حقوق الملكية', 'equity', None),
    ('31', 'رأس المال', 'equity', '3'),
    ('3101', 'رأس المال', 'equity', '31'),
    ('3102', 'الأرباح المحتجزة', 'equity', '31'),
    ('4', 'الإيرادات', 'income', None),
    ('41', 'إيرادات التشغيل', 'income', '4'),
    ('4101', 'المبيعات', 'income', '41'),
    ('42', 'إيرادات أخرى', 'income', '4'),
    ('4201', 'إيرادات أخرى', 'income', '42'),
    ('5', 'المصروفات', 'expense', None),
    ('51', 'تكلفة المبيعات', 'expense', '5'),
    ('5101', 'المشتريات', 'expense', '51'),
    ('52', 'مصروفات تشغيلية', 'expense', '5'),
    ('5201', 'الرواتب والأجور', 'expense', '52'),
    ('5202', 'الإيجارات', 'expense', '52'),
    ('5203', 'المصروفات العامة', 'expense', '52'),
]


def seed_default_accounts():
    if Account.query.count():
        return False
    by_code = {}
    for code, name, atype, parent_code in DEFAULT_ACCOUNTS:
        a = Account(code=code, name=name, account_type=atype,
                    parent_id=by_code[parent_code].id if parent_code else None)
        db.session.add(a)
        db.session.flush()
        by_code[code] = a
    db.session.commit()
    return True


# ── Chart of accounts ──

@accounts_bp.route('/')
@login_required
def index():
    accounts = Account.query.order_by(Account.code).all()
    tree = _build_tree(accounts)
    summary = _summary()
    counts = {t: sum(1 for a in accounts if a.account_type == t) for t in
              ('asset', 'liability', 'equity', 'income', 'expense')}
    return render_template('accounts/index.html', tree=_flatten_tree(tree),
                           summary=summary, counts=counts,
                           total_accounts=len(accounts),
                           leaf_parents=_leaf_accounts())


@accounts_bp.route('/seed', methods=['POST'])
@login_required
def seed():
    if not current_user.can_accounting:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('accounts.index'))
    if seed_default_accounts():
        log_activity(current_user.id, 'add', 'account', None,
                     'إنشاء الحسابات الافتراضية', request.remote_addr)
        flash('تم إنشاء الحسابات الافتراضية بنجاح', 'success')
    else:
        flash('توجد حسابات بالفعل — لم يتم إنشاء حسابات جديدة', 'warning')
    return redirect(url_for('accounts.index'))


@accounts_bp.route('/add', methods=['POST'])
@login_required
def account_add():
    if not (current_user.can_edit or current_user.can_accounting):
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('accounts.index'))
    form = AccountForm()
    form.parent_id.choices = _parent_choices()
    if form.validate():
        code = form.code.data.strip()
        if Account.query.filter_by(code=code).first():
            flash('يوجد حساب بنفس الرقم', 'danger')
        else:
            try:
                a = Account(
                    code=code,
                    name=form.name.data.strip(),
                    account_type=form.account_type.data,
                    parent_id=form.parent_id.data or None,
                    opening_balance=form.get_opening_balance_decimal(),
                )
                if a.parent_id and a.parent_id == a.id:
                    flash('لا يمكن أن يكون الحساب أباً لنفسه', 'danger')
                    return redirect(url_for('accounts.index'))
                db.session.add(a)
                db.session.commit()
                log_activity(current_user.id, 'add', 'account', a.id,
                             f'إضافة حساب: {a.code} {a.name}', request.remote_addr)
                flash(f'تم إضافة الحساب "{a.code} - {a.name}"', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'حدث خطأ أثناء الحفظ: {e}', 'danger')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
    return redirect(url_for('accounts.index'))


@accounts_bp.route('/account/<int:aid>/edit', methods=['GET', 'POST'])
@login_required
def account_edit(aid):
    if not (current_user.can_edit or current_user.can_accounting):
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('accounts.index'))
    a = _get_account_or_404(aid)
    form = AccountForm(obj=a)
    excluded = {aid} | _descendant_ids(aid)
    form.parent_id.choices = _parent_choices(exclude_ids=excluded)
    if request.method == 'POST' and form.validate():
        code = form.code.data.strip()
        dup = Account.query.filter(Account.code == code, Account.id != aid).first()
        if dup:
            flash('يوجد حساب آخر بنفس الرقم', 'danger')
        else:
            try:
                a.code = code
                a.name = form.name.data.strip()
                a.account_type = form.account_type.data
                a.parent_id = form.parent_id.data or None
                a.opening_balance = form.get_opening_balance_decimal()
                a.is_active = ('is_active' in request.form)
                db.session.commit()
                log_activity(current_user.id, 'edit', 'account', aid,
                             f'تعديل حساب: {a.code} {a.name}', request.remote_addr)
                flash('تم تحديث الحساب', 'success')
                return redirect(url_for('accounts.account_detail', aid=aid))
            except Exception as e:
                db.session.rollback()
                flash(f'حدث خطأ أثناء الحفظ: {e}', 'danger')
    elif request.method == 'POST':
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
    return render_template('accounts/account_form.html', account=a, form=form)


@accounts_bp.route('/account/<int:aid>/delete', methods=['POST'])
@login_required
def account_delete(aid):
    if not current_user.can_accounting:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('accounts.index'))
    a = _get_account_or_404(aid)
    if a.children:
        flash('لا يمكن حذف حساب له حسابات فرعية', 'danger')
        return redirect(url_for('accounts.account_detail', aid=aid))
    if a.lines.count():
        flash('لا يمكن حذف حساب عليه حركات محاسبية', 'danger')
        return redirect(url_for('accounts.account_detail', aid=aid))
    code_name = f'{a.code} {a.name}'
    log_activity(current_user.id, 'delete', 'account', aid,
                 f'حذف حساب: {code_name}', request.remote_addr)
    db.session.delete(a)
    db.session.commit()
    flash(f'تم حذف الحساب "{code_name}"', 'success')
    return redirect(url_for('accounts.index'))


@accounts_bp.route('/account/<int:aid>')
@login_required
def account_detail(aid):
    a = _get_account_or_404(aid)
    lines = a.lines.order_by(JournalEntryLine.id.asc()).all()
    running = float(a.opening_balance or 0)
    rows = []
    for line in lines:
        debit = float(line.debit or 0)
        credit = float(line.credit or 0)
        if a.normal_balance == 'debit':
            running = running + debit - credit
        else:
            running = running + credit - debit
        rows.append({'line': line, 'debit': debit, 'credit': credit, 'running': running})
    return render_template('accounts/account_detail.html', account=a,
                           rows=rows, opening=float(a.opening_balance or 0),
                           final_balance=a.balance())


# ── Journal entries ──

@accounts_bp.route('/entries')
@login_required
def entries():
    search = request.args.get('q', '').strip()
    date_from = request.args.get('from', '').strip()
    date_to = request.args.get('to', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    q = JournalEntry.query
    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(JournalEntry.entry_number.ilike(like),
                            JournalEntry.description.ilike(like)))
    if date_from:
        q = q.filter(JournalEntry.date >= date_from)
    if date_to:
        q = q.filter(JournalEntry.date <= date_to)

    pagination = q.order_by(JournalEntry.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    total_debits = sum(float(e.total) for e in pagination.items)
    return render_template('accounts/entries.html', entries=pagination.items,
                           pagination=pagination, total_debits=total_debits,
                           search=search, date_from=date_from, date_to=date_to)


@accounts_bp.route('/entries/add', methods=['GET', 'POST'])
@login_required
def entry_add():
    if not (current_user.can_edit or current_user.can_accounting):
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('accounts.entries'))
    form = JournalEntryForm()
    accounts = _leaf_accounts()
    if not accounts:
        flash('أضف حسابات أولاً — أو أنشئ الحسابات الافتراضية من صفحة دليل الحسابات', 'warning')
    if request.method == 'POST' and form.validate():
        lines, errors = form.get_lines_from_request(request)
        if errors:
            for e in errors:
                flash(e, 'danger')
        else:
            try:
                entry = JournalEntry(
                    entry_number=_next_entry_number(),
                    date=form.date.data,
                    description=form.description.data.strip(),
                    created_by=current_user.id,
                )
                db.session.add(entry)
                db.session.flush()
                for line in lines:
                    db.session.add(JournalEntryLine(
                        entry_id=entry.id,
                        account_id=line['account'].id,
                        debit=line['debit'],
                        credit=line['credit'],
                    ))
                db.session.commit()
                try:
                    from app.accounts.ledger import sync_entry
                    sync_entry(entry)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                log_activity(current_user.id, 'add', 'journal_entry', entry.id,
                             f'إضافة قيد: {entry.entry_number}', request.remote_addr)
                flash(f'تم حفظ القيد "{entry.entry_number}"', 'success')
                return redirect(url_for('accounts.entry_detail', eid=entry.id))
            except Exception as e:
                db.session.rollback()
                flash(f'حدث خطأ أثناء الحفظ: {e}', 'danger')
    elif request.method == 'POST':
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
    return render_template('accounts/entry_form.html', form=form, accounts=accounts)


@accounts_bp.route('/entries/<int:eid>')
@login_required
def entry_detail(eid):
    entry = _get_entry_or_404(eid)
    return render_template('accounts/entry_detail.html', entry=entry)


@accounts_bp.route('/entries/<int:eid>/delete', methods=['POST'])
@login_required
def entry_delete(eid):
    if not current_user.can_accounting:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('accounts.entries'))
    entry = _get_entry_or_404(eid)
    number = entry.entry_number
    log_activity(current_user.id, 'delete', 'journal_entry', eid,
                 f'حذف قيد: {number}', request.remote_addr)
    from app.models import LedgerEntry
    LedgerEntry.query.filter(LedgerEntry.entry_id == entry.id).delete()
    db.session.flush()
    db.session.delete(entry)
    db.session.commit()
    try:
        from app.accounts.ledger import rebuild_all
        rebuild_all()
        db.session.commit()
    except Exception:
        db.session.rollback()
    flash(f'تم حذف القيد "{number}"', 'success')
    return redirect(url_for('accounts.entries'))


@accounts_bp.route('/ledger/pdf')
@login_required
def ledger_pdf():
    """طباعة دفتر الأستاذ (كشف حساب) بصيغة PDF."""
    account_id = request.args.get('account_id', type=int) or None
    date_from = request.args.get('from', '').strip()
    date_to = request.args.get('to', '').strip()

    from app.accounts.ledger import ledger_sections
    sections = ledger_sections(account_id=account_id,
                               date_from=date_from, date_to=date_to)

    account_label = ''
    if account_id:
        account = db.session.get(Account, account_id)
        if account:
            account_label = f'{account.code} - {account.name}'

    from app.utils import create_ledger_pdf
    pdf_buffer = create_ledger_pdf(sections, account_label=account_label,
                                   date_from=date_from, date_to=date_to)
    return send_file(pdf_buffer, as_attachment=True,
                     download_name='ledger.pdf', mimetype='application/pdf')


@accounts_bp.route('/ledger')
@login_required
def ledger():
    """دفتر الأستاذ: كل حركات الحسابات مع الرصيد الجاري (كشف حساب عام)."""
    account_id = request.args.get('account_id', type=int) or None
    date_from = request.args.get('from', '').strip()
    date_to = request.args.get('to', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 50

    q = LedgerEntry.query
    if account_id:
        q = q.filter(LedgerEntry.account_id == account_id)
    if date_from:
        q = q.filter(LedgerEntry.date >= date_from)
    if date_to:
        q = q.filter(LedgerEntry.date <= date_to)

    pagination = q.order_by(LedgerEntry.date, LedgerEntry.entry_id,
                            LedgerEntry.id).paginate(page=page, per_page=per_page,
                                                     error_out=False)

    rows = []
    current_account_id = None
    running = 0.0
    for le in pagination.items:
        if le.account_id != current_account_id:
            current_account_id = le.account_id
            running = _opening_before(le.account_id, date_from)
        debit = float(le.debit or 0)
        credit = float(le.credit or 0)
        if le.account.normal_balance == 'debit':
            running = running + debit - credit
        else:
            running = running + credit - debit
        rows.append({'le': le, 'running': round(running, 2)})

    accounts = Account.query.order_by(Account.code).all()
    return render_template('accounts/ledger.html', rows=rows,
                           pagination=pagination, accounts=accounts,
                           selected_account_id=account_id,
                           date_from=date_from, date_to=date_to)


def _opening_before(account_id, date_from):
    """رصيد الحساب قبل نطاق التاريخ (الرصيد الافتتاحي + حركات ما قبل النطاق)."""
    account = db.session.get(Account, account_id)
    if not account:
        return 0.0
    if not date_from:
        return float(account.opening_balance or 0)
    last = (LedgerEntry.query
            .filter(LedgerEntry.account_id == account_id,
                    LedgerEntry.date < date_from)
            .order_by(LedgerEntry.date.desc(), LedgerEntry.entry_id.desc(),
                      LedgerEntry.id.desc()).first())
    if last:
        return float(last.running_balance or 0)
    return float(account.opening_balance or 0)


def _balance_asof(account_id, date_to):
    """رصيد الحساب حتى تاريخ معين (الرصيد الافتتاحي + حركات حتى التاريخ)."""
    last = (LedgerEntry.query
            .filter(LedgerEntry.account_id == account_id,
                    LedgerEntry.date <= date_to)
            .order_by(LedgerEntry.date.desc(), LedgerEntry.entry_id.desc(),
                      LedgerEntry.id.desc()).first())
    if last:
        return float(last.running_balance or 0)
    account = db.session.get(Account, account_id)
    return float(account.opening_balance or 0) if account else 0.0


def _period_movement(account_id, date_from, date_to):
    """صافي حركة الحساب ضمن الفترة (بالإشارة وفق طبيعة الحساب)."""
    q = LedgerEntry.query.filter(LedgerEntry.account_id == account_id)
    if date_from:
        q = q.filter(LedgerEntry.date >= date_from)
    if date_to:
        q = q.filter(LedgerEntry.date <= date_to)
    rows = q.all()
    debit = sum(float(r.debit or 0) for r in rows)
    credit = sum(float(r.credit or 0) for r in rows)
    account = db.session.get(Account, account_id)
    normal = account.normal_balance if account else 'debit'
    return debit - credit if normal == 'debit' else credit - debit


def _balance_sheet_data(date_from=None, date_to=None):
    """بيانات الميزانية العمومية (بداية/نهاية الفترة عند تمرير date_from).

    rows لكل نوع: (account, start_balance, end_balance).
    """
    from datetime import timedelta

    def _balance_map(asof):
        m = {}
        net_income = 0.0
        for a in _leaf_accounts():
            bal = _balance_asof(a.id, asof) if asof else a.balance()
            m[a.id] = bal
            if a.account_type == 'income':
                net_income += bal
            elif a.account_type == 'expense':
                net_income -= bal
        return m, net_income

    end_map, end_net = _balance_map(date_to or None)
    if date_from:
        try:
            start = (datetime.strptime(date_from, '%Y-%m-%d')
                     - timedelta(days=1)).strftime('%Y-%m-%d')
            start_map, start_net = _balance_map(start)
            has_start = True
        except ValueError:
            start_map, start_net, has_start = end_map, end_net, False
    else:
        start_map, start_net, has_start = end_map, end_net, False

    assets = []
    liabilities = []
    equity_rows = []
    for a in _leaf_accounts():
        end_bal = end_map[a.id]
        start_bal = start_map[a.id]
        if abs(end_bal) < 0.005 and abs(start_bal) < 0.005:
            continue
        row = (a, start_bal, end_bal)
        if a.account_type == 'asset':
            assets.append(row)
        elif a.account_type == 'liability':
            liabilities.append(row)
        elif a.account_type == 'equity':
            equity_rows.append(row)
    assets.sort(key=lambda r: r[0].code)
    liabilities.sort(key=lambda r: r[0].code)
    equity_rows.sort(key=lambda r: r[0].code)

    total_assets = sum(r[2] for r in assets)
    total_liab = sum(r[2] for r in liabilities)
    total_equity = sum(r[2] for r in equity_rows) + end_net
    total_assets_start = sum(r[1] for r in assets)
    total_liab_start = sum(r[1] for r in liabilities)
    total_equity_start = sum(r[1] for r in equity_rows) + start_net
    balanced = abs(total_assets - (total_liab + total_equity)) < 0.005
    balanced_start = (not has_start or
                      abs(total_assets_start - (total_liab_start + total_equity_start)) < 0.005)
    return {'assets': assets, 'liabilities': liabilities,
            'equity': equity_rows,
            'net_income': end_net, 'net_income_start': start_net,
            'total_assets': total_assets, 'total_liab': total_liab,
            'total_equity': total_equity,
            'total_assets_start': total_assets_start,
            'total_liab_start': total_liab_start,
            'total_equity_start': total_equity_start,
            'balanced': balanced, 'balanced_start': balanced_start,
            'has_start': has_start}


def _income_statement_data(date_from=None, date_to=None, compare=False):
    """بيانات قائمة الدخل مع إمكانية مقارنة الفترة السابقة (نفس الطول)."""
    from datetime import timedelta
    has_prev = False
    prev_from = prev_to = None
    if compare and date_from and date_to:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d')
            d_to = datetime.strptime(date_to, '%Y-%m-%d')
            length = (d_to - d_from).days
            if length >= 0:
                prev_to = (d_from - timedelta(days=1)).strftime('%Y-%m-%d')
                prev_from = (d_from - timedelta(days=length + 1)).strftime('%Y-%m-%d')
                has_prev = True
        except ValueError:
            has_prev = False

    income = []
    expenses = []
    for a in _leaf_accounts():
        if a.account_type not in ('income', 'expense'):
            continue
        cur = _period_movement(a.id, date_from, date_to)
        prev = _period_movement(a.id, prev_from, prev_to) if has_prev else None
        if abs(cur) < 0.005 and (prev is None or abs(prev) < 0.005):
            continue
        row = (a, cur, prev)
        if a.account_type == 'income':
            income.append(row)
        else:
            expenses.append(row)
    income.sort(key=lambda r: r[0].code)
    expenses.sort(key=lambda r: r[0].code)
    total_income = sum(r[1] for r in income)
    total_expense = sum(r[1] for r in expenses)
    total_income_prev = sum(r[2] or 0 for r in income) if has_prev else None
    total_expense_prev = sum(r[2] or 0 for r in expenses) if has_prev else None
    return {'income': income, 'expenses': expenses,
            'total_income': total_income, 'total_expense': total_expense,
            'net_income': total_income - total_expense,
            'total_income_prev': total_income_prev,
            'total_expense_prev': total_expense_prev,
            'net_income_prev': (total_income_prev - total_expense_prev)
            if has_prev else None,
            'has_prev': has_prev}


# ── القوائم المالية ──

@accounts_bp.route('/balance-sheet')
@login_required
def balance_sheet():
    date_from = request.args.get('from', '').strip() or None
    date_to = request.args.get('to', '').strip() or None
    data = _balance_sheet_data(date_from, date_to)
    return render_template('accounts/balance_sheet.html', data=data,
                           date_from=date_from or '', date_to=date_to or '')


@accounts_bp.route('/balance-sheet/pdf')
@login_required
def balance_sheet_pdf():
    date_from = request.args.get('from', '').strip() or None
    date_to = request.args.get('to', '').strip() or None
    data = _balance_sheet_data(date_from, date_to)
    subtitle = f"تاريخ التقرير: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if date_from or date_to:
        subtitle += f" — الفترة: {date_from or '...'} إلى {date_to or '...'}"
    amount_headers = (['بداية الفترة', 'نهاية الفترة'] if data['has_start']
                      else None)

    def _rows(pairs):
        if amount_headers:
            return [(a.code, a.name, [b_start, b_end])
                    for a, b_start, b_end in pairs]
        return [(a.code, a.name, b_end) for a, _, b_end in pairs]

    equity_rows = _rows(data['equity'])
    if amount_headers:
        equity_rows.append(('', 'صافي الدخل',
                            [data['net_income_start'], data['net_income']]))
    else:
        equity_rows.append(('', 'صافي الدخل', data['net_income']))
    sections = [
        ('الأصول', _rows(data['assets']),
         [data['total_assets_start'], data['total_assets']]
         if amount_headers else data['total_assets']),
        ('الخصوم', _rows(data['liabilities']),
         [data['total_liab_start'], data['total_liab']]
         if amount_headers else data['total_liab']),
        ('حقوق الملكية', equity_rows,
         [data['total_equity_start'], data['total_equity']]
         if amount_headers else data['total_equity']),
    ]
    footer = [f"إجمالي الأصول: {data['total_assets']:,.2f}",
              f"إجمالي الخصوم وحقوق الملكية: {data['total_liab'] + data['total_equity']:,.2f}"]
    if data['balanced']:
        footer.append('الميزان متوازن')
    else:
        footer.append('الميزان غير متوازن')
    from app.utils import create_statement_pdf
    pdf_buffer = create_statement_pdf('الميزانية العمومية', subtitle,
                                      sections, footer,
                                      amount_headers=amount_headers)
    return send_file(pdf_buffer, as_attachment=True,
                     download_name='balance_sheet.pdf',
                     mimetype='application/pdf')


@accounts_bp.route('/income-statement')
@login_required
def income_statement():
    date_from = request.args.get('from', '').strip() or None
    date_to = request.args.get('to', '').strip() or None
    compare = request.args.get('compare') == '1' or request.args.get('compare') == 'on'
    data = _income_statement_data(date_from, date_to, compare)
    return render_template('accounts/income_statement.html', data=data,
                           date_from=date_from or '', date_to=date_to or '',
                           compare=compare)


@accounts_bp.route('/income-statement/pdf')
@login_required
def income_statement_pdf():
    date_from = request.args.get('from', '').strip() or None
    date_to = request.args.get('to', '').strip() or None
    compare = request.args.get('compare') == '1' or request.args.get('compare') == 'on'
    data = _income_statement_data(date_from, date_to, compare)
    subtitle = f"تاريخ التقرير: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if date_from or date_to:
        subtitle += f" — الفترة: {date_from or '...'} إلى {date_to or '...'}"
    amount_headers = (['الفترة الحالية', 'الفترة السابقة']
                      if data['has_prev'] else None)

    def _rows(pairs):
        if amount_headers:
            return [(a.code, a.name, [cur, prev or 0])
                    for a, cur, prev in pairs]
        return [(a.code, a.name, cur) for a, cur, _ in pairs]

    sections = [
        ('الإيرادات', _rows(data['income']),
         [data['total_income'], data['total_income_prev']]
         if amount_headers else data['total_income']),
        ('المصروفات', _rows(data['expenses']),
         [data['total_expense'], data['total_expense_prev']]
         if amount_headers else data['total_expense']),
    ]
    if amount_headers:
        footer = [f"صافي الدخل: {data['net_income']:,.2f} "
                  f"(الفترة السابقة: {data['net_income_prev']:,.2f})"]
    else:
        footer = [f"صافي الدخل: {data['net_income']:,.2f}"]
    from app.utils import create_statement_pdf
    pdf_buffer = create_statement_pdf('قائمة الدخل', subtitle, sections, footer,
                                      amount_headers=amount_headers)
    return send_file(pdf_buffer, as_attachment=True,
                     download_name='income_statement.pdf',
                     mimetype='application/pdf')


@accounts_bp.route('/cash-flow')
@login_required
def cash_flow():
    date_from = request.args.get('from', '').strip() or None
    date_to = request.args.get('to', '').strip() or None
    data = _cash_flow_data(date_from, date_to)
    return render_template('accounts/cash_flow.html', data=data,
                           date_from=date_from or '', date_to=date_to or '')


@accounts_bp.route('/cash-flow/pdf')
@login_required
def cash_flow_pdf():
    date_from = request.args.get('from', '').strip() or None
    date_to = request.args.get('to', '').strip() or None
    data = _cash_flow_data(date_from, date_to)
    subtitle = f"تاريخ التقرير: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if date_from or date_to:
        subtitle += f" — الفترة: {date_from or '...'} إلى {date_to or '...'}"

    def _rows(rows):
        out = []
        for desc, value, _prev, note in rows:
            name = desc if not note else f'{desc} ({note})'
            out.append((None, name, value))
        return out

    def _amt(v):
        return f'{float(v):,.2f}'

    sections = [
        ('أولاً: الأنشطة التشغيلية', _rows(data['operating']),
         data['net_operating']),
        ('ثانياً: الأنشطة الاستثمارية', _rows(data['investing']),
         data['net_investing']),
        ('ثالثاً: الأنشطة التمويلية', _rows(data['financing']),
         data['net_financing']),
    ]
    footer = [f"صافي التغير في النقدية: {_amt(data['net_change'])}  |  "
              f"رصيد النقدية نهاية الفترة: {_amt(data['cash_balance'])}"]
    from app.utils import create_statement_pdf
    pdf_buffer = create_statement_pdf('بيان التدفقات النقدية', subtitle,
                                      sections, footer)
    return send_file(pdf_buffer, as_attachment=True,
                     download_name='cash_flow.pdf',
                     mimetype='application/pdf')


# ── التقرير المالي الشامل ──

def _cash_balance():
    """رصيد النقدية والبنك (1101/1102)."""
    total = 0.0
    for a in _leaf_accounts():
        if a.code in ('1101', '1102') or a.code.startswith('11'):
            total += a.balance()
    return total


@accounts_bp.route('/overview')
@login_required
def overview():
    date_from = request.args.get('from', '').strip() or None
    date_to = request.args.get('to', '').strip() or None
    compare = request.args.get('compare') == '1' or request.args.get('compare') == 'on'
    bs = _balance_sheet_data(date_from, date_to)
    is_ = _income_statement_data(date_from, date_to, compare)
    cf = _cash_flow_data(date_from, date_to)
    return render_template('accounts/overview.html', bs=bs, is_=is_, cf=cf,
                           cash_balance=_cash_balance(),
                           date_from=date_from or '', date_to=date_to or '',
                           compare=compare)


@accounts_bp.route('/overview/pdf')
@login_required
def overview_pdf():
    date_from = request.args.get('from', '').strip() or None
    date_to = request.args.get('to', '').strip() or None
    compare = request.args.get('compare') == '1' or request.args.get('compare') == 'on'
    bs = _balance_sheet_data(date_from, date_to)
    is_ = _income_statement_data(date_from, date_to, compare)
    cf = _cash_flow_data(date_from, date_to)
    subtitle = f"تاريخ التقرير: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if date_from or date_to:
        subtitle += f" — الفترة: {date_from or '...'} إلى {date_to or '...'}"

    def _bs_rows(pairs):
        return [(a.code, a.name, [start, end]) for a, start, end in pairs]

    def _is_rows(pairs):
        if is_['has_prev']:
            return [(a.code, a.name, [cur, prev or 0]) for a, cur, prev in pairs]
        return [(a.code, a.name, cur) for a, cur, _ in pairs]

    def _cf_rows(rows):
        out = []
        for desc, value, _prev, note in rows:
            name = desc if not note else f'{desc} ({note})'
            out.append((None, name, value))
        return out

    def _is_total():
        if is_['has_prev']:
            return [is_['total_income'], is_['total_income_prev']], \
                   [is_['total_expense'], is_['total_expense_prev']], \
                   [is_['net_income'], is_['net_income_prev']]
        return is_['total_income'], is_['total_expense'], is_['net_income']

    inc_total, exp_total, net_total = _is_total()

    def _net_fmt():
        if is_['has_prev']:
            return (f"صافي الدخل: {net_total[0]:,.2f} "
                    f"(الفترة السابقة: {net_total[1]:,.2f})")
        return f"صافي الدخل: {net_total:,.2f}"

    reports = [
        ('الميزانية العمومية', ['بداية', 'نهاية'], [
            ('الأصول', _bs_rows(bs['assets']),
             [bs['total_assets_start'], bs['total_assets']]),
            ('الخصوم', _bs_rows(bs['liabilities']),
             [bs['total_liab_start'], bs['total_liab']]),
            ('حقوق الملكية', _bs_rows(bs['equity']) +
             [('4101', 'صافي الدخل', [bs['net_income_start'], bs['net_income']])],
             [bs['total_equity_start'], bs['total_equity']]),
        ], [f"الميزانية {('متوازنة' if bs['balanced'] else 'غير متوازنة')}"]),
        ('قائمة الدخل', (['الفترة الحالية', 'الفترة السابقة'] if is_['has_prev']
                         else None), [
            ('الإيرادات', _is_rows(is_['income']), inc_total),
            ('المصروفات', _is_rows(is_['expenses']), exp_total),
        ], [_net_fmt()]),
        ('بيان التدفقات النقدية', None, [
            ('أولاً: الأنشطة التشغيلية', _cf_rows(cf['operating']),
             cf['net_operating']),
            ('ثانياً: الأنشطة الاستثمارية', _cf_rows(cf['investing']),
             cf['net_investing']),
            ('ثالثاً: الأنشطة التمويلية', _cf_rows(cf['financing']),
             cf['net_financing']),
        ], [f"صافي التغير: {cf['net_change']}  |  رصيد النقدية نهاية الفترة: {cf['cash_balance']}"]),
    ]
    from app.utils import create_financial_overview_pdf
    pdf_buffer = create_financial_overview_pdf('التقرير المالي الشامل',
                                               subtitle, reports)
    return send_file(pdf_buffer, as_attachment=True,
                     download_name='financial_overview.pdf',
                     mimetype='application/pdf')


# ── بيان التدفقات النقدية (الطريقة غير المباشرة) ──

_CASH_CODES = ('1101', '1102')  # نقدية + بنك


def _cash_flow_data(date_from=None, date_to=None):
    """بيانات بيان التدفقات النقدية بالطريقة غير المباشرة.

    صافي الدخل + تعديلات بنود رأس المال العامل + أنشطة استثمارية/تمويلية.
    """
    from datetime import timedelta

    def _asof_map(asof):
        m = {}
        net = 0.0
        for a in _leaf_accounts():
            bal = _balance_asof(a.id, asof) if asof else a.balance()
            m[a.code] = bal
            if a.account_type == 'income':
                net += bal
            elif a.account_type == 'expense':
                net -= bal
        return m, net

    def _opening_map():
        m = {}
        net = 0.0
        for a in _leaf_accounts():
            bal = float(a.opening_balance or 0)
            m[a.code] = bal
            if a.account_type == 'income':
                net += bal
            elif a.account_type == 'expense':
                net -= bal
        return m, net

    end_map, end_net = _asof_map(date_to or None)
    has_start = False
    if date_from:
        try:
            start = (datetime.strptime(date_from, '%Y-%m-%d')
                     - timedelta(days=1)).strftime('%Y-%m-%d')
            start_map, start_net = _asof_map(start)
            has_start = True
        except ValueError:
            start_map, start_net = _opening_map()
    else:
        start_map, start_net = _opening_map()

    def _change(code):
        return end_map.get(code, 0.0) - start_map.get(code, 0.0)

    def _find(codes):
        # إجمالي أرصدة مجموعة أكواد (أساسية/أبناء بنفس البادئة)
        total_end = total_start = 0.0
        for code, end_bal in end_map.items():
            if code.startswith(codes):
                total_end += end_bal
        for code, start_bal in start_map.items():
            if code.startswith(codes):
                total_start += start_bal
        return total_end, total_start

    # —— الأنشطة التشغيلية ——
    operating = []
    period_net = float(end_net) - float(start_net)
    operating.append(('صافي الدخل', period_net, 0.0, ''))
    ar_end, ar_start = _find('13')          # ذمم مدينة
    ar_change = ar_end - ar_start
    operating.append(('تغير الذمم المدينة (زيادة تُخصم)', -ar_change, 0.0,
                      'خصم' if ar_change > 0 else 'إضافة'))
    inv_end, inv_start = _find('12')        # المخزون
    inv_change = inv_end - inv_start
    operating.append(('تغير المخزون (زيادة تُخصم)', -inv_change, 0.0,
                      'خصم' if inv_change > 0 else 'إضافة'))
    ap_end, ap_start = _find('21')          # ذمم دائنة
    ap_change = ap_end - ap_start
    operating.append(('تغير الذمم الدائنة (زيادة تُضاف)', ap_change, 0.0,
                      'إضافة' if ap_change > 0 else 'خصم'))

    def _signed(v):
        return float(v or 0)

    net_operating = (float(period_net) - _signed(ar_change) - _signed(inv_change)
                     + _signed(ap_change))

    # —— الأنشطة الاستثمارية ——
    investing = []
    fa_end, fa_start = _find('14')          # أصول ثابتة
    fa_change = fa_end - fa_start
    investing.append(('مشتريات الأصول الثابتة', fa_change, 0.0,
                      'تجاه' if fa_change < 0 else 'زيادة'))
    net_investing = _signed(fa_change)

    # —— الأنشطة التمويلية ——
    financing = []
    loan_end, loan_start = _find('22')      # قروض
    loan_change = loan_end - loan_start
    financing.append(('القروض (صافي)', loan_change, 0.0,
                      'سداد' if loan_change < 0 else 'اقتراض'))
    cap_end, cap_start = _find('31')        # رأس المال
    cap_change = cap_end - cap_start
    financing.append(('رأس المال', cap_change, 0.0,
                      'نقص' if cap_change < 0 else 'زيادة'))
    net_financing = _signed(loan_change) + _signed(cap_change)

    net_change = net_operating + net_investing + net_financing

    # التحقق: صافي التغير = تغير النقدية والبنك
    cash_end, cash_start = _find(_CASH_CODES)
    actual_change = cash_end - cash_start
    cash_balance = cash_end
    consistent = abs(net_change - actual_change) < 0.01

    return {'operating': operating, 'investing': investing,
            'financing': financing,
            'net_operating': round(net_operating, 2),
            'net_investing': round(net_investing, 2),
            'net_financing': round(net_financing, 2),
            'net_change': round(net_change, 2),
            'actual_change': round(actual_change, 2),
            'cash_balance': round(cash_balance, 2),
            'consistent': consistent,
            'has_start': has_start}


# ── الرسوم البيانية للقوائم المالية ──

def _monthly_income_expense(months=12):
    """إيرادات/مصروفات/صافي دخل لكل شهر خلال آخر N أشهر."""
    from datetime import timedelta
    now = _now()
    first = datetime(now.year, now.month, 1)
    # بناء قائمة الأشهر من الأقدم للأحدث (يبدأ قبل months شهراً)
    start = first
    for _ in range(months - 1):
        start = (start.replace(year=start.year - 1, month=12)
                 if start.month == 1 else start.replace(month=start.month - 1))
    months_list = []
    d = start
    while d <= first:
        months_list.append(d.strftime('%Y-%m'))
        if d.month == 12:
            d = d.replace(year=d.year + 1, month=1)
        else:
            d = d.replace(month=d.month + 1)

    monthly = {m: {'income': 0.0, 'expense': 0.0} for m in months_list}
    for le in LedgerEntry.query.all():
        mkey = f'{le.date.year:04d}-{le.date.month:02d}' if le.date else None
        if mkey not in monthly:
            continue
        acc_type = le.account.account_type if le.account else ''
        debit = float(le.debit or 0)
        credit = float(le.credit or 0)
        if acc_type == 'income':
            monthly[mkey]['income'] += credit - debit
        elif acc_type == 'expense':
            monthly[mkey]['expense'] += debit - credit
    labels = []
    incomes = []
    expenses = []
    nets = []
    for m in months_list:
        labels.append(f'{m[5:7]}/{m[2:4]}')
        inc = monthly[m]['income']
        exp = monthly[m]['expense']
        incomes.append(round(inc, 2))
        expenses.append(round(exp, 2))
        nets.append(round(inc - exp, 2))
    return labels, incomes, expenses, nets


def _account_type_totals():
    """توزيع الأرصدة حسب نوع الحساب (ميزانية) مع صافي الدخل."""
    data = _balance_sheet_data()
    total = data['total_assets'] + data['total_liab'] + data['total_equity']
    if abs(total) < 0.005:
        return None
    return {
        'assets': data['total_assets'],
        'liabilities': data['total_liab'],
        'equity': data['total_equity'],
    }


@accounts_bp.route('/analytics')
@login_required
def analytics():
    labels, incomes, expenses, nets = _monthly_income_expense()
    type_totals = _account_type_totals()
    # أكبر الحسابات إيراداً ومصروفاً (كل الفترات)
    leafs = _leaf_accounts()
    income_top = sorted(
        ((a, a.balance()) for a in leafs if a.account_type == 'income'),
        key=lambda x: x[1], reverse=True)[:8]
    expense_top = sorted(
        ((a, a.balance()) for a in leafs if a.account_type == 'expense'),
        key=lambda x: x[1], reverse=True)[:8]
    return render_template('accounts/analytics.html',
                           labels=labels, incomes=incomes,
                           expenses=expenses, nets=nets,
                           type_totals=type_totals,
                           income_top=income_top, expense_top=expense_top)


@accounts_bp.route('/trial-balance')
@login_required
def trial_balance():
    date_to = request.args.get('to', '').strip() or None
    rows = []
    for a in _leaf_accounts():
        bal = _balance_asof(a.id, date_to) if date_to else a.balance()
        if abs(bal) < 0.005:
            continue
        if a.normal_balance == 'debit':
            rows.append({'account': a, 'debit': bal, 'credit': 0.0})
        else:
            rows.append({'account': a, 'debit': 0.0, 'credit': bal})
    rows.sort(key=lambda r: r['account'].code)
    total_debit = sum(r['debit'] for r in rows)
    total_credit = sum(r['credit'] for r in rows)
    balanced = abs(total_debit - total_credit) < 0.005
    return render_template('accounts/trial_balance.html', rows=rows,
                           total_debit=total_debit, total_credit=total_credit,
                           balanced=balanced, date_to=date_to or '')


@accounts_bp.route('/trial-balance/pdf')
@login_required
def trial_balance_pdf():
    from app.utils import create_statement_pdf
    date_to = request.args.get('to', '').strip() or None
    rows = []
    for a in _leaf_accounts():
        bal = _balance_asof(a.id, date_to) if date_to else a.balance()
        if abs(bal) < 0.005:
            continue
        if a.normal_balance == 'debit':
            rows.append((a.code, a.name, (bal, 0.0)))
        else:
            rows.append((a.code, a.name, (0.0, bal)))
    rows.sort(key=lambda r: r[0])
    total_debit = sum(r[2][0] for r in rows)
    total_credit = sum(r[2][1] for r in rows)
    subtitle = f'كما في {date_to}' if date_to else 'جميع الفترات'
    pdf_buffer = create_statement_pdf(
        'ميزان المراجعة', subtitle,
        [('الأرصدة', rows, (total_debit, total_credit))],
        amount_headers=['رصيد مدين', 'رصيد دائن'])
    return send_file(pdf_buffer, as_attachment=True,
                     download_name='trial_balance.pdf',
                     mimetype='application/pdf')


# ── الإقفال السنوي ──

@accounts_bp.route('/close-period', methods=['GET', 'POST'])
@login_required
def close_period():
    if not (current_user.can_edit or current_user.can_accounting):
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('accounts.index'))
    from app.accounts.auto import preview_close, close_period as _do_close, \
        is_closed, delete_closing
    date_str = request.args.get('date', '') or request.form.get('date', '')
    if request.method == 'POST':
        try:
            close_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            close_date = None
        entry = _do_close(close_date, current_user.id)
        if entry:
            flash(f'تم تنفيذ الإقفال السنوي بنجاح (قيد رقم {entry.entry_number})', 'success')
        else:
            if close_date and is_closed(close_date):
                flash('هذا التاريخ مُقفل مسبقاً', 'warning')
            else:
                flash('لا توجد إيرادات أو مصروفات لإقفالها', 'warning')
        return redirect(url_for('accounts.close_period', date=date_str))
    preview = preview_close()
    closed_date = date_str if is_closed(
        datetime.strptime(date_str, '%Y-%m-%d').date()
        if date_str else None) else None
    return render_template('accounts/close_period.html', preview=preview,
                           date_str=date_str, closed_date=closed_date)


@accounts_bp.route('/close-period/reverse', methods=['POST'])
@login_required
def close_period_reverse():
    if not (current_user.can_edit or current_user.can_accounting):
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('accounts.index'))
    date_str = request.form.get('date', '')
    from app.accounts.auto import delete_closing
    try:
        close_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        close_date = None
    if close_date and delete_closing(close_date, current_user.id):
        flash('تم عكس الإقفال السنوي — أعيدت أرصدة الإيرادات والمصروفات', 'success')
    else:
        flash('لا يوجد إقفال لعكسه في هذا التاريخ', 'warning')
    return redirect(url_for('accounts.close_period', date=date_str))
