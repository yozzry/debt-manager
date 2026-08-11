@echo off
chcp 65001 > nul
title Baileys WhatsApp Service
color 0A

cd /d "%~dp0baileys_service"

if not exist node_modules (
    echo ERROR: Dependencies not installed yet.
    echo Please run install_baileys.bat first.
    pause
    exit /b 1
)

echo ============================================
echo   Baileys WhatsApp Bridge - Port 3001
echo ============================================
echo.

echo [INFO] Freeing port 3001 if occupied...
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr /R "127\.0\.0\.1:3001 \[::1\]:3001 0\.0\.0\.0:3001"') do (
    if not "%%P"=="" (
        echo [INFO] Killing PID %%P
        taskkill /F /PID %%P > nul 2>&1
    )
)
timeout /t 1 /nobreak > nul

echo Starting Baileys WhatsApp bridge service...
echo Keep this window open while you want WhatsApp sending to work.
echo Open the app Settings page to see the QR code and connection status.
echo.
node index.js

pause
