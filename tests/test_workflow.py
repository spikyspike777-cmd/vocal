import json
import os
from pathlib import Path
import subprocess
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PySide6.QtWidgets import QApplication
from vocalstudio.app import MainWindow, STYLE
from vocalstudio.audio import AudioEngine
from vocalstudio.core import create_project
from vocalstudio.worker import prepare

_APP = QApplication.instance() or QApplication([])


def test_complete_demo_gui_persistence_and_mixer(tmp_path):
    folder = create_project(tmp_path, Path('demo.wav'), '')
    process = subprocess.run([sys.executable, '-m', 'vocalstudio.worker', str(folder), '--mode', 'demo'], capture_output=True, text=True, encoding='utf-8')
    assert process.returncode == 0, process.stdout + process.stderr
    metadata = json.loads((folder / 'project.json').read_text(encoding='utf-8'))
    assert metadata['state'] == 'ready'
    reference = json.loads((folder / 'reference.json').read_text(encoding='utf-8'))
    pitches = [p for t, p in zip(reference['times'], reference['midi']) if 2.2 < t < 3.5 and p is not None]
    assert len(pitches) > 40
    assert abs(np.median(pitches) - 60) < .15

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    window = MainWindow(tmp_path)
    window.open_project(folder)
    assert window.songs.count() == 1
    window.show()
    app.processEvents()
    assert window.pages.currentIndex() == 1
    assert len(window.notes) == 8
    assert [round(note['midi']) for note in window.notes] == [60, 62, 64, 67, 65, 64, 62, 60]

    # Manual sync: tapping stamps the focused line and moves on to the next one.
    window.audio.seek(5)
    window.set_sync_mode(True)
    window.line_clicked(0)
    window.stamp_line()
    assert json.loads((folder / 'project.json').read_text(encoding='utf-8'))['lines'][0]['time'] == 5
    assert window.sync_index == 1
    window.set_sync_mode(False)
    window.tick()
    assert window.lyrics_view.active == 0  # the line stamped at 5.0 s is the latest one
    # Clicking a lyric line seeks slightly before it.
    window.line_clicked(3)
    assert abs(window.audio.seconds - (window.project['lines'][3]['time'] - .3)) < .01

    # Singing the right note an octave lower is a hit in any-octave mode and lights the note up.
    window.octaves.setChecked(True)
    window.delay.setValue(0)
    window.audio.seek(2.5)
    window.audio.input = object()
    window.audio.input_rate = 44100
    tone = .2 * np.sin(2 * np.pi * 130.8128 * np.arange(3087) / 44100)
    window.audio.microphone_samples = lambda: tone
    window.audio.playing = True
    for _ in range(4):
        window.last_tick -= .016
        window.tick()
    assert window.feedback.text() == 'В ноту ✓'
    assert window.timeline.hits[0]
    assert window.score_hit > 0
    window.audio.microphone_samples = lambda: tone * 0
    window.audio.playing = False
    window.audio.input = None
    window.grab().save(str(tmp_path / 'studio.png'))

    engine = window.audio
    engine.seek(2.5)
    engine.playing = True  # exercise the real output callback without opening hardware
    data = np.zeros((512, 2), dtype='float32')
    engine.callback(data, 512, None, None)
    assert np.max(np.abs(data)) > .01
    assert engine.position == int(2.5 * 44100) + 512
    engine.seek(engine.duration - .001)
    engine.callback(data, 512, None, None)
    assert not engine.playing
    assert np.all(data[100:] == 0)
    window.close()
    window.timer.stop()
    from shiboken6 import delete
    delete(window)


def test_import_stems_and_length_validation(tmp_path):
    import soundfile as sf
    sample = np.sin(2 * np.pi * 220 * np.arange(22050) / 22050) * .2
    vocal, backing = tmp_path / 'voice.wav', tmp_path / 'back.wav'
    sf.write(vocal, sample, 22050)
    sf.write(backing, sample * .1, 22050)
    folder = create_project(tmp_path / 'library', vocal, 'Ла')
    prepare(folder, 'import', str(vocal), str(backing))
    engine = AudioEngine()
    engine.load(folder)
    assert engine.sample_rate == 44100
    assert engine.duration == 1
    sf.write(folder / 'instrumental.wav', np.zeros((22050, 2)), 44100)
    import pytest
    with pytest.raises(ValueError, match='Длительности'):
        engine.load(folder)


def test_own_separator_complete_file_workflow_without_model_imports(tmp_path, monkeypatch):
    import builtins
    import socket
    import soundfile as sf
    from test_separation import known_mix

    real_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name.split('.')[0] in {'torch', 'torchaudio', 'demucs'}:
            raise AssertionError(f'Unexpected external separator dependency: {name}')
        return real_import(name, *args, **kwargs)
    def no_network(*args, **kwargs):
        raise AssertionError('Separation must not access the network')
    monkeypatch.setattr(builtins, '__import__', guarded_import)
    monkeypatch.setattr(socket, 'create_connection', no_network)
    voice, backing = known_mix()
    source = tmp_path / 'song.wav'
    sf.write(source, voice + backing, 22050, subtype='FLOAT')
    folder = create_project(tmp_path / 'library', source, '[00:02.00]Ла-а-а')
    prepare(folder, 'separate')
    project = json.loads((folder / 'project.json').read_text(encoding='utf-8'))
    assert project['state'] == 'ready'
    assert project['separator'] == 'repetition-centre-v1'
    assert project['lines'][0]['time'] == 2
    assert not (folder / 'source.wav').exists()
    engine = AudioEngine()
    engine.load(folder)
    assert engine.duration == 12
    reference = json.loads((folder / 'reference.json').read_text(encoding='utf-8'))
    notes = [p for t, p in zip(reference['times'], reference['midi']) if 2.3 < t < 3 and p is not None]
    assert len(notes) > 20


def test_neural_engine_falls_back_to_builtin_separator_when_model_is_unavailable(tmp_path, monkeypatch):
    import soundfile as sf
    from test_separation import known_mix
    from vocalstudio import neural

    def offline(models, progress=None):
        raise OSError('offline')
    monkeypatch.setattr(neural, 'ensure_model', offline)
    voice, backing = known_mix()
    source = tmp_path / 'song.wav'
    sf.write(source, voice + backing, 22050, subtype='FLOAT')
    folder = create_project(tmp_path / 'library', source, 'Первая строка\nВторая строка', 'Моя песня')
    prepare(folder, 'separate', engine='neural', models=tmp_path / 'models')
    project = json.loads((folder / 'project.json').read_text(encoding='utf-8'))
    assert project['title'] == 'Моя песня'
    assert project['separator'] == 'repetition-centre-v1'
    # Plain lyrics are placed on the timeline automatically, in order.
    times = [line['time'] for line in project['lines']]
    assert all(line['auto'] for line in project['lines'])
    assert 0 <= times[0] < times[1] < 12


def test_lyrics_dialog_fills_text_from_search_result(monkeypatch):
    from vocalstudio import app as app_module
    found = [{'title': 'Song', 'artist': 'Band', 'duration': 200., 'synced': True, 'lyrics': '[00:01.00]Hello'}]
    monkeypatch.setattr(app_module.lyrics_online, 'search', lambda query: found)
    dialog = app_module.LyricsDialog(None, '', 'Band Song')
    dialog.search()
    dialog.worker.wait()
    _APP.processEvents()
    assert dialog.list.count() == 1
    dialog.pick(dialog.list.item(0))
    assert dialog.text() == '[00:01.00]Hello'
    dialog.reject()
