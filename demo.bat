@echo off
rem Open a DEMO copy of Research Hub filled with made-up sample data (port 8010, folder sample-data\).
rem Your real data in data\ is never touched. Delete the sample-data folder to reset the demo.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run start.bat once first; it installs Research Hub.
  pause
  exit /b 1
)
set "RESEARCH_HUB_DATA=%~dp0sample-data"
set "RESEARCH_HUB_PORT=8010"
.venv\Scripts\python scripts\load_sample_data.py || ( pause & exit /b 1 )
start "" .venv\Scripts\pythonw.exe scripts\launch.pyw
