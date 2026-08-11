@echo off
chcp 65001 > nul
echo Stopping Debt Manager services...

for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr /R "127\.0\.0\.1:5000 \[::1\]:5000 0\.0\.0\.0:5000"') do (
    if not "%%P"=="" taskkill /F /PID %%P > nul 2>&1
)
echo [OK] Flask stopped.

for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr /R "127\.0\.0\.1:9999 \[::1\]:9999 0\.0\.0\.0:9999"') do (
    if not "%%P"=="" taskkill /F /PID %%P > nul 2>&1
)
echo [OK] Eel stopped.

for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr /R "127\.0\.0\.1:3001 \[::1\]:3001 0\.0\.0\.0:3001"') do (
    if not "%%P"=="" taskkill /F /PID %%P > nul 2>&1
)
echo [OK] Baileys stopped.

del "%~dp0instance\.app.lock" > nul 2>&1
del "%~dp0instance\.app.pid" > nul 2>&1
echo [OK] Lock files cleaned.

echo Done.
timeout /t 2 /nobreak > nul
