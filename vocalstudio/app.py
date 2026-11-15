from __future__ import annotations

import bisect
import json
import os
import sys
from pathlib import Path

import sounddevice as sd
from PySide6.QtCore import QProcess, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSlider, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .audio import AudioEngine
from .core import active_line, atomic_json, cents_error, create_project, detect_pitch, note_name, parse_lyrics
from .widgets import PitchTimeline

STYLE = '''
QWidget { background: #0e121b; color: #e9edf7; font-family: "Inter", "Segoe UI", sans-serif; font-size: 14px; }
QMainWindow { background: #0e121b; }
QLabel#muted { color: #8996ad; }
QLabel#heading { font-size: 29px; font-weight: 700; }
QLabel#brand { font-size: 20px; font-weight: 700; color: #c1baff; }
QLabel#lyric { font-size: 27px; font-weight: 600; padding: 18px; color: #f5f2ff; }
QLabel#metric { font-size: 19px; font-weight: 600; color: #6ee6be; }
QPushButton { background: #222b3c; border: 1px solid #323e53; padding: 10px 16px; border-radius: 8px; }
QPushButton:hover { background: #303c54; }
QPushButton:disabled { color: #657085; background: #181e2a; }
QPushButton#primary { background: #8674ef; color: #ffffff; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #9787ff; }
QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox { background: #171e2b; border: 1px solid #303a4d; border-radius: 7px; padding: 9px; selection-background-color: #6352b6; }
QListWidget { background: #121824; border: none; border-radius: 10px; padding: 8px; }
QListWidget::item { padding: 14px 8px; border-radius: 7px; }
QListWidget::item:selected { background: #302b4e; color: #d5ceff; }
QTableWidget { background: #141b27; border: 1px solid #2a3447; gridline-color: #252f40; selection-background-color: #3d355e; }
QHeaderView::section { background: #1e2737; border: none; padding: 8px; }
QSlider::groove:horizontal { height: 5px; background: #2c364b; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #a393ff; border-radius: 2px; }
QSlider::handle:horizontal { background: #d5ccff; width: 13px; margin: -4px 0; border-radius: 6px; }
QProgressBar { border: none; background: #20283a; height: 5px; border-radius: 2px; }
QProgressBar::chunk { background: #9482ff; }
QCheckBox { spacing: 8px; }
QSplitter::handle { background: #20283a; }
'''


def label(text, style=None):
    item = QLabel(text)
    if style:
        item.setObjectName(style)
    item.setWordWrap(True)
    return item


def button(text, callback, primary=False):
    item = QPushButton(text)
    if primary:
        item.setObjectName('primary')
    item.clicked.connect(callback)
    return item


def clock(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds // 60:02}:{seconds % 60:02}'


class MainWindow(QMainWindow):
    def __init__(self, library: Path | None = None):
        super().__init__()
        self.setWindowTitle('Vocal Studio — пой в свою ноту')
        self.resize(1240, 920)
        self.setMinimumSize(980, 780)
        self.library = library or Path(os.environ.get('VOCALSTUDIO_LIBRARY') or
            str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / 'songs'))
        self.library.mkdir(parents=True, exist_ok=True)
        self.audio = AudioEngine()
        self.project = None
        self.folder = None
        self.source = None
        self.process = None
        self.job_folder = None
        self.log_tail = ''
        self.reference = {'times': [], 'midi': []}
        self.score = []
        self.last_scored = None
        self.table_loading = False
        self.seeking = False
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(20, 22, 24, 20)
        layout.setSpacing(24)
        sidebar = QWidget()
        sidebar.setFixedWidth(235)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 0)
        side.addWidget(label('◉  VOCAL STUDIO', 'brand'))
        side.addWidget(label('Твоя домашняя вокальная студия', 'muted'))
        side.addSpacing(25)
        self.new_button = button('+  Добавить песню', self.new_song, True)
        side.addWidget(self.new_button)
        side.addSpacing(16)
        side.addWidget(label('МОЯ БИБЛИОТЕКА', 'muted'))
        self.songs = QListWidget()
        self.songs.itemClicked.connect(self.open_item)
        side.addWidget(self.songs, 1)
        self.demo_button = button('♪  Попробовать распевку', self.make_demo)
        side.addWidget(self.demo_button)
        side.addWidget(label('Локальное хранение\nАудио не отправляется на сервер', 'muted'))
        layout.addWidget(sidebar)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        self.build_setup()
        self.build_studio()
        self.build_status()
        self.refresh_library()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(40)

    def build_setup(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label('Добавим твою песню', 'heading'))
        layout.addWidget(label('Выбери аудио и вставь текст. Всё остальное — здесь, на компьютере.', 'muted'))
        layout.addSpacing(22)
        layout.addWidget(label('01  АУДИОФАЙЛ', 'muted'))
        file_row = QHBoxLayout()
        self.file_label = label('MP3, WAV, FLAC, M4A или OGG', 'muted')
        file_row.addWidget(self.file_label, 1)
        file_row.addWidget(button('Выбрать файл…', self.choose_source))
        layout.addLayout(file_row)
        layout.addSpacing(22)
        layout.addWidget(label('02  ТЕКСТ ПЕСНИ', 'muted'))
        self.lyrics_input = QPlainTextEdit()
        self.lyrics_input.setPlaceholderText('Вставь текст сюда…\n\nКаждая строка — отдельная фраза караоке.\nМожно вставить LRC с метками [00:12.50].')
        layout.addWidget(self.lyrics_input, 1)
        layout.addWidget(label('Обычный текст размечается по строкам на экране исполнения. '
                               'Автоматической синхронизации текста в этой версии пока нет.', 'muted'))
        layout.addSpacing(12)
        layout.addWidget(label('03  ПОДГОТОВКА', 'muted'))
        layout.addWidget(label('Встроенный алгоритм выделит вокал по повторениям музыки и стереопанораме. '
                               'Работает офлайн, без скачивания моделей. Качество зависит от записи; поддерживаются песни до 10 минут.', 'muted'))
        row = QHBoxLayout()
        row.addWidget(button('Подготовить песню', self.prepare_song, True))
        row.addWidget(button('У меня уже есть вокал и минус', self.import_stems))
        layout.addLayout(row)
        self.pages.addWidget(page)

    def build_studio(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.song_title = label('Исполнение', 'heading')
        top.addWidget(self.song_title, 1)
        top.addWidget(button('Текст и разметка', self.toggle_editor))
        layout.addLayout(top)
        layout.addWidget(label('Фиолетовый — мелодия • Зелёный — попадание • Оранжевый — выше или ниже', 'muted'))
        self.timeline = PitchTimeline()
        layout.addWidget(self.timeline, 1)
        self.current_lyric = label('♪', 'lyric')
        self.current_lyric.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.current_lyric)
        self.next_lyric = label('Добавь текст и отметь начало каждой строки', 'muted')
        self.next_lyric.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.next_lyric)
        metrics = QHBoxLayout()
        self.pitch_label = label('Голос: —', 'metric')
        self.feedback = label('Подключи микрофон', 'metric')
        self.score_label = label('Попадание: —', 'muted')
        for item in [self.pitch_label, self.feedback, self.score_label]:
            metrics.addWidget(item)
        layout.addLayout(metrics)
        transport = QHBoxLayout()
        self.play_button = button('▶  Петь', self.toggle_play, True)
        transport.addWidget(self.play_button)
        transport.addWidget(button('↺', self.restart))
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.sliderPressed.connect(lambda: setattr(self, 'seeking', True))
        self.seek.sliderReleased.connect(self.seek_released)
        transport.addWidget(self.seek, 1)
        self.time_label = label('00:00 / 00:00', 'muted')
        transport.addWidget(self.time_label)
        layout.addLayout(transport)
        levels = QHBoxLayout()
        for title, initial, attribute in [('Минус', 80, 'backing_volume'), ('Вокал-подсказка', 25, 'guide_volume')]:
            levels.addWidget(label(title, 'muted'))
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(initial)
            slider.valueChanged.connect(lambda value, key=attribute: setattr(self.audio, key, value / 100))
            levels.addWidget(slider)
        layout.addLayout(levels)
        mic_row = QHBoxLayout()
        self.mic_devices = QComboBox()
        self.mic_devices.setMaximumWidth(260)
        self.mic_devices.setMinimumWidth(160)
        self.mic_devices.addItem('Микрофон по умолчанию', None)
        try:
            for i, device in enumerate(sd.query_devices()):
                if device['max_input_channels']:
                    self.mic_devices.addItem(device['name'], i)
        except sd.PortAudioError:
            pass
        mic_row.addWidget(self.mic_devices, 1)
        self.mic_button = button('Включить микрофон', self.toggle_mic)
        mic_row.addWidget(self.mic_button)
        self.octaves = QCheckBox('Любая октава')
        self.octaves.setToolTip('Разрешает петь на октаву выше или ниже оригинала')
        self.octaves.toggled.connect(self.reset_score)
        mic_row.addWidget(self.octaves)
        layout.addLayout(mic_row)
        options = QHBoxLayout()
        options.addWidget(label('Компенсация задержки, мс', 'muted'))
        self.delay = QDoubleSpinBox()
        self.delay.setRange(-500, 1000)
        self.delay.setSingleStep(10)
        self.delay.setValue(80)
        self.delay.setDecimals(0)
        self.delay.setToolTip('Положительное значение сдвигает измеренный голос назад по времени. Подбери в наушниках.')
        self.delay.valueChanged.connect(self.reset_score)
        options.addWidget(self.delay)
        options.addStretch()
        options.addWidget(label('Рекомендуем петь в наушниках', 'muted'))
        layout.addLayout(options)
        self.editor = QWidget()
        editor_layout = QVBoxLayout(self.editor)
        editor_layout.setContentsMargins(0, 8, 0, 0)
        self.line_table = QTableWidget(0, 2)
        self.line_table.setHorizontalHeaderLabels(['Начало, сек.', 'Текст строки'])
        self.line_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.line_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.line_table.setMaximumHeight(170)
        self.line_table.itemChanged.connect(self.save_table)
        editor_layout.addWidget(self.line_table)
        editor_row = QHBoxLayout()
        editor_row.addWidget(button('Отметить строку сейчас ↓', self.stamp_line, True))
        editor_row.addWidget(button('Заменить текст…', self.replace_lyrics))
        editor_layout.addLayout(editor_row)
        editor_layout.addWidget(label('Выбери первую строку, включи песню и отмечай начало каждой фразы. '
                                      'Выбор перейдёт к следующей строке. Время можно исправить в таблице.', 'muted'))
        layout.addWidget(self.editor)
        self.editor.hide()
        self.pages.addWidget(page)

    def build_status(self):
        self.status_label = QLabel('Готов к работе')
        self.statusBar().addWidget(self.status_label, 1)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(150)
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)

    def report_error(self, message):
        self.status_label.setText('Не удалось выполнить действие')
        QMessageBox.warning(self, 'Vocal Studio', str(message))

    def refresh_library(self):
        self.songs.clear()
        for path in sorted(self.library.glob('*/project.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if data.get('state') != 'ready':
                    continue
                item = QListWidgetItem(f"♪  {data['title']}\n    {clock(data.get('duration', 0))}")
                item.setData(Qt.ItemDataRole.UserRole, str(path.parent))
                self.songs.addItem(item)
            except (ValueError, OSError, KeyError):
                continue

    def new_song(self):
        self.audio.pause()
        self.pages.setCurrentIndex(0)

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Выбрать песню', '', 'Аудио (*.mp3 *.wav *.flac *.m4a *.ogg *.aac);;Все файлы (*)')
        if path:
            self.source = Path(path)
            self.file_label.setText(self.source.name)

    def prepare_song(self):
        if not self.source:
            self.report_error('Сначала выбери аудиофайл.')
            return
        import shutil
        if not shutil.which('ffmpeg'):
            self.report_error('Установи FFmpeg и добавь его в PATH. Инструкция — в README.md.')
            return
        folder = create_project(self.library, self.source, self.lyrics_input.toPlainText())
        self.start_job(folder, 'separate')

    def import_stems(self):
        vocal, _ = QFileDialog.getOpenFileName(self, 'Выбрать отдельный вокал', '', 'Аудио (*.wav *.mp3 *.flac *.m4a *.ogg)')
        if not vocal:
            return
        backing, _ = QFileDialog.getOpenFileName(self, 'Выбрать минус той же длительности', '', 'Аудио (*.wav *.mp3 *.flac *.m4a *.ogg)')
        if not backing:
            return
        folder = create_project(self.library, self.source or Path(vocal), self.lyrics_input.toPlainText())
        self.start_job(folder, 'import', ['--vocal', vocal, '--backing', backing])

    def make_demo(self):
        folder = create_project(self.library, Path('Первая распевка.wav'), '')
        self.start_job(folder, 'demo')

    def start_job(self, folder, mode, extra=None):
        if self.process:
            return
        self.audio.pause()
        self.job_folder = folder
        self.log_tail = ''
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_progress)
        self.process.finished.connect(self.job_finished)
        self.process.errorOccurred.connect(self.job_error)
        self.pages.setEnabled(False)
        self.new_button.setEnabled(False)
        self.demo_button.setEnabled(False)
        self.songs.setEnabled(False)
        self.progress.show()
        self.status_label.setText('Начинаем подготовку…')
        self.process.setWorkingDirectory(str(Path(__file__).resolve().parent.parent))
        self.process.start(sys.executable, ['-u', '-m', 'vocalstudio.worker', str(folder), '--mode', mode] + (extra or []))

    def read_progress(self):
        if not self.process:
            return
        text = bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self.log_tail = (self.log_tail + text)[-10000:]
        rows = text.replace('\r', '\n').strip().splitlines()
        if rows:
            self.status_label.setText(rows[-1][:180])

    def job_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.log_tail += '\nНе удалось запустить процесс Python.'
            self.job_finished(1, QProcess.ExitStatus.CrashExit)

    def job_finished(self, code, status):
        if not self.process:
            return
        self.read_progress()
        self.process.deleteLater()
        self.process = None
        self.pages.setEnabled(True)
        self.new_button.setEnabled(True)
        self.demo_button.setEnabled(True)
        self.songs.setEnabled(True)
        self.progress.hide()
        if code == 0:
            self.refresh_library()
            self.open_project(self.job_folder)
            self.status_label.setText('Песня готова. Можно петь!')
        else:
            (self.job_folder / 'processing.log').write_text(self.log_tail, encoding='utf-8')
            self.report_error('Подготовка не завершена.\n\n' + self.log_tail[-1800:])

    def open_item(self, item):
        self.open_project(Path(item.data(Qt.ItemDataRole.UserRole)))

    def open_project(self, folder):
        try:
            project = json.loads((folder / 'project.json').read_text(encoding='utf-8'))
            reference = json.loads((folder / 'reference.json').read_text(encoding='utf-8'))
            self.audio.load(folder)
        except (OSError, ValueError, KeyError) as error:
            self.report_error(error)
            return
        self.folder, self.project, self.reference = folder, project, reference
        self.timeline.set_reference(reference)
        self.song_title.setText(project['title'])
        self.seek.setRange(0, int(self.audio.duration * 1000))
        self.reset_score()
        self.populate_table()
        self.pages.setCurrentIndex(1)
        self.editor.setVisible(bool(project['lines']) and any(line['time'] is None for line in project['lines']))

    def reset_score(self, *args):
        self.score = []
        self.last_scored = None
        self.timeline.history = []
        self.score_label.setText('Попадание: —')

    def toggle_play(self):
        try:
            if self.audio.playing:
                self.audio.pause()
            else:
                if self.audio.position >= len(self.audio.backing):
                    self.reset_score()
                self.audio.play()
        except (sd.PortAudioError, ValueError) as error:
            self.audio.pause()
            self.report_error(f'Не удалось открыть аудиовыход. Проверь устройство звука.\n{error}')

    def restart(self):
        self.audio.seek(0)
        self.reset_score()

    def seek_released(self):
        self.audio.seek(self.seek.value() / 1000)
        self.seeking = False
        self.reset_score()

    def toggle_mic(self):
        try:
            if self.audio.input is None:
                self.audio.start_microphone(self.mic_devices.currentData())
                self.mic_button.setText('Выключить микрофон')
                self.mic_devices.setEnabled(False)
            else:
                self.audio.stop_microphone()
                self.mic_button.setText('Включить микрофон')
                self.mic_devices.setEnabled(True)
        except (sd.PortAudioError, ValueError) as error:
            self.audio.stop_microphone()
            self.report_error(f'Не удалось открыть микрофон. Проверь подключение и разрешения системы.\n{error}')

    def toggle_editor(self):
        self.editor.setVisible(not self.editor.isVisible())

    def populate_table(self):
        self.table_loading = True
        lines = self.project['lines']
        self.line_table.setRowCount(len(lines))
        for row, line in enumerate(lines):
            self.line_table.setItem(row, 0, QTableWidgetItem('' if line['time'] is None else f"{line['time']:.2f}"))
            self.line_table.setItem(row, 1, QTableWidgetItem(line['text']))
        if lines:
            self.line_table.selectRow(0)
        self.table_loading = False

    def save_table(self, item):
        if self.table_loading or not self.project:
            return
        old = self.project['lines'][item.row()]
        if item.column() == 0:
            try:
                value = float(item.text().replace(',', '.')) if item.text().strip() else None
                if value is not None and not 0 <= value <= self.audio.duration:
                    raise ValueError()
            except ValueError:
                self.table_loading = True
                item.setText('' if old['time'] is None else f"{old['time']:.2f}")
                self.table_loading = False
                self.status_label.setText('Время должно быть числом от 0 до длительности песни.')
                return
            old['time'] = value
        else:
            old['text'] = item.text()
        atomic_json(self.folder / 'project.json', self.project)
        self.status_label.setText('Разметка сохранена')

    def stamp_line(self):
        row = self.line_table.currentRow()
        if row < 0:
            return
        self.line_table.item(row, 0).setText(f'{self.audio.seconds:.2f}')
        if row + 1 < self.line_table.rowCount():
            self.line_table.selectRow(row + 1)

    def replace_lyrics(self):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dialog = QDialog(self)
        dialog.setWindowTitle('Текст песни')
        dialog.resize(560, 430)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('Вставь текст или LRC. При сохранении прежняя разметка будет заменена.', 'muted'))
        edit = QPlainTextEdit()
        edit.setPlainText(self.project.get('lyrics', ''))
        layout.addWidget(edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.project['lyrics'] = edit.toPlainText()
            self.project['lines'] = parse_lyrics(edit.toPlainText())
            atomic_json(self.folder / 'project.json', self.project)
            self.populate_table()

    def tick(self):
        position = self.audio.seconds
        self.timeline.position = position
        if not self.seeking:
            self.seek.setValue(int(position * 1000))
        self.time_label.setText(f'{clock(position)} / {clock(self.audio.duration)}')
        self.play_button.setText('Ⅱ  Пауза' if self.audio.playing else '▶  Петь')
        if self.project:
            lines = self.project['lines']
            index = active_line(lines, position)
            if index is not None:
                self.current_lyric.setText(lines[index]['text'])
                self.next_lyric.setText(lines[index + 1]['text'] if index + 1 < len(lines) else '♪')
            else:
                self.current_lyric.setText('♪  Приготовься' if any(line['time'] is not None for line in lines) else 'Текст ещё не размечен')
                self.next_lyric.setText(lines[0]['text'] if lines else 'Открой «Текст и разметка», чтобы добавить слова')
        samples = self.audio.microphone_samples()
        midi = detect_pitch(samples, self.audio.input_rate)[0] if samples is not None else None
        self.pitch_label.setText(f'Голос: {note_name(midi)}')
        self.feedback.setText('Пой в микрофон' if self.audio.input is not None else 'Подключи микрофон')
        if self.audio.playing and self.audio.input is not None:
            stamp = position - self.delay.value() / 1000
            times = self.reference['times']
            index = bisect.bisect_right(times, stamp) - 1
            target = self.reference['midi'][index] if 0 <= index < len(times) and stamp - times[index] < .06 else None
            good = False
            display_midi = midi
            if target is not None:
                error = cents_error(midi, target, self.octaves.isChecked()) if midi is not None else None
                good = error is not None and abs(error) <= 50
                if self.last_scored != index:
                    self.score.append(good)
                    self.last_scored = index
                if error is None:
                    self.feedback.setText('Спой эту ноту')
                elif good:
                    self.feedback.setText('В ноту ✓')
                else:
                    self.feedback.setText('Пой ниже ↓' if error > 0 else 'Пой выше ↑')
                if midi is not None and self.octaves.isChecked():
                    display_midi = target + error / 100
            else:
                self.feedback.setText('Пауза в мелодии')
            self.timeline.history.append((stamp, display_midi, good))
            self.timeline.history = [point for point in self.timeline.history if point[0] >= position - 15]
            if self.score:
                self.score_label.setText(f'Попадание: {sum(self.score) / len(self.score):.0%}')
        self.timeline.update()

    def closeEvent(self, event):
        if self.process is not None:
            QMessageBox.information(self, 'Идёт обработка', 'Дождись завершения подготовки песни перед закрытием приложения.')
            event.ignore()
            return
        self.timer.stop()
        self.audio.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('VocalStudio')
    app.setOrganizationName('VocalStudio')
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
