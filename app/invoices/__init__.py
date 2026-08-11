import os
import uuid
from datetime import datetime, date

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.models import db, Client, Invoice
from app.utils import recalc_client, allowed_file, log_activity

invoices_bp = Blueprint('invoices', __name__)


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


@invoices_bp.route('/client/<int:cid>/invoice/add', methods=['POST'])
@login_required
def invoice_add(cid):
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

    img_path = None
    if 'image' in request.files:
        f = request.files['image']
        if f and f.filename and allowed_file(f.filename):
            fn = secure_filename(f.filename)
            unique_fn = f"{uuid.uuid4().hex}_{fn}"
            upload_dir = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_dir, exist_ok=True)
            f.save(os.path.join(upload_dir, unique_fn))
            img_path = unique_fn

    invoice_date = _parse_date(request.form.get('date'), date.today())

    inv = Invoice(
        client_id=cid,
        description=request.form.get('description', '').strip(),
        amount=amount,
        date=invoice_date,
        image_path=img_path,
    )
    db.session.add(inv)
    db.session.commit()
    recalc_client(cid)
    log_activity(current_user.id, 'add', 'invoice', inv.id,
                 f'فاتورة {amount:,.2f} للعميل {c.name}', request.remote_addr)
    try:
        from app.accounts.auto import post_invoice_entries
        post_invoice_entries(inv, current_user.id)
        db.session.commit()
    except Exception:
        db.session.rollback()
    return jsonify({'ok': True, 'msg': 'تم إضافة الفاتورة'})


@invoices_bp.route('/invoice/<int:iid>/delete', methods=['POST'])
@login_required
def invoice_delete(iid):
    if not current_user.can_edit:
        return jsonify({'ok': False, 'msg': 'غير مصرح'}), 403
    inv = db.session.get(Invoice, iid)
    if not inv:
        return jsonify({'ok': False, 'msg': 'الفاتورة غير موجودة'}), 404
    cid = inv.client_id
    if inv.image_path:
        try:
            os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], inv.image_path))
        except Exception:
            pass
    log_activity(current_user.id, 'delete', 'invoice', iid,
                 f'حذف فاتورة #{iid}', request.remote_addr)
    db.session.delete(inv)
    db.session.commit()
    recalc_client(cid)
    try:
        from app.accounts.auto import reverse_invoice_entries
        reverse_invoice_entries(inv, current_user.id)
        db.session.commit()
    except Exception:
        db.session.rollback()
    return jsonify({'ok': True})


@invoices_bp.route('/invoice/<int:iid>/edit', methods=['POST'])
@login_required
def invoice_edit(iid):
    if not current_user.can_edit:
        return jsonify({'ok': False, 'msg': 'غير مصرح'}), 403
    inv = db.session.get(Invoice, iid)
    if not inv:
        return jsonify({'ok': False, 'msg': 'الفاتورة غير موجودة'}), 404
    try:
        amount = float(request.form.get('amount', inv.amount))
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'msg': 'مبلغ غير صالح'}), 400
    if amount <= 0:
        return jsonify({'ok': False, 'msg': 'المبلغ يجب أن يكون أكبر من صفر'}), 400

    inv.description = request.form.get('description', inv.description or '').strip()
    inv.amount = amount
    inv.date = _parse_date(request.form.get('date'), inv.date)

    if 'image' in request.files:
        f = request.files['image']
        if f and f.filename and allowed_file(f.filename):
            if inv.image_path:
                try:
                    os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], inv.image_path))
                except Exception:
                    pass
            fn = secure_filename(f.filename)
            unique_fn = f"{uuid.uuid4().hex}_{fn}"
            upload_dir = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_dir, exist_ok=True)
            f.save(os.path.join(upload_dir, unique_fn))
            inv.image_path = unique_fn

    db.session.commit()
    recalc_client(inv.client_id)
    log_activity(current_user.id, 'edit', 'invoice', iid,
                 f'تعديل فاتورة #{iid}: {amount:,.2f}', request.remote_addr)
    try:
        from app.accounts.auto import reverse_invoice_entries, post_invoice_entries
        reverse_invoice_entries(inv, current_user.id)
        post_invoice_entries(inv, current_user.id)
        db.session.commit()
    except Exception:
        db.session.rollback()
    return jsonify({'ok': True, 'msg': 'تم تعديل الفاتورة'})
