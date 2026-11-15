@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -e .
if errorlevel 1 goto fail
echo.
echo Setup complete. Start the app with start.bat.
pause
exit /b 0
:fail
echo.
echo Setup failed. See the error above. Python 3.10-3.13 (64-bit) from python.org is required.
pause
exit /b 1
