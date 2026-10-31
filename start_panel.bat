@echo off
cd /d "%~dp0"
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
set BLOCKCHAIN_API_URL=http://127.0.0.1:3000/api/v1
set API_KEY=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
panel serve app.py --show --autoreload
pause
