@echo off
rem Arranca el VTuber en Windows: doble clic en este archivo.
cd /d "%~dp0"
if not exist .venv (
  echo Preparando el entorno por primera vez...
  python -m venv .venv || (echo No encuentro Python. Instalalo desde python.org marcando "Add to PATH". & pause & exit /b)
  call .venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)
start "" http://127.0.0.1:8765/panel
python servidor.py
pause
