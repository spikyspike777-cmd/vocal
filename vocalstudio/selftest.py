"""Hardware-free packaged-app smoke check, used by Windows CI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run(report: Path) -> int:
    result = {}
    try:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from shiboken6 import delete
        from .app import MainWindow, LEARNING
        from .core import create_project
        from .curriculum import LESSONS
        from .worker import ffmpeg_path
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(prefix='vocal-smoke-') as directory:
            library = Path(directory) / 'songs'
            folder = create_project(library, Path('demo.wav'), '')
            command = [sys.executable, '--worker'] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'vocalstudio.worker']
            subprocess.run(command + [str(folder), '--mode', 'demo'], check=True, timeout=90)
            assert json.loads((folder / 'project.json').read_text(encoding='utf-8'))['state'] == 'ready'
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            assert ffmpeg and Path(ffmpeg).exists(), 'Bundled FFmpeg missing'
            subprocess.run([ffmpeg, '-version'], check=True, capture_output=True, timeout=20)
            window = MainWindow(library)
            window.open_project(folder)
            window.show_learning()
            window.show()
            app.processEvents()
            assert window.pages.currentIndex() == LEARNING
            assert len(window.learning.items) == 14
            window.learning.select(0)
            window.learning.answers.button(LESSONS[0].correct).setChecked(True)
            window.learning.check_answer()
            window.learning.mark_complete()
            assert LESSONS[0].id in window.learning.completed
            window.close()
            delete(window)
            result = {'ok': True, 'frozen': bool(getattr(sys, 'frozen', False)),
                      'worker': 'passed', 'ffmpeg': 'passed', 'learning': 'passed'}
    except Exception:
        import traceback
        result = {'ok': False, 'error': traceback.format_exc()}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1
