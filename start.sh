#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/Scripts/python.exe" ] && [ ! -x ".venv/bin/python" ]; then
  python -m venv .venv
fi

if [ -x ".venv/Scripts/python.exe" ]; then
  PYTHON=".venv/Scripts/python.exe"
else
  PYTHON=".venv/bin/python"
fi

"$PYTHON" -m pip install -r requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Vul eerst je nieuwe KLING_API_KEY in .env in en start daarna opnieuw."
  exit 1
fi

"$PYTHON" -m streamlit run app.py
