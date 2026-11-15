@echo off
cd /d "%~dp0"
py -3.12 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -e .
if errorlevel 1 goto fail
where ffmpeg >nul 2>nul
if errorlevel 1 echo Install FFmpeg: winget install --id Gyan.FFmpeg -e
 echo Setup complete. Start the app with start.bat.
pause
exit /b 0
:fail
 echo Setup failed. See the error above. Python 3.12 is required.
pause
exit /b 1
