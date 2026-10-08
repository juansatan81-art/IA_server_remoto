#!/usr/bin/env bash
# Arranca el VTuber en Linux o Mac: ./iniciar.sh
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Preparando el entorno por primera vez..."
  python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
else
  . .venv/bin/activate
fi
( sleep 2; (xdg-open http://127.0.0.1:8765/panel || open http://127.0.0.1:8765/panel) >/dev/null 2>&1 ) &
python servidor.py
