@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Eerste installatie wordt uitgevoerd...
  py -m venv .venv
  if errorlevel 1 goto :error
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo.
  echo LET OP: .env is aangemaakt.
  echo Vul eerst je nieuwe KLING_API_KEY in .env in.
  start notepad ".env"
  pause
  exit /b
)

".venv\Scripts\python.exe" -m streamlit run app.py
goto :eof

:error
echo.
echo Installatie mislukt. Controleer of Python 3.11 is geinstalleerd.
pause
