import os
import re
import time
import json
import sqlite3
import tempfile
import threading
from datetime import datetime

from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user

from app.models import db, Settings, ActivityLog, _utcnow

database_bp = Blueprint('database', __name__)
_restore_lock = threading.Lock()


def _log_activity(action, details=None, entity_type='database'):
    try:
        log = ActivityLog(
            user_id=current_user.id,
            action=action,
            entity_type=entity_type,
            details=details,
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _get_db_path():
    return os.path.join(current_app.instance_path, 'debtors.db')


def _is_sqlite():
    try:
        return db.engine.dialect.name == 'sqlite'
    except Exception:
        return False


def _sqlite_only_response():
    return jsonify({'ok': False, 'msg': 'هذه الميزة متاحة فقط عند استخدام قاعدة بيانات SQLite'}), 400


def _get_backups_dir():
    return os.path.join(current_app.config['BASE_DIR'], 'backups')


def _get_exports_dir():
    return os.path.join(current_app.config['BASE_DIR'], 'exports')


def _is_valid_sqlite(path):
    if not os.path.isfile(path):
        return False
    try:
        with open(path, 'rb') as f:
            header = f.read(16)
        return header[:16] == b'SQLite format 3\x00'
    except Exception:
        return False


def _get_db_size(path):
    try:
        return os.path.getsize(path)
    except Exception:
        return 0


def _flush_wal(conn):
    try:
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    except Exception:
        pass


def _format_size(n):
    if n < 1024:
        return f'{n} B'
    elif n < 1024**2:
        return f'{n // 1024} KB'
    elif n < 1024**3:
        return f'{n / 1024**2:.1f} MB'
    return f'{n / 1024**3:.2f} GB'


def _require_admin(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user.is_admin:
            return jsonify({'ok': False, 'msg': 'غير مصرح'}), 403
        return f(*a, **kw)
    return wrapper


# ---------------------------------------------------------------------------
# Stats (standalone for settings page import)
# ---------------------------------------------------------------------------

def _get_db_stats():
    from app.models import User, Client, Invoice, Payment, ActivityLog
    db_path = _get_db_path()
    db_size = _get_db_size(db_path)
    backups_dir = _get_backups_dir()
    backups = []
    total_backup_size = 0
    if os.path.exists(backups_dir):
        for f in sorted(os.listdir(backups_dir), reverse=True):
            fpath = os.path.join(backups_dir, f)
            if os.path.isfile(fpath) and f.endswith('.db'):
                sz = os.path.getsize(fpath)
                total_backup_size += sz
                mt = os.path.getmtime(fpath)
                backups.append({
                    'name': f,
                    'size': sz,
                    'modified': mt,
                    'modified_str': datetime.fromtimestamp(mt).strftime('%Y-%m-%d %H:%M'),
                })
    return {
        'engine': db.engine.dialect.name,
        'db_size': db_size,
        'db_size_str': _format_size(db_size),
        'tables': {
            'users': User.query.count(),
            'clients': Client.query.count(),
            'invoices': Invoice.query.count(),
            'payments': Payment.query.count(),
            'activity_log': ActivityLog.query.count(),
            'settings': Settings.query.count(),
        },
        'backups': backups,
        'backups_count': len(backups),
        'backups_total_size': total_backup_size,
        'backups_dir': backups_dir,
    }


@database_bp.route('/api/database/stats')
@login_required
def db_stats():
    return jsonify({'ok': True, 'data': _get_db_stats()})


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

@database_bp.route('/api/database/backup', methods=['POST'])
@login_required
@_require_admin
def db_backup():
    if not _is_sqlite():
        return _sqlite_only_response()
    db_path = _get_db_path()
    if not _is_valid_sqlite(db_path):
        return jsonify({'ok': False, 'msg': 'قاعدة البيانات غير موجودة أو تالفة'})

    backup_dir = _get_backups_dir()
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(backup_dir, f'db_backup_{timestamp}.db')

    try:
        src_conn = sqlite3.connect(db_path, timeout=5)
        src_conn.execute('PRAGMA busy_timeout=5000')
        _flush_wal(src_conn)

        dst_conn = sqlite3.connect(dst, timeout=5)
        src_conn.backup(dst_conn, pages=1000, name='main')
        dst_conn.close()
        src_conn.close()

        current_app.logger.info(f"Backup created: {dst}")
        _log_activity('backup', f'نسخة احتياطية: db_backup_{timestamp}.db')
        return jsonify({'ok': True, 'msg': 'تم إنشاء نسخة احتياطية بنجاح', 'file': f'db_backup_{timestamp}.db'})
    except Exception as e:
        current_app.logger.error(f"Backup failed: {e}")
        return jsonify({'ok': False, 'msg': f'فشلت النسخة الاحتياطية: {e}'})


# ---------------------------------------------------------------------------
# Upload & Restore (import database file)
# ---------------------------------------------------------------------------

@database_bp.route('/api/database/import', methods=['POST'])
@login_required
@_require_admin
def db_import():
    if not _is_sqlite():
        return _sqlite_only_response()
    if 'file' not in request.files:
        return jsonify({'ok': False, 'msg': 'لم يتم رفع ملف'})

    f = request.files['file']
    if not f.filename:
        return jsonify({'ok': False, 'msg': 'اسم الملف فارغ'})

    if not f.filename.lower().endswith('.db'):
        return jsonify({'ok': False, 'msg': 'يجب أن يكون الملف .db'})

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    f.save(tmp.name)
    tmp.close()

    if not _is_valid_sqlite(tmp.name):
        os.unlink(tmp.name)
        return jsonify({'ok': False, 'msg': 'الملف ليس قاعدة بيانات SQLite صالحة'})

    if not _restore_lock.acquire(blocking=False):
        os.unlink(tmp.name)
        return jsonify({'ok': False, 'msg': 'عملية استعادة قيد التنفيذ بالفعل'})

    now = _utcnow()
    backup_timestamp = now.strftime('%Y%m%d_%H%M%S')

    try:
        backup_dir = _get_backups_dir()
        os.makedirs(backup_dir, exist_ok=True)
        auto_backup = os.path.join(backup_dir, f'pre_import_backup_{backup_timestamp}.db')

        db_path = _get_db_path()

        if _is_valid_sqlite(db_path):
            src_conn = sqlite3.connect(db_path, timeout=5)
            src_conn.execute('PRAGMA busy_timeout=5000')
            _flush_wal(src_conn)
            bak_conn = sqlite3.connect(auto_backup, timeout=5)
            src_conn.backup(bak_conn, pages=1000, name='main')
            bak_conn.close()
            src_conn.close()
            current_app.logger.info(f"Auto-backup before import: {auto_backup}")

        db.session.close_all()
        db.engine.dispose()

        dst_conn = sqlite3.connect(db_path, timeout=10)
        dst_conn.execute('PRAGMA busy_timeout=10000')
        dst_conn.execute('PRAGMA foreign_keys=OFF')

        src_conn = sqlite3.connect(tmp.name, timeout=5)
        src_conn.execute('PRAGMA busy_timeout=5000')
        _flush_wal(src_conn)

        src_conn.backup(dst_conn, pages=1000, name='main')
        dst_conn.close()
        src_conn.close()

        os.unlink(tmp.name)

        current_app.logger.info(f"Database imported from uploaded file (backup: {auto_backup})")
        _log_activity('import', f'استيراد قاعدة بيانات من ملف')
        return jsonify({
            'ok': True,
            'msg': 'تم استيراد قاعدة البيانات بنجاح',
            'auto_backup': os.path.basename(auto_backup) if os.path.exists(auto_backup) else None,
        })
    except Exception as e:
        current_app.logger.error(f"Import failed: {e}")
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        return jsonify({'ok': False, 'msg': f'فشل الاستيراد: {e}'})
    finally:
        _restore_lock.release()


# ---------------------------------------------------------------------------
# Restore from existing backup
# ---------------------------------------------------------------------------

@database_bp.route('/api/database/restore', methods=['POST'])
@login_required
@_require_admin
def db_restore():
    if not _is_sqlite():
        return _sqlite_only_response()
    if not _restore_lock.acquire(blocking=False):
        return jsonify({'ok': False, 'msg': 'عملية استعادة قيد التنفيذ بالفعل'})
    try:
        data = request.get_json(silent=True) or {}
        filename = data.get('filename', '')
        if not filename or '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'ok': False, 'msg': 'اسم الملف غير صالح'})
        if not re.match(r'^[\w\-. ]+\.db$', filename):
            return jsonify({'ok': False, 'msg': 'اسم الملف غير صالح'})
        backups_dir = _get_backups_dir()
        src = os.path.join(backups_dir, filename)
        if not _is_valid_sqlite(src):
            return jsonify({'ok': False, 'msg': 'الملف غير موجود أو ليس قاعدة بيانات صالحة'})
        db_path = _get_db_path()
        db.session.close_all()
        db.engine.dispose()
        src_conn = sqlite3.connect(src, timeout=5)
        src_conn.execute('PRAGMA busy_timeout=5000')
        _flush_wal(src_conn)
        dst_conn = sqlite3.connect(db_path, timeout=5)
        dst_conn.execute('PRAGMA busy_timeout=5000')
        dst_conn.execute('PRAGMA foreign_keys=OFF')
        src_conn.backup(dst_conn, pages=1000, name='main')
        dst_conn.close()
        src_conn.close()
        current_app.logger.info(f"Restored from backup: {filename}")
        _log_activity('restore', f'استعادة من: {filename}')
        return jsonify({'ok': True, 'msg': 'تمت الاستعادة بنجاح'})
    except Exception as e:
        current_app.logger.error(f"Restore failed: {e}")
        return jsonify({'ok': False, 'msg': f'فشلت الاستعادة: {e}'})
    finally:
        _restore_lock.release()


# ---------------------------------------------------------------------------
# Download / Delete backup
# ---------------------------------------------------------------------------

@database_bp.route('/api/database/download-backup')
@login_required
@_require_admin
def db_download_backup():
    if not _is_sqlite():
        return _sqlite_only_response()
    filename = request.args.get('file', '')
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'ok': False, 'msg': 'اسم الملف غير صالح'}), 400
    backups_dir = _get_backups_dir()
    fpath = os.path.join(backups_dir, filename)
    if not os.path.isfile(fpath):
        return jsonify({'ok': False, 'msg': 'الملف غير موجود'}), 404
    return send_file(fpath, as_attachment=True, download_name=filename)


@database_bp.route('/api/database/delete-backup', methods=['POST'])
@login_required
@_require_admin
def db_delete_backup():
    if not _is_sqlite():
        return _sqlite_only_response()
    data = request.get_json(silent=True) or {}
    filename = data.get('filename', '')
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'ok': False, 'msg': 'اسم الملف غير صالح'})
    if not re.match(r'^[\w\-. ]+\.\w+$', filename):
        return jsonify({'ok': False, 'msg': 'اسم الملف غير صالح'})
    backups_dir = _get_backups_dir()
    fpath = os.path.join(backups_dir, filename)
    if not os.path.isfile(fpath):
        return jsonify({'ok': False, 'msg': 'الملف غير موجود'})
    try:
        os.remove(fpath)
        current_app.logger.info(f"Backup deleted: {filename}")
        _log_activity('delete_backup', f'حذف نسخة احتياطية: {filename}')
        return jsonify({'ok': True, 'msg': 'تم حذف النسخة الاحتياطية'})
    except OSError as e:
        current_app.logger.error(f"Delete backup failed: {e}")
        return jsonify({'ok': False, 'msg': 'فشل حذف الملف'})


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

@database_bp.route('/api/database/reset', methods=['POST'])
@login_required
@_require_admin
def db_reset():
    from app.models import Client, Invoice, Payment, ActivityLog
    data = request.get_json(silent=True) or {}
    confirm = data.get('confirm', '')
    if confirm != 'DELETE_ALL':
        return jsonify({'ok': False, 'msg': 'تأكيد الحذف غير صحيح'})
    try:
        Payment.query.delete()
        Invoice.query.delete()
        ActivityLog.query.delete()
        Client.query.delete()
        db.session.commit()
        current_app.logger.warning(f"All data reset by user {current_user.username}")
        _log_activity('reset', 'حذف جميع بيانات العملاء والفواتير والدفعات')
        return jsonify({'ok': True, 'msg': 'تم حذف جميع البيانات بنجاح — بقيت المستخدمين والإعدادات'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Reset failed: {e}")
        return jsonify({'ok': False, 'msg': f'فشلت العملية: {e}'})


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@database_bp.route('/api/database/export-db')
@login_required
@_require_admin
def db_export():
    if not _is_sqlite():
        return _sqlite_only_response()
    db_path = _get_db_path()
    if not _is_valid_sqlite(db_path):
        return jsonify({'ok': False, 'msg': 'قاعدة البيانات غير موجودة'}), 404
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db', prefix=f'debtors_backup_{timestamp}_')
        tmp.close()
        src = sqlite3.connect(db_path, timeout=5)
        src.execute('PRAGMA busy_timeout=5000')
        _flush_wal(src)
        dst = sqlite3.connect(tmp.name, timeout=5)
        src.backup(dst, pages=1000, name='main')
        dst.close()
        src.close()
        _log_activity('export', 'تحميل قاعدة البيانات')
        tmp_path = tmp.name
        response = send_file(tmp_path, as_attachment=True,
                             download_name=f'debtors_backup_{timestamp}.db')
        return response
    except Exception as e:
        current_app.logger.error(f"Export failed: {e}")
        return jsonify({'ok': False, 'msg': 'فشل تحميل قاعدة البيانات'}), 500


@database_bp.route('/api/database/save-export', methods=['POST'])
@login_required
@_require_admin
def db_save_export():
    if not _is_sqlite():
        return _sqlite_only_response()
    db_path = _get_db_path()
    if not _is_valid_sqlite(db_path):
        return jsonify({'ok': False, 'msg': 'قاعدة البيانات غير موجودة'}), 404
    try:
        export_dir = _get_exports_dir()
        os.makedirs(export_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dest = os.path.join(export_dir, f'debtors_backup_{timestamp}.db')
        src = sqlite3.connect(db_path, timeout=5)
        src.execute('PRAGMA busy_timeout=5000')
        _flush_wal(src)
        dst = sqlite3.connect(dest, timeout=5)
        src.backup(dst, pages=1000, name='main')
        dst.close()
        src.close()
        _log_activity('save_export', f'حفظ نسخة في: {dest}')
        return jsonify({'ok': True, 'path': os.path.abspath(dest), 'file': f'debtors_backup_{timestamp}.db'})
    except Exception as e:
        current_app.logger.error(f"Save export failed: {e}")
        return jsonify({'ok': False, 'msg': 'فشل حفظ قاعدة البيانات'}), 500


# ---------------------------------------------------------------------------
# Integrity check
# ---------------------------------------------------------------------------

@database_bp.route('/api/database/integrity', methods=['GET'])
@login_required
@_require_admin
def db_integrity():
    if not _is_sqlite():
        return _sqlite_only_response()
    db_path = _get_db_path()
    if not _is_valid_sqlite(db_path):
        return jsonify({'ok': False, 'msg': 'قاعدة البيانات غير موجودة'}), 404
    try:
        results = {}
        conn = sqlite3.connect(db_path, timeout=5)

        cur = conn.execute('PRAGMA integrity_check')
        results['integrity_check'] = cur.fetchone()[0]

        cur = conn.execute('PRAGMA quick_check')
        results['quick_check'] = cur.fetchone()[0]

        cur = conn.execute('PRAGMA foreign_key_check')
        results['foreign_key_violations'] = len(cur.fetchall())

        cur = conn.execute('PRAGMA page_count')
        page_count = cur.fetchone()[0]
        cur = conn.execute('PRAGMA page_size')
        page_size = cur.fetchone()[0]
        results['page_count'] = page_count
        results['page_size'] = page_size
        results['theoretical_size'] = page_count * page_size

        cur = conn.execute('PRAGMA freelist_count')
        results['freelist_pages'] = cur.fetchone()[0]

        results['total_tables'] = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        results['total_indexes'] = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index'"
        ).fetchone()[0]

        conn.close()

        ok = results['integrity_check'] == 'ok' and results['foreign_key_violations'] == 0
        return jsonify({'ok': ok, 'data': results})
    except Exception as e:
        current_app.logger.error(f"Integrity check failed: {e}")
        return jsonify({'ok': False, 'msg': f'فشل فحص السلامة: {e}'})


# ---------------------------------------------------------------------------
# Optimize
# ---------------------------------------------------------------------------

@database_bp.route('/api/database/optimize', methods=['POST'])
@login_required
@_require_admin
def db_optimize():
    if not _is_sqlite():
        return _sqlite_only_response()
    mode = (request.get_json(silent=True) or {}).get('mode', 'vacuum')
    if mode not in ('vacuum', 'reindex', 'analyze'):
        return jsonify({'ok': False, 'msg': 'وضع غير صالح. استخدم vacuum, reindex, أو analyze'})
    db_path = _get_db_path()
    if not _is_valid_sqlite(db_path):
        return jsonify({'ok': False, 'msg': 'قاعدة البيانات غير موجودة'}), 404
    try:
        before = _get_db_size(db_path)
        conn = sqlite3.connect(db_path, timeout=30)
        conn.execute('PRAGMA busy_timeout=10000')
        if mode == 'vacuum':
            conn.execute('VACUUM')
        elif mode == 'reindex':
            conn.execute('REINDEX')
        elif mode == 'analyze':
            conn.execute('ANALYZE')
        conn.close()
        after = _get_db_size(db_path)
        current_app.logger.info(f"DB {mode}: {before} -> {after} bytes")
        _log_activity('optimize', f'{mode}: {_format_size(before)} → {_format_size(after)}')
        return jsonify({
            'ok': True,
            'msg': f'تم تحسين قاعدة البيانات ({mode})',
            'before': before,
            'after': after,
            'saved': before - after,
        })
    except Exception as e:
        current_app.logger.error(f"Optimize failed: {e}")
        return jsonify({'ok': False, 'msg': f'فشل التحسين: {e}'})
