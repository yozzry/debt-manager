from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
import requests as http_requests
import os
import subprocess

from app.models import Client, Settings
from app.utils import build_reminder_message, send_whatsapp, get_whatsapp_settings, get_app_settings

whatsapp_bp = Blueprint('whatsapp', __name__)


@whatsapp_bp.route('/api/whatsapp/send-reminder/<int:cid>', methods=['POST'])
@login_required
def send_reminder_now(cid):
    if not current_user.can_edit:
        return jsonify({'ok': False, 'msg': 'غير مصرح'}), 403
    from app.models import db
    c = db.session.get(Client, cid)
    if not c:
        return jsonify({'ok': False, 'msg': 'العميل غير موجود'}), 404
    if not c.phone:
        return jsonify({'ok': False, 'msg': 'لا يوجد رقم هاتف للعميل'})
    msg = build_reminder_message(c, c.reminder_template or 1)
    ok, resp = send_whatsapp(c.phone, msg)
    if not ok:
        if 'Baileys' in resp or 'baileys' in resp or '3001' in resp:
            return jsonify({'ok': False, 'msg': f'{resp} — شغّل الخدمة من صفحة الإعدادات أولاً'})
    return jsonify({'ok': ok, 'msg': resp})


@whatsapp_bp.route('/api/whatsapp/status')
@login_required
def whatsapp_status():
    ws = get_whatsapp_settings()
    try:
        r = http_requests.get(f"{ws['baileys_url']}/status", timeout=5)
        data = r.json()
        status_str = data.get('status', 'disconnected')
        return jsonify({
            'connected': status_str == 'connected',
            'qr_available': status_str == 'qr' and bool(data.get('qr')),
            'qr': data.get('qr'),
            'status': status_str,
            'error': data.get('error'),
        })
    except http_requests.ConnectionError:
        return jsonify({'connected': False, 'qr_available': False,
                        'status': 'offline', 'error': 'خدمة Baileys غير شغالة — شغّلها من صفحة الإعدادات'})
    except http_requests.Timeout:
        return jsonify({'connected': False, 'qr_available': False,
                        'status': 'offline', 'error': 'Baileys لا يستجيب — تحقق من المنفذ 3001'})
    except Exception as e:
        return jsonify({'connected': False, 'qr_available': False,
                        'status': 'disconnected', 'error': str(e)})


@whatsapp_bp.route('/api/baileys/logout', methods=['POST'])
@login_required
def baileys_logout():
    if not current_user.can_edit:
        return jsonify({'ok': False}), 403
    ws = get_whatsapp_settings()
    try:
        r = http_requests.post(f"{ws['baileys_url']}/logout", timeout=10)
        data = r.json()
        return jsonify({'ok': data.get('success', False)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@whatsapp_bp.route('/api/baileys/start', methods=['POST'])
@login_required
def baileys_start():
    if not current_user.is_admin:
        return jsonify({'ok': False, 'msg': 'غير مصرح'}), 403
    from flask import current_app

    baileys_dir = os.path.join(current_app.config.get('BASE_DIR', os.path.dirname(current_app.instance_path)), 'baileys_service')
    index_js = os.path.join(baileys_dir, 'index.js')
    if not os.path.isfile(index_js):
        return jsonify({'ok': False, 'msg': 'ملف index.js غير موجود في baileys_service'})

    from app.utils import ensure_baileys_ready, start_baileys_bridge
    ok, msg = ensure_baileys_ready(baileys_dir)
    if not ok:
        return jsonify({'ok': False, 'msg': msg})
    ok2, msg2 = start_baileys_bridge(baileys_dir)
    return jsonify({'ok': ok2, 'msg': msg2})


@whatsapp_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    from flask import request, render_template, redirect, url_for, flash, current_app as _app
    from app.models import db
    from app.utils import COUNTRY_OPTIONS
    from app.database import _get_db_stats

    if not current_user.is_admin:
        flash('يجب أن تكون مسؤولاً للوصول للإعدادات', 'danger')
        return redirect(url_for('clients.index'))

    if request.method == 'POST':
        tab = request.form.get('tab', 'general')

        if tab == 'general':
            country = request.form.get('app_country', 'EG')
            Settings.set('app_country', country)
            info = COUNTRY_OPTIONS.get(country, COUNTRY_OPTIONS['EG'])
            Settings.set('app_timezone', request.form.get('app_timezone', info['timezone']))
            Settings.set('app_currency', request.form.get('app_currency', info['currency']))
            Settings.set('app_currency_short', request.form.get('app_currency_short', info['currency_short']))
            Settings.set('company_name', request.form.get('company_name', '').strip())
            Settings.set('login_locked', 'true' if request.form.get('login_locked') else 'false')
            Settings.set('pos_printer_name', request.form.get('pos_printer_name', '').strip())
            Settings.set('auto_accounting_enabled',
                         'true' if request.form.get('auto_accounting_enabled') else 'false',
                         value_type='bool')

        elif tab == 'whatsapp':
            Settings.set('baileys_url', request.form.get('baileys_url', 'http://localhost:3001'))

        elif tab == 'reminder':
            Settings.set('reminder_enabled', 'true' if request.form.get('reminder_enabled') else 'false')
            Settings.set('reminder_times', request.form.get('reminder_times', '10:00'))
            Settings.set('reminder_frequency', request.form.get('reminder_frequency', 'daily'))
            Settings.set('reminder_day', request.form.get('reminder_day', 'sun'))
            Settings.set('reminder_dom', request.form.get('reminder_dom', '1'))
            Settings.set('payment_link', request.form.get('payment_link', ''))
            from app import _init_scheduler
            _init_scheduler(_app._get_current_object())

        elif tab == 'templates':
            Settings.set('template_1', request.form.get('template_1', ''))
            Settings.set('template_2', request.form.get('template_2', ''))
            Settings.set('template_3', request.form.get('template_3', ''))

        flash('تم حفظ الإعدادات بنجاح', 'success')
        return redirect(url_for('whatsapp.settings') + f'?tab={tab}')

    ws = get_whatsapp_settings()
    app_s = get_app_settings()
    active_tab = request.args.get('tab', 'general')
    cur = app_s['currency_short']
    db_stats = _get_db_stats() if active_tab == 'database' else None
    return render_template('settings.html',
                           ws=ws,
                           app_settings=app_s,
                           active_tab=active_tab,
                           db_stats=db_stats,
                           login_locked=Settings.get('login_locked', 'false'),
                           reminder_enabled=Settings.get('reminder_enabled', 'false'),
                           reminder_times=Settings.get('reminder_times', '10:00'),
                           reminder_frequency=Settings.get('reminder_frequency', 'daily'),
                           reminder_day=Settings.get('reminder_day', 'sun'),
                           reminder_dom=Settings.get('reminder_dom', '1'),
                           payment_link=Settings.get('payment_link', ''),
                           pos_printer_name=Settings.get('pos_printer_name', ''),
                           auto_accounting_enabled=Settings.get('auto_accounting_enabled', False),
                           template_1=Settings.get('template_1', f'السلام عليكم {{name}}، تذكير بأن لديك رصيد مستحق بقيمة {{balance}} {cur}.'),
                           template_2=Settings.get('template_2', f'عزيزي/عزيزتي {{name}}، يُرجى العلم بأن مديونيتك المستحقة بلغت {{balance}} {cur}.'),
                           template_3=Settings.get('template_3', f'{{name}}، رصيدك المستحق: {{balance}} {cur}.'),
                           )
