@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".env" if exist ".env.example" (
  copy /y ".env.example" ".env" >nul
  echo Created .env from .env.example
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv || exit /b 1
  ) else (
    python -m venv .venv || exit /b 1
  )
)

echo Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip || exit /b 1

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt || exit /b 1

echo.
echo Starting Telegram bot...
echo.
".venv\Scripts\python.exe" main.py
exit /b %errorlevel%
