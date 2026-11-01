@echo off
setlocal
title Forest Traceability - API and Panel

REM Always run from this project's folder.
cd /d "%~dp0"

REM Keep the same development API key for both Node.js and Panel.
REM Change this value before any deployment beyond local testing.
set "PORT=3000"
set "API_KEY=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"
set "BLOCKCHAIN_API_URL=http://127.0.0.1:3000/api/v1"

echo.
echo ==============================================
echo   FOREST TRACEABILITY - START ALL SERVICES
echo ==============================================
echo.

REM Check Node.js and npm.
where node >nul 2>nul
if errorlevel 1 (
    echo ERROR: Node.js is not installed or not in PATH.
    echo Install Node.js LTS, then reopen this terminal.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm was not found. Reinstall Node.js LTS.
    pause
    exit /b 1
)

REM Install backend packages once, if needed.
if not exist "node_modules\express" (
    echo Installing Node.js dependencies...
    call npm install
    if errorlevel 1 (
        echo ERROR: npm install failed.
        pause
        exit /b 1
    )
)

REM Create and activate the Python virtual environment.
if not exist ".venv\Scripts\activate.bat" (
    echo Creating Python virtual environment...
    py -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create .venv. Check that Python is installed.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

REM Install/update Python requirements.
echo Checking Python dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Python dependency installation failed.
    pause
    exit /b 1
)

REM Start the Node.js REST API in its own terminal.
echo.
echo Starting the blockchain REST API on port 3000...
start "Forest Traceability - Node API" cmd /k "cd /d ""%CD%"" && node blockchain.js"

REM Wait until the API port accepts connections.
echo Waiting for the API to become available...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(30); while ((Get-Date) -lt $deadline) { $client=New-Object System.Net.Sockets.TcpClient; try { $client.Connect('127.0.0.1',3000); $client.Close(); exit 0 } catch { $client.Close(); Start-Sleep -Seconds 1 } }; exit 1"
if errorlevel 1 (
    echo.
    echo ERROR: The API did not start on port 3000.
    echo Check the 'Forest Traceability - Node API' terminal for errors.
    echo If port 3000 is already in use, stop the other process and retry.
    pause
    exit /b 1
)

REM Confirm the health endpoint before opening Panel.
echo Checking API health...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod 'http://127.0.0.1:3000/api/v1/health' -TimeoutSec 5; Write-Host ('API status: ' + $r.status); exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo ERROR: API port is open, but the health endpoint failed.
    echo Check the Node API terminal.
    pause
    exit /b 1
)

echo.
echo Starting Panel dashboard on port 5006...
echo Dashboard URL: http://localhost:5006/app
echo Keep both terminal windows open while using the application.
echo.
panel serve app.py --port 5006 --show --autoreload

pause
