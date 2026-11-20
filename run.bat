@echo off
setlocal
cd /d "%~dp0"

rem Force UTF-8 so Chinese/emoji log messages do not crash on Windows console.
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"

set "PY=.venv\Scripts\python.exe"

rem 1) Create the virtual environment if it does not exist
if not exist "%PY%" (
  echo [1/3] Creating virtual environment in .venv ...
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if not exist "%PY%" goto :fail
) else (
  echo [1/3] Virtual environment found.
)

rem 2) Install dependencies only when they are missing
"%PY%" -c "import fastapi, uvicorn, requests, websocket" >nul 2>nul
if errorlevel 1 (
  echo [2/3] Installing dependencies from requirements.txt ...
  "%PY%" -m pip install --upgrade pip
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
) else (
  echo [2/3] Dependencies already installed.
)

rem 3) Resolve host/port: arguments > environment > .env > defaults
set "HOST="
set "PORT="
if not "%~1"=="" set "HOST=%~1"
if not "%~2"=="" set "PORT=%~2"
if not defined HOST if defined MUSE2API_HOST set "HOST=%MUSE2API_HOST%"
if not defined PORT if defined MUSE2API_PORT set "PORT=%MUSE2API_PORT%"
if not defined HOST for /f "tokens=1,* delims==" %%A in ('findstr /b /c:"MUSE2API_HOST=" .env 2^>nul') do set "HOST=%%B"
if not defined PORT for /f "tokens=1,* delims==" %%A in ('findstr /b /c:"MUSE2API_PORT=" .env 2^>nul') do set "PORT=%%B"
if not defined HOST set "HOST=127.0.0.1"
if not defined PORT set "PORT=18610"

echo [3/3] Starting Muse2API ...
echo   URL:   http://%HOST%:%PORT%
echo   Admin: http://%HOST%:%PORT%/admin
echo   Press Ctrl+C to stop.
echo.

"%PY%" -m uvicorn app:app --host %HOST% --port %PORT%
if errorlevel 1 goto :fail
goto :eof

:fail
echo.
echo Startup failed. See errors above.
pause
exit /b 1