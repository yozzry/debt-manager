from datetime import datetime, date

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app.models import db, Client, Payment
from app.utils import recalc_client, log_activity

payments_bp = Blueprint('payments', __name__)


def _parse_date(value, default):
    value = (value or '').strip()
    if value:
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            pass
    if isinstance(default, date):
        return default
    return date.today()


@payments_bp.route('/client/<int:cid>/payment/add', methods=['POST'])
@login_required
def payment_add(cid):
    if not current_user.can_edit:
        return jsonify({'ok': False, 'msg': 'غير مصرح'}), 403
    c = db.session.get(Client, cid)
    if not c:
        return jsonify({'ok': False, 'msg': 'العميل غير موجود'}), 404
    try:
        amount = float(request.form.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'msg': 'مبلغ غير صالح'}), 400
    if amount <= 0:
        return jsonify({'ok': False, 'msg': 'المبلغ يجب أن يكون أكبر من صفر'}), 400

    payment_date = _parse_date(request.form.get('date'), date.today())

    p = Payment(
        client_id=cid,
        amount=amount,
        date=payment_date,
        notes=request.form.get('notes', '').strip(),
        payment_method=request.form.get('payment_method', '').strip() or None,
    )
    db.session.add(p)
    try:
        with db.session.begin_nested():
            from app.accounts.auto import post_payment_entries
            post_payment_entries(p, current_user.id)
    except Exception:
        pass
    db.session.commit()
    recalc_client(cid)
    log_activity(current_user.id, 'add', 'payment', p.id,
                 f'دفعة {amount:,.2f} للعميل {c.name}', request.remote_addr)
    return jsonify({'ok': True, 'msg': 'تم تسجيل الدفعة', 'balance': c.balance})


@payments_bp.route('/payment/<int:pid>/delete', methods=['POST'])
@login_required
def payment_delete(pid):
    if not current_user.can_edit:
        return jsonify({'ok': False, 'msg': 'غير مصرح'}), 403
    p = db.session.get(Payment, pid)
    if not p:
        return jsonify({'ok': False, 'msg': 'الدفعة غير موجودة'}), 404
    cid = p.client_id
    log_activity(current_user.id, 'delete', 'payment', pid,
                 f'حذف دفعة #{pid}', request.remote_addr)
    try:
        with db.session.begin_nested():
            from app.accounts.auto import reverse_payment_entries
            reverse_payment_entries(p, current_user.id)
    except Exception:
        pass
    db.session.delete(p)
    db.session.commit()
    recalc_client(cid)
    return jsonify({'ok': True})


@payments_bp.route('/payment/<int:pid>/edit', methods=['POST'])
@login_required
def payment_edit(pid):
    if not current_user.can_edit:
        return jsonify({'ok': False, 'msg': 'غير مصرح'}), 403
    p = db.session.get(Payment, pid)
    if not p:
        return jsonify({'ok': False, 'msg': 'الدفعة غير موجودة'}), 404
    try:
        amount = float(request.form.get('amount', p.amount))
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'msg': 'مبلغ غير صالح'}), 400
    if amount <= 0:
        return jsonify({'ok': False, 'msg': 'المبلغ يجب أن يكون أكبر من صفر'}), 400

    p.amount = amount
    p.date = _parse_date(request.form.get('date'), p.date)
    p.notes = request.form.get('notes', p.notes or '').strip()
    p.payment_method = request.form.get('payment_method', p.payment_method or '').strip() or None

    try:
        with db.session.begin_nested():
            from app.accounts.auto import reverse_payment_entries, post_payment_entries
            reverse_payment_entries(p, current_user.id)
            post_payment_entries(p, current_user.id)
    except Exception:
        pass
    db.session.commit()
    recalc_client(p.client_id)
    log_activity(current_user.id, 'edit', 'payment', pid,
                 f'تعديل دفعة #{pid}: {amount:,.2f}', request.remote_addr)
    return jsonify({'ok': True, 'msg': 'تم تعديل الدفعة'})
