from datetime import datetime, date, timedelta, timezone
import os
import io
import json
import threading

from flask import Blueprint, request, render_template, redirect, url_for, flash, send_file, current_app, session
from flask_login import login_required, current_user
import openpyxl
import uuid

from app.models import db, Client, Invoice, Payment, Settings, ImportCache
from app.utils import (create_pdf_report, create_period_comparison, export_excel, backup_database,
                       parse_uploaded_file, auto_detect_columns, validate_import_rows,
                       create_sample_template)

reports_bp = Blueprint('reports', __name__)


def _store_preview(preview):
    key = uuid.uuid4().hex
    ImportCache.store(key, preview)
    return key


def _get_preview(key):
    return ImportCache.get_data(key)


def _pop_preview(key):
    ImportCache.pop(key)


def _import_cache_write(key, preview):
    ImportCache.store(key, preview)


@reports_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_excel():
    if not current_user.can_edit:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('clients.index'))

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('لم يتم اختيار ملف', 'danger')
            return redirect(request.url)
        f = request.files['file']
        if not f.filename:
            flash('لم يتم اختيار ملف', 'danger')
            return redirect(request.url)
        if not f.filename.lower().endswith(('.xlsx', '.csv')):
            flash('صيغة الملف غير مدعومة - يُرجى استخدام .xlsx أو .csv', 'danger')
            return redirect(request.url)

        from app.importers.accounting_excel import detect_format, parse_accounting_excel, build_customer_preview

        fmt = detect_format(f)
        if fmt and fmt.get('type') == 'accounting':
            f.seek(0)
            parsed_acc = parse_accounting_excel(f)

            existing_codes = {c.name.strip().lower() for c in Client.query.all()}
            customer_preview = build_customer_preview(parsed_acc)
            for cp in customer_preview:
                cp['is_duplicate'] = cp['name'].lower() in existing_codes if cp['name'] else False

            preview = {
                'format': 'accounting',
                'filename': f.filename,
                'meta': parsed_acc['meta'],
                'customers': customer_preview,
                'branches': parsed_acc.get('branches', {}),
                'payment_methods': parsed_acc.get('payment_methods', {}),
                'revenue_types': parsed_acc.get('revenue_types', {}),
                'total': len(customer_preview),
                'valid_count': sum(1 for c in customer_preview if c['name']),
                'duplicate_count': sum(1 for c in customer_preview if c.get('is_duplicate')),
                'total_revenue': sum(c.get('revenue', 0) for c in customer_preview),
                'total_collected': sum(c.get('collected', 0) for c in customer_preview),
                'total_balance': sum(c.get('balance', 0) for c in customer_preview),
            }
            key = _store_preview(preview)
            session['import_key'] = key
            return redirect(url_for('reports.import_preview'))

        f.seek(0)
        parsed = parse_uploaded_file(f)
        if not parsed or not parsed['data']:
            flash('الملف فارغ أو لا يحتوي على بيانات', 'warning')
            return redirect(request.url)

        mapping = auto_detect_columns(parsed['headers'])
        validated = validate_import_rows(parsed['data'], mapping)

        existing_names = {name.strip().lower() for (name,) in Client.query.with_entities(Client.name).all()}
        for row in validated:
            row['is_duplicate'] = row['name'].lower() in existing_names if row['valid'] else False

        preview = {
            'format': 'generic',
            'headers': parsed['headers'],
            'data': [list(r) for r in parsed['data']],
            'mapping': mapping,
            'rows': validated,
            'filename': f.filename,
            'total': len(validated),
            'valid_count': sum(1 for r in validated if r['valid']),
            'error_count': sum(1 for r in validated if not r['valid']),
            'duplicate_count': sum(1 for r in validated if r.get('is_duplicate')),
        }

        key = _store_preview(preview)
        session['import_key'] = key
        return redirect(url_for('reports.import_preview'))

    return render_template('import.html', phase='upload')


@reports_bp.route('/import/preview', methods=['GET', 'POST'])
@login_required
def import_preview():
    if not current_user.can_edit:
        flash('ليس لديك صلاحية', 'danger')
        return redirect(url_for('clients.index'))

    import_key = session.get('import_key')
    preview = _get_preview(import_key) if import_key else None
    if not preview:
        flash('لم يتم العثور على بيانات الاستيراد، يُرجى رفع الملف مرة أخرى', 'warning')
        return redirect(url_for('reports.import_excel'))

    if request.method == 'POST':
        action = request.form.get('action', 'import')

        # ── Accounting format remap ──
        if action == 'remap' and preview.get('format') == 'accounting':
            return redirect(url_for('reports.import_preview'))

        # ── Generic format remap ──
        if action == 'remap' and preview.get('format') != 'accounting':
            new_mapping = {}
            for field in ('name', 'phone', 'total_debt', 'total_paid', 'notes'):
                val = request.form.get(f'map_{field}', '')
                new_mapping[field] = int(val) if val != '' else None

            raw_data = preview.get('data', [])
            new_validated = validate_import_rows(raw_data, new_mapping)

            existing_names_set = {c.name.strip().lower() for c in Client.query.all()}
            for row in new_validated:
                row['is_duplicate'] = row['name'].lower() in existing_names_set if row['valid'] else False

            preview['mapping'] = new_mapping
            preview['rows'] = new_validated
            preview['valid_count'] = sum(1 for r in new_validated if r['valid'])
            preview['error_count'] = sum(1 for r in new_validated if not r['valid'])
            preview['duplicate_count'] = sum(1 for r in new_validated if r.get('is_duplicate'))
            _import_cache_write(import_key, preview)
            return redirect(url_for('reports.import_preview'))

        # ── Accounting format import ──
        if preview.get('format') == 'accounting':
            import_mode = request.form.get('import_mode', 'new_only')
            customers = preview.get('customers', [])
            valid_customers = [c for c in customers if c.get('name')]
            if not valid_customers:
                flash('لا توجد بيانات صالحة للاستيراد', 'warning')
                return redirect(url_for('reports.import_excel'))

            imported = 0
            updated = 0
            skipped = 0

            if import_mode == 'new_only':
                for cp in valid_customers:
                    if cp.get('is_duplicate'):
                        skipped += 1
                        continue
                    c = Client(
                        name=cp['name'],
                        notes=f"كود: {cp.get('code', '')}",
                        total_debt=cp.get('revenue', 0),
                        total_paid=cp.get('collected', 0),
                        base_debt=cp.get('revenue', 0),
                        base_paid=cp.get('collected', 0),
                        status='paid' if cp.get('revenue', 0) <= cp.get('collected', 0) else 'due',
                    )
                    db.session.add(c)
                    imported += 1

            elif import_mode == 'update_existing':
                existing_map = {c.name.strip().lower(): c for c in Client.query.all()}
                for cp in valid_customers:
                    key = cp['name'].strip().lower()
                    if key in existing_map:
                        c = existing_map[key]
                        c.total_debt = cp.get('revenue', 0)
                        c.total_paid = cp.get('collected', 0)
                        c.base_debt = cp.get('revenue', 0)
                        c.base_paid = cp.get('collected', 0)
                        c.status = 'paid' if c.total_debt <= c.total_paid else 'due'
                        c.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                        updated += 1
                    else:
                        c = Client(
                            name=cp['name'],
                            notes=f"كود: {cp.get('code', '')}",
                            total_debt=cp.get('revenue', 0),
                            total_paid=cp.get('collected', 0),
                            status='paid' if cp.get('revenue', 0) <= cp.get('collected', 0) else 'due',
                        )
                        db.session.add(c)
                        imported += 1

            else:
                for cp in valid_customers:
                    c = Client(
                        name=cp['name'],
                        notes=f"كود: {cp.get('code', '')}",
                        total_debt=cp.get('revenue', 0),
                        total_paid=cp.get('collected', 0),
                        base_debt=cp.get('revenue', 0),
                        base_paid=cp.get('collected', 0),
                        status='paid' if cp.get('revenue', 0) <= cp.get('collected', 0) else 'due',
                    )
                    db.session.add(c)
                    imported += 1

            db.session.commit()
            from app.accounts.auto import create_client_account
            for cp in valid_customers:
                c = Client.query.filter_by(name=cp['name']).order_by(Client.id.desc()).first()
                if c:
                    create_client_account(c)
            db.session.commit()
            from app.utils import log_activity
            log_activity(current_user.id, 'import', 'client', None,
                         f"استيراد محاسبي: {imported} عميل، تحديث {updated}، تخطي {skipped} من ملف {preview.get('filename', '?')}")
            session.pop('import_key', None)
            _pop_preview(import_key)

            parts = []
            if imported:
                parts.append(f'تمت إضافة {imported} عميل')
            if updated:
                parts.append(f'تم تحديث {updated} عميل')
            if skipped:
                parts.append(f'تم تخطي {skipped} عميل مكرر')
            flash(' | '.join(parts) if parts else 'لا توجد بيانات جديدة', 'success')
            return redirect(url_for('clients.index'))

        # ── Generic format import ──
        import_mode = request.form.get('import_mode', 'new_only')
        valid_rows = [r for r in preview.get('rows', []) if r.get('valid')]
        if not valid_rows:
            flash('لا توجد بيانات صالحة للاستيراد', 'warning')
            return redirect(url_for('reports.import_excel'))

        imported = 0
        updated = 0
        skipped = 0

        if import_mode == 'new_only':
            for row in valid_rows:
                if row['is_duplicate']:
                    skipped += 1
                    continue
                c = Client(name=row['name'], phone=row['phone'], notes=row['notes'],
                           total_debt=row['total_debt'], total_paid=row['total_paid'],
                           base_debt=row['total_debt'], base_paid=row['total_paid'],
                           status='paid' if row['total_debt'] <= row['total_paid'] else 'due')
                db.session.add(c)
                imported += 1

        elif import_mode == 'update_existing':
            existing_map = {c.name.strip().lower(): c for c in Client.query.all()}
            for row in valid_rows:
                key = row['name'].strip().lower()
                if key in existing_map:
                    c = existing_map[key]
                    if row['phone']:
                        c.phone = row['phone']
                    if row['total_debt']:
                        c.total_debt = row['total_debt']
                        c.base_debt = row['total_debt']
                    if row['total_paid']:
                        c.total_paid = row['total_paid']
                        c.base_paid = row['total_paid']
                    if row['notes']:
                        c.notes = row['notes']
                    c.status = 'paid' if c.total_debt <= c.total_paid else 'due'
                    c.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    updated += 1
                else:
                    c = Client(name=row['name'], phone=row['phone'], notes=row['notes'],
                               total_debt=row['total_debt'], total_paid=row['total_paid'],
                               status='paid' if row['total_debt'] <= row['total_paid'] else 'due')
                    db.session.add(c)
                    imported += 1

        else:
            for row in valid_rows:
                c = Client(name=row['name'], phone=row['phone'], notes=row['notes'],
                           total_debt=row['total_debt'], total_paid=row['total_paid'],
                           base_debt=row['total_debt'], base_paid=row['total_paid'],
                           status='paid' if row['total_debt'] <= row['total_paid'] else 'due')
                db.session.add(c)
                imported += 1

        db.session.commit()
        from app.accounts.auto import create_client_account
        for row in valid_rows:
            c = Client.query.filter_by(name=row['name']).order_by(Client.id.desc()).first()
            if c:
                create_client_account(c)
        db.session.commit()
        from app.utils import log_activity
        log_activity(current_user.id, 'import', 'client', None,
                     f"استيراد {imported} عميل، تحديث {updated}، تخطي {skipped} من ملف {preview.get('filename', '?')}")
        session.pop('import_key', None)
        _pop_preview(import_key)

        parts = []
        if imported:
            parts.append(f'تمت إضافة {imported} عميل')
        if updated:
            parts.append(f'تم تحديث {updated} عميل')
        if skipped:
            parts.append(f'تم تخطي {skipped} عميل مكرر')
        flash(' | '.join(parts) if parts else 'لا توجد بيانات جديدة', 'success')
        return redirect(url_for('clients.index'))

    return render_template('import.html', phase='preview', preview=preview)


@reports_bp.route('/import/template')
@login_required
def import_template():
    wb = create_sample_template()
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    wb.close()
    return send_file(buf, as_attachment=True,
                     download_name='sample_import.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@reports_bp.route('/export')
@login_required
def export_excel_route():
    search = request.args.get('q', '')
    status = request.args.get('status', '')
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    q = Client.query
    if search:
        q = q.filter(Client.name.ilike(f'%{search}%') | Client.phone.ilike(f'%{search}%'))
    if from_date:
        try:
            fd = datetime.strptime(from_date, '%Y-%m-%d').date()
            q = q.filter(Client.created_at >= datetime.combine(fd, datetime.min.time()))
        except ValueError:
            pass
    if to_date:
        try:
            td = datetime.strptime(to_date, '%Y-%m-%d').date()
            q = q.filter(Client.created_at <= datetime.combine(td, datetime.max.time()))
        except ValueError:
            pass
    if status in ('paid', 'due'):
        q = q.filter_by(status=status)
    clients = q.order_by(Client.name).all()
    wb = export_excel(clients)

    export_path = os.path.join(current_app.config.get('BASE_DIR', os.path.dirname(current_app.instance_path)), 'exports',
                               f'export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
    os.makedirs(os.path.dirname(export_path), exist_ok=True)
    wb.save(export_path)
    return send_file(export_path, as_attachment=True,
                     download_name='debt_report.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@reports_bp.route('/export/pdf')
@login_required
def export_pdf():
    search = request.args.get('q', '')
    status = request.args.get('status', '')
    q = Client.query
    if search:
        q = q.filter(Client.name.ilike(f'%{search}%') | Client.phone.ilike(f'%{search}%'))
    if status in ('paid', 'due'):
        q = q.filter_by(status=status)
    clients = q.order_by(Client.name).all()
    pdf_buffer = create_pdf_report(clients)
    return send_file(pdf_buffer, as_attachment=True,
                     download_name=f'report_{datetime.now().strftime("%Y%m%d")}.pdf',
                     mimetype='application/pdf')


@reports_bp.route('/export/save')
@login_required
def export_save():
    from flask import jsonify
    fmt = request.args.get('fmt', 'xlsx')
    clients = Client.query.order_by(Client.name).all()
    export_dir = os.path.join(current_app.config.get('BASE_DIR', os.path.dirname(current_app.instance_path)), 'exports')
    os.makedirs(export_dir, exist_ok=True)
    if fmt == 'pdf':
        pdf_buffer = create_pdf_report(clients)
        path = os.path.join(export_dir, 'report.pdf')
        with open(path, 'wb') as f:
            f.write(pdf_buffer.getvalue())
    else:
        wb = export_excel(clients)
        path = os.path.join(export_dir, 'debt_report.xlsx')
        wb.save(path)
    return jsonify({'ok': True, 'path': os.path.abspath(path)})


@reports_bp.route('/report')
@login_required
def report():
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    
    q = Client.query
    
    if from_date:
        try:
            fd = datetime.strptime(from_date, '%Y-%m-%d').date()
            q = q.filter(Client.created_at >= datetime.combine(fd, datetime.min.time()))
        except ValueError:
            pass
    if to_date:
        try:
            td = datetime.strptime(to_date, '%Y-%m-%d').date()
            q = q.filter(Client.created_at <= datetime.combine(td, datetime.max.time()))
        except ValueError:
            pass
    
    clients = q.order_by(Client.name).all()

    total_debt = sum(c.total_debt for c in clients)
    total_paid = sum(c.total_paid for c in clients)
    total_balance = sum(c.balance for c in clients)

    return render_template('report.html', clients=clients,
                           total_debt=total_debt, total_paid=total_paid,
                           total_balance=total_balance,
                           from_date=from_date, to_date=to_date)


@reports_bp.route('/advanced-report')
@login_required
def advanced_report():
    due_clients = Client.query.filter_by(status='due').order_by(Client.total_debt.desc()).all()
    paid_clients = Client.query.filter_by(status='paid').all()
    return render_template('advanced_report.html',
                           due_clients=due_clients, paid_clients=paid_clients)


@reports_bp.route('/compare')
@login_required
def compare_report():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    first_of_last_month = (first_of_month - timedelta(days=1)).replace(day=1)

    current_clients = Client.query.filter(Client.created_at >= first_of_month).all()
    previous_clients = Client.query.filter(
        Client.created_at >= first_of_last_month,
        Client.created_at < first_of_month
    ).all()

    current_label = now.strftime('%Y-%m')
    previous_label = first_of_last_month.strftime('%Y-%m')

    pdf_buffer = create_period_comparison(current_clients, previous_clients,
                                          current_label, previous_label)
    return send_file(pdf_buffer, as_attachment=True,
                     download_name=f'comparison_{current_label}.pdf',
                     mimetype='application/pdf')


@reports_bp.route('/aging')
@login_required
def aging_report():
    date_to = request.args.get('to', '').strip() or None
    try:
        asof = date.fromisoformat(date_to) if date_to else date.today()
    except ValueError:
        asof = date.today()
    buckets = _aging_data(asof)
    total_overdue = sum(b['total'] for b in buckets.values())
    total_clients_aging = sum(len(b['clients']) for b in buckets.values())
    return render_template('aging_report.html',
                           buckets=buckets,
                           total_overdue=total_overdue,
                           total_clients_aging=total_clients_aging,
                           date_to=asof.isoformat())


@reports_bp.route('/aging/pdf')
@login_required
def aging_pdf():
    from app.utils import create_aging_pdf
    date_to = request.args.get('to', '').strip() or None
    try:
        asof = date.fromisoformat(date_to) if date_to else date.today()
    except ValueError:
        asof = date.today()
    buckets = _aging_data(asof)
    pdf_buffer = create_aging_pdf(buckets, asof)
    return send_file(pdf_buffer, as_attachment=True,
                     download_name=f'aging_{asof.isoformat()}.pdf',
                     mimetype='application/pdf')


def _aging_data(asof):
    """مصفوفة أعمار الديون حتى تاريخ معين."""
    due_clients = Client.query.filter(
        Client.status == 'due',
        (Client.total_debt - Client.total_paid) > 0
    ).all()

    buckets = {
        'current': {'label': 'حالي (أقل من 30 يوم)', 'clients': [], 'total': 0},
        '30': {'label': '30 - 60 يوم', 'clients': [], 'total': 0},
        '60': {'label': '61 - 90 يوم', 'clients': [], 'total': 0},
        '90': {'label': 'أكثر من 90 يوم', 'clients': [], 'total': 0},
    }

    client_ids = [c.id for c in due_clients]
    latest_invoices = {}
    if client_ids:
        from sqlalchemy import func
        subq = db.session.query(
            Invoice.client_id,
            func.max(Invoice.date).label('max_date')
        ).filter(Invoice.client_id.in_(client_ids)).group_by(Invoice.client_id).subquery()
        for row in db.session.query(subq).all():
            latest_invoices[row.client_id] = row.max_date

    for c in due_clients:
        max_date = latest_invoices.get(c.id)
        if max_date:
            age_days = (asof - max_date).days
        else:
            age_days = (asof - c.created_at.date()).days if c.created_at else 0
        if age_days < 0:
            age_days = 0

        balance = c.balance
        if age_days <= 30:
            buckets['current']['clients'].append((c, age_days, balance))
            buckets['current']['total'] += balance
        elif age_days <= 60:
            buckets['30']['clients'].append((c, age_days, balance))
            buckets['30']['total'] += balance
        elif age_days <= 90:
            buckets['60']['clients'].append((c, age_days, balance))
            buckets['60']['total'] += balance
        else:
            buckets['90']['clients'].append((c, age_days, balance))
            buckets['90']['total'] += balance

    for b in buckets.values():
        b['clients'].sort(key=lambda x: x[1], reverse=True)
    return buckets


@reports_bp.route('/backup')
@login_required
def manual_backup():
    if not current_user.is_admin:
        flash('غير مصرح', 'danger')
        return redirect(url_for('clients.index'))
    path = backup_database(current_app)
    if path:
        flash(f'تم إنشاء نسخة احتياطية بنجاح', 'success')
    else:
        flash('قاعدة البيانات غير موجودة', 'warning')
    return redirect(url_for('clients.index'))
