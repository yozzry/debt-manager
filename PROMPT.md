# مشروع: نظام إدارة المديونيات (Debt Manager) — التوثيق الكامل

> هذا الملف يوثّق المشروع **بكامل تفاصيله** كما هو موجود على الجهاز الآن.
> المسار الجذر الحالي: `C:\Users\YUZZRY\Desktop\debt_manager_deploy`
> تاريخ التوثيق: 2026-08-06

---

## 1) نظرة عامة

نظام سطح مكتب + متصفح لإدارة المديونيات (عملاء، فواتير، دفعات، تقارير، نسخ احتياطية،
تذكيرات واتساب تلقائية) بواجهة عربية كاملة RTL.

- **نقطة الدخول:** `debt_manager.pyw`
- **الخادم:** Flask + Waitress على `http://127.0.0.1:5000` (منفذ واحد فقط، 4 خيوط افتراضيًا)
- **النافذة:** تُفتح تلقائيًا داخل Chrome/Edge بوضع `--app` بملف تعريف مخصص
- **واتساب:** جسر محلي Node.js (Baileys) على المنفذ `3001` (بديل مجاني عن Ultramsg)
- **قاعدة البيانات:** SQLite في `instance\debtors.db`
- **الواجهة:** Bootstrap 5 (نسخة RTL) + أيقونات Bootstrap Icons + خط IBM Plex Sans Arabic

> ملاحظة مهمة: المسار القديم `Desktop\debt_manager_deploy\debt_manager_deploy\debt_manager_deploy`
> **لم يعد موجودًا**. كل العمل الآن على `Desktop\debt_manager_deploy` مباشرة.

---

## 2) التقنيات والمكتبات (`requirements.txt`)

### الأساسيات (Core)
| المكتبة | الإصدار |
|---|---|
| flask | 3.0.x |
| flask-sqlalchemy | 3.1.x |
| flask-login | 0.6.x |
| flask-wtf | 1.2.x (تفعيل CSRF) |
| wtforms | 3.1.x |
| flask-compress | 1.17.x |
| flask-limiter | 3.5.x (حماية معدل الطلبات) |
| apscheduler | 3.10.x (المجدول) |
| alembic | 1.13.x (ترحيلات قاعدة البيانات) |
| flasgger | 0.9.x (توثيق API عبر Swagger) |

### البيانات والتصدير
| المكتبة | الاستخدام |
|---|---|
| openpyxl | تصدير/استيراد Excel |
| reportlab | توليد تقارير PDF |
| arabic-reshaper + python-bidi | دعم النصوص العربية (احتياطي) |

### HTTP والبيئة
| المكتبة | الاستخدام |
|---|---|
| requests | التواصل مع جسر واتساب |
| python-dotenv | متغيرات البيئة |
| werkzeug (3.x) | مثبّت لتفعيل flask-login |

### الخادم والنافذة
| المكتبة | الاستخدام |
|---|---|
| waitress | خادم الإنتاج |
| pywin32 | تغيير أيقونة نافذة المتصفح + رسائل Windows |
| Pillow | صور الأيقونة |
| psutil | مراقبة عمليات المتصفح وقتل الكروم العالق |

### تطوير/اختبار
pytest ، pytest-cov ، pyinstaller

> ملاحظة: توجد `eel` في requirements.txt لكنها **غير مستخدمة** في التشغيل الفعلي
> (أُزيلت نهائيًا لصالح نافذة Chrome المباشرة).

---

## 3) بنية المجلدات

```
debt_manager_deploy\
├── debt_manager.pyw        ← نقطة الدخول (يُشغَّل بها البرنامج)
├── run_production.py       ← تشغيل الخادم فقط (بدون نافذة) عبر waitress
├── launch.vbs              ← إقلاع بدون نافذة كونسول
├── install.bat             ← تثبيت البيئة (venv + npm + قاعدة البيانات)
├── start.bat               ← تشغيل نسخة التطوير (Flask + المتصفح)
├── stop.bat                ← إيقاف كل الخدمات (5000 + 9999 + 3001)
├── install_baileys.bat     ← تثبيت مكتبات واتساب يدويًا (Node)
├── start_baileys.bat       ← تشغيل جسر واتساب يدويًا
├── install-tools.ps1       ← تثبيت Git عبر winget
├── build_exe.py            ← بناء الـ EXE عبر PyInstaller
├── DebtManager.spec        ← ملف PyInstaller الاحتياطي
├── installer.iss           ← ملف Inno Setup (المثبّت النهائي)
├── upgrade_db.py           ← ترقية قاعدة بيانات قديمة (أعمدة/جداول مفقودة)
├── requirements.txt        ← مكتبات بايثون
├── icon.ico                ← أيقونة البرنامج
├── alembic\ + alembic.ini  ← ترحيلات قاعدة البيانات
├── app\                    ← كود التطبيق (Flask)
│   ├── __init__.py         ← create_app + الإعدادات + المجدول + الأمان
│   ├── models.py           ← كل النماذج (جداول قاعدة البيانات)
│   ├── utils.py            ← دوال مساعدة (واتساب، تصدير، نسخ احتياطي، استيراد)
│   ├── auth\               ← تسجيل الدخول والمستخدمين
│   ├── clients\            ← إدارة العملاء
│   ├── invoices\           ← الفواتير
│   ├── payments\           ← الدفعات
│   ├── reports\            ← التقارير + استيراد/تصدير
│   ├── whatsapp\           ← إعدادات واتساب والتذكيرات
│   ├── api\                ← REST API
│   ├── database\           ← إدارة قاعدة البيانات (نسخ، استعادة، فحص)
│   └── importers\          ← parser محاسبي متخصص (accounting_excel.py)
├── baileys_service\        ← جسر واتساب Node.js
│   ├── index.js            ← الخادم (Express على 3001)
│   ├── package.json        ← اعتماديات Baileys
│   ├── auth_session\       ← جلسة واتساب (تُنشأ بعد مسح QR)
│   └── baileys.log         ← سجل الجسر
├── templates\              ← قوالب HTML (عربية RTL)
├── static\                 ← Bootstrap/CSS/JS/أيقونات/خطوط/أصوات
├── tests\                  ← اختبارات pytest
├── instance\               ← قاعدة البيانات الفعلية debtors.db + مفاتيح + أقفال
├── logs\                   ← app.log + startup.log + background_errors.log
├── backups\                ← نسخ احتياطية تلقائية/يدوية
├── exports\                ← ملفات التصدير
├── uploads\                ← صور الفواتير المرفوعة
├── dist\                   ← مخرجات البناء
│   ├── DebtManager\        ← مجلد البرنامج المجمَّع
│   └── installer\          ← DebtManagerSetup.exe (المثبّت النهائي)
└── PROMPT.md               ← هذا الملف
```

---

## 4) نقطة الدخول `debt_manager.pyw` — سير التشغيل بالتفصيل

1. **تحديد المسارات:** عند التجميع (`frozen`) يكون `BASE_DIR = مجلد الـ exe`
   و`DATA_DIR = sys._MEIPASS`؛ وإلا فكلاهما مجلد المشروع.
2. **إنشاء المجلدات المطلوبة:** `logs`, `uploads`, `exports`, `backups`, `instance`.
3. **تسجيل `logs\startup.log`** بمستوى DEBUG لكل خطوات الإقلاع.
4. **نسخ `baileys_service`** من داخل الـ exe إلى `BASE_DIR` إن غاب (بدون node_modules/auth_session).
5. **منع التشغيل المزدوج:**
   - ملفات `instance\.app.lock` و `instance\.app.pid` تحمل PID.
   - `_kill_stale()` تقتل أي نسخة قديمة وتحاول تنظيف المنفذين 5000 و 9999.
6. **إنشاء تطبيق Flask** عبر `create_app()` (انظر البند 6).
7. **تشغيل Waitress** في خيط خلفي: `127.0.0.1:5000`، 4 خيوط، يمكن تغييره بـ env
   `PORT` و `THREADS`.
8. **فتح النافذة** في خيط مستقل (`_open_browser`):
   - البحث عن المتصفح: Chrome → Edge → EdgeCore (أحدث إصدار) → fallback للمتصفح الافتراضي.
   - قبل فتح الصفحة تنتظر `_wait_until_up()` حتى يستجيب الخادم فعلًا (مهلة 40 ثانية)
     لمنع `ERR_CONNECTION_REFUSED` عند أول تشغيل بارد.
   - فتح Chrome بـ **ملف تعريف مخصص**: `--user-data-dir=<BASE_DIR>\.app_chrome_cache`
     مع `--app=http://127.0.0.1:5000/login` و `--window-size=1280,800` و `--no-first-run`.
   - هذا يضمن أن تكون النافذة مملوكة لعملية مستقلة (لا يُمرَّر الرابط لكروم شغّال).
   - `_find_and_set_icon()` تغيّر أيقونة النافذة في شريط المهام عبر pywin32.
   - **حلقة المراقبة:** كل ثانيتين تفحص `_browser_proc.poll()`. إذا أُغلقت النافذة
     مرتين متتاليتين → `_kill_everything()` تُغلق البرنامج (مع قتل كروم الملف التعريفي).
   - `_kill_profile_chrome()` تُقتل عند الإطلاق والإغلاق أي عملية chrome عالقة تخص
     `.app_chrome_cache` (كانت سابقًا تتسبب في إغلاق البرنامج صامتًا).
9. **الإعداد التلقائي لواتساب** في خيط مستقل (`_auto_setup_baileys`):
   - `ensure_baileys_ready()` تثبّت `node_modules` تلقائيًا عبر `npm install --no-audit --no-fund`
     إن كانت غائبة، مع ضبط git لتحويل SSH إلى HTTPS.
   - `start_baileys_bridge()` تشغّل `node index.js` بشكل منفصل (DETACHED_PROCESS)
     على المنفذ 3001 إن لم يكن شغالًا، وتسجّل في `baileys.log`.
   - أي فشل يُسجَّل في startup.log **بدون إيقاف البرنامج**.
10. **الخيط الرئيسي** يبقى في `while True: time.sleep(1)` حتى تغلق النافذة.

---

## 5) إعداد التطبيق `app\__init__.py` — `create_app()`

### 5.1 الإعدادات العامة
- `SECRET_KEY`: من متغير البيئة، أو من ملف `instance\.secret_key`، أو توليد تلقائي وحفظه.
- قاعدة البيانات: `sqlite:///instance/debtors.db` (في الاختبار: ذاكرة).
- رفع الملفات: `uploads` بحد أقصى **16 ميجابايت**.
- CSRF: `WTF_CSRF_TIME_LIMIT = 3600` (ساعة).
- `BASE_DIR` متاح للتطبيق عبر `app.config['BASE_DIR']`.

### 5.2 الامتدادات المُفعَّلة
| الامتداد | الغرض |
|---|---|
| SQLAlchemy (`db`) | ORM |
| CSRFProtect | حماية النماذج من CSRF |
| LoginManager | جلسات المستخدمين (صفحة الدخول `auth.login`) |
| Compress | ضغط الاستجابات (gzip) |
| Limiter | معدل الطلبات (get_remote_address) — يمكن إيقافه بـ `RATELIMIT_ENABLED=false` |
| BackgroundScheduler | المهام المجدولة |
| Swagger (flasgger) | توثيق API على `/apidocs/` |

### 5.3 إجراءات الحماية تلقائيًا على كل استجابة
```
X-Content-Type-Options: nosniff
X-Frame-Options: SAMEORIGIN
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; ...
```
بالإضافة إلى تعيين كوكي `csrf_token` (samesite=Lax, httponly=false حتى يقرأه JS).

### 5.4 معالجة الأخطاء (Error Handlers)
- كل أخطاء HTTP (400/403/404/405/500) تعرض صفحة عربية جميلة،
  وعند طلبات `/api/*` تُرجع JSON بصيغة `{'ok': False, 'msg': ...}`.

### 5.5 عند الإقلاع (داخل app_context)
- `db.create_all()` — إنشاء الجداول إن لم تكن موجودة.
- `_ensure_default_admin()` — لو جدول users فارغ تمامًا يُنشئ:
  - المستخدم: **admin** ، كلمة المرور: **admin123** ، الدور: **admin**
  - ⚠️ يجب تغييرها فورًا من صفحة المستخدمين.
- `_init_scheduler(app)` — إعداد المجدول (انظر البند 9).
- `_enable_sqlite_wal(app)` — تفعيل PRAGMA على كل اتصال:
  - `journal_mode=WAL`
  - `busy_timeout=5000`
  - `foreign_keys=ON`

### 5.6 البلوبرينتات (Blueprints) والمسارات المسجَّلة
| البلوبرينت | البادئة | الملف |
|---|---|---|
| auth_bp | — | app\auth\__init__.py |
| clients_bp | — | app\clients\__init__.py |
| invoices_bp | — | app\invoices\__init__.py |
| payments_bp | — | app\payments\__init__.py |
| whatsapp_bp | — | app\whatsapp\__init__.py |
| reports_bp | — | app\reports\__init__.py |
| api_bp | `/api` | app\api\__init__.py |
| database_bp | — | app\database\__init__.py |

ملاحظة: `strict_slashes = False` (لا يتأثر بوجود شرطة مائلة).

---

## 6) قاعدة البيانات — `app\models.py`

الملف الفعلي: `instance\debtors.db` (SQLite). الجداول:

### 6.1 users (المستخدمون)
| العمود | النوع | ملاحظات |
|---|---|---|
| id | Integer PK | |
| username | String(80) | فريد، مفهرس |
| password_hash | String(256) | عبر werkzeug |
| role | String(20) | admin / editor / viewer |
| is_active_flag | Boolean | للتفعيل/التعطيل |
| created_at | DateTime | |

خواص: `is_admin` (role=admin)، `can_edit` (admin أو editor).
دالة `to_dict()`.

### 6.2 clients (العملاء)
| العمود | النوع | ملاحظات |
|---|---|---|
| id | Integer PK | |
| name | String(200) | مطلوب |
| phone | String(30) | |
| notes | Text | |
| total_debt | Numeric(10,2) | إجمالي المديونية |
| total_paid | Numeric(10,2) | إجمالي المدفوع |
| base_debt | Numeric(10,2) | الأساس (من الاستيراد) |
| base_paid | Numeric(10,2) | الأساس |
| status | String(20) | due / paid |
| reminder_enabled | Boolean | تفعيل التذكير |
| reminder_template | Integer | 1 / 2 / 3 |
| reminder_times | Text | "10:00,14:00" أو فارغ (افتراضي) |
| reminder_frequency | String(10) | daily / weekly / monthly |
| reminder_day | String(10) | sun..sat |
| reminder_dom | Integer | يوم الشهر 1..31 |
| created_at / updated_at | DateTime | |

فهارس: idx_client_status, idx_client_name, idx_client_phone, idx_client_updated.
خاصية `balance = max(0, total_debt - total_paid)`.
علاقات cascade: حذف العميل يحذف فواتيره ودفعاته.

### 6.3 invoices (الفواتير)
| العمود | النوع |
|---|---|
| id | Integer PK |
| client_id | FK → clients.id |
| description | String(500) |
| amount | Numeric(10,2) |
| date | Date |
| image_path | String(500) — صورة الفاتورة |
| created_at | DateTime |

فهارس: idx_invoice_client, idx_invoice_date.

### 6.4 payments (الدفعات)
| العمود | النوع |
|---|---|
| id | Integer PK |
| client_id | FK → clients.id |
| amount | Numeric(10,2) |
| date | Date |
| notes | String(500) |
| payment_method | String(50) |
| created_at | DateTime |

فهارس: idx_payment_client, idx_payment_date.

### 6.5 settings (الإعدادات)
| العمود | النوع |
|---|---|
| id | Integer PK |
| key | String(100) فريد |
| value | Text |
| value_type | string / bool / int / float / json |

- `Settings.get(key, default)` — تُرجِع القيمة محوَّلة حسب النوع.
- `Settings.set(key, value)` — تحدد النوع تلقائيًا من نوع القيمة.

مفاتيح معروفة: `app_country`, `app_timezone`, `app_currency`, `app_currency_short`,
`login_locked`, `baileys_url`, `reminder_enabled`, `reminder_times`, `reminder_frequency`,
`reminder_day`, `reminder_dom`, `payment_link`, `template_1`, `template_2`, `template_3`,
`upload_retention_days`.

### 6.6 activity_log (سجل النشاط)
| العمود | النوع |
|---|---|
| id | Integer PK |
| user_id | FK → users.id |
| action | String(50) |
| entity_type | String(50) |
| entity_id | Integer |
| details | Text |
| ip_address | String(45) |
| created_at | DateTime |

فهارس: idx_activity_user, idx_activity_entity, idx_activity_created.
تُسجَّل كل العمليات (إضافة/تعديل/حذف/استيراد/نسخ/استعادة/حذف نسخة/إعادة تعيين).

### 6.7 import_cache (ذاكرة مؤقتة للاستيراد)
| العمود | النوع |
|---|---|
| id | Integer PK |
| cache_key | String(64) فريد |
| data_json | Text |
| created_at | DateTime |

تُخزَّن معاينات الاستيراد وتنتهي تلقائيًا بعد **ساعة واحدة**.

### 6.8 الحساب الأساسي (recalc_client في utils.py)
```
total_debt = base_debt + مجموع كل الفواتير
total_paid = base_paid + مجموع كل الدفعات
status = 'paid' إذا balance <= 0 وإلا 'due'
```
وهذا يعني أن المبالغ الأساسية المحمَّلة من الاستيراد تُحفظ في base_debt/base_paid،
وأي فاتورة/دفعة لاحقة تُضاف فوقها.

### 6.9 ترقيات قاعدة البيانات
- `upgrade_db.py`: يضيف الأعمدة/الجداول المفقودة للقواعد القديمة (قائمة بيضاء للجداول،
  وبدون حقن SQL)، ويُعيد تعبئة base_debt/base_paid للعملاء المستوردين.
- `alembic\env.py`: مهيّأ مع `render_as_batch=True` (لدعم SQLite) ويستخدم `db.metadata`.
  الترحيلة الأولى: `c9da808b5967_initial_schema.py`.
  الأوامر: `python -m alembic upgrade head` و `python -m alembic revision --autogenerate -m "..."`.

---

## 7) الصفحات والمسارات (واجهة المستخدم)

### 7.1 صفحة العملاء `clients_bp` (templates\index.html)
| المسار | الوصف |
|---|---|
| `GET /` | قائمة العملاء: بحث بالاسم/الهاتف، فلتر الحالة (due/paid)، ترقيم 20 لكل صفحة، 5 بطاقات إحصائيات (عدد العملاء، مستحق، مدفوع، إجمالي المديونية، إجمالي المدفوع، الرصيد) |
| `GET/POST /client/add` | إضافة عميل (الاسم مطلوب، الهاتف اختياري، ملاحظات) |
| `GET /client/<id>` | صفحة تفاصيل العميل مع فواتيره ودفعاته |
| `GET/POST /client/<id>/edit` | تعديل العميل |
| `POST /client/<id>/delete` | حذف العميل (admin فقط) |
| `GET/POST /client/<id>/settings` | إعدادات التذكير للعميل (انظر البند 9) |
| `POST /api/toggle-dark` | تبديل الوضع الليلي (جلسة) |

### 7.2 الفواتير `invoices_bp` (تُدار من صفحة العميل)
| المسار | الوصف |
|---|---|
| `POST /client/<id>/invoice/add` | إضافة فاتورة (مبلغ + وصف + تاريخ + صورة اختيارية png/jpg/jpeg/gif/webp/pdf) |
| `POST /invoice/<id>/edit` | تعديل فاتورة (يستبدل الصورة) |
| `POST /invoice/<id>/delete` | حذف فاتورة (يحذف ملف الصورة) + إعادة حساب العميل |

### 7.3 الدفعات `payments_bp`
| المسار | الوصف |
|---|---|
| `POST /client/<id>/payment/add` | تسجيل دفعة (مبلغ + تاريخ + ملاحظات + طريقة دفع) |
| `POST /payment/<id>/edit` | تعديل دفعة |
| `POST /payment/<id>/delete` | حذف دفعة + إعادة حساب |

### 7.4 التقارير `reports_bp`
| المسار | الوصف |
|---|---|
| `GET /report` | تقرير كامل مع فلترة تاريخ إنشاء + إجماليات (مديونية/مدفوع/متبقي) |
| `GET /advanced-report` | تقرير متقدم (عملاء مستحقون مرتبون تنازليًا + المدفوعون) |
| `GET /aging` | تقرير الأعمار: حالي (<30) / 30-60 / 61-90 / أكثر من 90 حسب آخر فاتورة |
| `GET /compare` | PDF مقارنة بين الشهر الحالي والسابق |
| `GET /export` | تصدير Excel (مع فلترة بحث/حالة/تاريخ) |
| `GET /export/pdf` | تصدير PDF |
| `GET /export/save?fmt=xlsx/pdf` | حفظ في مجلد exports وإرجاع المسار |
| `GET /import` | صفحة استيراد Excel/CSV (انظر البند 10) |
| `GET /import/template` | تنزيل نموذج الاستيراد sample_import.xlsx |
| `GET /backup` | نسخة احتياطية فورية (admin فقط) |

### 7.5 الإعدادات `whatsapp_bp` (templates\settings.html — تبويبات)
| التبويب | المحتوى |
|---|---|
| عام | الدولة (مصر/السعودية) + المنطقة الزمنية + العملة + رمزها + قفل تسجيل الدخول |
| واتساب (Baileys) | عنوان الجسر + حالة الاتصال + رمز QR + زر "تشغيل الخدمة" + زر خروج |
| التذكيرات | تفعيل/تعطيل + الأوقات (CSV) + التكرار + اليوم + يوم الشهر + رابط الدفع |
| القوالب | قوالب الرسائل الثلاثة (تحتوي {name} و {balance}) |
| قاعدة البيانات | إحصائيات + نسخ + استعادة + تحميل/حذف نسخ + فحص سلامة + تحسين (Vacuum) |

### 7.6 المستخدمون `auth_bp` (templates\users.html)
- صفحة إدارة المستخدمين (admin فقط): عرض، إضافة (دور viewer/editor/admin)،
  تفعيل/تعطيل، حذف. لا يمكن تعطيل/حذف حسابك الخاص.

### 7.7 الأخطاء
templates\errors\base.html (و 404.html و 500.html).

---

## 8) REST API — `app\api\__init__.py`

الموثّق تلقائيًا عبر Swagger على `/apidocs/`. جميع النقاط تتطلب تسجيل دخول.

| المسار | الطريقة | الوصف | حد المعدل |
|---|---|---|---|
| `/api/v1/clients` | GET | قائمة العملاء مع page/per_page/q/status | 30/دقيقة |
| `/api/v1/clients` | POST | إضافة عميل (JSON أو form) | 10/دقيقة |
| `/api/v1/clients/<id>` | GET | تفاصيل عميل مع فواتيره ودفعاته | |
| `/api/v1/clients/<id>` | PUT | تعديل عميل | |
| `/api/v1/clients/<id>` | DELETE | حذف عميل (admin) | |
| `/api/v1/clients/<id>/invoices` | POST | إضافة فاتورة | |
| `/api/v1/invoices/<id>` | DELETE | حذف فاتورة | |
| `/api/v1/clients/<id>/payments` | POST | إضافة دفعة | |
| `/api/v1/payments/<id>` | DELETE | حذف دفعة | |
| `/api/v1/reports/summary` | GET | إحصائيات عامة | 20/دقيقة |
| `/api/v1/reports/trends` | GET | اتجاه 6 أشهر | 20/دقيقة |
| `/api/v1/reports/aging` | GET | توزيع الأعمار (current/30/60/90) | |
| `/api/v1/activity` | GET | سجل النشاط (admin) | |
| `/api/v1/users` | GET | قائمة المستخدمين (admin) | |

صلاحيات: العمليات الكتابية تتطلب `can_edit`، الحذف يتطلب `is_admin`.

### API إدارة قاعدة البيانات — `app\database\__init__.py`
| المسار | الوصف |
|---|---|
| `GET /api/database/stats` | إحصائيات (حجم، عدد الجداول، النسخ الاحتياطية) |
| `POST /api/database/backup` | إنشاء نسخة احتياطية |
| `POST /api/database/import` | استيراد ملف .db (يأخذ نسخة تلقائية أولًا) |
| `POST /api/database/restore` | استعادة من نسخة احتياطية |
| `GET /api/database/download-backup` | تحميل نسخة |
| `POST /api/database/delete-backup` | حذف نسخة |
| `POST /api/database/reset` | مسح كل العملاء/الفواتير/الدفعات (تأكيد DELETE_ALL) |
| `GET /api/database/export-db` | تحميل قاعدة البيانات كاملة |
| `POST /api/database/save-export` | حفظ نسخة في مجلد exports |
| `GET /api/database/integrity` | فحص سلامة (integrity/quick/foreign keys/page) |
| `POST /api/database/optimize` | vacuum / reindex / analyze |

ملاحظات أمان: التحقق من أسماء الملفات (يمنع `..` والفواصل)، قفل استعادة
`threading.Lock`، فحص رأس SQLite قبل أي عملية، `sqlite3.backup()` للاتساق،
WAL checkpoint قبل النسخ.

---

## 9) المجدول والتذكيرات — APScheduler

### 9.1 المهام الثابتة
| المهمة | التوقيت | الوصف |
|---|---|---|
| `daily_backup` | 3:00 صباحًا | نسخة احتياطية + حذف النسخ الأقدم من 30 يوم + تنظيف exports الأقدم من 7 أيام |
| `cleanup_uploads` | 00:00 | حذف الصور المرفوعة الأقدم من `upload_retention_days` (افتراضي 7) |

### 9.2 تذكيرات واتساب
- تُنشأ فقط إذا كان `Settings.get('reminder_enabled') == 'true'`.
- لكل وقت/تكرار/يوم يُضاف `CronTrigger` (مع `misfire_grace_time=3600`).
- عند التنفيذ، `send_scheduled_reminders()` تبدأ خيطًا خلفيًا `_send_reminders_background`:
  - تختار العملاء `status='due' AND reminder_enabled=True` مع رقم هاتف.
  - تطابق تفضيلات العميل مع تفضيلات التذكير المشغَّل (freq/day/dom/time).
  - تنام عشوائيًا 3–8 ثوانٍ بين كل عميل لتجنب الحظر.
  - تبني الرسالة من القالب (`template_1/2/3`) + رابط الدفع إن وُجد.
  - ترسل عبر `send_whatsapp()` وتُسجّل النتيجة في `app.log`.
  - أي خطأ يُسجَّل في `logs\background_errors.log` دون إيقاف باقي العملاء.

### 9.3 إعدادات تذكير عميل معيّن (صفحة client settings)
- `reminder_enabled` (مربع اختيار)
- `reminder_template` (1/2/3)
- `reminder_times` بصيغة `HH:MM,HH:MM` — فارغ = يتبع الإعداد العام
- `reminder_frequency` (daily/weekly/monthly) — فارغ = عام
- `reminder_day` (sun..sat) — فارغ = عام
- `reminder_dom` (1..31) — فارغ = عام
- التحقق صارم (صيغة الوقت والتكرار واليوم ويوم الشهر).

> **افتراضيًا على تثبيت جديد التذكيرات معطلة** (الجدول فارغ أو reminder_enabled=false).
> لا يُرسل شيء حتى تُفعَّل من الإعدادات + عملاء بحالة due وتذكير مفعّل.

---

## 10) الاستيراد من Excel/CSV — التفاصيل الكاملة

### 10.1 النموذج العام (generic)
- الصيغات: `.xlsx` و `.csv` (مع اكتشاف ترميز: utf-8-sig → utf-8 → cp1256 → cp1252 → latin-1).
- اكتشاف الأعمدة تلقائيًا عبر كلمات مفتاحية:
  - name ← اسم/عميل/name
  - phone ← هاتف/موبايل/جوال/رقم
  - total_debt ← مديونية/مبلغ/رصيد/amount
  - total_paid ← مدفوع/سداد/paid
  - notes ← ملاحظ/بيان/notes
- معاينة مع تحديد الصفوف الصالحة والخاطئة والمكررة (باسم متطابق).
- إعادة تخطيط الأعمدة يدويًا (remap) من صفحة المعاينة.
- أوضاع الاستيراد: `new_only` (جدد فقط) / `update_existing` (تحديث الموجود وإضافة الجدد) / overwrite.
- تحميل نموذج جاهز: `/import/template`.

### 10.2 النموذج المحاسبي المتخصص (accounting_excel.py)
- اكتشاف تلقائي: يحتوي الملف على شيتين `all` (الحركات) و `Data` (ملخص العملاء).
- `all`: 17 عمودًا (تسلسل، كود العميل، رقم التقرير، المالك، اسم العميل، الموقع،
  الصنف، التاريخ، الكمية، السعر، مدين، دائن، البيان، الفرع، طريقة الدفع، الشهر)
  مع اكتشاف رأس ديناميكي و fallbacks ثابتة.
- `Data`: الكود | م | كود الحساب | اسم العميل | الإيرادات | التحصيلات | الرصيد | النسبة.
  ملاحظة: الأعمدة المالية SUMIF صيغ قد تُرجع None (الملف لم يُفتح في Excel)،
  فيُحسب الإجمالي من حركات شيت `all`.
- شيت المراجع `بيان العملاء`: الفروع، طرق الدفع، أنواع الإيرادات.
- معاينة غنية (مكررات، إجماليات إيراد/تحصيل/رصيد) ثم استيراد بطرق الأوضاع الثلاثة.
- عند الاستيراد: العميل يُنشأ بـ `notes="كود: ..."` و base_debt/base_paid = الإيراد/التحصيل.

---

## 11) واتساب (Baileys) — التفاصيل الكاملة

### 11.1 الجسر `baileys_service\index.js`
- خادم Express يستمع على `127.0.0.1:3001`.
- يستخدم مكتبة `@whiskeysockets/baileys` (بروتوكول واتساب ويب) — مجاني وبدون API رسمي.
- الجلسة تُخزَّن في `baileys_service\auth_session` (تبقى متصلة بعد أول مسح QR).
- واجهة داخلية (اختياري حماية بـ `BAILEYS_API_TOKEN` عبر هيدر `x-api-token`):
  - `GET /status` → `{status, qr, error}` حيث status ∈ {disconnected, connecting, qr, connected}
  - `POST /send` → `{to, message}` يُحوَّل الرقم تلقائيًا ثم يُرسل، مهلة 30 ثانية
  - `POST /logout` → يخلي الجلسة ويعيد الاتصال
- طابور إرسال بفاصل عشوائي 3–8 ثوانٍ لتجنب الحظر.
- معالجات أخطاء عامة تمنع انهيار العملية + إعادة اتصال تلقائية بعد 3 ثوانٍ.

### 11.2 تحويل الأرقام (normalize_phone)
المنطق متطابق في Python (`app/utils.py`) و JavaScript (`index.js`):
| الرقم المدخل | النتيجة |
|---|---|
| مصري موبايل `010...` | `2010...` |
| مصري موبايل `011/012/015...` | `2011/2012/2015...` |
| مصري أرضي `02...` | `202...` |
| سعودي `05...` | `9665...` |
| رقم دولي `966...` أو `20...` | يُترك كما هو |
| يبدأ بـ `00` | يُحذف 00 أولًا |
| رمز الدولة في التطبيق (مصر/السعودية) يُستخدم للحالات غير المعروفة |

> أي رقم يبدأ بـ 0 يتحول حسب بادئته أولًا (01/02 → مصر، 05 → سعودية)
> حتى لو كانت دولة التطبيق مختلفة.

### 11.3 الإرسال من التطبيق (send_whatsapp)
1. يطبّع الرقم ثم `GET {baileys_url}/status` (مهلة 5 ثوانٍ).
2. إذا لم يكن `connected` → يُرجع رسالة "واتساب غير متصل".
3. `POST {baileys_url}/send` (مهلة 60 ثانية).
4. رسائل خطأ عربية واضحة عند انقطاع الجسر أو انتهاء المهلة.

### 11.4 الإعداد التلقائي (auto-setup)
- عند إقلاع البرنامج: `_auto_setup_baileys()` يستدعي `ensure_baileys_ready()`:
  - يتحقق من وجود Node.js و npm.
  - لو `node_modules/@whiskeysockets/baileys` غائب → `npm install --no-audit --no-fund`
    تلقائيًا (مع تحويل git SSH→HTTPS لمنع فشل تثبيت libsignal).
  - ثم `start_baileys_bridge()`: يفحص المنفذ 3001، وإن لم يكن شغالًا يشغّل
    `node index.js` كعملية منفصلة تسجّل في `baileys.log`.
- زر "تشغيل الخدمة" في الإعدادات يستخدم نفس الدالتين.
- أول تشغيل: امسح رمز QR من صفحة الإعدادات على هاتفك، وبعدها تبقى متصلة تلقائيًا.
- المتطلبات: **Node.js 18+** و **Git** (Git مطلوب فقط عند تثبيت الاعتماديات).
- بدون Node يعمل باقي البرنامج (إدارة الديون والفواتير) عاديًا — واتساب فقط معطل.

---

## 12) الأمان والحماية

- كلمات مرور مشفرة (werkzeug).
- CSRF على كل النماذج + كوكي csrf_token.
- قيود معدل: تسجيل الدخول 10/دقيقة، API 10–30/دقيقة، تقارير 20/دقيقة.
- رؤوس أمان أمان على كل استجابة.
- حماية `next` في تسجيل الدخول من redirect مفتوح (فحص scheme/netloc).
- التحقق من المبالغ (موجبة > 0) والاسم والهاتف عبر نماذج Flask-WTF.
- لا يمكن للمستخدم تعطيل/حذف حسابه.
- صلاحيات أدوار: viewer (قراءة فقط)، editor (قراءة + تعديل)، admin (كل شيء).
- ملفات الرفع: امتدادات بيضاء فقط + أسماء آمنة (secure_filename + uuid).
- منع SQL injection (ORM + معلمات).
- قفل تشغيل مزدوج (lock/pid files).
- `stop.bat` يقفل المنافذ 5000/9999/3001.

---

## 13) النسخ الاحتياطية والتصدير

- **تلقائية:** يوميًا 3:00 صباحًا في `backups\db_backup_YYYYMMDD_HHMMSS.db`.
  يُحذف ما يتجاوز 30 يومًا. التصدير في `exports\` يُحذف بعد 7 أيام.
- **يدوية:** زر في الإعدادات أو `GET /backup`.
- كل العمليات تستخدم `sqlite3.Connection.backup()` (نسخة متسقة أثناء الكتابة)
  مع WAL checkpoint وتحديد مهلة والتحقق من سلامة الملف.
- تصدير Excel بجداول منسقة (عناوين، ألوان، صيغ أرقام، RTL) و PDF بتنسيق عربي.
- تقرير مقارنة الفترات (الشهر الحالي/السابق) PDF.
- تصدير/استيراد قاعدة البيانات كاملة بصيغة .db.

---

## 14) السجلات (Logs) — في مجلد `logs\`
| الملف | المحتوى |
|---|---|
| `app.log` | سجل التطبيق (5MB × 3 نسخ) |
| `startup.log` | كل خطوات إقلاع debt_manager.pyw (Debug) |
| `background_errors.log` | أخطاء مهام الخلفية (2MB × 3 نسخ) |
| `baileys.log` | سجل جسر واتساب (في baileys_service) |

---

## 15) الواجهة (templates + static)

القوالب: base.html (هيكل مشترك مع الوضع الليلي)، index.html، client_edit.html،
client_detail.html، client_settings.html، import.html، report.html،
advanced_report.html، aging_report.html، settings.html، users.html، login.html، errors\.

الثوابت: bootstrap.rtl.min.css، bootstrap.bundle.min.js، bootstrap-icons.min.css،
chart.umd.min.js (رسوم بيانية)، css/ و js/، خطوط، أصوات (sounds/)، favicon.ico.

ميزات الواجهة: بطاقات إحصائيات، بحث، ترقيم، وضع ليلي (زر في الشريط)،
أزرار إجراءات لكل عميل، نوافذ تعديل سريعة، RTL كامل، خط IBM Plex Sans Arabic.

---

## 16) البناء والتثبيت (Packaging)

### 16.1 بناء الـ EXE — `build_exe.py`
1. يبحث عن Python (Python312/313 ثم venv ثم PATH).
2. يشغّل PyInstaller بـ `python -m PyInstaller`:
   - `--onedir --windowed --icon=icon.ico --name=DebtManager`
   - يضم `templates`, `static`, `icon.ico`, `baileys_service/index.js + package.json + Dockerfile`
   - قائمة hidden-imports شاملة لكل الوحدات (flask, sqlalchemy, reportlab, openpyxl,
     apscheduler, psutil, flasgger, limits, marshmallow, yaml, ...) و collect-submodules.
3. بعد النجاح: ينسخ أيقونة + مجلد `baileys_service` (بدون node_modules/auth_session)
   + ملفات `install_baileys.bat`, `start_baileys.bat`, `stop.bat` إلى مجلد الناتج.
4. الناتج: `dist\DebtManager\DebtManager.exe`.

### 16.2 المثبّت النهائي — `installer.iss` (Inno Setup)
- الأوامر: `"C:\Users\YUZZRY\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss`
- الاسم: DebtManagerSetup.exe — التثبيت في `{userappdata}\DebtManager` (بدون صلاحيات إدارية).
- لغات: عربي + إنجليزي.
- يضم: الـ exe، الأيقونة، الـ bat files، `_internal\*`، `baileys_service\*`
  (مع استثناء `auth_session`).
- **لا يضم** قاعدة البيانات أو المفاتيح أو السجلات — يتولد دائمًا قاعدة فارغة عند أول تشغيل.
- بعد التثبيت: يفحص Node.js (يفتح صفحة تنزيله إن غاب) و Git (ملاحظة فقط).
- الناتج الحالي: `dist\installer\DebtManagerSetup.exe` — **52.1 MB** (8/2/2026 5:26 م).

### 16.3 ملفات التشغيل المساعدة
- `install.bat`: يفحص Python/Node/Git → ينشئ venv → pip install → مجلدات →
  npm install (بايلز) → تهيئة قاعدة البيانات → `python upgrade_db.py`.
- `start.bat`: يشغّل بايلز ثم `pythonw run_production.py` ثم يفتح المتصفح.
- `launch.vbs`: تشغيل صامت (pythonw أو exe) بدون نافذة كونسول.
- `stop.bat`: يقتل المنافذ 5000/9999/3001 وينظف الأقفال.

---

## 17) الاختبارات

- `tests\` — اختبارات pytest مع `conftest.py` (create_app(testing=True) بقاعدة في الذاكرة).
  تشمل: test_all.py، test_clients.py، test_full.py.
- `test_deep.py` — فحص عميق: إقلاع، admin، المجدول، API قاعدة البيانات، سجل النشاط...
- `test_edge.py` — حالات حافة.
- التشغيل: `python -m pytest tests` (من مجلد المشروع مع تفعيل venv).

---

## 18) سجل الإصلاحات السابقة (ملخص)

### الجولة 1 (v1.1.0) — 14 إصلاحًا
utcnow → helper، منع SQL injection في upgrade_db، Numeric للمبالغ، إزالة كود ميت،
قفل للاستيراد، التذكيرات في خيط خلفي، إصلاح SchedulerAlreadyRunningError،
قفل تسجيل الدخول، إلخ.

### الجولة 2 (v1.2.0)
معالجة أخطاء الخلفية، ImportCache بقاعدة البيانات، نماذج Flask-WTF مع validators،
Alembic، استبدال Query.get بـ db.session.get، Swagger، تنظيف المرفوعات،
value_type للإعدادات، نسخ متسقة عبر sqlite3.backup.

### الجولة 3 (v1.3.0) — نافذة سطح المكتب
Eel، كشف المتصفح تلقائيًا، مراقبة إغلاق النافذة، lock/pid، أيقونة المحفظة،
stop.bat، وتحسينات عميقة لقاعدة البيانات (integrity + optimize + stats + logging).

### الإصلاحات الأخيرة (المشروع الحالي)
1. **إزالة Eel نهائيًا** — خادم waitress واحد على 5000 ونافذة Chrome مباشرة
   (كانت نسخة Eel تتطلب منفذًا ثانيًا 9999 وتسبب تعقيدات).
2. **نافذة كروم بملف تعريف مخصص** `.app_chrome_cache` — حل مشكلة اختفاء النافذة
   عندما يستحوذ كروم شغّال على الرابط.
3. **رصد الإغلاق عبر `_browser_proc.poll()`** مع عدّاد (مرتان متتاليتان) ثم إغلاق البرنامج.
4. **`_kill_profile_chrome()`** — قتل كروم الملف التعريفي العالق عند الإطلاق والإغلاق
   (كان يموت البرنامج صامتًا بسبب psutil غير المجمّع → ثُبّت psutil + أسلوب دفاعي + تسجيل).
5. **التشغيل التلقائي لواتساب** — تثبيت node_modules ذاتيًا وتشغيل الجسر على 3001
   من `_auto_setup_baileys()` دون أي خطوة يدوية، مع زر "تشغيل الخدمة" في الإعدادات.
6. **تحويل أرقام مصري/سعودي** موحّد في Python و JS.

---

## 19) حالة البيانات على هذا الجهاز الآن (مهم)

قاعدة `instance\debtors.db` الحالية على جهاز التطوير تحتوي **بيانات اختبار/عمل**:
- `clients`: **3100 عميل** (من استيراد سابق مثل `متاخرين السداد.xlsx`)
- `invoices` / `payments`: 0
- `settings`: 11 مفتاحًا — الدولة **السعودية**، المنطقة Asia/Riyadh،
  والعملة ر.س، و `reminder_enabled=true` (بوقت 10:00 يوميًا)
- `users`: admin + admin1
- `activity_log`: 5

> **تنبيه:** المثبّت النهائي (`DebtManagerSetup.exe`) **لا يضم هذه البيانات**
> (المثبّت يستثني instance/ نهائيًا)، وعند التثبيت النظيف على جهاز آخر تُنشأ
> قاعدة فارغة تلقائيًا مع مستخدم admin/admin123 فقط.
> إذا أردت تسليم بياناتك، استخدم استيراد/تصدير قاعدة البيانات من الإعدادات.

---

## 20) بيانات الدخول الافتراضية

- المستخدم: `admin`
- كلمة المرور: `admin123`
- ⚠️ **غيّر كلمة المرور فورًا** من صفحة المستخدمين بعد أول دخول.

---

## 21) دليل سريع للتشغيل

### على جهاز التطوير (من الكود المصدري)
1. `install.bat` (ينشئ البيئة ويجهّز كل شيء)
2. `start.bat` أو `launch.vbs` أو `python debt_manager.pyw`

### للمستخدم النهائي
1. شغّل `dist\installer\DebtManagerSetup.exe`
2. اختار اللغة (عربي/إنجليزي) → التثبيت في `%AppData%\DebtManager`
3. أول تشغيل: ادخل admin/admin123 وغيّر كلمة المرور
4. للواتساب: تأكد من وجود Node.js (سيفتح صفحة تنزيله إن غاب) ثم من
   الإعدادات → واتساب → شغّل الخدمة → امسح QR
5. بياناتك تُخزَّن محليًا في مجلد التثبيت ولا تُرفع لأي خادم خارجي

### إعادة البناء من الصفر
1. `python build_exe.py` → ينتج `dist\DebtManager`
2. `ISCC.exe installer.iss` → ينتج `dist\installer\DebtManagerSetup.exe`

---

## 22) المنافذ المستخدمة
| المنفذ | الخدمة |
|---|---|
| 5000 | خادم Flask/Waitress (التطبيق) |
| 3001 | جسر واتساب Baileys (Node) |
| 9999 | كان خاصًا بـ Eel — **أُزيل** ويبقى مذكورًا في stop.bat كاحتياط |