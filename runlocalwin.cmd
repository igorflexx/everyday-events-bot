@echo off
setlocal EnableExtensions
title everyday-events-bot launcher

call :main
set "EXIT_CODE=%errorlevel%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] Script finished with code %EXIT_CODE%.
  echo Press any key to close this window.
  pause >nul
)
exit /b %EXIT_CODE%

:main
cd /d "%~dp0"

if not exist ".env" (
  >".env" echo BOT_TOKEN=PASTE_YOUR_BOT_TOKEN_HERE
  >>".env" echo DATABASE_PATH=data/everyday_events.db
  echo Created .env with local defaults
)

set "BOT_TOKEN_VALUE="
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /i "BOT_TOKEN=" ".env"`) do set "BOT_TOKEN_VALUE=%%B"

if not defined BOT_TOKEN_VALUE (
  echo [ERROR] Open .env and set BOT_TOKEN to your Telegram bot token.
  exit /b 1
)

if /i "%BOT_TOKEN_VALUE%"=="PASTE_YOUR_BOT_TOKEN_HERE" (
  echo [ERROR] Open .env and set BOT_TOKEN to your Telegram bot token.
  exit /b 1
)

if /i "%BOT_TOKEN_VALUE%"=="your_telegram_bot_token_here" (
  echo [ERROR] Open .env and set BOT_TOKEN to your Telegram bot token.
  exit /b 1
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

echo Installing dependencies...
call :install_requirements || exit /b 1

echo.
echo Starting Telegram bot...
echo.
".venv\Scripts\python.exe" main.py
exit /b %errorlevel%

:install_requirements
set "NO_PROXY=*"
set "no_proxy=*"
set "ALL_PROXY="
set "all_proxy="
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "http_proxy="
set "https_proxy="
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
".venv\Scripts\python.exe" -m pip install -r requirements.txt
exit /b %errorlevel%
