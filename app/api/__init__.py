from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, abort
from flask_login import login_required, current_user

from app.models import db, Client, Invoice, Payment, ActivityLog, User
from app.utils import recalc_client, log_activity

api_bp = Blueprint('api', __name__)

from app import limiter


def require_edit():
    if not current_user.can_edit:
        return jsonify({'error': 'غير مصرح'}), 403
    return None


def _parse_date(value):
    try:
        return datetime.strptime(value or str(datetime.now().date()), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


@api_bp.route('/v1/clients', methods=['GET'])
@login_required
@limiter.limit("30/minute")
def list_clients():
    """قائمة العملاء
    ---
    tags: [العملاء]
    parameters:
      - name: page
        in: query
        type: integer
        default: 1
      - name: per_page
        in: query
        type: integer
        default: 20
      - name: q
        in: query
        type: string
        description: بحث بالاسم أو الهاتف
      - name: status
        in: query
        type: string
        enum: [paid, due]
    responses:
      200:
        description: قائمة العملاء مع pagination
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('q', '')
    status = request.args.get('status', '')

    q = Client.query
    if search:
        q = q.filter(Client.name.ilike(f'%{search}%') | Client.phone.ilike(f'%{search}%'))
    if status in ('paid', 'due'):
        q = q.filter_by(status=status)

    pagination = q.order_by(Client.updated_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)

    return jsonify({
        'clients': [c.to_dict() for c in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'pages': pagination.pages,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev,
    })


@api_bp.route('/v1/clients', methods=['POST'])
@login_required
@limiter.limit("10/minute")
def create_client():
    """إضافة عميل جديد
    ---
    tags: [العملاء]
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required: [name]
          properties:
            name:
              type: string
              description: اسم العميل
            phone:
              type: string
              description: رقم الهاتف
            notes:
              type: string
              description: ملاحظات
    responses:
      201:
        description: تم الإضافة بنجاح
      400:
        description: اسم العميل مطلوب
    """
    err = require_edit()
    if err:
        return err

    data = request.get_json(silent=True) or request.form
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'اسم العميل مطلوب'}), 400

    c = Client(
        name=name,
        phone=data.get('phone', '').strip(),
        notes=data.get('notes', '').strip(),
    )
    db.session.add(c)
    db.session.commit()
    from app.accounts.auto import create_client_account
    create_client_account(c)
    db.session.commit()
    log_activity(current_user.id, 'add', 'client', c.id, f'API: إضافة عميل {name}',
                 request.remote_addr)
    return jsonify({'client': c.to_dict(), 'message': 'تم الإضافة بنجاح'}), 201


@api_bp.route('/v1/clients/<int:cid>', methods=['GET'])
@login_required
def get_client(cid):
    """تفاصيل عميل
    ---
    tags: [العملاء]
    parameters:
      - name: cid
        in: path
        type: integer
        required: true
        description: معرّف العميل
    responses:
      200:
        description: بيانات العميل مع الفواتير والدفعات
      404:
        description: العميل غير موجود
    """
    c = db.session.get(Client, cid)
    if not c:
        abort(404)
    data = c.to_dict()
    data['invoices'] = [i.to_dict() for i in c.invoices]
    data['payments'] = [p.to_dict() for p in c.payments]
    return jsonify(data)


@api_bp.route('/v1/clients/<int:cid>', methods=['PUT'])
@login_required
def update_client(cid):
    err = require_edit()
    if err:
        return err

    c = db.session.get(Client, cid)
    if not c:
        abort(404)
    data = request.get_json(silent=True) or request.form

    if 'name' in data:
        c.name = data['name'].strip()
    if 'phone' in data:
        c.phone = data['phone'].strip()
    if 'notes' in data:
        c.notes = data['notes'].strip()
    c.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    log_activity(current_user.id, 'edit', 'client', cid, f'API: تعديل عميل {c.name}',
                 request.remote_addr)
    return jsonify({'client': c.to_dict(), 'message': 'تم التحديث بنجاح'})


@api_bp.route('/v1/clients/<int:cid>', methods=['DELETE'])
@login_required
def delete_client(cid):
    if not current_user.is_admin:
        return jsonify({'error': 'غير مصرح'}), 403
    c = db.session.get(Client, cid)
    if not c:
        abort(404)
    name = c.name
    log_activity(current_user.id, 'delete', 'client', cid, f'API: حذف عميل {name}',
                 request.remote_addr)
    db.session.delete(c)
    db.session.commit()
    return jsonify({'message': f'تم حذف العميل "{name}"'})


@api_bp.route('/v1/clients/<int:cid>/invoices', methods=['POST'])
@login_required
def add_invoice(cid):
    err = require_edit()
    if err:
        return err

    c = db.session.get(Client, cid)
    if not c:
        abort(404)
    data = request.get_json(silent=True) or request.form
    try:
        amount = float(data.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'مبلغ غير صالح'}), 400
    if amount <= 0:
        return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400

    invoice_date = _parse_date(data.get('date'))
    if invoice_date is None:
        return jsonify({'error': 'التاريخ غير صالح'}), 400

    inv = Invoice(
        client_id=cid,
        description=data.get('description', '').strip(),
        amount=amount,
        date=invoice_date,
    )
    db.session.add(inv)
    db.session.commit()
    recalc_client(cid)
    log_activity(current_user.id, 'add', 'invoice', inv.id,
                 f'API: فاتورة {amount:,.2f} للعميل {c.name}', request.remote_addr)
    return jsonify({'invoice': inv.to_dict(), 'message': 'تم إضافة الفاتورة'}), 201


@api_bp.route('/v1/invoices/<int:iid>', methods=['DELETE'])
@login_required
def delete_invoice(iid):
    err = require_edit()
    if err:
        return err
    inv = db.session.get(Invoice, iid)
    if not inv:
        abort(404)
    cid = inv.client_id
    log_activity(current_user.id, 'delete', 'invoice', iid,
                 f'API: حذف فاتورة #{iid}', request.remote_addr)
    db.session.delete(inv)
    db.session.commit()
    recalc_client(cid)
    return jsonify({'message': 'تم حذف الفاتورة'})


@api_bp.route('/v1/clients/<int:cid>/payments', methods=['POST'])
@login_required
def add_payment(cid):
    err = require_edit()
    if err:
        return err

    c = db.session.get(Client, cid)
    if not c:
        abort(404)
    data = request.get_json(silent=True) or request.form
    try:
        amount = float(data.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'مبلغ غير صالح'}), 400
    if amount <= 0:
        return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400

    payment_date = _parse_date(data.get('date'))
    if payment_date is None:
        return jsonify({'error': 'التاريخ غير صالح'}), 400

    p = Payment(
        client_id=cid,
        amount=amount,
        date=payment_date,
        notes=data.get('notes', '').strip(),
    )
    db.session.add(p)
    db.session.commit()
    recalc_client(cid)
    log_activity(current_user.id, 'add', 'payment', p.id,
                 f'API: دفعة {amount:,.2f} للعميل {c.name}', request.remote_addr)
    return jsonify({'payment': p.to_dict(), 'message': 'تم تسجيل الدفعة', 'balance': c.balance}), 201


@api_bp.route('/v1/payments/<int:pid>', methods=['DELETE'])
@login_required
def delete_payment(pid):
    err = require_edit()
    if err:
        return err
    p = db.session.get(Payment, pid)
    if not p:
        abort(404)
    cid = p.client_id
    log_activity(current_user.id, 'delete', 'payment', pid,
                 f'API: حذف دفعة #{pid}', request.remote_addr)
    db.session.delete(p)
    db.session.commit()
    recalc_client(cid)
    return jsonify({'message': 'تم حذف الدفعة'})


@api_bp.route('/v1/reports/summary', methods=['GET'])
@login_required
@limiter.limit("20/minute")
def report_summary():
    """ملخص التقارير
    ---
    tags: [التقارير]
    responses:
      200:
        description: إحصائيات عامة (عدد العملاء، إجمالي المديونية، إلخ)
    """
    total_clients = Client.query.count()
    due_clients = Client.query.filter_by(status='due').count()
    paid_clients = Client.query.filter_by(status='paid').count()
    total_debt = db.session.query(db.func.sum(Client.total_debt)).scalar() or 0
    total_paid = db.session.query(db.func.sum(Client.total_paid)).scalar() or 0
    total_balance = db.session.query(
        db.func.sum(Client.total_debt - Client.total_paid)).scalar() or 0

    return jsonify({
        'total_clients': total_clients,
        'due_clients': due_clients,
        'paid_clients': paid_clients,
        'total_debt': total_debt,
        'total_paid': total_paid,
        'total_balance': total_balance,
    })


@api_bp.route('/v1/reports/trends', methods=['GET'])
@login_required
@limiter.limit("20/minute")
def report_trends():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    months = []
    for k in range(5, -1, -1):
        total = now.year * 12 + (now.month - 1) - k
        y = total // 12
        m = total % 12 + 1
        month_start = datetime(y, m, 1)
        if k == 0:
            month_end = now
        else:
            ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
            month_end = datetime(ny, nm, 1)

        month_clients = Client.query.filter(
            Client.updated_at >= month_start,
            Client.updated_at < month_end
        ).all()

        months.append({
            'month': month_start.strftime('%Y-%m'),
            'total_debt': sum(c.total_debt for c in month_clients),
            'total_paid': sum(c.total_paid for c in month_clients),
            'count': len(month_clients),
        })

    return jsonify({'trends': months})


@api_bp.route('/v1/activity', methods=['GET'])
@login_required
def activity_log():
    if not current_user.is_admin:
        return jsonify({'error': 'غير مصرح'}), 403
    page = request.args.get('page', 1, type=int)
    pagination = ActivityLog.query.order_by(
        ActivityLog.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False)
    return jsonify({
        'activities': [a.to_dict() for a in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'pages': pagination.pages,
    })


@api_bp.route('/v1/users', methods=['GET'])
@login_required
def list_users():
    if not current_user.is_admin:
        return jsonify({'error': 'غير مصرح'}), 403
    users = User.query.all()
    return jsonify({'users': [u.to_dict() for u in users]})


@api_bp.route('/v1/reports/aging', methods=['GET'])
@login_required
def report_aging():
    from datetime import date as date_type
    from app.models import Invoice
    today = date_type.today()
    due_clients = Client.query.filter(
        Client.status == 'due',
        (Client.total_debt - Client.total_paid) > 0
    ).all()

    buckets = {'current': 0, '30': 0, '60': 0, '90': 0}
    for c in due_clients:
        latest_invoice = Invoice.query.filter_by(client_id=c.id).order_by(Invoice.date.desc()).first()
        if not latest_invoice:
            age_days = (today - c.created_at.date()).days if c.created_at else 0
        else:
            age_days = (today - latest_invoice.date).days

        balance = c.balance
        if age_days <= 30:
            buckets['current'] += balance
        elif age_days <= 60:
            buckets['30'] += balance
        elif age_days <= 90:
            buckets['60'] += balance
        else:
            buckets['90'] += balance

    return jsonify({'aging': buckets})
