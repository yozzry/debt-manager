# -*- coding: utf-8 -*-
import os, sys, shutil, subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Try system python first, then venv (venv may be a broken symlink)
_PYTHON_CANDIDATES = [
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Python', 'Python312', 'python.exe'),
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Python', 'Python313', 'python.exe'),
    os.path.join(PROJECT_DIR, 'venv', 'Scripts', 'python.exe'),
    shutil.which('python'),
    shutil.which('python3'),
]
PYTHON = None
for p in _PYTHON_CANDIDATES:
    if p and os.path.exists(p):
        try:
            r = subprocess.run([p, '--version'], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                PYTHON = p
                break
        except Exception:
            pass
if not PYTHON:
    print('ERROR: No working Python installation found')
    sys.exit(1)
print(f'Using Python: {PYTHON}')

# Use python -m PyInstaller to avoid needing pyinstaller.exe in PATH
PYINSTALLER = None
_PYI_MOD = os.path.join(os.path.dirname(PYTHON), 'Lib', 'site-packages', 'PyInstaller', '__init__.py')
if os.path.exists(_PYI_MOD):
    PYINSTALLER = [PYTHON, '-m', 'PyInstaller']
if not PYINSTALLER:
    # Fallback: look for pyinstaller.exe
    _PYI_CANDIDATES = [
        os.path.join(PROJECT_DIR, 'venv', 'Scripts', 'pyinstaller.exe'),
        os.path.join(os.path.dirname(PYTHON), 'pyinstaller.exe'),
        os.path.join(os.path.dirname(PYTHON), 'Scripts', 'pyinstaller.exe'),
    ]
    for p in _PYI_CANDIDATES:
        if p and os.path.exists(p):
            PYINSTALLER = [p]
            break
if not PYINSTALLER:
    print('ERROR: PyInstaller not found. Install with: pip install pyinstaller')
    sys.exit(1)
ENTRY_POINT = os.path.join(PROJECT_DIR, 'debt_manager.pyw')
ICON = os.path.join(PROJECT_DIR, 'icon.ico')
OUT_DIR = os.path.join(PROJECT_DIR, 'dist')
WORK_DIR = os.path.join(PROJECT_DIR, 'build_temp')


def _force_rmtree(path):
    """Remove a directory tree even if it contains read-only files (Windows)."""
    def _onerror(func, p, exc_info):
        try:
            os.chmod(p, 0o777)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=_onerror)


for d in [OUT_DIR, WORK_DIR]:
    if os.path.exists(d):
        _force_rmtree(d)

cmd = PYINSTALLER + [
    '--noconfirm',
    '--onedir',
    '--windowed',
    f'--distpath={OUT_DIR}',
    f'--workpath={WORK_DIR}',
    f'--icon={ICON}',
    '--name=DebtManager',
    f'--add-data={os.path.join(PROJECT_DIR, "templates")}{os.pathsep}templates',
    f'--add-data={os.path.join(PROJECT_DIR, "static")}{os.pathsep}static',
    f'--add-data={ICON}{os.pathsep}.',
    f'--add-data={os.path.join(PROJECT_DIR, "baileys_service", "index.js")}{os.pathsep}baileys_service',
    f'--add-data={os.path.join(PROJECT_DIR, "baileys_service", "package.json")}{os.pathsep}baileys_service',
    f'--add-data={os.path.join(PROJECT_DIR, "baileys_service", "Dockerfile")}{os.pathsep}baileys_service',
    '--hidden-import=app',
    '--hidden-import=app.models',
    '--hidden-import=app.utils',
    '--hidden-import=app.auth',
    '--hidden-import=app.auth.forms',
    '--hidden-import=app.clients',
    '--hidden-import=app.clients.forms',
    '--hidden-import=app.invoices',
    '--hidden-import=app.invoices.forms',
    '--hidden-import=app.payments',
    '--hidden-import=app.payments.forms',
    '--hidden-import=app.whatsapp',
    '--hidden-import=app.reports',
    '--hidden-import=app.api',
    '--hidden-import=app.database',
    '--hidden-import=app.importers',
    '--hidden-import=app.importers.accounting_excel',
    '--hidden-import=flask',
    '--hidden-import=flask_sqlalchemy',
    '--hidden-import=flask_login',
    '--hidden-import=flask_wtf',
    '--hidden-import=flask_wtf.csrf',
    '--hidden-import=flask_compress',
    '--hidden-import=flask_limiter',
    '--hidden-import=waitress',
    '--hidden-import=eel',
    '--hidden-import=bottle',
    '--hidden-import=bottle_websocket',
    '--hidden-import=gevent',
    '--hidden-import=geventwebsocket',
    '--hidden-import=apscheduler',
    '--hidden-import=apscheduler.triggers.cron',
    '--hidden-import=reportlab',
    '--hidden-import=reportlab.pdfbase',
    '--hidden-import=reportlab.pdfbase.ttfonts',
    '--hidden-import=reportlab.lib',
    '--hidden-import=reportlab.platypus',
    '--hidden-import=openpyxl',
    '--hidden-import=openpyxl.styles',
    '--hidden-import=psutil',
    '--hidden-import=flasgger',
    '--hidden-import=flasgger.utils',
    '--hidden-import=marshmallow',
    '--hidden-import=yaml',
    '--hidden-import=limits',
    '--hidden-import=sqlite3',
    '--hidden-import=python_dotenv',
    '--hidden-import=dotenv',
    '--hidden-import=wtforms',
    '--hidden-import=werkzeug',
    '--hidden-import=werkzeug.security',
    '--hidden-import=sqlalchemy',
    '--hidden-import=sqlalchemy.orm',
    '--hidden-import=sqlalchemy.event',
    '--hidden-import=urllib.parse',
    '--hidden-import=shutil',
    '--hidden-import=ctypes',
    '--hidden-import=ctypes.wintypes',
    '--hidden-import=threading',
    '--hidden-import=subprocess',
    '--hidden-import=logging',
    '--hidden-import=logging.handlers',
    '--hidden-import=re',
    '--hidden-import=json',
    '--hidden-import=io',
    '--hidden-import=base64',
    '--hidden-import=tempfile',
    '--collect-submodules=flask',
    '--collect-submodules=sqlalchemy',
    '--collect-submodules=reportlab',
    '--collect-submodules=openpyxl',
    '--collect-submodules=apscheduler',
    '--log-level=INFO',
    ENTRY_POINT,
]

print('Building Debt Manager executable...')
print(f'Entry point: {ENTRY_POINT}')
print(f'Python: {PYTHON}')
print()

result = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=False)
if result.returncode == 0:
    print('\n=== BUILD SUCCESSFUL ===')
    exe_path = os.path.join(OUT_DIR, 'DebtManager', 'DebtManager.exe')
    print(f'EXE: {exe_path}')
    if os.path.exists(exe_path):
        size = os.path.getsize(exe_path) / (1024 * 1024)
        print(f'Size: {size:.1f} MB')
    shutil.copy2(ICON, os.path.join(OUT_DIR, 'DebtManager', 'icon.ico'))
    print('Icon copied to output folder')

    dst = os.path.join(OUT_DIR, 'DebtManager')
    baileys_dst = os.path.join(dst, 'baileys_service')
    if not os.path.exists(baileys_dst):
        baileys_src = os.path.join(PROJECT_DIR, 'baileys_service')
        if os.path.isdir(baileys_src):
            def _ignore(src, names):
                return [n for n in names if n in ('node_modules', 'auth_session')]
            shutil.copytree(baileys_src, baileys_dst, ignore=_ignore)
            print(f'baileys_service/ copied to dist (without node_modules, auth_session)')
        else:
            print('WARNING: baileys_service/ not found in project root')
    else:
        print('baileys_service/ already exists in dist')

    for fn in ('install_baileys.bat', 'start_baileys.bat', 'stop.bat'):
        src = os.path.join(PROJECT_DIR, fn)
        if os.path.isfile(src) and not os.path.exists(os.path.join(dst, fn)):
            shutil.copy2(src, os.path.join(dst, fn))
            print(f'{fn} copied to dist')
    print(f'  -> Run install_baileys.bat in the dist folder to install npm deps')
else:
    print(f'\n=== BUILD FAILED (code {result.returncode}) ===')
    sys.exit(1)
