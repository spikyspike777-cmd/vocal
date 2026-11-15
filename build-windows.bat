@echo off
rem Builds dist\VocalStudio\VocalStudio.exe with PyInstaller. Run setup-windows.bat first.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run setup-windows.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install "pyinstaller>=6"
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name VocalStudio ^
  --collect-all onnxruntime --collect-data imageio_ffmpeg ^
  run.py
if errorlevel 1 goto fail
echo.
echo Done: dist\VocalStudio\VocalStudio.exe
pause
exit /b 0
:fail
echo Build failed. See the error above.
pause
exit /b 1
