@echo off
REM Run the whole weekly cycle. Double-click, or schedule with Task Scheduler (Sundays 6pm).
cd /d "%~dp0.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
school-planner weekly %*
for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set TODAY=%%c-%%a-%%b
if exist "data\outbox\week-%TODAY%" start "" "data\outbox\week-%TODAY%"
pause
