# برومبت المشروع الكامل — نظام إدارة المديونيات والتجارة (Debt Manager)

> وثيقة مرجعية شاملة تصف المشروع **بكامل مواصفاته** كما هو موجود الآن على الجهاز.
> المسار الجذري: `C:\Users\YUZZRY\Desktop\debt_manager_dev`
> آخر تحديث للتوثيق: 2026-08-11

---

## 1) نظرة عامة

نظام سطح مكتب + متصفح (عربي RTL بالكامل) لإدارة **المديونيات** و**التجارة**:

- **وضع المديونية (debt):** عملاء، فواتير، دفعات، تذكيرات واتساب تلقائية، تقارير أعمار الديون.
- **وضع التجارة (commerce):** منتجات، تصنيفات، مخزون، مبيعات (نقطة بيع POS)، أوامر شراء، لوحة تحكم وإحصائيات.
- **محاسبة مزدوجة اختيارية:** دليل حسابات، قيود يومية تلقائية من العمليات، دفتر أستاذ، ميزانية، قائمة دخل، تدفق نقدي، ميزان مراجعة، إقفال سنوي.
- **نافذة التطبيق:** تُفتح تلقائيًا داخل Chrome/Edge بوضع `--app` مع ملف تعريف مخصص.

### نقاط الدخول
| الملف | الوظيفة |
|---|---|
| `debt_manager.pyw` | نقطة الدخول لسطح المكتب (الخادم + النافذة + واتساب تلقائيًا) |
| `run_production.py` | تشغيل الخادم فقط عبر Waitress (بدون نافذة) |
| `build_exe.py` | بناء الـ EXE عبر PyInstaller |

### البنية التشغيلية
- الخادم: **Flask + Waitress** على `http://127.0.0.1:5000` (4 خيوط افتراضيًا).
- واتساب: جسر Node.js محلي (Baileys) على المنفذ `3001` — مجاني وبدون API رسمي.
- قاعدة البيانات: **SQLite** في `instance\debtors.db` (وضع WAL) مع دعم PostgreSQL عبر `DATABASE_URL`.
- الواجهة: Bootstrap 5 (RTL) + Bootstrap Icons + خط IBM Plex Sans Arabic + Chart.js للرسوم.

---

## 2) التقنيات والمكتبات بالإصدارات

### 2.1 Python (المثبتة فعليًا في venv)
| المكتبة | الإصدار | الاستخدام |
|---|---|---|
| Flask | 3.1.3 | إطار الويب |
| SQLAlchemy | 2.0.51 | ORM |
| Flask-SQLAlchemy | 3.1.1 | تكامل SQLAlchemy مع Flask |
| Flask-Login | 0.6.3 | جلسات المستخدمين |
| Flask-WTF | 1.3.0 | حماية CSRF + نماذج |
| WTForms | 3.2.2 | نماذج والتحقق |
| Flask-Compress | 1.24 | ضغط الاستجابات (gzip) |
| Flask-Limiter | 3.12 | حدود معدل الطلبات |
| APScheduler | 3.11.3 | المهام المجدولة (نسخ/تذكيرات/تنظيف) |
| Alembic | 1.19.0 | ترحيلات قاعدة البيانات |
| flasgger | 0.9.7.1 | توثيق API عبر Swagger UI |
| openpyxl | 3.1.5 | استيراد/تصدير Excel |
| reportlab | 4.5.1 | توليد تقارير PDF |
| arabic-reshaper | 3.0.1 | تشكيل النص العربي |
| python-bidi | 0.6.11 | اتجاه النص العربي |
| python-barcode | 0.16.1 | باركود المنتجات |
| requests | 2.34.2 | التواصل مع جسر واتساب |
| python-dotenv | 1.2.2 | متغيرات البيئة |
| psycopg2-binary | 2.9.12 | دعم PostgreSQL الاختياري |
| Werkzeug | 3.1.8 | WSGI + تشفير كلمات المرور |
| waitress | 3.0.2 | خادم الإنتاج |
| Eel | 0.18.2 | موجود في requirements (غير مستخدم فعليًا) |
| pywin32 | 312 | أيقونة النافذة ورسائل Windows |
| Pillow | 10.4.0 | معالجة الصور |
| psutil | 7.2.2 | مراقبة عمليات المتصفح وقتل الكروم العالق |
| python-escpos | 3.1 | الطباعة الحرارية لإيصالات POS |
| pytest | 9.1.1 | الاختبارات |
| pytest-cov | 7.1.0 | تغطية الكود |
| pyinstaller | 6.21.0 | التغليف |
| greenlet | 3.5.4 | اعتماد SQLAlchemy |

### 2.2 Node.js (اختياري — واتساب فقط)
- Node.js **18+** (مطلوب فقط لخدمة بايلز؛ البرنامج يعمل بدونه).
- `@whiskeysockets/baileys` — جسر واتساب ويب في `baileys_service\`.
- Express يستمع على `127.0.0.1:3001`.

---

## 3) المعمارية

### 3.1 هيكل المجلدات
```
debt_manager_dev\
├── debt_manager.pyw          ← نقطة الدخول لسطح المكتب
├── run_production.py         ← تشغيل الخادم فقط
├── build_exe.py              ← بناء الـ EXE
├── upgrade_db.py             ← ترقية قواعد قديمة
├── requirements.txt
├── icon.ico
├── app\                      ← كود Flask
│   ├── __init__.py           ← create_app + إعدادات + مجدول + أمان + ترحيل خفيف
│   ├── models.py             ← كل النماذج
│   ├── utils.py              ← دوال مساعدة (PDF/Excel/واتساب/نسخ/استيراد)
│   ├── auth\                 ← دخول + مستخدمون + أدوار
│   ├── clients\              ← عملاء + حساب فرعي محاسبي
│   ├── invoices\             ← فواتير
│   ├── payments\             ← دفعات
│   ├── reports\              ← تقارير + استيراد/تصدير + أعمار الديون
│   ├── whatsapp\             ← إعدادات واتساب والتذكيرات
│   ├── api\                  ← REST API
│   ├── database\             ← إدارة القاعدة (نسخ/استعادة/فحص/تحسين)
│   ├── products\             ← منتجات/تصنيفات/مخزون/باركود
│   ├── purchases\            ← أوامر الشراء
│   ├── pos\                  ← نقطة البيع + طباعة حرارية (printer.py)
│   ├── accounts\             ← دليل الحسابات + قيود + دفتر أستاذ + قوائم مالية
│   │   ├── __init__.py       ← دليل الحسابات + التقارير المالية
│   │   ├── ledger.py         ← دفتر الأستاذ (الرصيد الجاري)
│   │   └── auto.py           ← القيود التلقائية (قيد مزدوج)
│   ├── dashboard\            ← لوحة تحكم التجارة والتقارير
│   └── importers\            ← accounting_excel.py (مُحلِّل محاسبي)
├── baileys_service\          ← جسر واتساب (index.js + package.json)
├── templates\                ← HTML عربي RTL
├── static\                   ← Bootstrap/CSS/JS/خطوط/أيقونات
├── tests\                    ← اختبارات pytest
├── instance\                 ← debtors.db + .secret_key + أقفال
├── logs\                     ← app.log + startup.log + background_errors.log
├── backups\                  ← نسخ احتياطية
├── exports\                  ← ملفات التصدير
├── uploads\                  ← صور الفواتير
└── dist\                     ← مخرجات البناء (DebtManager\ + installer\)
```

### 3.2 نمط `create_app` (factory)
`app\__init__.py`:
- تحديد `BASE_DIR`/`DATA_DIR` (يراعي وضع `frozen` لـ PyInstaller).
- `SECRET_KEY`: متغير بيئة ← ملف `instance\.secret_key` ← توليد تلقائي.
- قاعدة البيانات: `sqlite:///instance/debtors.db` (أو `DATABASE_URL`)؛ في الاختبار `:memory:`.
- الامتدادات: SQLAlchemy، CSRFProtect، LoginManager، Compress، Limiter، BackgroundScheduler، Swagger (flasgger).
- عند الإقلاع داخل `app_context`:
  1. `db.create_all()`
  2. `_apply_schema_migrations(db)` — ترحيل خفيف: يضيف عمود `account_id` لجداول clients القائمة (SQLite).
  3. `_ensure_default_admin()` — إنشاء `admin/admin123` لو الجدول فارغ.
  4. `_init_scheduler(app)` — المجدول.
  5. `_enable_sqlite_wal(app)` — PRAGMAs لكل اتصال: `journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`.

### 3.3 البلوبرينتات والبادئات
| البلوبرينت | البادئة | المسؤولية |
|---|---|---|
| auth_bp | — | دخول/خروج/مستخدمون/تبديل الوضع |
| clients_bp | — | العملاء + كشوف الحساب |
| invoices_bp | — | الفواتير |
| payments_bp | — | الدفعات |
| whatsapp_bp | — | واتساب + الإعدادات العامة |
| reports_bp | — | تقارير/استيراد/تصدير/أعمار |
| api_bp | `/api` | REST API |
| database_bp | — | إدارة قاعدة البيانات |
| products_bp | `/products` | المنتجات/التصنيفات/المخزون |
| purchases_bp | `/purchases` | أوامر الشراء |
| pos_bp | `/pos` | نقطة البيع |
| accounts_bp | `/accounts` | المحاسبة |
| dashboard_bp | `/dashboard` | لوحة تحكم التجارة |

`strict_slashes = False` (لا يتأثر بالشرطة المائلة).

### 3.4 معالجة الأخطاء
- 400/403/404/405/500: صفحة عربية جميلة؛ ولطلبات `/api/*` استجابة JSON `{'ok': False, 'msg': ...}`.
- رؤوس أمان تُضاف في `after_request` (انظر قسم الأمان).

---

## 4) نموذج البيانات (SQLite / `app\models.py`)

### 4.1 users (المستخدمون)
| العمود | النوع | ملاحظات |
|---|---|---|
| id | Integer PK | |
| username | String(80) | فريد، مفهرس |
| password_hash | String(256) | werkzeug |
| role | String(20) | admin / editor / viewer / cashier / accountant |
| is_active_flag | Boolean | تفعيل/تعطيل |
| created_at | DateTime | |

خواص الدور: `is_admin`=admin، `can_edit`=admin+editor، `can_pos`=admin+cashier، `can_accounting`=admin+accountant.

### 4.2 clients (العملاء)
| العمود | النوع | ملاحظات |
|---|---|---|
| id | Integer PK | |
| name | String(200) | مطلوب |
| type | String(20) | customer / supplier / employee |
| company_name / tax_id | String | اختياري |
| phone | String(30) | |
| notes | Text | |
| total_debt / total_paid | Numeric(10,2) | الإجماليات المحسوبة |
| base_debt / base_paid | Numeric(10,2) | الأساس من الاستيراد |
| status | String(20) | due / paid |
| reminder_enabled | Boolean | |
| reminder_template | Integer | 1/2/3 |
| reminder_times | Text | "10:00,14:00" أو فارغ (عام) |
| reminder_frequency | String(10) | daily / weekly / monthly |
| reminder_day | String(10) | sun..sat |
| reminder_dom | Integer | 1..31 |
| created_at / updated_at | DateTime | |
| **account_id** | FK → accounts.id | الحساب الفرعي المحاسبي (nullable) |

فهارس: idx_client_status/name/phone/updated/type.
خاصية `balance = max(0, total_debt - total_paid)`.
Cascade: حذف العميل يحذف فواتيره ودفعاته.

### 4.3 categories / products (التصنيفات والمنتجات)
- **categories**: id, name (فريد), description.
- **products**: id, name, sku, barcode, category_id (FK), unit (افتراضي "قطعة"), cost_price, selling_price, current_stock, min_stock, description, is_active.
- خصائص: `stock_status` (out/low/ok) من مقارنة المخزون بالحد الأدنى.
- فهارس على name/sku/barcode/category_id.

### 4.4 stock_movements (حركات المخزون)
- product_id (FK), movement_type (IN/OUT/ADJUST), quantity, balance_after, reference, notes, created_by (FK users), created_at.

### 4.5 invoices (فواتير العملاء)
- client_id (FK), description(500), amount Numeric(10,2), sale_id (FK sales، إن نشأت من POS), date, image_path(500), created_at.
- فهارس: client, date.

### 4.6 payments (الدفعات)
- client_id (FK), amount, date, notes(500), payment_method(50), created_at.
- فهارس: client, date.

### 4.7 purchase_orders / purchase_items (أوامر الشراء)
- **purchase_orders**: order_number (فريد), supplier_id (FK clients), date, status (draft/received/cancelled), total_amount, notes, created_by (FK users).
- **purchase_items**: order_id (FK), product_id (FK), quantity, unit_cost.
- `recalc_total()` = مجموع الكميات × تكلفة الوحدة.

### 4.8 sales / sale_items (المبيعات)
- **sales**: invoice_number (فريد), client_id (FK، اختياري), date, subtotal, discount, total, payment_method (cash/credit), status (completed/cancelled), notes, created_by.
- **sale_items**: sale_id, product_id, quantity, unit_price.

### 4.9 accounts (دليل الحسابات)
| العمود | النوع | ملاحظات |
|---|---|---|
| id | Integer PK | |
| code | String(30) | فريد |
| name | String(200) | |
| account_type | String(20) | asset / liability / equity / income / expense |
| parent_id | FK → accounts.id | شجري |
| opening_balance | Numeric(14,2) | |
| is_active | Boolean | |
| created_at | DateTime | |

- `normal_balance`: debit للأصل/المصروف، credit للخصم/حقوق/إيراد.
- `balance()`: رصيد الحركات المباشرة + الافتتاحي.
- `is_leaf`: بدون أبناء.

### 4.10 journal_entries / journal_entry_lines (قيود اليومية)
- **journal_entries**: entry_number (فريد), date, description(500), created_by, created_at, source_type/source_id (فريدان معًا لمنع تكرار القيد: sale/purchase/invoice/payment/closing).
- **journal_entry_lines**: entry_id, account_id, debit, credit (Numeric(14,2)).
- `is_balanced`: |المدين − الدائن| < 0.005.

### 4.11 ledger_entries (دفتر الأستاذ)
- account_id, entry_id, line_id (فريد لكل سطر), date, debit, credit, running_balance.
- يُبنى من journal_entry_lines بالترتيب (تاريخ، رقم قيد، رقم سطر) ويُعاد حسابه عند الإضافة/الحذف.

### 4.12 settings (إعدادات) — انظر قسم الإعدادات
### 4.13 activity_log (سجل النشاط)
- user_id, action(50), entity_type, entity_id, details, ip_address(45), created_at.
- يُسجَّل كل شيء: إضافة/تعديل/حذف/استيراد/نسخ/استعادة/تصدير/حذف نسخة/إعادة تعيين.

### 4.14 import_cache (ذاكرة معاينة الاستيراد)
- cache_key (فريد), data_json, created_at. تنتهي تلقائيًا بعد **ساعة**.

### 4.15 الحساب الأساسي (recalc_client)
```
total_debt = base_debt + Σ الفواتير
total_paid = base_paid + Σ الدفعات
status = paid لو balance ≤ 0 وإلا due
```

### 4.16 ترحيلات القاعدة
- `_apply_schema_migrations()` في `app\__init__.py` (تشغيل تلقائي عند الإقلاع).
- `upgrade_db.py` لقواعد قديمة.
- Alembic مهيأ مع `render_as_batch=True` لدعم SQLite.

---

## 5) الإعدادات (Settings keys)

| المفتاح | النوع | الافتراضي | الوصف |
|---|---|---|---|
| app_country | string | EG | مصر / السعودية |
| app_timezone | string | Africa/Cairo | منطقة التوقيت للمجدول |
| app_currency | string | جنيه مصري | اسم العملة |
| app_currency_short | string | ج.م | اختصار العملة (يظهر في رؤوس التقارير) |
| company_name | string | '' | اسم المنشأة على التقارير المالية |
| login_locked | bool | false | قفل تسجيل الدخول (فتح بكلمة مرور admin) |
| pos_printer_name | string | '' | اسم طابعة ESC/POS الحرارية |
| auto_accounting_enabled | bool | false | تفعيل القيود المحاسبية التلقائية |
| baileys_url | string | http://localhost:3001 | عنوان جسر واتساب |
| reminder_enabled | bool | false | تفعيل التذكيرات المجدولة |
| reminder_times | string | 10:00 | أوقات CSV (HH:MM,HH:MM) |
| reminder_frequency | string | daily | daily/weekly/monthly |
| reminder_day | string | sun | يوم أسبوعي |
| reminder_dom | int | 1 | يوم شهري |
| payment_link | string | '' | رابط دفع يُلحق بالرسالة |
| template_1/2/3 | string | نص افتراضي | قوالب الرسائل ({name}/{balance}) |
| upload_retention_days | int | 7 | أيام الاحتفاظ بالصور المرفوعة |

الدول المدعومة (utils.COUNTRY_OPTIONS): مصر (رمز 20) والسعودية (رمز 966).

---

## 6) API

### 6.1 REST API (`/api`) — موثّق عبر Swagger على `/apidocs/`
كل النقاط تتطلب تسجيل دخول. الكتابة تتطلب `can_edit`؛ الحذف يتطلب `is_admin`.

| المسار | الطريقة | الوصف | حد المعدل |
|---|---|---|---|
| /api/v1/clients | GET | قائمة (page/per_page/q/status) | 30/دقيقة |
| /api/v1/clients | POST | إضافة عميل (JSON أو form) + إنشاء حساب فرعي | 10/دقيقة |
| /api/v1/clients/\<id\> | GET | تفاصيل + فواتير + دفعات | |
| /api/v1/clients/\<id\> | PUT | تعديل عميل | |
| /api/v1/clients/\<id\> | DELETE | حذف (admin) | |
| /api/v1/clients/\<id\>/invoices | POST | إضافة فاتورة | |
| /api/v1/invoices/\<id\> | DELETE | حذف فاتورة | |
| /api/v1/clients/\<id\>/payments | POST | إضافة دفعة | |
| /api/v1/payments/\<id\> | DELETE | حذف دفعة | |
| /api/v1/reports/summary | GET | إحصائيات عامة | 20/دقيقة |
| /api/v1/reports/trends | GET | اتجاه 6 أشهر | 20/دقيقة |
| /api/v1/reports/aging | GET | توزيع الأعمار (current/30/60/90) | |
| /api/v1/activity | GET | سجل النشاط (admin) | |
| /api/v1/users | GET | قائمة المستخدمين (admin) | |

### 6.2 API قاعدة البيانات (`/api/database`)
| المسار | الوصف | صلاحية |
|---|---|---|
| GET /api/database/stats | إحصائيات (حجم/جداول/نسخ) | دخول |
| POST /api/database/backup | إنشاء نسخة احتياطية | admin |
| POST /api/database/import | استيراد ملف .db (نسخة تلقائية أولًا) | admin |
| POST /api/database/restore | استعادة من نسخة | admin |
| GET /api/database/download-backup | تحميل نسخة | admin |
| POST /api/database/delete-backup | حذف نسخة | admin |
| POST /api/database/reset | مسح كل العملاء/الفواتير/الدفعات (تأكيد DELETE_ALL) | admin |
| GET /api/database/export-db | تنزيل القاعدة كاملة | admin |
| POST /api/database/save-export | حفظ نسخة في exports | admin |
| GET /api/database/integrity | فحص سلامة (integrity/quick/foreign_key/page/freelist) | admin |
| POST /api/database/optimize | vacuum / reindex / analyze | admin |

---

## 7) الصفحات والوظائف الرئيسية

### 7.1 العملاء (clients_bp)
- `GET /` — قائمة + بحث + فلتر حالة + بطاقات إحصائيات + ترقيم.
- `GET/POST /client/add` — إضافة عميل (ينشئ حسابًا فرعيًا محاسبيًا تحت 1301/2101 إن وُجد الدليل).
- `GET /client/<id>` — تفاصيل مع فواتير ودفعات وحساب العميل المحاسبي.
- `GET /client/<id>/statement` — كشف حساب برصيد جاري + فلترة تاريخ.
- `GET /client/<id>/statement/pdf` — PDF كشف الحساب.
- `GET/POST /client/<id>/edit` — تعديل (مزامنة حساب العميل).
- `POST /client/<id>/delete` — حذف (admin، يفعّل تعطيل الحساب المحاسبي).
- `GET/POST /client/<id>/settings` — إعدادات التذكير للعميل.
- `POST /api/toggle-dark` — الوضع الليلي (جلسة).

### 7.2 الفواتير (invoices_bp)
- `POST /client/<id>/invoice/add` — مبلغ + وصف + تاريخ + صورة (png/jpg/jpeg/gif/webp/pdf).
- `POST /invoice/<id>/edit` — تعديل (استبدال الصورة).
- `POST /invoice/<id>/delete` — حذف + إعادة حساب.

### 7.3 الدفعات (payments_bp)
- `POST /client/<id>/payment/add` — مبلغ + تاريخ + ملاحظات + طريقة دفع.
- `POST /payment/<id>/edit` / `delete`.

### 7.4 التقارير (reports_bp)
- `GET /report` — تقرير كامل مع فلترة تاريخ.
- `GET /advanced-report` — مستحقون تنازليًا + المدفوعون.
- `GET /compare` — PDF مقارنة شهر حالي/سابق.
- `GET /export` — تصدير Excel؛ `GET /export/pdf` — PDF؛ `GET /export/save` — حفظ في exports.
- `GET /aging` — مصفوفة أعمار الديون (حالي/30/60/90) مع **تاريخ مرجعي `?to=`**.
- `GET /aging/pdf` — PDF التقادم.
- `GET /import` + `GET /import/preview` — استيراد Excel/CSV.
- `GET /import/template` — نموذج الاستيراد.
- `GET /backup` — نسخة فورية (admin).

### 7.5 المنتجات والمخزون (products_bp)
- تصنيفات (إضافة/حذف مع منع الحذف عند وجود منتجات)، منتجات، تفاصيل، تعديل، حذف.
- ضبط المخزون IN/OUT/ADJUST مع تسجيل حركات ومنع السحب فوق المتاح.
- صفحة حركات المخزون، صفحة المخزون المنخفض، طباعة باركود (SVG/PNG).

### 7.6 المشتريات (purchases_bp)
- إنشاء أمر شراء (draft)، استلام (received → زيادة المخزون + إنشاء قيد تلقائي)، إلغاء (cancelled).
- قائمة الأوامر مع فلترة الحالة.

### 7.7 نقطة البيع (pos_bp)
- `GET /pos/` — شاشة البيع (بحث منتجات، سلة).
- `GET /api/product` — استعلام منتج (بحث/باركود).
- `POST /complete` — إتمام البيع: نقص المخزون، إنشاء Sale، فاتورة آجلة لو credit، قيد تلقائي.
- `GET /history` — سجل المبيعات مع الفلاتر.
- `GET /<id>/receipt` — معاينة الإيصال؛ `POST /<id>/print` — طباعة حرارية؛ `POST /<id>/cancel` — إلغاء.

### 7.8 المحاسبة (accounts_bp)
- دليل الحسابات (شجرة)، إنشاء/تعديل/حذف/تعطيل، تفاصيل حساب.
- `POST /seed` — تهيئة دليل افتراضي.
- قيود يومية (إضافة/حذف) مع التحقق من التوازن.
- دفتر الأستاذ `GET /ledger` + `GET /ledger/pdf` (حساب/فترة/رصيد جاري).
- ميزانية `GET /balance-sheet` + `/pdf` (حتى تاريخ).
- قائمة دخل `GET /income-statement` + `/pdf` (فترة).
- تدفق نقدي `GET /cash-flow` + `/pdf`.
- نظرة شاملة `GET /overview` + `/pdf` (عدة قوائم في مستند واحد).
- ميزان مراجعة `GET /trial-balance` + `/trial-balance/pdf` (فلترة `?to=`).
- تحليلات `GET /analytics` — هرمية التقرير بالأوراق النقدية وقيود التحصيل.
- إقفال سنوي `GET /close-period` + `POST /close-period/reverse`.

### 7.9 لوحة التحكم (dashboard_bp)
- مؤشرات: مبيعات، إيرادات، تكلفة، أرباح، مخزون، أوامر معلقة.
- تقارير مبيعات/مشتريات/مخزون/أرباح مع فلاتر وتصدير Excel.

### 7.10 واتساب والإعدادات (whatsapp_bp)
- `/settings` — تبويبات: عام / واتساب / تذكيرات / قوالب / قاعدة البيانات.
- `/api/whatsapp/send-reminder/<id>` — إرسال فوري.
- `/api/whatsapp/status` — حالة الجسر + QR.
- `/api/baileys/start` — تشغيل الخدمة؛ `/api/baileys/logout` — خروج.

### 7.11 المستخدمون (auth_bp)
- صفحة مستخدمين (admin فقط): إضافة (viewer/editor/cashier/accountant/admin)، تفعيل/تعطيل، حذف. لا يمكن تعطيل/حذف حسابك.

---

## 8) الأمان

- كلمات مرور مشفرة عبر werkzeug (`generate_password_hash`).
- CSRF على كل النماذج + كوكي `csrf_token` (samesite=Lax) لكل استجابة.
- رؤوس أمان على كل استجابة:
  ```
  X-Content-Type-Options: nosniff
  X-Frame-Options: SAMEORIGIN
  X-XSS-Protection: 1; mode=block
  Referrer-Policy: strict-origin-when-cross-origin
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; ...
  ```
- حدود معدل (Flask-Limiter): دخول 10/دقيقة، API 10–30/دقيقة، تقارير 20/دقيقة. يمكن تعطيلها بـ `RATELIMIT_ENABLED=false` (تُعطل في الاختبارات).
- حماية `next` من إعادة التوجيه المفتوحة (فحص scheme/netloc).
- أدوار: viewer قراءة فقط / editor تعديل / cashier نقطة بيع / accountant محاسبة / admin كل شيء.
- منع إساءة أسماء الملفات في النسخ/الاستعادة (منع `..` والفواصل + regex صارم + فحص رأس SQLite).
- قفل استعادة `threading.Lock` (منع عمليتين متزامنتين).
- رفع ملفات: قائمة امتدادات بيضاء + أسماء آمنة.
- منع حقن SQL عبر ORM والمعاملات؛ `upgrade_db.py` بقائمة بيضاء للجداول.
- منع تشغيل مزدوج: ملفات `instance\.app.lock` و `.app.pid` + `_kill_stale()` + قتل المنافذ.
- `PRAGMA foreign_keys=ON` على كل اتصال SQLite.

---

## 9) النسخ الاحتياطي والتصدير

### 9.1 النسخ الاحتياطي
- **تلقائي:** يوميًا 3:00 صباحًا عبر APScheduler → `backups\db_backup_YYYYMMDD_HHMMSS.db`، مع حذف النسخ الأقدم من **30 يومًا** وتنظيف `exports\` الأقدم من **7 أيام**.
- **يدوي:** زر في الإعدادات (admin) أو `GET /backup`.
- **تقنية:** `sqlite3.Connection.backup()` (نسخة متسقة أثناء الكتابة) + `PRAGMA wal_checkpoint(TRUNCATE)` قبل النسخ + `busy_timeout`.
- **استعادة:** استيراد ملف .db (يأخذ `pre_import_backup_*.db` تلقائيًا أولًا) أو من النسخ المحفوظة، مع `PRAGMA foreign_keys=OFF` أثناء الاستبدال.
- **فحص السلامة:** `PRAGMA integrity_check`, `quick_check`, `foreign_key_check`, `page_count/page_size/freelist`.
- **تحسين:** VACUUM / REINDEX / ANALYZE مع الإبلاغ بالحجم قبل/بعد.

### 9.2 التنظيف المجدول
- `cleanup_uploads` يوميًا 00:00 — حذف صور أقدم من `upload_retention_days` (افتراضي 7).

### 9.3 التصدير
- **Excel** (openpyxl): جداول منسقة (عناوين بيضاء على بنفسجي، حدود، تنسيق أرقام `#,##0.00`، RTL، تظليل المدفوع بالأخضر).
- **PDF** (reportlab): تقارير عربية بخط Arial (له جلائف عربية)، أفقية/عمودية حسب النوع، مع اسم المنشأة والعملة.

---

## 10) الطباعة

### 10.1 تقارير PDF (reportlab)
جميعها تُولَّد في ذاكرة (BytesIO) وتُعاد عبر `send_file`. تسجّل الخط `C:/Windows/Fonts/arial.ttf` تحت اسم `Arabic` (fallback: Helvetica). تتضمن اسم المنشأة `company_name` ولاحقة العملة `currency_suffix()`.

| المولّد | الوصف |
|---|---|
| create_pdf_report | تقرير المديونيات (عملاء) |
| create_period_comparison | مقارنة فترتين |
| create_ledger_pdf | دفتر الأستاذ (أقسام لكل حساب + رصيد جاري) |
| create_statement_pdf | قائمة مالية عامة (ميزانية/دخل) بدعم عدة أعمدة مبالغ |
| create_financial_overview_pdf | نظرة شاملة (عدة قوائم في مستند واحد) |
| create_client_statement_pdf | كشف حساب عميل |
| create_aging_pdf | تقرير أعمار الديون |

### 10.2 Excel (openpyxl)
- `export_excel(clients)` لتقرير المديونيات؛ نماذج الاستيراد عبر `create_sample_template()`.

### 10.3 الطباعة الحرارية (python-escpos) — `app\pos\printer.py`
- `build_receipt_bytes(sale)`: يبني دفق ESC/POS عبر `escpos.printer.Dummy` (charcode CP1256) — اسم النظام، التاريخ، العميل، بنود (كمية × سعر)، خصم، إجمالي، طريقة دفع، شكرًا، قص.
- `print_receipt(sale)`: يرسل عبر `Win32Raw(printer_name)` حيث اسم الطابعة من `pos_printer_name`. يُرجع `(ok, msg)` دون رمي استثناءات؛ يُحذّر إن كانت الطباعة معطلة.

### 10.4 الباركود (python-barcode)
- توليد SVG/PNG لباركود المنتج (code128) لصفحة الملصقات.

---

## 11) التغليف (Packaging)

### 11.1 بناء الـ EXE — `build_exe.py`
1. البحث عن Python (LocalAppData Python312/313 ← venv ← PATH).
2. PyInstaller عبر `python -m PyInstaller`:
   - `--onedir --windowed --icon=icon.ico --name=DebtManager`
   - `--add-data`: templates, static, icon, baileys_service (index.js + package.json + Dockerfile).
   - قائمة hidden-imports شاملة (flask, sqlalchemy, reportlab, openpyxl, apscheduler, psutil, flasgger, limits, marshmallow, yaml, waitress, eel, escpos...) + collect-submodules للوحدة الأساسية.
3. بعد النجاح: نسخ `icon.ico`، مجلد `baileys_service` (بدون node_modules/auth_session)، وملفات `install_baileys.bat`, `start_baileys.bat`, `stop.bat` إلى الناتج.
4. الناتج: `dist\DebtManager\DebtManager.exe`.

### 11.2 المثبّت — `installer.iss` (Inno Setup)
- التثبيت في `{userappdata}\DebtManager` (بدون صلاحيات إدارية)، لغات عربي/إنجليزي.
- **يستثني** قاعدة البيانات والمفاتيح والسجلات وجلسة واتساب — يتولد دائمًا قاعدة فارغة عند أول تشغيل.
- الناتج: `dist\installer\DebtManagerSetup.exe`.

### 11.3 ملفات المساعدة
- `install.bat`: فحص Python/Node/Git ← venv ← pip install ← مجلدات ← npm install (بايلز) ← ترقية القاعدة.
- `start.bat` / `launch.vbs` / `stop.bat` (منافذ 5000/3001/9999 احتياطيًا).

### 11.4 بيئة التشغيل
- تشغيل التطوير: `python debt_manager.pyw` أو `start.bat`.
- خادم فقط: `python run_production.py` (env: HOST=127.0.0.1، PORT=5000، THREADS=4).

---

## 12) واتساب (Baileys) — التكامل

- الجسر: `baileys_service\index.js` (Express على `127.0.0.1:3001`)، جلسة محفوظة في `auth_session`.
- واجهات الجسر: `GET /status` (disconnected/connecting/qr/connected + qr) و`POST /send` و`POST /logout`. حماية اختيارية بـ `BAILEYS_API_TOKEN` (هيدر x-api-token).
- طابور إرسال بفاصل 3–8 ثوانٍ لتجنب الحظر؛ إعادة اتصال تلقائية.
- تحويل الأرقام `normalize_phone` (متطابق Python/JS): `01x→20`, `05→966`, `02→20`, يترك الدولي، `00` يُحذف.
- الإعداد التلقائي عند الإقلاع: `ensure_baileys_ready()` (npm install ذاتي مع تحويل git SSH→HTTPS) ثم `start_baileys_bridge()` على 3001.
- رسائل التذكيرات من القوالب `template_1/2/3` + رابط الدفع `payment_link`.

---

## 13) المحاسبة التلقائية — `app\accounts\auto.py`

تعمل عند `auto_accounting_enabled=true` ومع وجود دليل الحسابات المزوَّر (`POST /accounts/seed`).

### 13.1 الأكواد الافتراضية
| الكود | الحساب | النوع |
|---|---|---|
| 1101 | النقدية | أصل |
| 1102 | البنك | أصل |
| 1201 | المخزون | أصل |
| 1301 | العملاء (ذمم مدينة) | أصل |
| 2101 | الموردون (ذمم دائنة) | خصم |
| 3102 | الأرباح المحتجزة | حقوق ملكية |
| 4101 | المبيعات | إيراد |
| 5101 | تكلفة البضاعة المباعة | مصروف |

### 13.2 الحسابات الفرعية للعملاء
- عند إضافة عميل: يُنشأ حساب فرعي بكود `1301{id}` (عميل) أو `2101{id}` (مورد) تحت حساب الذمم، مع رصيد افتتاحي = `base_debt − base_paid`.
- عند التعديل: مزامنة الاسم والأب والنوع (`sync_client_account`).
- عند الحذف: تعطيل الحساب مع الإبقاء على السجل (`deactivate_client_account`).
- `_leaf_accounts()` في `app\accounts\__init__.py` تشمل الأوراق + الأصول المجمعة ذات الرصيد المباشر (مثل 1301) حتى لا تُعدَّ الأرصدة مرتين.

### 13.3 القيود التلقائية (قيد مزدوج، بدون تكرار عبر source_type/source_id)
| المصدر | القيد |
|---|---|
| بيع نقدي | مدين نقدية/بنك، مدين COGS ∥ دائن مبيعات، دائن مخزون |
| بيع آجل | مدين حساب العميل (أو 1301)، مدين COGS ∥ دائن مبيعات، دائن مخزون |
| استلام أمر شراء | مدين مخزون ∥ دائن موردون |
| فاتورة يدوية لعميل | مدين حساب العميل (أو 1301) ∥ دائن مبيعات |
| دفعة من عميل | مدين نقدية/بنك ∥ دائن حساب العميل (أو 1301) |
| دفعة لمورد | مدين حساب المورد (أو 2101) ∥ دائن نقدية/بنك |
| إقفال سنوي | إقفال الإيرادات والمصروفات ونقل الصافي إلى 3102 |

- عند الإلغاء/الحذف: يُحذف القيد المرتبط ويُعاد بناء رصيد دفتر الأستاذ للحسابات المتأثرة.
- كل قيد يستدعي `sync_entry()` لكتابة صفوف دفتر الأستاذ بالرصيد الجاري.

---

## 14) مجلدات التشغيل والسجلات
| المجلد | المحتوى |
|---|---|
| instance\ | debtors.db + .secret_key + أقفال |
| logs\app.log | سجل التطبيق (5MB × 3) |
| logs\startup.log | إقلاع debt_manager.pyw (Debug) |
| logs\background_errors.log | أخطاء الخلفية (2MB × 3) |
| backups\ | نسخ احتياطية |
| exports\ | ملفات التصدير |
| uploads\ | صور الفواتير |
| baileys_service\baileys.log | سجل جسر واتساب |

---

## 15) الاختبارات

- الإطار: **pytest** + `pytest-cov`.
- `tests\conftest.py`:
  - يضبط `RATELIMIT_ENABLED=false` و `TESTING=1`.
  - `create_app(testing=True)` → قاعدة SQLite في الذاكرة.
  - معطل CSRF، `SERVER_NAME='localhost'`.
  - fixture `reset_db` (autouse): يمسح كل الجداول ويعيد إنشاء admin/admin123 قبل كل اختبار.
  - `auth_client` يتسجل دخولًا كـ admin.
- **254 دالة اختبار / 495 حالة اختبار** موزعة على 12 ملفًا:
  - test_accounts.py (31): دليل حسابات، قيود، ميزانية، قائمة دخل، تدفق نقدي، ميزان مراجعة (بما فيها فلترة to + PDF).
  - test_auto_accounting.py (24): القيود التلقائية + الحسابات الفرعية للعملاء + الإقفال.
  - test_clients.py (23): عملاء، كشوف، إجماليات، API، تقادم + PDF.
  - test_dashboard.py (22): لوحة التحكم وتقارير التجارة.
  - test_db_config.py (3): DATABASE_URL، ذاكرة الاختبار، رفض غير-SQLite.
  - test_ledger.py (48): دفتر الأستاذ (رصيد جاري، إعادة بناء، فلاتر، PDF) + القوائم المالية.
  - test_modes.py (7): تبديل وضع debt/commerce.
  - test_pos.py (33): نقطة البيع (سلة، إتمام، إلغاء، إيصال، مخزون).
  - test_products.py (25): منتجات/تصنيفات/مخزون/باركود + صلاحيات.
  - test_purchases.py (22): أوامر الشراء والحالات.
  - test_roles.py (16): صلاحيات الأدوار (viewer/editor/cashier/accountant/admin).
  - test_all.py / test_full.py: مجموعات تشغيل شاملة.
- التشغيل: `python -m pytest tests` (من مجلد المشروع مع تفعيل venv).
- ملاحظة: تعديل `testing=True` يفرض دائمًا `:memory:` حتى لو وُضعت `DATABASE_URL`.

---

## 16) بيانات الدخول الافتراضية
- المستخدم: `admin` — كلمة المرور: `admin123` — الدور: admin.
- ⚠️ يجب تغيير كلمة المرور فورًا من صفحة المستخدمين.

---

## 17) المنافذ
| المنفذ | الخدمة |
|---|---|
| 5000 | خادم Flask/Waitress (التطبيق) |
| 3001 | جسر واتساب Baileys (Node) |
| 9999 | احتياطي قديم لـ Eel (يُنظَّف في stop.bat) |
