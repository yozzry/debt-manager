@echo off
chcp 65001 > nul

REM Start Baileys in background (hidden)
if exist "%~dp0baileys_service\index.js" (
    cd /d "%~dp0baileys_service"
    start /min node index.js
    cd /d "%~dp0"
)

REM Activate venv
if not exist "%~dp0venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Run install.bat first.
    pause & exit /b 1
)
call "%~dp0venv\Scripts\activate.bat"

REM Start Flask with pythonw (no console window)
start /min "" pythonw "%~dp0run_production.py"

REM Open browser after delay
start /b "" cmd /c "timeout /t 4 /nobreak > nul && start http://127.0.0.1:5000"
