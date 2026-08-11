@echo off
chcp 65001 > nul
title Debt Manager - Installer
color 0A

echo ============================================
echo   Debt Manager - Installation Script
echo ============================================
echo.

REM Check Python
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ first.
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% found.

REM Check Node.js
node --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Node.js not found. Baileys will not work.
    echo           Install Node.js 18+ from https://nodejs.org
) else (
    for /f %%v in ('node --version 2^>^&1') do set NODEVER=%%v
    echo [OK] Node.js %NODEVER% found.
)

REM Check Git
git --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Git not found. Baileys install may fail.
) else (
    echo [OK] Git found.
)

echo.
echo [1/5] Creating virtual environment...
if exist venv (
    echo       venv already exists, skipping...
) else (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create venv.
        pause & exit /b 1
    )
)

echo [2/5] Installing Python dependencies...
call venv\Scripts\activate.bat
pip install --upgrade pip -q 2>nul
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python packages.
    pause & exit /b 1
)
echo [OK] Python packages installed.

echo [3/5] Creating required directories...
if not exist instance mkdir instance
if not exist uploads mkdir uploads
if not exist exports mkdir exports
if not exist backups mkdir backups
if not exist logs mkdir logs
if not exist static mkdir static
if not exist static\css mkdir static\css
if not exist static\js mkdir static\js
if not exist tests mkdir tests
echo [OK] Directories ready.

echo [4/5] Installing Baileys dependencies...
if exist "%~dp0baileys_service\package.json" (
    cd /d "%~dp0baileys_service"
    npm install --loglevel error
    cd /d "%~dp0"
    echo [OK] Baileys installed.
) else (
    echo [SKIP] baileys_service not found.
)

echo [5/5] Initializing database...
python -c "from app import create_app; app=create_app(); app.app_context().push(); from app.models import db; db.create_all(); print('[OK] Database initialized.')" 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] DB init skipped (will create on first run).
)
echo [5/5] Running DB migrations (if needed)...
python upgrade_db.py 2>nul

echo.
echo ============================================
echo   Installation complete!
echo   Run start.bat to launch the application.
echo ============================================
pause
