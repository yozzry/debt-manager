import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

from flask import Flask, send_from_directory, jsonify, session
from flask_login import LoginManager, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler
from flasgger import Swagger

from app.models import db, User, Settings
from werkzeug.exceptions import HTTPException

login_manager = LoginManager()
csrf = CSRFProtect()
compress = Compress()
limiter = Limiter(get_remote_address)
scheduler = BackgroundScheduler()


def create_app(testing=False):
    if getattr(sys, 'frozen', False):
        DATA_DIR = sys._MEIPASS
        BASE_DIR = os.path.dirname(sys.executable)
    else:
        DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        BASE_DIR = DATA_DIR

    app = Flask(__name__,
                template_folder=os.path.join(DATA_DIR, 'templates'),
                static_folder=os.path.join(DATA_DIR, 'static'))
    app.url_map.strict_slashes = False

    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key or secret_key == 'dev-secret-key-change-in-prod':
        secret_file = os.path.join(BASE_DIR, 'instance', '.secret_key')
        if os.path.isfile(secret_file):
            with open(secret_file, 'r') as f:
                secret_key = f.read().strip()
        if not secret_key:
            import secrets
            secret_key = secrets.token_urlsafe(32)
            os.makedirs(os.path.dirname(secret_file), exist_ok=True)
            with open(secret_file, 'w') as f:
                f.write(secret_key)
            app.logger.warning("SECRET_KEY generated and saved to instance/.secret_key")
    app.config['SECRET_KEY'] = secret_key
    if testing:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    else:
        db_url = os.environ.get('DATABASE_URL')
        if db_url:
            app.config['SQLALCHEMY_DATABASE_URI'] = db_url
        else:
            app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'debtors.db')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600
    app.config['BASE_DIR'] = BASE_DIR

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'يجب تسجيل الدخول للوصول لهذه الصفحة'
    login_manager.login_message_category = 'warning'
    compress.init_app(app)
    if os.environ.get('RATELIMIT_ENABLED', 'true').lower() == 'false':
        app.config['RATELIMIT_ENABLED'] = False
    limiter.init_app(app)

    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": "apispec",
                "route": "/apidocs/spec.json",
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/apidocs/static",
        "swagger_ui": True,
        "specs_route": "/apidocs/",
    }
    Swagger(app, config=swagger_config, template={
        "info": {
            "title": "نظام إدارة المديونيات — API",
            "description": "API endpoints لإدارة العملاء والفواتير والدفعات",
            "version": "1.2.0",
        }
    })

    os.makedirs(os.path.join(BASE_DIR, 'logs'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'exports'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'backups'), exist_ok=True)

    handler = RotatingFileHandler(
        os.path.join(BASE_DIR, 'logs', 'app.log'),
        maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    @app.context_processor
    def inject_globals():
        from app.utils import get_app_settings
        return {'now': datetime.now(timezone.utc).replace(tzinfo=None),
                'app_settings': get_app_settings(),
                'app_mode': session.get('app_mode', 'debt')}

    @app.route('/uploads/<filename>')
    @login_required
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    from app.auth import auth_bp
    from app.clients import clients_bp
    from app.invoices import invoices_bp
    from app.payments import payments_bp
    from app.whatsapp import whatsapp_bp
    from app.reports import reports_bp
    from app.api import api_bp
    from app.database import database_bp
    from app.products import products_bp
    from app.purchases import purchases_bp
    from app.pos import pos_bp
    from app.accounts import accounts_bp
    from app.dashboard import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(invoices_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(whatsapp_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(database_bp)
    app.register_blueprint(products_bp, url_prefix='/products')
    app.register_blueprint(purchases_bp, url_prefix='/purchases')
    app.register_blueprint(pos_bp, url_prefix='/pos')
    app.register_blueprint(accounts_bp, url_prefix='/accounts')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')

    def _api_error_response(code, msg):
        from flask import request as _req, jsonify as _jsonify
        if _req.path.startswith('/api/'):
            return _jsonify({'ok': False, 'msg': msg}), code

    def _error_page(code, msg, detail=''):
        from flask import render_template, make_response
        return make_response(render_template('errors/base.html', code=code, msg=msg, detail=detail), code)

    @app.errorhandler(400)
    def bad_request(e):
        resp = _api_error_response(400, str(e) or 'Bad Request')
        if resp: return resp
        return _error_page(400, 'طلب غير صالح', str(e))

    @app.errorhandler(403)
    def forbidden(e):
        resp = _api_error_response(403, str(e) or 'غير مصرح')
        if resp: return resp
        return _error_page(403, 'غير مصرح', 'ليس لديك صلاحية للوصول لهذه الصفحة')

    @app.errorhandler(404)
    def not_found(e):
        resp = _api_error_response(404, 'الرابط غير موجود')
        if resp: return resp
        return _error_page(404, 'الصفحة غير موجودة', 'الصفحة التي تبحث عنها غير موجودة أو تم نقلها.')

    @app.errorhandler(405)
    def method_not_allowed(e):
        resp = _api_error_response(405, 'طريقة الطلب غير صحيحة')
        if resp: return resp
        return _error_page(405, 'طريقة الطلب غير صحيحة', str(e))

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        resp = _api_error_response(500, 'خطأ داخلي في الخادم')
        if resp: return resp
        return _error_page(500, 'خطأ داخلي في الخادم', 'حدث خطأ غير متوقع. يُرجى المحاولة مرة أخرى.')

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self' ws:; frame-ancestors 'self'"
        if not response.headers.get('Set-Cookie', '').startswith('csrf_token='):
            from flask_wtf.csrf import generate_csrf
            try:
                token = generate_csrf()
                response.set_cookie('csrf_token', token, httponly=False, samesite='Lax')
            except Exception:
                pass
        return response

    with app.app_context():
        db.create_all()
        _apply_schema_migrations(db)
        if not testing:
            _ensure_default_admin()
            _init_scheduler(app)
            if db.engine.dialect.name == 'sqlite':
                _enable_sqlite_wal(app)

    return app


def _apply_schema_migrations(db):
    """ترقيات خفيفة للقاعدة: إضافة الأعمدة الجديدة للجداول القائمة."""
    inspector = db.inspect(db.engine)
    if 'clients' in inspector.get_table_names():
        columns = {c['name'] for c in inspector.get_columns('clients')}
        if 'account_id' not in columns:
            db.session.execute(
                db.text('ALTER TABLE clients ADD COLUMN account_id INTEGER '
                        'REFERENCES accounts(id)'))
            db.session.commit()


def _ensure_default_admin():
    if not User.query.first():
        admin = User(username='admin', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()


def _enable_sqlite_wal(app):
    from sqlalchemy import event as _sa_event
    from sqlalchemy.engine import Engine as _Engine

    if db.engine.dialect.name != 'sqlite':
        return

    @_sa_event.listens_for(_Engine, 'connect')
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA busy_timeout=5000')
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()


def _init_scheduler(app):
    if scheduler.running:
        scheduler.shutdown(wait=False)
    scheduler.remove_all_jobs()
    from app.utils import get_app_settings
    tz = get_app_settings()['timezone']
    scheduler.configure(timezone=tz)
    if Settings.get('reminder_enabled', 'false') == 'true':
        global_times_str = Settings.get('reminder_times', '10:00')
        global_freq = Settings.get('reminder_frequency', 'daily')
        global_day = Settings.get('reminder_day', 'sun')
        global_dom = int(Settings.get('reminder_dom', '1'))

        from app.models import Client
        clients = Client.query.filter_by(reminder_enabled=True).filter(
            db.or_(Client.reminder_times.isnot(None),
                   Client.reminder_frequency.isnot(None))
        ).all()

        schedules = []
        seen = set()
        for t in [x.strip() for x in global_times_str.split(',') if x.strip()]:
            key = (t, global_freq, global_day, global_dom)
            if key not in seen:
                seen.add(key)
                schedules.append(key)

        for c in clients:
            times_str = c.reminder_times or global_times_str
            freq = c.reminder_frequency or global_freq
            day = c.reminder_day or global_day
            dom = c.reminder_dom if c.reminder_dom is not None else global_dom
            for t in [x.strip() for x in times_str.split(',') if x.strip()]:
                key = (t, freq, day, str(dom))
                if key not in seen:
                    seen.add(key)
                    schedules.append(key)

        from apscheduler.triggers.cron import CronTrigger
        from app.utils import send_scheduled_reminders

        for t, freq, day, dom in schedules:
            try:
                h, m = t.split(':')
                if freq == 'daily':
                    trigger = CronTrigger(hour=int(h), minute=int(m))
                elif freq == 'weekly':
                    trigger = CronTrigger(day_of_week=day, hour=int(h), minute=int(m))
                elif freq == 'monthly':
                    trigger = CronTrigger(day=int(dom), hour=int(h), minute=int(m))
                else:
                    trigger = CronTrigger(hour=int(h), minute=int(m))
                scheduler.add_job(send_scheduled_reminders, trigger,
                                  args=[app, t, freq, day, dom],
                                  id=f'rem_{t}_{freq}_{day}_{dom}',
                                  replace_existing=True, misfire_grace_time=3600)
            except Exception as e:
                app.logger.error(f"Scheduler error for time {t}, freq {freq}: {e}")

    from app.utils import backup_database, cleanup_old_uploads
    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(backup_database, CronTrigger(hour=3, minute=0),
                      args=[app], id='daily_backup',
                      replace_existing=True, misfire_grace_time=3600)

    scheduler.add_job(cleanup_old_uploads, CronTrigger(hour=0, minute=0),
                      args=[app], id='cleanup_uploads',
                      replace_existing=True, misfire_grace_time=3600)

    if not scheduler.running:
        scheduler.start()
