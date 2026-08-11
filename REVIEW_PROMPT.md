# برومبت مراجعة كاملة ومفصلة لنظام إدارة المديونية والتجارة

> هذا الملف برومبت جاهز للإرسال إلى أداة مراجعة كود (ذكاء اصطناعي/مراجع).
> انسخه كاملاً كرسالة للمراجع، واطلب الالتزام بقسم «صيغة التقرير» حرفياً.

---

## 1) الدور والمطلوب

أنت مراجع كود خبير في **Python/Flask/SQLAlchemy** ونظم **ERP/POS** و**قيد الدفع المزدوج (Double-Entry Accounting)** وأمن تطبيقات الويب. قم بمراجعة **شاملة ومفصلة** للمشروع التالي، واكشف كل الأخطاء والثغرات والتحسينات الممكنة مع الاستشهاد الدقيق `file:line`.

## 2) معلومات المشروع

- **المسار:** `C:\Users\YUZZRY\Desktop\debt_manager_dev`
- **نقطة الدخول:** `debt_manager.pyw` (Waitress على `127.0.0.1:5000`، فتح نافذة Chrome بملف تعريف مخصص).
- **البيئة:** Windows، Python 3.13 (venv داخل المشروع: `venv\Scripts\python.exe`).
- **قاعدة البيانات:** SQLite `instance\debtors.db` (WAL، busy_timeout=5000، foreign_keys=ON) — وفي الاختبارات قاعدة ذاكرة. يدعم أيضاً PostgreSQL عبر `DATABASE_URL` (خارج وضع testing فقط).
- **الدخول الافتراضي:** admin / admin123.
- **الواجهة:** Bootstrap 5 RTL عربي + Bootstrap Icons، وضع ليلي، خط IBM Plex Sans Arabic.
- **المرجع التوثيقي القديم (متقادم جزئياً):** `PROMPT.md` يصف نسخة `debt_manager_deploy` القديمة — لا تعتمد عليه للبنية الحالية.

## 3) الأوامر المرجعية (نفّذها للتحقق)

```powershell
cd C:\Users\YUZZRY\Desktop\debt_manager_dev
.\venv\Scripts\python.exe -m pytest tests\ -q          # الحزمة الكاملة (المتوقع ≥ 411 ناجحاً)
.\venv\Scripts\python.exe -m coverage run -m pytest tests\ -q
.\venv\Scripts\python.exe -m coverage report --include="app/*" -m
.\venv\Scripts\python.exe -m py_compile app\models.py app\utils.py app\__init__.py
```

## 4) نطاق المراجعة (كل ملف داخل app\ وما يليه)

- `app\__init__.py` — create_app، الإعدادات، الأمان، CSRF، Limiter، المجدول، معالجات الأخطاء، تسجيل البلوبيرنات.
- `app\models.py` — كل الجداول: users, clients, categories, products, stock_movements, invoices, payments, settings, activity_log, import_cache, purchase_orders, purchase_items, sales, sale_items, accounts, journal_entries, journal_entry_lines.
- `app\utils.py` — recalc_client, landing_url, backup/import/restore/export، ضغط الصور، النشاط، الإشعارات، تحويل الأرقام، تنظيف.
- بلوبيرنات: `app\auth\` (دخول/مستخدمين/وضع التشغيل)، `app\clients\`، `app\invoices\`، `app\payments\`، `app\whatsapp\` (إعدادات)، `app\reports\`، `app\api\` (REST)، `app\database\` (نسخ/استعادة/فحص)، `app\products\`، `app\purchases\`، `app\pos\` (نقطة البيع + `printer.py` طابعة حرارية)، `app\accounts\` (شجرة حسابات + قيود + `auto.py` الربط التلقائي بالمحاسبة)، `app\dashboard\` (لوحة العمليات والتقارير التشغيلية).
- `templates\` — خاصة `base.html` (نافبار الوضعين)، pos\، products\، purchases\، accounts\، dashboard\، settings.html.
- `upgrade_db.py`، `debt_manager.pyw`، `requirements.txt`.
- `tests\` — conftest + 12 ملف اختبار (test_all, test_full, test_clients, test_pos, test_products, test_purchases, test_accounts, test_auto_accounting, test_dashboard, test_db_config, test_modes, test_edge/deep إن وُجدت).

## 5) محاور المراجعة بالتفاصيل

### 5.1 الأمان (Security) — أولوية قصوى
- CSRF على كل نماذج POST (Flask-WTF)، وصحة إعداد `WTF_CSRF_TIME_LIMIT`.
- صلاحيات الأدوار: admin / editor / viewer — هل كل عملية كتابية (POST/PUT/DELETE) تتحقق من `can_edit`، وكل حذف من `is_admin`؟ في **كل** البلوبيرنات الجديدة (pos، products، purchases، accounts، dashboard) وليس القديمة فقط.
- التحقق من الصلاحيات على مستوى الرابط مقابل الوظيفة (authorization) لا العرض فقط (UI hiding).
- معدل الطلبات (flask-limiter) على مسارات الحساسة، وتأثير التعطيل عبر `RATELIMIT_ENABLED=false`.
- حماية إعادة التوجيه المفتوحة في login (`next` مع فحص netloc/scheme) وباقي المسارات.
- رفع الملفات: قائمة بيضاء بالامتدادات، `secure_filename`، UUID، حد الحجم (16MB)، منع رفع ملفات باسم خطير.
- سرية: أين تُخزَّن `SECRET_KEY`؟ تسريب أسرار في السجلات؟ كلمات مرور عبر werkzeug؟ إخفاء بيانات الجلسة؟
- رؤوس الأمان: X-Content-Type-Options, X-Frame-Options, CSP, Referrer-Policy على كل استجابة.
- تخمين/تجاوز: هل يمكن الوصول لصفحات admin عبر المعاملات (id ترقيمي، مسارات `/<id>`) مع تحقق ملكية/صلاحية؟
- `app_mode` في الجلسة: هل يمكن حقن قيم أخرى؟ هل يُعالَج غير المسجَّل بأمان؟

### 5.2 قاعدة البيانات و ORM (SQLAlchemy)
- كل `Query.get` القديمة مستبدلة بـ `db.session.get` (أبلغ عن أي بقايا).
- العلاقات و`cascade` بين sales/sale_items و purchase_orders/purchase_items و clients/invoices/payments.
- التعامل مع المبالغ: `Numeric(10,2)` — أخطاء تقريب عند الجمع/الطرح؟ مقارنات float؟ قيود القيمة الموجبة؟
- حسابات المخزون: `stock_movements` هل تتحدّث بشكل ذرّي مع `products.quantity`؟ معالجة الكمية السالبة والكمية الجزئية؟
- المعاملات: أين `commit`/`rollback`؟ هل توجد عمليات متعددة داخل `begin_nested()`/SAVEPOINT غير مستردة عند الفشل؟
- الفهارس المفقودة على المفاتيح الأجنبية وحقول الفلترة والتاريخ.
- ترحيلات `upgrade_db.py`: قائمة بيضاء للجداول/الأعمدة ضد حقن SQL، ومرور آمن للقواعد القديمة.
- `journal_entries.source_type/source_id` + الفهرس الفريد `idx_journal_source`: هل يمنع التكرار فعلاً في كل المسارات؟

### 5.3 وضعا التشغيل (debt / commerce)
- `app\utils.py: landing_url()` و `app\auth\__init__.py: switch_mode()` و `GET /mode/<mode>` — صحة القيم المقبولة، التوجيه الافتراضي.
- `context_processor` في `app\__init__.py` يمرر `app_mode` لكل القوالب.
- `templates\base.html`: القائمة الظاهرة في كل وضع (وضع debt: قائمة المديونية فقط؛ وضع commerce: كل العناصر)، الشعار الديناميكي، المبدّل، والوضع النشط.
- هل كل الصفحات تبقى متاحة ومحمية بالصلاحيات في كلا الوضعين؟ (العزل تجربة واجهة لا عزل بيانات)
- الاختبارات: `tests\test_modes.py` (7 اختبارات) — هل تغطي الحالة الافتراضية والتبديل والتوجيه بعد الدخول وحفظ الجلسة؟

### 5.4 نقطة البيع (POS)
- `app\pos\__init__.py` + `forms.py` + `templates\pos\index.html`:
  - البيع النقدي الفوري عبر عميل افتراضي «نقدي» (`_cash_client()`) — إنشاء/إعادة استخدام، والربط الصحيح بـ `client_id`.
  - `GET /pos/api/product?q=` (بحث بالباركود ثم SKU ثم الاسم، النشطة فقط).
  - مسح الباركود من الحقل وإضافة للسلة وإعادة التركيز — لا تكرار إضافة عند Enter متكرر.
  - تحديث المخزون عند إتمام البيع (نزول الكميات) وعكسه عند الإلغاء.
  - إلغاء البيع: هل يعيد المخزون ويلغي قيد المحاسبة؟ هل يمنع إلغاء البيع المكتمل مرتين؟
  - حساب الإجماليات/الخصم/المدفوع/الباقي، وحالة البيع (مكتمل/ملغي/آجل).
  - الطابعة الحرارية `printer.py` (escpos + CP1256 + Win32Raw): ترميز عربي، أسماء طابعات، أمان الاسم (منع حقن أوامر)، فشل الطباعة لا يكسر البيع.
  - `tests\test_pos.py` — تغطية النقدي/الماسح/الإلغاء/المخزون.

### 5.5 المحاسبة (Double-Entry) — أعلى خطر مالي
- `app\accounts\auto.py`: `post_sale_entries` (1101/1301، تكلفة 5101، مبيعات 4101، مخزون 1201)، `post_purchase_entries` (1201/2101)، `post_payment_entries` (تحصيل/دفع، نقدية/بنك)، و`reverse_*`.
- صحة القيد: لكل entry مجموع دائن = مجموع مدين، لا قيد بدون طرفين، لا قيود مكررة (idempotency عبر `idx_journal_source`).
- خطافات الاستدعاء في pos (complete/cancel)، purchases (receive)، payments (add/edit/delete) — كلها داخل `begin_nested()`: هل فشل المحاسبة يوقف العملية الأصلية أم يُسجَّل ويُتجاهل؟ هل هذا متسق في كل المسارات؟
- احترام `auto_accounting_enabled` (مع معالجة النصوص 'true'/'false') في كل نقطة وليس بعضها.
- الحسابات الافتراضية الغائبة (لم تُنشأ) — سلوك آمن.
- تعديل/حذف فاتورة/دفعة لاحقاً: هل يُعكس القيد الأصلي ثم يُنشأ الجديد؟ هل يُعكس مرتين إن تعدَّل تعديلين؟
- الميزان التجريبي `templates\accounts\trial_balance.html` والتحقق من رصيد صفر للمجموع.

### 5.6 المنتجات والمخزون والمشتريات
- `app\products\__init__.py`: CRUD، الفئات، الباركود (`generate_barcode_png` + مسار `/products/barcode/<pid>/image.png`)، حركات المخزون، الجرد (`stock_adjust`)، التنبيهات (`low_stock`).
- `app\purchases\__init__.py`: أمر شراء ← عناصر ← استلام (receive) يزيد المخزون ويقيّد المحاسبة. تكرار الاستلام؟ استلام أكثر من الكمية؟
- عمليات الحذف: هل تحذف الحركات والقيود المرتبطة أم تتركها ميتة؟

### 5.7 الدفعات والتحصيل
- تحصيل من عميل / دفع لمورد، طرق الدفع (نقدية/بنك...)، الربط بالحسابات الصحيحة في القيد.
- تعديل/حذف دفعة: عكس القيد القديم + إعادة حساب رصيد العميل + إنشاء القيد الجديد — بدون فقدان.

### 5.8 التقارير ولوحة العمليات
- `app\dashboard\`: إحصائيات البيع/الشراء/الربح/المخزون، تقارير sales/profit/purchases/inventory.
- `app\reports\`: التقارير القديمة + aging + compare — اتساق الأرقام مع الجداول الفعلية (لا حسابات يدوية مختلفة).
- الاستيراد المحاسبي `app\importers\accounting_excel.py` — المبالغ SUMIF الخاطئة (None) عند غياب فتح Excel.
- أداء الاستعلامات على بيانات كبيرة (3000+ عميل): تجميع في SQL بدل حلقات Python حيث أمكن.

### 5.9 المجدول والنسخ الاحتياطي والاتساق
- مهام APScheduler: daily_backup، cleanup_uploads، التذكيرات — منع SchedulerAlreadyRunningError وإعادة التشغيل الآمن.
- نسخ احتياطية عبر `sqlite3.backup()` مع WAL checkpoint ومهلة والتحقق من سلامة الملف، وحماية مسارات backup/import/restore/export عند PostgreSQL.

### 5.10 التزامن والحالات
- مزامنة التحديثات المتزامنة على نفس المنتج/العميل (قفل/معاملة) — فقدان التحديث (lost update) في المخزون.
- السلة في الجلسة عند POS: صلاحية انتهاء الجلسة/المشاركة.
- `debt_manager.pyw`: قفل التشغيل المزدوج (lock/pid)، قتل العمليات العالقة، بدء واتساب بدون إيقاف البرنامج.

### 5.11 الاختبارات والتغطية
- أكمل قائمة الاختبارات الحالية ونتيجة التشغيل الكاملة وعددها (المتوقع ≥ 411).
- أعد `coverage report` واذكر الملفات الأقل تغطية (مثل reports، printer، api) وحدد اختبارات مقترحة محددة لكل فجوة.
- هل هناك سيناريوهات حرجة بلا اختبار: تعديل قيد محاسبي مرتين، استلام مشتريات مكرر، إلغاء بيع نقدي، POS بلا عميل، تعطيل `auto_accounting_enabled` في منتصف التشغيل؟

## 6) صيغة التقرير النهائي (التزم بها)

### أ. ملخص تنفيذي
فقرتان: الحالة العامة (من 1–10) وأهم 5 نتائج.

### ب. جدول النتائج
| # | الخطورة (حرجة/عالية/متوسطة/منخفضة/تحسين) | الملف:السطر | الوصف | الأثر | الإصلاح المقترح |
|---|---|---|---|---|---|
| 1 | حرجة | app\pos\__init__.py:120 | ... | ... | ... |

### ج. التحقق العملي
- أرقام الاختبارات النهائية (ناجح/فاشل/عدد) وأي تحذيرات.
- أرقام التغطية لكل ملف + الإجمالي.
- أي اختبار أُضيف أثناء المراجعة (مع اسمه) ليثبت الخلل.

### د. توصيات الأولوية
قائمة مرقّمة (حرجة أولاً) بحدود 10 بنود، كل بند: الإصلاح + الجهد التقديري + الخطر لو تُرك.

> ملاحظة: المشروع **بدون git** — لا تعتمد على تاريخ التعديلات؛ اعتمد على فحص الكود المباشر.
> ممنوع تعديل أي كود أثناء المراجعة إلا لإضافة اختبارات إثبات الخلل فقط، مع عرضها في التقرير.
