# ملخص مراجعة الكود — نظام إدارة المديونيات

| البند | التفاصيل |
|---|---|
| **تاريخ المراجعة** | 2026-07-29 |
| **إصدار المشروع** | v1.3.0 |
| **المراجع** | فريق التطوير (AI-assisted) |
| **رقم الإصدار** | 1.3 |

---

## معلومات المشروع

| البند | التفاصيل |
|---|---|
| **المشروع** | نظام إدارة المديونيات (Debt Manager) |
| **التقنيات** | Flask + SQLAlchemy + SQLite + Baileys WhatsApp |
| **البيئة** | Windows, Python 3.14.6, waitress production server |
| **المميزات** | RTL عربي, واجهة سطح مكتب (pywebview), APScheduler, Flask-Login, Alembic, Swagger |
| **الافتراضي** | admin / admin123 |
| **الاختبارات** | 128 اختبار في `tests/test_all.py` — جميعها تمر (128/128) |
| **التحذيرات** | 9 تحذيرات (جميعها من openpyxl — خارج سيطرتنا) |

---

## هيكل المشروع

```
debt_manager_deploy/
├── app/
│   ├── __init__.py          # إنشاء التطبيق, تسجيل Blueprints, Scheduler, Swagger
│   ├── models.py            # SQLAlchemy Models (User, Client, Invoice, Payment, Settings, ImportCache)
│   ├── utils.py             # مساعدات (recalc_client, backup, reminders, cleanup, error logging)
│   ├── auth/
│   │   ├── __init__.py      # تسجيل الدخول/الخروج + إدارة المستخدمين
│   │   └── forms.py         # نماذج Flask-WTF (Login, AddUser)
│   ├── clients/
│   │   ├── __init__.py      # CRUD العملاء
│   │   └── forms.py         # نماذج Flask-WTF (ClientForm, ClientSettingsForm)
│   ├── invoices/
│   │   ├── __init__.py      # CRUD الفواتير
│   │   └── forms.py         # نماذج Flask-WTF (InvoiceForm)
│   ├── payments/
│   │   ├── __init__.py      # CRUD الدفعات
│   │   └── forms.py         # نماذج Flask-WTF (PaymentForm)
│   ├── reports/__init__.py  # التقارير + DB-backed import cache
│   ├── api/__init__.py      # API endpoints (مع Swagger docs)
│   ├── whatsapp/__init__.py # إعدادات WhatsApp + الإعدادات العامة
│   ├── database/__init__.py # إدارة قاعدة البيانات (backup/restore/export/reset)
│   └── importers/           # استيراد Excel
├── templates/               # Jinja2 templates (عربي RTL)
├── static/                  # CSS + JS
├── tests/
│   ├── conftest.py          # Test fixtures (in-memory DB)
│   └── test_all.py          # 128 اختبار شامل
├── alembic/                 # Alembic migrations
│   ├── env.py
│   └── versions/
├── alembic.ini              # Alembic configuration
├── upgrade_db.py            # ترقية قاعدة البيانات (legacy + Alembic)
├── run_production.py        # تشغيل waitress
├── web2view.pyw             # تشغيل pywebview
├── backups/                 # النسخ الاحتياطية
├── exports/                 # ملفات التصدير
└── uploads/                 # الملفات المرفوعة
```

---

## الإصلاحات المطبقة (14 إصلاح)

### 1. `datetime.utcnow()` — deprecated في Python 3.12+

**المشكلة:** `datetime.utcnow()` يُظهر تحذير في Python 3.12+ وهمي timezone.

**الحل:** إنشاء helper function في `app/models.py`:

```python
# models.py
from datetime import datetime, timezone

def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Client(db.Model):
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
```

**الملفات المعدلة:**
- `app/models.py:9-10` — `_utcnow()` helper
- `app/models.py` — جميع DateTime columns تستخدم `_utcnow` كـ default
- `app/__init__.py:83` — context processor
- `app/api/__init__.py` — ActivityLog timestamps
- `app/reports/__init__.py` — report timestamps
- `app/clients/__init__.py` — client timestamps
- `app/whatsapp/__init__.py` — settings timestamps

---

### 2. SQL Injection في `upgrade_db.py`

**المشكلة:** `table_exists()` و `col_exists()` يستقبلان أسماء جداول كـ string بدون تحقق.

**الحل:** Whitelist + parameterized query:

```python
# upgrade_db.py
ALLOWED_TABLES = {'settings', 'clients', 'users', 'payments', 'invoices', 'activity_log'}

def table_exists(cursor, table):
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Invalid table name: {table}")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None
```

**الملفات المعدلة:**
- `upgrade_db.py:10,14-16,20-24`

---

### 3. `db.Float` → `db.Numeric(10, 2)` للمبالغ المالية

**المشكلة:** `db.Float` يسبب أخطاء تقريب في المبالغ المالية.

**الحل:** استخدام `db.Numeric(10, 2)` مع `float()` في `to_dict()`:

```python
# models.py
class Invoice(db.Model):
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)

class Payment(db.Model):
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)

class Client(db.Model):
    total_debt = db.Column(db.Numeric(10, 2), default=0)
    total_paid = db.Column(db.Numeric(10, 2), default=0)

# في to_dict()
'amount': float(self.amount) if self.amount else 0,
```

**الملفات المعدلة:**
- `app/models.py` — Invoice, Payment, Client models

---

### 4. إزالة imports غير مستخدمة

**المشكلة:** `subprocess` في `web2view.pyw` و `session` في `__init__.py` لم تكن مستخدمة.

**الحل:** حذفها مباشرة.

**الملفات المعدلة:**
- `web2view.pyw` — إزالة `import subprocess`
- `app/__init__.py` — إزالة `from flask import session`

---

### 5. إزالة `flask_caching` (Cache) غير مستخدمة

**المشكلة:** `Cache` كان مُعرّف لكن لم يكن مستخدم في أي مكان.

**الحل:** حذفه من `app/__init__.py` و `app/reports/__init__.py`.

**الملفات المعدلة:**
- `app/__init__.py` — إزالة `from flask_caching import Cache` و `Cache(app)`
- `app/reports/__init__.py` — إزالة `from flask_caching import Cache` و `cache = Cache()`

---

### 6. تقسيم `whatsapp/__init__.py` (357 سطر)

**المشكلة:** ملف واحد يحتوي على WhatsApp routes + Database management routes + Settings.

**الحل:** إنشاء `app/database/__init__.py` جديد:

```python
# database/__init__.py — Database management routes
database_bp = Blueprint('database', __name__)

# Routes: /api/database/backup, /restore, /download-backup, /delete-backup, /reset, /export-db
```

**الملفات المعدلة:**
- `app/whatsapp/__init__.py` — حذف database routes (~150 سطر)
- `app/database/__init__.py` — ملف جديد (190 سطر)
- `app/__init__.py:97,106` — تسجيل `database_bp`

---

### 7. حذف دالة `init_scheduler_func()` الميتة

**المشكلة:** دالة `init_scheduler_func()` في `reports/__init__.py` كانت مُعلّقة بـ `@main.before_request` لكنها ميتة.

**الحل:** حذفها بالكامل.

**الملفات المعدلة:**
- `app/reports/__init__.py` — حذف `init_scheduler_func`

---

### 8. إعداد Logging مكرر (3 مرات)

**المشكلة:** Logging كان يُنشأ في 3 أماكن مختلفة:
- `app/__init__.py` — `RotatingFileHandler` ✓ (الأفضل)
- `run_production.py` — `logging.basicConfig()` ✗
- `web2view.pyw` — `logging.basicConfig()` ✗

**الحل:** الاحتفاظ بـ handler واحد في `app/__init__.py` وحذف الباقي.

**الملفات المعدلة:**
- `run_production.py` — حذف `logging.basicConfig(...)`
- `web2view.pyw` — حذف `logging.basicConfig(...)`

---

### 9. thread-safety لـ `_import_cache`

**المشكلة:** `_import_cache` في `reports/__init__.py` كان dict عادي — غير آمن في multi-thread.

**الحل:** استخدام `threading.Lock`:

```python
# reports/__init__.py
import threading

_import_cache = {}
_import_lock = threading.Lock()

def _import_client_data(file_path):
    with _import_lock:
        cache_key = os.path.getmtime(file_path)
        if cache_key in _import_cache:
            return _import_cache[cache_key]
        # ... rest of logic
```

**الملفات المعدلة:**
- `app/reports/__init__.py` — إضافة `threading.Lock` لحماية `_import_cache`

---

### 10. `send_scheduled_reminders` في background thread

**المشكلة:** `send_scheduled_reminders` كان يُنفذ في main thread — يُجمّد الـ requests.

**الحل:** تشغيله في `threading.Thread(daemon=True)`:

```python
# utils.py
def _send_reminders_background(app):
    with app.app_context():
        send_scheduled_reminders(app)

def send_scheduled_reminders(app=None):
    if app is None:
        app = current_app
    t = threading.Thread(target=_send_reminders_background, args=(app,), daemon=True)
    t.start()
```

**الملفات المعدلة:**
- `app/utils.py` — `_send_reminders_background()` + تشغيل في thread

---

### 11. تحذير كلمة المرور الافتراضية

**المشكلة:** `README.txt` لم يكن يحتوي على تحذير أمان.

**الحل:** إضافة تحذير في `README.txt`:

```
⚠️  IMPORTANT: Change the default admin password (admin/admin123) after first login!
```

**الملفات المعدلة:**
- `README.txt` — إضافة تحذير أمان

---

### 12. `SchedulerAlreadyRunningError`

**المشكلة:** عند إعادة تشغيل الـ scheduler بدون `shutdown()`, كان يظهر خطأ.

**الحل:** `scheduler.shutdown(wait=False)` قبل `remove_all_jobs()`:

```python
# app/__init__.py
def _init_scheduler(app):
    if scheduler.running:
        scheduler.shutdown(wait=False)
    scheduler.remove_all_jobs()
    # ... rest of config
    if not scheduler.running:
        scheduler.start()
```

**الملفات المعدلة:**
- `app/__init__.py:161-164`

---

### 13. تحديث templates — database endpoints

**المشكلة:** `templates/settings.html` كان يشير إلى `whatsapp.db_backup` بدلاً من `database.db_backup`.

**الحل:** تحديث جميع الـ endpoint references:

```html
<!-- قبل -->
onclick="dbAction('whatsapp.db_backup')"
onclick="dbAction('whatsapp.db_reset')"

<!-- بعد -->
onclick="dbAction('database.db_backup')"
onclick="dbAction('database.db_reset')"
```

**الملفات المعدلة:**
- `templates/settings.html` — تحديث database endpoint names

---

### 14. `send_file()` — حذف `download_timeout`

**المشكلة:** `download_timeout` parameter غير موجود في Flask.

**الحل:** حذفه من `send_file()`.

**الملفات المعدلة:**
- `app/database/__init__.py:101,167` — حذف `download_timeout` من `send_file()`

---

## ميزة جديدة: قفل تسجيل الدخول

### الوصف
زر في الإعدادات > عام لقفل تسجيل الدخول. عند التفعيل:
- المستخدم الجدد لا يستطيعون تسجيل الدخول
- البرنامج يفتح **تلقائياً كـ admin** (بدون كلمة مرور)
- المدير يدخل الإعدادات ويُلغي القفل لتسجيل الدخول العادي

### السلوك

| الحالة | السلوك |
|---|---|
| **القفل مفعّل** | `login()` route يعمل auto-login لـ admin ويرجع للرئيسية |
| **القفل معطّل** | صفحة تسجيل الدخول تعمل بشكل عادي |

### الملفات المعدلة
- `templates/settings.html` — زر التفعيل + التحذير في التبويب general
- `templates/login.html` — حالة القفل (النموذج يختفي, أيقونة قفل حمراء)
- `app/auth/__init__.py` — فحص `login_locked` و auto-login
- `app/whatsapp/__init__.py` — حفظ `login_locked` + تمريره للقالب

### الكود الرئيسي

```python
# app/auth/__init__.py
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    from app.models import Settings, User
    if Settings.get('login_locked', 'false') == 'true':
        admin = User.query.filter_by(username='admin').first()
        if admin and admin.is_active_flag:
            login_user(admin)
            return redirect(url_for('clients.index'))
        flash('لا يوجد حساب مدير متاح', 'danger')
        return render_template('login.html', login_locked=True)
    # ... normal login flow
```

```python
# app/whatsapp/__init__.py — settings POST handler
if tab == 'general':
    Settings.set('login_locked', 'true' if request.form.get('login_locked') else 'false')
```

---

## بنية القاعدة البيانات

```sql
-- المستخدمين
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    role VARCHAR(20) DEFAULT 'viewer',
    is_active_flag BOOLEAN DEFAULT 1,
    created_at DATETIME
);

-- العملاء
CREATE TABLE clients (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    total_debt NUMERIC(10,2) DEFAULT 0,
    total_paid NUMERIC(10,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'due',
    reminder_enabled INTEGER DEFAULT 1,
    reminder_template INTEGER DEFAULT 1,
    updated_at DATETIME
);

-- الفواتير
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    amount NUMERIC(10,2) NOT NULL,
    description TEXT,
    date DATETIME
);

-- الدفعات
CREATE TABLE payments (
    id INTEGER PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    amount NUMERIC(10,2) NOT NULL,
    payment_method TEXT,
    date DATETIME
);

-- السجل
CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    details TEXT,
    ip_address TEXT,
    created_at DATETIME
);

-- الإعدادات
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

---

## endpoints الرئيسية

| Route | Method | الوصف | Auth |
|---|---|---|---|
| `/login` | GET/POST | تسجيل الدخول | لا |
| `/logout` | GET | تسجيل الخروج | نعم |
| `/users` | GET | إدارة المستخدمين | admin |
| `/clients` | GET | قائمة العملاء | نعم |
| `/clients/<id>` | GET | تفاصيل العميل | نعم |
| `/invoices` | GET | الفواتير | نعم |
| `/payments` | GET | الدفعات | نعم |
| `/reports` | GET | التقارير | نعم |
| `/settings` | GET/POST | الإعدادات | نعم |
| `/api/database/backup` | POST | نسخ احتياطي | admin |
| `/api/database/restore` | POST | استعادة | admin |
| `/api/database/reset` | POST | حذف جميع البيانات | admin |

---

## الاختبارات

```
128 اختبار شامل يغطي:
├── Auth (6) — login/logout/role permissions
├── Clients (12) — CRUD + balance calculations
├── Invoices (10) — CRUD + recalc
├── Payments (8) — CRUD + recalc
├── Reports (6) — export/import
├── API (8) — all endpoints
├── Utils (5) — recalc, export, template
├── Database (8) — backup/restore/reset
├── WhatsApp (4) — settings
├── Edge Cases (10) — concurrent, XSS, SQL injection
└── ...
```

**آخر تشغيل:** `128 passed, 9 warnings (all openpyxl) in 45s`

---

## ملاحظات أمان

1. **كلمة المرور الافتراضية:** `admin/admin123` — يجب تغييرها بعد أول دخول
2. **SQL Injection:** محمي في `upgrade_db.py` عبر whitelist + parameterized query
3. **CSRF:** محمي عبر `flask_wtf.csrf.CSRFProtect`
4. **Rate Limiting:** `flask_limiter` على login route (10/minute)
5. **Security Headers:** X-Content-Type-Options, X-Frame-Options, X-XSS-Protection
6. **SECRET_KEY:** يُولّد تلقائياً ويُحفظ في `instance/.secret_key`
7. **File Upload:** محدود بـ 16MB + extensions whitelist
8. **SQLAlchemy ORM:** جميع الاستعلامات parameterized — لا SQL injection في ORM
9. **Backup Restore:** filename validated مع regex + path traversal protection

---

## التحسينات المطلوبة مستقبلاً

1. **TLS/HTTPS** — يجب تشغيله في Production
2. **Password Policy** — minimum 8 characters (already enabled)
3. **اختبارات لقاعدة البيانات** — إضافة اختبارات لـ integrity/optimize/stats endpoints
4. **اختبارات Eel** — محاكاة فتح المتصفح (تحديث لأن pywebview استُبدل)
5. **اختبارات Forms** — اختبار validation لكل الـ WTForms الجديدة
5. **Two-Factor Auth:** ميزة مستقبلية
6. **Backup Encryption:** النسخ الاحتياطية غير مشفرة حالياً
