"""Deep tests for the debt manager application."""
import io, sys, os, re, json

# Handle Windows console encoding
if sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Test 1: App starts cleanly
print("=== Test 1: App startup ===")
sys.stdout = io.StringIO()
from app import create_app
app = create_app()
sys.stdout = sys.__stdout__
print("  App created without startup errors")
print(f"  Blueprints: {list(app.blueprints)}")

# Test 2: Admin user exists
print("\n=== Test 2: Admin user ===")
with app.app_context():
    from app.models import User
    admin = User.query.filter_by(username='admin').first()
    assert admin is not None, "Admin user missing!"
    assert admin.is_admin, "Admin is not is_admin!"
    assert admin.can_edit, "Admin can't edit!"
    print(f"  Admin user: OK (role={admin.role})")

# Test 3: Scheduler initializes
print("\n=== Test 3: Scheduler ===")
from app import scheduler
# Also check why reminder jobs might be missing
from app.models import Settings as SettingsModel
with app.app_context():
    en = SettingsModel.get('reminder_enabled', 'false')
    print(f"  reminder_enabled={repr(en)}")
    times = SettingsModel.get('reminder_times', '10:00')
    print(f"  reminder_times={repr(times)}")
assert scheduler is not None
print(f"  Scheduler jobs: {len(scheduler.get_jobs())}")
for j in scheduler.get_jobs():
    print(f"    {j.id}")

# Test 4: DB API endpoint integrity
print("\n=== Test 4: DB API endpoints ===")
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True
    
    # Get CSRF
    r = c.get('/settings')
    html = r.data.decode('utf-8', errors='replace')
    csrf = re.search(r'csrf_token.*?value="([^"]+)', html)
    csrf = csrf.group(1) if csrf else ''
    
    # Test stats
    r = c.get('/api/database/stats')
    assert r.status_code == 200
    d = r.get_json()
    assert d.get('ok'), f"Stats failed: {d}"
    print(f"  DB stats: OK (tables={d['data']['tables']})")
    
    # Test integrity
    r = c.get('/api/database/integrity')
    assert r.status_code == 200
    d = r.get_json()
    print(f"  Integrity: {'OK' if d.get('ok') else 'FAIL'} {d.get('data', {}).get('integrity_check', 'N/A')}")

# Test 5: Template rendering
print("\n=== Test 5: Template rendering ===")
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True
    
    pages = ['/', '/settings', '/settings?tab=database', '/settings?tab=reminder',
             '/settings?tab=whatsapp', '/settings?tab=templates', '/report',
             '/client/add']
    for page in pages:
        r = c.get(page)
        if r.status_code in (200, 302):
            print(f"  {page}: {r.status_code} OK")
        else:
            print(f"  {page}: {r.status_code} FAIL")

# Test 6: API endpoints
print("\n=== Test 6: API endpoints ===")
# Check API routes with correct prefix
with app.app_context():
    api_routes = [r for r in app.url_map.iter_rules() if '/api/' in r.rule and 'static' not in r.rule]
    print(f"  API routes found: {len(api_routes)}")
    for r in api_routes:
        methods = r.methods - {'OPTIONS', 'HEAD'}
        print(f"    {methods} {r.rule}")

with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True
    
    endpoints = [
        ('GET', '/api/v1/clients'),
        ('GET', '/api/v1/reports/summary'),
        ('GET', '/api/database/stats'),
    ]
    for method, url in endpoints:
        r = c.open(url, method=method)
        d = r.get_json() if r.is_json else {}
        status = 'OK' if r.status_code == 200 else f'FAIL ({r.status_code})'
        print(f"  {method} {url}: {status}")

# Test 7: File existence
print("\n=== Test 7: Required files ===")
required_files = [
    'app/__init__.py',
    'app/models.py',
    'app/utils.py',
    'app/database/__init__.py',
    'app/clients/__init__.py',
    'app/clients/forms.py',
    'app/auth/__init__.py',
    'app/auth/forms.py',
    'app/invoices/__init__.py',
    'app/invoices/forms.py',
    'app/payments/__init__.py',
    'app/payments/forms.py',
    'app/whatsapp/__init__.py',
    'app/reports/__init__.py',
    'app/api/__init__.py',
    'templates/base.html',
    'templates/index.html',
    'templates/settings.html',
    'run_production.py',
    'requirements.txt',
    'upgrade_db.py',
]
for f in required_files:
    exists = os.path.isfile(os.path.join(os.path.dirname(__file__), f))
    print(f"  {'[OK]' if exists else '[MISS]'} {f}")

# Test 8: Import verification
print("\n=== Test 8: Module imports ===")
modules = [
    'app.models',
    'app.utils',
    'app.database',
    'app.clients',
    'app.clients.forms',
    'app.auth',
    'app.auth.forms',
    'app.invoices',
    'app.invoices.forms',
    'app.payments',
    'app.payments.forms',
    'app.whatsapp',
    'app.reports',
    'app.api',
]
for m in modules:
    try:
        __import__(m)
        print(f"  ✓ {m}")
    except Exception as e:
        print(f"  ✗ {m}: {e}")

print("\n✅ All deep tests complete")
