@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0baileys_service"

echo ============================================
echo   Baileys WhatsApp Bridge - Installation
echo ============================================
echo   Working folder: %cd%
echo.

where node >nul 2>nul
if errorlevel 1 (
    echo ERROR: Node.js was not found in PATH.
    echo Please install Node.js LTS from https://nodejs.org/
    echo.
    pause
    exit /b 1
)

echo Node.js found:
node --version
echo.

REM --- One of Baileys' internal dependencies (libsignal) is fetched
REM directly from GitHub via git instead of the normal npm registry, so
REM git must be installed and in PATH for this install to work at all. ---
where git >nul 2>nul
if errorlevel 1 (
    echo ERROR: Git was not found in PATH.
    echo.
    echo One of the packages this service depends on is fetched directly
    echo from GitHub using git, so git must be installed for this to work.
    echo.
    echo Please install Git for Windows from:
    echo     https://git-scm.com/download/win
    echo.
    echo Make sure to keep the default option "Git from the command line
    echo and also from 3rd-party software" during installation, then run
    echo this file again.
    echo.
    pause
    exit /b 1
)

echo Git found:
git --version
echo.

REM --- Force git to use HTTPS instead of SSH for GitHub links. Without
REM this, npm can end up trying to fetch the dependency over SSH, which
REM fails unless you already have a GitHub SSH key configured. ---
git config --global url."https://github.com/".insteadOf "ssh://git@github.com/"
git config --global url."https://github.com/".insteadOf "git@github.com:"

if not exist package.json (
    echo ERROR: package.json was not found in this folder:
    echo     !cd!
    echo.
    pause
    exit /b 1
)

echo Installing required packages, this may take a few minutes...
call npm install

REM --- Don't just trust the exit code here (some npm/git failures don't
REM always propagate cleanly through "call"); actually check that the
REM main package folder exists, which is a much more reliable signal. ---
if not exist "node_modules\@whiskeysockets\baileys" (
    echo.
    echo ============================================
    echo   ERROR: Installation did not complete correctly
    echo ============================================
    echo.
    echo The @whiskeysockets/baileys package failed to install.
    echo This is usually the git/GitHub dependency issue described above.
    echo.
    echo Try running these two commands manually in this folder and see
    echo the detailed error message:
    echo     cd /d "!cd!"
    echo     npm install
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Installation complete!
echo ============================================
echo.
echo To start the Baileys service:
echo     start_baileys.bat
echo.
echo Then open the app Settings page and scan the QR code
echo with WhatsApp on your phone to link it.
echo.
pause
