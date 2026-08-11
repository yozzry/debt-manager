Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Installing Dev Tools (Python, Node, Git)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Ensure winget exists
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] winget not found. Install App Installer from Microsoft Store." -ForegroundColor Red
    exit 1

}

# --- Git ---
Write-Host ""
Write-Host "[3/3] Checking Git..." -ForegroundColor Yellow
$gitInstalled = git --version 2>$null
if ($gitInstalled -match "git version") {
    Write-Host "  -> $gitInstalled already installed. Skipping." -ForegroundColor Green
} else {
    Write-Host "  -> Installing Git..." -ForegroundColor White
    winget install --id Git.Git --accept-source-agreements --accept-package-agreements --silent
    if ($?) { Write-Host "  -> Git installed successfully." -ForegroundColor Green }
    else    { Write-Host "  -> Git install failed." -ForegroundColor Red }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Done! Restart your terminal for PATH" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
