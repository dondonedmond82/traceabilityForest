@echo off
setlocal
chcp 65001 >nul
title Forest Traceability - Demarrage complet
cd /d "%~dp0"

echo ==================================================
echo       FOREST TRACEABILITY - DEMARRAGE COMPLET
echo ==================================================
echo.

if not exist "blockchain.js" (
    echo ERREUR : blockchain.js est introuvable dans %CD%
    echo Placez ce fichier BAT dans le dossier du projet.
    pause
    exit /b 1
)

if not exist "app.py" (
    echo ERREUR : app.py est introuvable dans %CD%
    pause
    exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
    echo ERREUR : Node.js n'est pas installe ou absent du PATH.
    echo Installez Node.js 18 ou plus recent, puis relancez ce fichier.
    pause
    exit /b 1
)

REM Utiliser la meme cle pour le backend et l'interface Panel.
REM Cle de developpement uniquement : remplacez-la avant tout usage partage.
set "API_KEY=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"
set "BLOCKCHAIN_API_URL=http://127.0.0.1:3000/api/v1"

echo [1/4] Verification des dependances Node.js...
if not exist "node_modules\express" (
    echo Installation des dependances JavaScript...
    call npm install
    if errorlevel 1 (
        echo ERREUR : npm install a echoue.
        pause
        exit /b 1
    )
)

echo.
echo [2/4] Demarrage du serveur blockchain dans une nouvelle fenetre...
start "Forest Traceability - API Node.js" cmd /k "cd /d ""%~dp0"" && set ""API_KEY=%API_KEY%"" && node blockchain.js"

echo.
echo [3/4] Attente de l'API sur le port 3000...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$ok=$false; for($i=0; $i -lt 25; $i++){ try { $r=Invoke-RestMethod -Uri 'http://127.0.0.1:3000/api/v1/health' -TimeoutSec 2; if($r.status -eq 'ok'){ $ok=$true; break } } catch {} ; Start-Sleep -Seconds 1 }; if($ok){ Write-Host 'API blockchain accessible.' -ForegroundColor Green; exit 0 } else { Write-Host 'API blockchain inaccessible apres 25 secondes.' -ForegroundColor Red; exit 1 }"

if errorlevel 1 (
    echo.
    echo ECHEC : le serveur Node.js ne repond pas.
    echo Consultez la fenetre "Forest Traceability - API Node.js".
    echo Verifiez les erreurs Node.js et le port 3000.
    pause
    exit /b 1
)

echo.
echo [4/4] Verification et demarrage de Python Panel...

if not exist ".venv\Scripts\activate.bat" (
    echo Creation de l'environnement Python...
    py -3.10 -m venv .venv
    if errorlevel 1 (
        echo ERREUR : impossible de creer l'environnement Python.
        pause
        exit /b 1
    )
)
call ".venv\Scripts\activate.bat"

python -c "import panel, requests, pandas" >nul 2>&1
if errorlevel 1 (
    echo Installation des dependances Python...
    python -m pip install --upgrade pip
    if exist "requirements.txt" (
        python -m pip install -r requirements.txt
    ) else (
        python -m pip install panel pandas requests hvplot
    )
    if errorlevel 1 (
        echo ERREUR : installation des dependances Python impossible.
        pause
        exit /b 1
    )
)

echo.
echo Lancement de l'application web :
echo http://127.0.0.1:5006
echo Laissez cette fenetre et celle du backend ouvertes.
echo.

panel serve app.py --show --autoreload

echo.
echo Le serveur Panel est arrete.
pause
endlocal
