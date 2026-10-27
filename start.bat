@echo off
rem First-time setup for Research Hub. Run once; afterwards use the "Research Hub" desktop shortcut.
cd /d "%~dp0"
where py >nul 2>nul || (
  echo Python 3 is not installed. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then run start.bat again.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  echo Setting up Research Hub for the first time. This takes a few minutes...
  py -3 -m venv .venv || goto :failed
  .venv\Scripts\python -m pip install --disable-pip-version-check -q -r requirements.txt || goto :failed
)
if not exist static\vendor\bootstrap\bootstrap.min.css ( .venv\Scripts\python scripts\fetch_vendor.py || goto :failed )
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1
echo.
echo Research Hub is ready. From now on, double-click the "Research Hub" shortcut on your desktop.
echo Opening it now...
start "" .venv\Scripts\pythonw.exe scripts\launch.pyw
timeout /t 5 >nul
exit /b 0

:failed
echo.
echo Setup failed. Check your internet connection and run start.bat again.
echo If the error mentions "Long Path", move this folder to a short path such as C:\ResearchHub,
echo delete the .venv folder inside it, and run start.bat again.
pause
exit /b 1
