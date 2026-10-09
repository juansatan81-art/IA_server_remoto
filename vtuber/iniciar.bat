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
rem Instala lo que falte y pone al dia edge-tts (Microsoft cambia a veces su servicio de voz)
pip install -q -r requirements.txt
pip install -q -U edge-tts
rem Si quedo abierto un servidor anterior (por ejemplo de otra ventana), se cierra
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; if ($p -and $p.ProcessName -like 'python*') { Stop-Process -Id $p.Id -Force; Write-Host 'Cerrado un servidor anterior que seguia abierto.' } }"
start "" http://127.0.0.1:8765/panel
python servidor.py
pause
