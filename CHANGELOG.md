# CHANGELOG — نظام إدارة المديونيات

## v1.2.0 (2026-07-28)

### تحسينات جديدة

#### 1. معالجة أخطاء خلفية إرسال التذكيرات
- **الملف:** `app/utils.py`
- إضافة `log_background_error()` مع `RotatingFileHandler` لتسجيل أخطاء الخلفية في `logs/background_errors.log`
- `_send_reminders_background` أصبح يحتوي على try/except شامل علىمستوى العميل وعلى مستوى المهمة بأكملها
- الفشل في إرسال تذكير لعميل واحد لا يوقف باقي العملاء

#### 2. تخزين الاستيراد المؤقت في قاعدة البيانات
- **الملف:** `app/models.py`, `app/reports/__init__.py`
- نموذج `ImportCache` جديد لتخزين معاينات الاستيراد في قاعدة البيانات
- استبدال `_import_cache` (dict + threading.Lock) بـ `ImportCache.store()`, `get_data()`, `pop()`
- انتهاء الصلاحية التلقائي بعد ساعة
- حذف المدخلات القديمة يدوياً عبر `ImportCache.cleanup_expired()`

#### 3. تحقق صارم من صحة المدخلات (Flask-WTF Forms)
- **ملفات جديدة:**
  - `app/auth/forms.py` — `LoginForm`, `AddUserForm`
  - `app/clients/forms.py` — `ClientForm`, `ClientSettingsForm`
  - `app/invoices/forms.py` — `InvoiceForm`, `InvoiceEditForm`
  - `app/payments/forms.py` — `PaymentForm`, `PaymentEditForm`
- validators مخصصة:
  - `validate_phone_ar` — التحقق من رقم الهاتف (أرقام فقط، 3+ أرقام)
  - `validate_name_simple` — منع الأحرف الخاصة، الحد الأقصى 200 حرف
  - `NumberRange` — المبالغ المالية أكبر من صفر
  - `Length` — حدود الطول لكل حقل
- ربط النماذج بالـ routes مع `form.validate()`
- رسائل خطأ بالعربية

#### 4. Alembic لإدارة ترقيات قاعدة البيانات
- **ملفات جديدة:** `alembic/`, `alembic.ini`
- تثبيت `alembic` وتهيئته مع `render_as_batch=True` لدعم SQLite
- `env.py` مُعدّل للعمل مع `app.models.db.metadata`
- الترحيلة الأولى: `c9da808b5967_initial_schema.py` (إضافة `settings.value_type`)
- `upgrade_db.py` محدّث ليشمل إشارة إلى Alembic

#### 5. معالجة التحذيرات المتبقية
- **الملفات:** جميع ملفات `app/` + `tests/test_all.py`
- استبدال `Query.get()` بـ `db.session.get()` في:
  - `app/utils.py` (`recalc_client`)
  - `app/__init__.py` (`load_user`)
  - `app/auth/__init__.py` (toggle, delete)
  - `app/clients/__init__.py` (all routes)
  - `app/invoices/__init__.py` (all routes)
  - `app/payments/__init__.py` (all routes)
  - `app/api/__init__.py` (all routes)
  - `app/whatsapp/__init__.py` (send reminder)
  - `tests/test_all.py` (5 اختبارات)
- **النتيجة:** تحذيرات انخفضت من 59 إلى 9 (البقية من openpyxl خارج سيطرتنا)

#### 6. توثيق API بـ Swagger/OpenAPI
- **الملف:** `app/__init__.py`, `app/api/__init__.py`
- تثبيت `flasgger` وربطه بالتطبيق
- Swagger UI على مسار `/apidocs/`
- توثيق Swagger للـ endpoints الرئيسية:
  - `GET /api/v1/clients` — قائمة العملاء
  - `POST /api/v1/clients` — إضافة عميل
  - `GET /api/v1/clients/<id>` — تفاصيل عميل
  - `GET /api/v1/reports/summary` — ملخص التقارير

#### 7. تنظيف الملفات المرفوعة القديمة تلقائياً
- **الملف:** `app/utils.py`, `app/__init__.py`
- دالة `cleanup_old_uploads(app)` جديدة
- مهمة مجدولة يومياً عند منتصف الليل عبر APScheduler
- مدة الاحتفاظ configurable عبر `Settings.get('upload_retention_days', '7')`

#### 8. تحسين تخزين الإعدادات (أنواع البيانات)
- **الملف:** `app/models.py`
- عمود `value_type` جديد في جدول `settings`
- `Settings.get()` يُرجع القيمة محولة حسب النوع:
  - `string` → نص
  - `bool` → True/False
  - `int` → عدد صحيح
  - `float` → عدد عشري
  - `json` → dict/list
- `Settings.set()` يُحدّد النوع تلقائياً من نوع القيمة المرسلة
- متوافق مع البيانات القديمة (تُعامل كـ string)

#### 9. تناسق البيانات أثناء التصدير والنسخ الاحتياطي
- **الملف:** `app/database/__init__.py`
- استخدام `sqlite3.Connection.backup()` بدلاً من `shutil.copy2()`:
  - `db_export()` — تصدير قاعدة البيانات
  - `db_save_export()` — حفظ نسخة احتياطية
- هذا يضمن نسخة متناسقة حتى أثناء الكتابة

### إصلاحات تقنية

- **conftest.py:** إضافة `testing` parameter لـ `create_app()` لإنشاء in-memory DB
- **requirements.txt:** إضافة `alembic>=1.13,<2.0`, `flasgger>=0.9,<1.0`، حذف `flask-caching`
- **upgrade_db.py:** إضافة `value_type` column migration

---

## v1.1.0 (2016-07-27)

### الإصلاحات الأصلية (14 إصلاح)

1. `datetime.utcnow()` → `_utcnow()` helper
2. SQL Injection في `upgrade_db.py` — whitelist + parameterized query
3. `db.Float` → `db.Numeric(10, 2)` للمبالغ المالية
4. إزالة imports غير مستخدمة
5. إزالة `flask_caching` غير مستخدمة
6. تقسيم `whatsapp/__init__.py` → `database/__init__.py`
7. حذف دالة `init_scheduler_func()` الميتة
8. إزالة logging مكرر (3 أماكن → 1)
9. `threading.Lock` لحماية `_import_cache`
10. `send_scheduled_reminders` في background thread
11. تحذير كلمة المرور الافتراضية في README
12. `SchedulerAlreadyRunningError` — shutdown قبل remove_all_jobs
13. تحديث templates — database endpoint names
14. حذف `download_timeout` من `send_file()`

### ميزة قفل تسجيل الدخول

- زر في الإعدادات > عام لقفل تسجيل الدخول
- عند التفعيل: البرنامج يفتح تلقائياً كـ admin
- صفحة تسجيل الدخول تُخفي النموذج وتعرض حالة القفل

---

## v1.3.0 (2026-07-29)

### Eel Desktop Integration
- **الملف:** `web2view.pyw`
- استبدال `pywebview` بـ `Eel` لفتح البرنامج في Chrome/Edge (وضع `--app`)
- كشف تلقائي للمتصفح: Chrome → Edge → EdgeCore → Fallback للمتصفح الافتراضي
- مراقبة عملية المتصفح ← تقفيل البرنامج تلقائياً عند غلق النافذة
- Lock file + PID file لمنع تشغيل نسختين في نفس الوقت
- أيقونة محفظة ذهبية (`static/favicon.ico`) مع 6 أحجام
- `pywin32` API لتغيير أيقونة نافذة المتصفح (تظهر في التاسك بار)
- إضافة `stop.bat` يقفل كل البورتات (5000 + 9999 + 3001)

### تحسينات قاعدة البيانات (مراجعة عميقة)
- **الملف:** `app/database/__init__.py`
- إصلاح **جميع** عمليات `shutil.copy2` → `sqlite3.backup()`:
  - `db_restore()` — استعادة النسخ الاحتياطية
  - `backup_database()` في `utils.py` — النسخة الاحتياطية المجدولة
  - `db_export()` — تحميل قاعدة البيانات
  - `db_save_export()` — حفظ نسخة
- إضافة **lock أثناء الاستعادة** (`threading.Lock`) لمنع التصادم
- إضافة **فحص صحة SQLite** قبل أي عملية (header magic bytes)
- إضافة **WAL checkpoint (TRUNCATE)** قبل النسخ لضمان التناسق
- **تصدير مع timestamp** في اسم الملف بدلاً من `debtors_backup.db` ثابت
- **تسجيل نشاط المستخدم** لكل عمليات قاعدة البيانات (backup/restore/export/delete/reset/optimize)
- **API جديدة:**
  - `GET /api/database/stats` — إحصائيات كاملة (بما في ذلك حجم النسخ)
  - `GET /api/database/integrity` — فحص سلامة (integrity_check + foreign_key_check + page info)
  - `POST /api/database/optimize` — تحسين (vacuum / reindex / analyze)
- **تحديث واجهة المستخدم:** بطاقة إضافية لحجم النسخ الاحتياطية + زرار فحص سلامة + زرار Vacuum + عرض النتائج في الصفحة
- `db_restore()` — تعطيل `foreign_keys` مؤقتاً قبل الاستعادة + إغلاق كل الجلسات + dispose لل engine
