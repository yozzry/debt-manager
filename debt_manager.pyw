import os
import sys
import time
import signal
import threading
import subprocess
import shutil
import logging

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    DATA_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = BASE_DIR

os.makedirs(os.path.join(BASE_DIR, 'logs'), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'uploads'), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'exports'), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'backups'), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)

logging.basicConfig(
    filename=os.path.join(BASE_DIR, 'logs', 'startup.log'),
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    force=True
)

if getattr(sys, 'frozen', False):
    baileys_src = os.path.join(DATA_DIR, 'baileys_service')
    baileys_dst = os.path.join(BASE_DIR, 'baileys_service')
    if os.path.isdir(baileys_src) and not os.path.isdir(baileys_dst):
        try:
            shutil.copytree(baileys_src, baileys_dst, ignore=shutil.ignore_patterns('node_modules', 'auth_session'))
            logging.info('Copied baileys_service to BASE_DIR')
        except Exception as ex:
            logging.warning(f'Could not copy baileys_service: {ex}')

LOCK_FILE = os.path.join(BASE_DIR, 'instance', '.app.lock')
PID_FILE = os.path.join(BASE_DIR, 'instance', '.app.pid')


def _kill_stale():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            if old_pid != os.getpid():
                import psutil
                try:
                    p = psutil.Process(old_pid)
                    p.kill()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            if old_pid != os.getpid():
                import psutil
                try:
                    p = psutil.Process(old_pid)
                    p.kill()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            os.remove(LOCK_FILE)
        except Exception:
            pass

    import socket
    for port in [int(os.environ.get('PORT', 5000)), int(os.environ.get('EEL_PORT', 9999))]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            result = s.connect_ex(('127.0.0.1', port))
            s.close()
            if result == 0:
                import subprocess as sp
                sp.run(['taskkill', '/F', '/FI', f'WINDOWTITLE eq *{port}*'],
                       capture_output=True, timeout=3)
        except Exception:
            pass


_kill_stale()

try:
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
except Exception:
    pass

logging.info('Creating Flask app...')
try:
    from app import create_app
    app = create_app()
except Exception as ex:
    logging.critical(f'Failed to create Flask app: {ex}', exc_info=True)
    raise

logging.info('Debt Manager started')

host = '127.0.0.1'
port = int(os.environ.get('PORT', 5000))
threads_count = int(os.environ.get('THREADS', 4))

from waitress import serve as waitress_serve

server_thread = threading.Thread(
    target=lambda: waitress_serve(app, host=host, port=port, threads=threads_count, url_scheme='http'),
    daemon=True,
)
server_thread.start()

_browser_proc = None


def _cleanup():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception:
        pass
    os._exit(0)


def _kill_everything():
    _kill_profile_chrome()
    if _browser_proc and _browser_proc.poll() is None:
        try:
            _browser_proc.terminate()
            _browser_proc.wait(timeout=3)
        except Exception:
            pass
    _cleanup()


signal.signal(signal.SIGTERM, lambda *_: _kill_everything())
signal.signal(signal.SIGINT, lambda *_: _kill_everything())

import atexit
atexit.register(_cleanup)


def _find_browser():
    candidates = [
        os.path.join(os.environ.get('PROGRAMFILES', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(os.environ.get('PROGRAMFILES', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p

    edgecore_dir = os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Microsoft', 'EdgeCore')
    if os.path.isdir(edgecore_dir):
        for ver in sorted(os.listdir(edgecore_dir), reverse=True):
            exe = os.path.join(edgecore_dir, ver, 'msedge.exe')
            if os.path.exists(exe):
                return exe

    edge_path = shutil.which('msedge') or shutil.which('chrome')
    if edge_path:
        return edge_path

    return None


browser_path = _find_browser()

_browser_proc = None


def _set_window_icon(hwnd, ico_path):
    import ctypes
    import ctypes.wintypes

    WM_SETICON = 0x0080
    ICON_SMALL = 0
    ICON_BIG = 1

    hicon = ctypes.windll.user32.LoadImageW(
        0, ico_path, 1,
        0, 0,
        0x00000010 | 0x00000080
    )
    if hicon:
        ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
        ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)


def _find_and_set_icon(ico_path):
    import ctypes
    import ctypes.wintypes

    EnumWindows = ctypes.windll.user32.EnumWindows
    GetWindowTextW = ctypes.windll.user32.GetWindowTextW
    GetClassNameW = ctypes.windll.user32.GetClassNameW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.wintypes.BOOL,
        ctypes.wintypes.HWND,
        ctypes.wintypes.LPARAM,
    )

    found = []

    def callback(hwnd, lparam):
        if IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(256)
            GetClassNameW(hwnd, cls, 256)
            if cls.value in ('Chrome_WidgetWin_1', 'Chrome_WidgetWin_0', 'Edge_WidgetWin_1'):
                title = ctypes.create_unicode_buffer(256)
                GetWindowTextW(hwnd, title, 256)
                if 'نظام' in title or 'Debt' in title or 'http' in title:
                    found.append(hwnd)
                    _set_window_icon(hwnd, ico_path)
                    return False
        return True

    EnumWindows(WNDENUMPROC(callback), 0)

    if not found:
        def callback_all(hwnd, lparam):
            if IsWindowVisible(hwnd):
                cls = ctypes.create_unicode_buffer(256)
                GetClassNameW(hwnd, cls, 256)
                if cls.value in ('Chrome_WidgetWin_1', 'Chrome_WidgetWin_0', 'Edge_WidgetWin_1'):
                    _set_window_icon(hwnd, ico_path)
                    found.append(hwnd)
                    return False
            return True
        EnumWindows(WNDENUMPROC(callback_all), 0)


def _wait_until_up(url, timeout=40, interval=0.5):
    """Poll a local URL until it actually serves, so the app window is only opened
    once the servers are listening. This prevents ERR_CONNECTION_REFUSED during
    slow cold starts (e.g. first launch of the frozen ~47 MB exe)."""
    import urllib.request
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                status = resp.status
            if status < 500:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def _app_window_open():
    """True if the app's browser window is still open.

    We match the window by OWNER PID instead of the page title: every visible
    browser window is mapped back to its process id and compared against the
    process tree of the browser we launched. This is reliable while the user
    navigates between pages (the launched browser keeps its process + window the
    whole session), never fires on the user's *other* Chrome/Edge windows (which
    have different PIDs), and closes cleanly when that window disappears."""
    if _browser_proc is None:
        return True
    import psutil
    import ctypes
    import ctypes.wintypes

    owner_pids = {_browser_proc.pid}
    try:
        base = psutil.Process(_browser_proc.pid)
        owner_pids.update(p.pid for p in base.children(recursive=True))
    except Exception:
        pass

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL,
                                     ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    found = [False]

    def _cb(hwnd, _lp):
        try:
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                cls = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetClassNameW(hwnd, cls, 256)
                if cls.value in ('Chrome_WidgetWin_1', 'Chrome_WidgetWin_2',
                                 'Chrome_WidgetWin_0', 'Edge_WidgetWin_1'):
                    pid = ctypes.wintypes.DWORD()
                    ctypes.windll.user32.GetWindowThreadProcessId(
                        hwnd, ctypes.byref(pid))
                    if pid.value in owner_pids:
                        found[0] = True
        except Exception:
            pass
        return True

    ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return found[0]


def _kill_profile_chrome():
    """Kill any leftover Chrome processes that belong to our dedicated profile
    dir. Stale instances (orphaned when the app exited) make a fresh launch
    hand the URL off to them instead of starting a new window, which made the
    app think its window had closed and shut itself down. Never crashes the
    caller even if the process list cannot be read."""
    profile_dir = os.path.join(BASE_DIR, '.app_chrome_cache')
    killed = 0
    try:
        import psutil
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                    cmd = ' '.join(proc.info['cmdline'] or [])
                    if profile_dir in cmd:
                        proc.kill()
                        killed += 1
            except Exception:
                pass
    except Exception as ex:
        logging.warning('_kill_profile_chrome: skipped (%s)', ex)
    if killed:
        logging.info('_kill_profile_chrome: killed %s stale chrome process(es)', killed)


def _open_browser():
    global _browser_proc
    try:
        _kill_profile_chrome()
        time.sleep(1)
        ico_path = os.path.join(DATA_DIR, 'static', 'favicon.ico')
        app_url = 'http://' + host + ':' + str(port) + '/login'
        logging.info('_open_browser: resolving app_url=%s browser_path=%r', app_url, browser_path)
        # Only open the app window once the server is actually listening. Otherwise
        # the browser loads before the server is up and shows ERR_CONNECTION_REFUSED.
        up = _wait_until_up(app_url)
        logging.info('_open_browser: server up=%s', up)
        if browser_path:
            logging.info('_open_browser: launching %s', browser_path)
            # Use a dedicated user-data-dir so the app window runs in its own,
            # independent Chrome instance. This avoids Chrome handing the URL off to
            # an already-running browser (which made the window vanish). The launched
            # process then owns the window, so navigation never ends the process and
            # closing the window lets us detect it reliably.
            profile_dir = os.path.join(BASE_DIR, '.app_chrome_cache')
            try:
                _browser_proc = subprocess.Popen([
                    browser_path,
                    '--user-data-dir=' + profile_dir,
                    '--app=' + app_url,
                    '--window-size=1280,800',
                    '--no-first-run',
                    '--no-default-browser-check',
                ], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            except Exception as ex:
                logging.warning('_open_browser: could not launch dedicated profile (%s); trying default browser', ex)
                import webbrowser
                _browser_proc = None
                webbrowser.open(app_url)
            logging.info('_open_browser: launched pid=%s', _browser_proc.pid if _browser_proc else 'n/a')

            for _ in range(10):
                time.sleep(1)
                if os.path.exists(ico_path):
                    try:
                        _find_and_set_icon(ico_path)
                    except Exception:
                        pass
        else:
            logging.warning('_open_browser: no browser found; opening default browser')
            import webbrowser
            webbrowser.open('http://' + host + ':' + str(port))
    except Exception as ex:
        logging.critical('_open_browser: browser launch FAILED: %r', ex, exc_info=True)

    # Give the browser window a moment to appear before we start watching.
    time.sleep(3)
    closed_since = 0
    logging.info('_open_browser: entering monitor loop (browser_proc=%s)', _browser_proc)
    while True:
        time.sleep(2)
        dead = False
        try:
            # With the dedicated user-data-dir, _browser_proc is the independent
            # browser instance that owns the app window. It stays alive through
            # page navigation and only exits when the window is closed, so a
            # non-None poll() reliably means the app window is gone.
            dead = _browser_proc is not None and _browser_proc.poll() is not None
        except Exception:
            dead = False
        if dead:
            closed_since += 1
            logging.info('_open_browser: browser proc closed, count=%s', closed_since)
            if closed_since >= 2:
                _kill_everything()
                break
        else:
            closed_since = 0


def _auto_setup_baileys():
    """تشغيل خدمة واتساب تلقائيًا عند إطلاق البرنامج: تثبيت المكتبات إن غابت
    (بدل تركيب install_baileys.bat يدويًا) ثم تشغيل الجسر على المنفذ 3001.
    أي فشل يُسجَّل في startup.log بدون إيقاف البرنامج."""
    try:
        from app.utils import ensure_baileys_ready, start_baileys_bridge
        baileys_dir = os.path.join(BASE_DIR, 'baileys_service')
        ok, msg = ensure_baileys_ready(baileys_dir)
        logging.info('baileys auto-setup: ok=%s msg=%s', ok, msg)
        if not ok:
            logging.warning('baileys auto-setup failed: %s', msg)
            return
        ok2, msg2 = start_baileys_bridge(baileys_dir)
        logging.info('baileys auto-start: ok=%s msg=%s', ok2, msg2)
    except Exception as ex:
        logging.warning('baileys auto-setup exception: %r', ex)


threading.Thread(target=_open_browser, daemon=True).start()
threading.Thread(target=_auto_setup_baileys, daemon=True).start()

# Keep the production (waitress on port 5000) server serving. The main thread
# stays alive until _app_window_open() observes the app window is closed.
while True:
    time.sleep(1)
