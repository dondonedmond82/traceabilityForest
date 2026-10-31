
@echo off
title Forest Traceability - Python Panel

cd /d "%~dp0"

echo ==========================================
echo   FOREST TRACEABILITY BLOCKCHAIN
echo ==========================================

REM Activate Python virtual environment if available
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

REM Configure blockchain API
set "BLOCKCHAIN_API_URL=http://127.0.0.1:3000/api/v1"
set "API_KEY=dev-change-this-key"

echo.
echo Starting Python Panel application...
echo URL: http://127.0.0.1:5006
echo.

panel serve app.py --port 5006 --show --autoreload

pause
