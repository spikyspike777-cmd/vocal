# Build on Windows. A folder bundle keeps startup fast and includes native audio DLLs.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

root = Path(SPECPATH).parent
onnx_data, onnx_binaries, onnx_hidden = collect_all('onnxruntime')
data = onnx_data + collect_data_files('imageio_ffmpeg') + collect_data_files('_sounddevice_data')
a = Analysis(
    [str(root / 'run.py')], pathex=[str(root)],
    binaries=onnx_binaries, datas=data,
    hiddenimports=onnx_hidden + ['vocalstudio.worker', 'vocalstudio.selftest'],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'torch', 'torchaudio', 'demucs'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='VocalStudio',
          debug=False, strip=False, upx=False, console=False,
          icon=str(root / 'assets' / 'vocalstudio.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='VocalStudio')
