import subprocess
import time
import os

proc = subprocess.Popen([
    r'C:\Program Files (x86)\Microsoft\EdgeCore\150.0.4078.99\msedge.exe',
    '--app=http://127.0.0.1:5000',
    '--no-first-run',
    '--no-default-browser-check',
], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
print(f'PID: {proc.pid}', flush=True)
for i in range(8):
    poll = proc.poll()
    print(f'  t={i}s poll={poll}', flush=True)
    time.sleep(1)
print('Done', flush=True)
os._exit(0)
