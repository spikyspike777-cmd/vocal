@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build-windows.ps1 %*
if errorlevel 1 (
  echo Build failed. See the error above.
  pause
  exit /b 1
)
echo Done. Open dist for the installer and portable app.
pause
