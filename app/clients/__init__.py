from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file
from flask_login import login_required, current_user
from datetime import datetime, timezone

from app.models import db, Client, Settings
from app.utils import recalc_client, log_activity
from app.clients.forms import ClientForm, ClientSettingsForm

clients_bp = Blueprint('clients', __name__)


@clients_bp.route('/')
@login_required
def index():
    search = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    q = Client.query
    if search:
        q = q.filter(Client.name.ilike(f'%{search}%') | Client.phone.ilike(f'%{search}%'))
    if status_filter in ('paid', 'due'):
        q = q.filter_by(status=status_filter)
    q = q.order_by(Client.updated_at.desc())
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    from app.models import db as _db
    stats = {
        'total_clients': Client.query.count(),
        'due_clients': Client.query.filter_by(status='due').count(),
        'paid_clients': Client.query.filter_by(status='paid').count(),
        'total_debt': _db.session.query(_db.func.sum(Client.total_debt)).scalar() or 0,
        'total_paid': _db.session.query(_db.func.sum(Client.total_paid)).scalar() or 0,
        'total_balance': _db.session.query(
            _db.func.sum(Client.total_debt - Client.total_paid)).scalar() or 0,
    }

    from app.models import Account
    has_accounts = Account.query.count() > 0
    acct = None
    if has_accounts:
        from app.accounts import _leaf_accounts
        totals = {'asset': 0.0, 'liability': 0.0, 'equity': 0.0,
                  'income': 0.0, 'expense': 0.0}
        for a in _leaf_accounts():
            totals[a.account_type] += a.balance()
        cash_balance = sum(
            float(a.balance()) for a in Account.query.all()
            if a.is_leaf and (a.code == '1101' or a.code == '1102'
                              or a.code.startswith('11')))
        acct = {'assets': totals['asset'], 'liabilities': totals['liability'],
                'equity': totals['equity'],
                'net_income': totals['income'] - totals['expense'],
                'cash': cash_balance}
    return render_template('index.html', clients=pagination.items,
                           pagination=pagination, stats=stats,
                           acct=acct, has_accounts=has_accounts,
                           search=search, status_filter=status_filter)


@clients_bp.route('/client/add', methods=['GET', 'POST'])
@login_required
def client_add():
    if not current_user.can_edit:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('clients.index'))
    form = ClientForm()
    if request.method == 'POST' and form.validate():
        c = Client(
            name=form.name.data.strip(),
            type=form.type.data,
            company_name=(form.company_name.data or '').strip() or None,
            tax_id=(form.tax_id.data or '').strip() or None,
            phone=(form.phone.data or '').strip(),
            notes=(form.notes.data or '').strip(),
        )
        db.session.add(c)
        db.session.commit()
        from app.accounts.auto import create_client_account
        create_client_account(c)
        db.session.commit()
        log_activity(current_user.id, 'add', 'client', c.id, f'إضافة عميل: {form.name.data.strip()}',
                     request.remote_addr)
        flash(f'تم إضافة العميل "{form.name.data.strip()}" بنجاح', 'success')
        return redirect(url_for('clients.client_detail', cid=c.id))
    if request.method == 'POST':
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
    return render_template('client_edit.html', client=None, form=form)


@clients_bp.route('/client/<int:cid>')
@login_required
def client_detail(cid):
    from app.models import Invoice, Payment
    c = db.session.get(Client, cid)
    if not c:
        from flask import abort
        abort(404)
    invoices = Invoice.query.filter_by(client_id=cid).order_by(Invoice.date.desc()).all()
    payments = Payment.query.filter_by(client_id=cid).order_by(Payment.date.desc()).all()
    from datetime import date
    return render_template('client_detail.html', client=c, invoices=invoices,
                           payments=payments, today=str(date.today()))


def _client_statement_data(cid, date_from=None, date_to=None):
    """كشف حساب عميل: فواتير (مدين) + مدفوعات (دائن) برصيد جاري.

    يعيد: {rows, opening, closing, total_debt, total_paid, client}
    rows: [{kind, id, date, ref, notes, debit, credit, running}]
    """
    from app.models import Invoice, Payment
    from datetime import date as _date
    client = db.session.get(Client, cid)
    if not client:
        return None

    d_from = None
    d_to = None
    try:
        d_from = _date.fromisoformat(date_from) if date_from else None
        d_to = _date.fromisoformat(date_to) if date_to else None
    except ValueError:
        d_from = d_to = None

    def _opening():
        if not d_from:
            return 0.0
        from app.models import db as _db
        inv = (_db.session.query(_db.func.coalesce(_db.func.sum(Invoice.amount), 0))
               .filter(Invoice.client_id == cid, Invoice.date < d_from))
        pay = (_db.session.query(_db.func.coalesce(_db.func.sum(Payment.amount), 0))
               .filter(Payment.client_id == cid, Payment.date < d_from))
        return float(inv.scalar() or 0) - float(pay.scalar() or 0)

    events = []
    for inv in Invoice.query.filter_by(client_id=cid).all():
        if d_from and inv.date < d_from:
            continue
        if d_to and inv.date > d_to:
            continue
        events.append({'kind': 'invoice', 'id': inv.id, 'date': inv.date,
                       'ref': f'فاتورة #{inv.id}',
                       'notes': inv.description or '',
                       'debit': float(inv.amount or 0), 'credit': 0.0})
    for pay in Payment.query.filter_by(client_id=cid).all():
        if d_from and pay.date < d_from:
            continue
        if d_to and pay.date > d_to:
            continue
        method = pay.payment_method or ''
        events.append({'kind': 'payment', 'id': pay.id, 'date': pay.date,
                       'ref': f'دفعة #{pay.id}',
                       'notes': (pay.notes or '') + (f' ({method})' if method else ''),
                       'debit': 0.0, 'credit': float(pay.amount or 0)})

    events.sort(key=lambda e: (e['date'], e['kind'], e['id']))
    running = _opening()
    rows = []
    for e in events:
        running += e['debit'] - e['credit']
        e['running'] = round(running, 2)
        rows.append(e)
    return {'rows': rows, 'opening': round(_opening(), 2),
            'closing': round(running, 2),
            'total_debt': sum(e['debit'] for e in events),
            'total_paid': sum(e['credit'] for e in events),
            'client': client}


@clients_bp.route('/client/<int:cid>/statement')
@login_required
def client_statement(cid):
    date_from = request.args.get('from', '').strip() or None
    date_to = request.args.get('to', '').strip() or None
    data = _client_statement_data(cid, date_from, date_to)
    if not data:
        from flask import abort
        abort(404)
    return render_template('client_statement.html', data=data,
                           date_from=date_from or '', date_to=date_to or '')


@clients_bp.route('/client/<int:cid>/statement/pdf')
@login_required
def client_statement_pdf(cid):
    date_from = request.args.get('from', '').strip() or None
    date_to = request.args.get('to', '').strip() or None
    data = _client_statement_data(cid, date_from, date_to)
    if not data:
        from flask import abort
        abort(404)
    from app.utils import create_client_statement_pdf
    pdf_buffer = create_client_statement_pdf(
        data, date_from=date_from or '', date_to=date_to or '')
    return send_file(pdf_buffer, as_attachment=True,
                     download_name=f'statement_{data["client"].name}.pdf',
                     mimetype='application/pdf')


@clients_bp.route('/client/<int:cid>/edit', methods=['GET', 'POST'])
@login_required
def client_edit(cid):
    if not current_user.can_edit:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('clients.index'))
    c = db.session.get(Client, cid)
    if not c:
        from flask import abort
        abort(404)
    form = ClientForm()
    if request.method == 'POST' and form.validate():
        c.name = form.name.data.strip()
        c.type = form.type.data
        c.company_name = (form.company_name.data or '').strip() or None
        c.tax_id = (form.tax_id.data or '').strip() or None
        c.phone = (form.phone.data or '').strip()
        c.notes = (form.notes.data or '').strip()
        c.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        from app.accounts.auto import sync_client_account
        sync_client_account(c)
        db.session.commit()
        log_activity(current_user.id, 'edit', 'client', cid, f'تعديل عميل: {c.name}',
                     request.remote_addr)
        flash('تم تحديث بيانات العميل', 'success')
        return redirect(url_for('clients.client_detail', cid=cid))
    if request.method == 'POST':
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
    return render_template('client_edit.html', client=c, form=form)


@clients_bp.route('/client/<int:cid>/delete', methods=['POST'])
@login_required
def client_delete(cid):
    if not current_user.is_admin:
        flash('ليس لديك صلاحية لهذا الإجراء', 'danger')
        return redirect(url_for('clients.index'))
    c = db.session.get(Client, cid)
    if not c:
        from flask import abort
        abort(404)
    name = c.name
    from app.accounts.auto import deactivate_client_account
    deactivate_client_account(c)
    log_activity(current_user.id, 'delete', 'client', cid, f'حذف عميل: {name}',
                 request.remote_addr)
    db.session.delete(c)
    db.session.commit()
    flash(f'تم حذف العميل "{name}"', 'success')
    return redirect(url_for('clients.index'))


@clients_bp.route('/client/<int:cid>/settings', methods=['GET', 'POST'])
@login_required
def client_settings(cid):
    if not current_user.can_edit:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('clients.index'))
    c = db.session.get(Client, cid)
    if not c:
        from flask import abort
        abort(404)
    if request.method == 'POST':
        reminder_times = request.form.get('reminder_times', '').strip()
        try:
            for value in filter(None, (x.strip() for x in reminder_times.split(','))):
                datetime.strptime(value, '%H:%M')
        except ValueError:
            flash('وقت التذكير يجب أن يكون بصيغة HH:MM', 'danger')
            return redirect(url_for('clients.client_settings', cid=cid))

        frequency = request.form.get('reminder_frequency', '').strip()
        if frequency not in ('', 'daily', 'weekly', 'monthly'):
            flash('تكرار التذكير غير صالح', 'danger')
            return redirect(url_for('clients.client_settings', cid=cid))

        day = request.form.get('reminder_day', '').strip()
        if day not in ('', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'):
            flash('يوم التذكير غير صالح', 'danger')
            return redirect(url_for('clients.client_settings', cid=cid))

        dom = request.form.get('reminder_dom', '').strip()
        try:
            reminder_dom = int(dom) if dom else None
        except ValueError:
            reminder_dom = None
            flash('يوم الشهر يجب أن يكون رقمًا من 1 إلى 31', 'danger')
            return redirect(url_for('clients.client_settings', cid=cid))
        if reminder_dom is not None and not 1 <= reminder_dom <= 31:
            flash('يوم الشهر يجب أن يكون رقمًا من 1 إلى 31', 'danger')
            return redirect(url_for('clients.client_settings', cid=cid))

        c.reminder_enabled = request.form.get('reminder_enabled') == 'on'
        c.reminder_template = int(request.form.get('reminder_template', 1))
        c.reminder_times = reminder_times or None
        c.reminder_frequency = frequency or None
        c.reminder_day = day or None
        c.reminder_dom = reminder_dom
        db.session.commit()
        flash('تم حفظ إعدادات التذكير', 'success')
        return redirect(url_for('clients.client_detail', cid=cid))
    return render_template('client_settings.html', client=c)


@clients_bp.route('/api/toggle-dark', methods=['POST'])
@login_required
def toggle_dark():
    session['dark_mode'] = not session.get('dark_mode', False)
    return {'ok': True}
