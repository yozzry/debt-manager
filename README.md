# Debt Manager — نظام إدارة المديونيات والتجارة

نظام سطح مكتب + متصفح (عربي RTL) لإدارة المديونيات والتجارة والمحاسبة، يعمل محليًا على Windows.

## الميزات

- **المديونية:** عملاء، فواتير، دفعات، كشوف حساب، تقارير أعمار الديون (aging) بتقارير PDF.
- **التجارة:** منتجات، تصنيفات، مخزون مع حركات، نقطة بيع (POS) بطباعة حرارية وباركود، أوامر شراء، لوحة تحكم.
- **المحاسبة المزدوجة (اختياري):** دليل حسابات، قيود تلقائية من العمليات، دفتر أستاذ، ميزانية، قائمة دخل، تدفق نقدي، ميزان مراجعة، إقفال سنوي.
- **واتساب:** تذكيرات سداد تلقائية عبر جسر Baileys محلي (مجاني، بدون API رسمي).
- **النسخ الاحتياطي:** تلقائي يوميًا + يدوي + استعادة + فحص سلامة (SQLite WAL).
- **الأمان:** تسجيل دخول بأدوار (admin/editor/viewer/cashier/accountant)، CSRF، حدود معدل، رؤوس أمان، سجل نشاط.

## التقنيات

Python 3.13 · Flask 3.1 · SQLAlchemy 2.0 · SQLite (WAL) + PostgreSQL اختياري · APScheduler · ReportLab (PDF) · openpyxl (Excel) · python-escpos (طباعة حرارية) · Baileys (Node.js) · PyInstaller + Inno Setup (تغليف).

## التشغيل من الكود المصدري

```bash
install.bat          # إعداد البيئة (venv + مكتبات + npm لبايلز)
start.bat            # تشغيل التطوير
```

أو مباشرة:

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
python debt_manager.pyw
```

الدخول الافتراضي: `admin` / `admin123` — **غيّر كلمة المرور فورًا بعد أول دخول.**

## الاختبارات

```bash
venv\Scripts\python -m pytest tests
```

(254 دالة اختبار / 495 حالة — قاعدة اختبار في الذاكرة.)

## البناء (EXE + مثبّت)

```bash
python build_exe.py                                  # → dist\DebtManager\DebtManager.exe
"C:\...\Inno Setup 6\ISCC.exe" installer.iss         # → dist\installer\DebtManagerSetup.exe
```

## الوثائق

- `PROMPT.md` / `PROMPT_FULL.md` — مواصفات المشروع الكاملة.
- `CHANGELOG.md` — سجل الإصلاحات.

> ⚠️ بياناتك تُخزَّن محليًا في `instance\` ولا تُرفع لأي خادم خارجي. احتفظ بنسخ احتياطية من `instance\debtors.db`.
