@echo off
setlocal
cd /d "%~dp0landscaping_app"

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

echo Starting Landscaping App on http://127.0.0.1:5050
echo Press Ctrl+C to stop.
"%PY%" app.py

echo.
echo App stopped. Press any key to close.
pause >nul
