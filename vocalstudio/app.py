from __future__ import annotations

import json
import os
import re
import shutil
import statistics
import sys
import time
from collections import deque
from pathlib import Path

import sounddevice as sd
from PySide6.QtCore import QProcess, QSettings, QSize, QStandardPaths, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSlider, QSpinBox,
    QStackedWidget, QStyle, QVBoxLayout, QWidget,
)

from . import lyrics_online, neural
from .audio import AudioEngine
from .learning import LearningPage
from .core import (
    active_line, atomic_json, auto_align, cents_error, create_project, detect_pitch,
    note_at, note_name, parse_lyrics, realign_following,
)
from .widgets import (
    ACCENT, DropZone, LevelMeter, LyricsView, MUTED, PitchTimeline, PlayButton, TEXT, icon,
)

AUDIO_FILTER = 'Аудио (*.mp3 *.wav *.flac *.m4a *.ogg *.aac *.opus *.wma);;Все файлы (*)'
AUDIO_SUFFIXES = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac', '.opus', '.wma', '.aiff', '.aif', '.mp4', '.webm'}
TOLERANCE_CENTS = 60
SETUP, STUDIO, BUSY, LEARNING = 0, 1, 2, 3

STYLE = '''
* { font-family: "Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Noto Sans", sans-serif; font-size: 14px; color: #f3f4f8; outline: none; }
QMainWindow, QWidget#root, QDialog { background: #0b0c12; }
QLabel { background: transparent; }
QLabel#muted { color: #8a90a6; }
QLabel#small { color: #8a90a6; font-size: 12px; }
QLabel#caps { color: #6f7590; font-size: 11px; font-weight: 700; letter-spacing: 1.4px; }
QLabel#heading { font-size: 30px; font-weight: 800; }
QLabel#title { font-size: 26px; font-weight: 800; }
QLabel#brand { font-size: 19px; font-weight: 800; }
QLabel#panelTitle { font-size: 16px; font-weight: 700; }
QLabel#chip { background: #1b1e2b; border: 1px solid #2a2f42; border-radius: 15px; padding: 0 14px; min-height: 30px; max-height: 30px; font-weight: 600; }
QLabel#feedback { background: #16302c; border: 1px solid #245046; border-radius: 15px; padding: 0 14px; min-height: 30px; max-height: 30px; font-weight: 700; color: #3fe5a6; }
QLabel#percent { font-size: 54px; font-weight: 800; }
QWidget#sidebar { background: #101119; border-right: 1px solid #1c1f2c; }
QFrame#card { background: #13151f; border: 1px solid #1f2331; border-radius: 18px; }
QFrame#lyrics { border-radius: 18px; border: 1px solid #3a3170;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3a2f7c, stop:0.55 #251f52, stop:1 #171531); }
QFrame#syncBar { background: rgba(0, 0, 0, 70); border-radius: 12px; }
QPushButton { background: #1d2130; border: 1px solid #2c3145; padding: 9px 16px; border-radius: 10px; font-weight: 600; }
QPushButton:hover { background: #272c40; border-color: #3a4160; }
QPushButton:pressed { background: #181b28; }
QPushButton:disabled { color: #5d6379; background: #151824; border-color: #1f2331; }
QPushButton:checked { background: #2c2757; border-color: #8b7bff; color: #ffffff; }
QPushButton#primary { border: none; color: #ffffff; font-weight: 700; padding: 12px 20px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b7bff, stop:1 #d86be0); }
QPushButton#primary:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9c8eff, stop:1 #e582ea); }
QPushButton#primary:disabled { background: #2a2e3f; color: #6d7389; }
QPushButton#ghost { background: rgba(255, 255, 255, 22); border: none; padding: 7px 13px; border-radius: 15px; font-size: 13px; }
QPushButton#ghost:hover { background: rgba(255, 255, 255, 42); }
QPushButton#ghost:checked { background: #f06bd0; color: #ffffff; }
QPushButton#link { background: transparent; border: none; color: #a99cff; padding: 6px 4px; font-weight: 600; }
QPushButton#link:hover { color: #c9c0ff; }
QPushButton#round { border-radius: 19px; padding: 0; min-width: 38px; max-width: 38px; min-height: 38px; max-height: 38px; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { background: #141722; border: 1px solid #262b3c; border-radius: 10px; padding: 9px 12px;
    selection-background-color: #5e4fd1; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #8b7bff; }
QPlainTextEdit { font-size: 15px; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView { background: #1b1e2b; border: 1px solid #2c3145; selection-background-color: #332d66; padding: 4px; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }
QListWidget { background: transparent; border: none; }
QListWidget::item { padding: 10px 10px; border-radius: 10px; margin: 1px 0; color: #c9cddd; }
QListWidget::item:hover { background: #181b28; }
QListWidget::item:selected { background: #24213f; color: #ffffff; }
QSlider::groove:horizontal { height: 5px; background: #262a3a; border-radius: 2px; }
QSlider::sub-page:horizontal { border-radius: 2px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b7bff, stop:1 #d86be0); }
QSlider::handle:horizontal { background: #ffffff; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QSlider::handle:horizontal:hover { background: #d9d3ff; }
QProgressBar { border: none; background: #1d2130; height: 8px; border-radius: 4px; }
QProgressBar::chunk { border-radius: 4px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b7bff, stop:1 #f06bd0); }
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 34px; height: 18px; border-radius: 9px; background: #2a2e40; }
QCheckBox::indicator:checked { background: #8b7bff; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #2c3145; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar:horizontal { height: 0; }
QMenu { background: #1b1e2b; border: 1px solid #2c3145; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 7px 18px; border-radius: 6px; }
QMenu::item:selected { background: #332d66; }
QToolTip { background: #1b1e2b; color: #f3f4f8; border: 1px solid #2c3145; padding: 5px 8px; }
QMessageBox QLabel { font-size: 14px; }
'''


def label(text, style=None, wrap=True):
    item = QLabel(text)
    if style:
        item.setObjectName(style)
    item.setWordWrap(wrap)
    return item


def button(text, callback, style=None, glyph=None):
    item = QPushButton(text)
    if style:
        item.setObjectName(style)
    if glyph:
        item.setIcon(icon(glyph, '#ffffff' if style == 'primary' else TEXT))
        item.setIconSize(QSize(17, 17))
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    item.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    item.clicked.connect(callback)
    return item


def clock(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds // 60}:{seconds % 60:02}'


class JumpSlider(QSlider):
    """Slider that jumps to the clicked position instead of paging towards it."""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setValue(QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                                                         int(event.position().x()), self.width()))
        super().mousePressEvent(event)


class SearchThread(QThread):
    finished_search = Signal(list, str)

    def __init__(self, query, parent=None):
        super().__init__(parent)
        self.query = query

    def run(self):
        try:
            self.finished_search.emit(lyrics_online.search(self.query), '')
        except Exception as error:  # network errors are reported in the dialog
            self.finished_search.emit([], str(error))


class LyricsDialog(QDialog):
    """Paste lyrics (plain or LRC) or look up time-synced lyrics online."""

    def __init__(self, parent, text: str, query: str):
        super().__init__(parent)
        self.setWindowTitle('Текст песни')
        self.resize(640, 640)
        self.worker = None
        self.results = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)
        layout.addWidget(label('Текст песни', 'title'))
        layout.addWidget(label('Вставь слова — каждая строка станет отдельной фразой. Обычный текст приложение расставит '
                               'по мелодии само, а LRC с метками [00:12.50] встанет точно.', 'muted'))
        self.edit = QPlainTextEdit()
        self.edit.setPlainText(text)
        self.edit.setPlaceholderText('Вставь текст сюда…')
        layout.addWidget(self.edit, 1)
        layout.addWidget(label('НАЙТИ СИНХРОННЫЙ ТЕКСТ В ИНТЕРНЕТЕ', 'caps'))
        row = QHBoxLayout()
        self.query = QLineEdit(query)
        self.query.setPlaceholderText('Исполнитель и название')
        self.query.returnPressed.connect(self.search)
        row.addWidget(self.query, 1)
        self.find_button = button('Найти', self.search, glyph='search')
        row.addWidget(self.find_button)
        layout.addLayout(row)
        self.status = label('Поиск идёт по открытой базе LRCLIB. Отправляется только строка запроса.', 'small')
        layout.addWidget(self.status)
        self.list = QListWidget()
        self.list.setMaximumHeight(150)
        self.list.itemClicked.connect(self.pick)
        self.list.hide()
        layout.addWidget(self.list)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(button('Отмена', self.reject))
        buttons.addWidget(button('Сохранить', self.accept, 'primary'))
        layout.addLayout(buttons)

    def text(self) -> str:
        return self.edit.toPlainText()

    def search(self):
        if self.worker is not None or not self.query.text().strip():
            return
        self.find_button.setEnabled(False)
        self.status.setText('Ищем…')
        self.worker = SearchThread(self.query.text(), self)
        self.worker.finished_search.connect(self.show_results)
        self.worker.start()

    def show_results(self, results, error):
        self.worker.wait()
        self.worker = None
        self.find_button.setEnabled(True)
        self.results = results
        self.list.clear()
        if error:
            self.status.setText(f'Не удалось выполнить поиск: {error}')
        elif not results:
            self.status.setText('Ничего не найдено. Попробуй уточнить запрос.')
        else:
            self.status.setText('Выбери вариант — текст подставится в поле выше.')
            for item in results[:30]:
                kind = 'с таймингом' if item['synced'] else 'без тайминга'
                self.list.addItem(f"{item['artist']} — {item['title']}  ·  {clock(item['duration'])}  ·  {kind}")
        self.list.setVisible(bool(results))

    def pick(self, item):
        self.edit.setPlainText(self.results[self.list.row(item)]['lyrics'])

    def done(self, code):
        if self.worker is not None:
            self.worker.finished_search.disconnect()
            self.worker.wait(100)
        super().done(code)


class MainWindow(QMainWindow):
    def __init__(self, library: Path | None = None):
        super().__init__()
        self.setWindowTitle('Vocal Studio')
        self.resize(1360, 860)
        self.setMinimumSize(1120, 700)
        self.setAcceptDrops(True)
        data = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        self.library = Path(library or os.environ.get('VOCALSTUDIO_LIBRARY') or data / 'songs')
        self.library.mkdir(parents=True, exist_ok=True)
        self.models = Path(os.environ.get('VOCALSTUDIO_MODELS') or self.library.parent / 'models')
        self.settings = QSettings(str(self.library / 'settings.ini'), QSettings.Format.IniFormat)
        self.audio = AudioEngine()
        self.project = None
        self.folder = None
        self.source = None
        self.process = None
        self.job_folder = None
        self.log_tail = ''
        self.polled = ''
        self.notes = []
        self.starts = []
        self.score_hit = 0.
        self.score_total = 0.
        self.last_tick = time.monotonic()
        self.recent_pitch = deque(maxlen=3)
        self.sync_index = None
        self.seeking = False

        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.build_sidebar())
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        self.pages.addWidget(self.build_setup())
        self.pages.addWidget(self.build_studio())
        self.pages.addWidget(self.build_busy())
        self.learning = LearningPage(self.settings)
        self.learning.practice_requested.connect(self.make_demo)
        self.pages.addWidget(self.learning)
        self.refresh_library()

        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.space_pressed)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=lambda: self.nudge(-5))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=lambda: self.nudge(5))
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    # ---------------------------------------------------------------- layout

    def build_sidebar(self):
        sidebar = QWidget()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(250)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 22, 16, 16)
        side.setSpacing(8)
        brand = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(icon('mic', ACCENT, 24).pixmap(QSize(24, 24)))
        brand.addWidget(mark)
        brand.addWidget(label('Vocal Studio', 'brand', False), 1)
        side.addLayout(brand)
        side.addSpacing(16)
        self.new_button = button('Новая песня', self.new_song, 'primary', 'plus')
        side.addWidget(self.new_button)
        self.learning_button = button('Обучение', self.show_learning, glyph='note')
        side.addWidget(self.learning_button)
        side.addSpacing(16)
        side.addWidget(label('МОИ ПЕСНИ', 'caps'))
        self.songs = QListWidget()
        self.songs.setIconSize(QSize(20, 20))
        self.songs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.songs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.songs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.songs.customContextMenuRequested.connect(self.song_menu)
        self.songs.itemClicked.connect(self.open_item)
        side.addWidget(self.songs, 1)
        self.empty_library = label('Здесь появятся твои песни.\nНачни с распевки или добавь свою.', 'small')
        side.addWidget(self.empty_library)
        self.demo_button = button('Попробовать распевку', self.make_demo, glyph='note')
        side.addWidget(self.demo_button)
        side.addWidget(label('Всё хранится и обрабатывается на этом компьютере', 'small'))
        return sidebar

    def build_setup(self):
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(40, 34, 40, 30)
        outer.addStretch(1)
        column = QWidget()
        column.setMaximumWidth(820)
        outer.addWidget(column, 8)
        outer.addStretch(1)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(label('Новая песня', 'heading'))
        layout.addWidget(label('Загрузи трек — приложение отделит вокал от минуса, расставит ноты и текст по таймлайну.', 'muted'))
        layout.addSpacing(10)
        self.drop = DropZone()
        self.drop.clicked.connect(self.choose_source)
        self.drop.dropped.connect(self.set_source)
        layout.addWidget(self.drop)
        layout.addSpacing(8)
        layout.addWidget(label('НАЗВАНИЕ', 'caps'))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText('Исполнитель — название')
        layout.addWidget(self.title_input)
        layout.addSpacing(8)
        head = QHBoxLayout()
        head.addWidget(label('ТЕКСТ ПЕСНИ', 'caps'), 1)
        head.addWidget(button('Найти текст в интернете', self.find_lyrics_for_setup, 'link'))
        layout.addLayout(head)
        self.lyrics_input = QPlainTextEdit()
        self.lyrics_input.setPlaceholderText('Вставь текст сюда — можно и позже.\n\nКаждая строка — отдельная фраза. '
                                             'Обычный текст расставится по мелодии автоматически, LRC с метками [00:12.50] — точно.')
        layout.addWidget(self.lyrics_input, 1)
        layout.addSpacing(8)
        layout.addWidget(label('КАЧЕСТВО РАЗДЕЛЕНИЯ', 'caps'))
        modes = QHBoxLayout()
        self.engine_neural = QPushButton('Нейросеть · лучшее качество')
        self.engine_fast = QPushButton('Быстрый режим · без загрузок')
        group = QButtonGroup(self)
        for item in (self.engine_neural, self.engine_fast):
            item.setCheckable(True)
            item.setCursor(Qt.CursorShape.PointingHandCursor)
            item.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            item.toggled.connect(self.update_engine_hint)
            group.addButton(item)
            modes.addWidget(item)
        layout.addLayout(modes)
        self.engine_hint = label('', 'small')
        layout.addWidget(self.engine_hint)
        (self.engine_neural if neural.available() else self.engine_fast).setChecked(True)
        self.engine_neural.setEnabled(neural.available())
        layout.addSpacing(10)
        row = QHBoxLayout()
        row.addWidget(button('У меня уже есть вокал и минус', self.import_stems, 'link'))
        row.addStretch()
        self.prepare_button = button('Подготовить песню', self.prepare_song, 'primary')
        self.prepare_button.setMinimumWidth(220)
        row.addWidget(self.prepare_button)
        layout.addLayout(row)
        return page

    def build_studio(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(16)

        top = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.song_title = label('Исполнение', 'title', False)
        self.song_meta = label('', 'muted', False)
        titles.addWidget(self.song_title)
        titles.addWidget(self.song_meta)
        top.addLayout(titles, 1)
        self.pitch_label = label('Твоя нота  —', 'chip', False)
        self.feedback = label('Включи микрофон', 'feedback', False)
        self.score_label = label('Попадание  —', 'chip', False)
        for item in (self.pitch_label, self.feedback, self.score_label):
            top.addWidget(item, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(16)
        self.timeline = PitchTimeline()
        self.timeline.seekRequested.connect(self.seek_to)
        body.addWidget(self.timeline, 1)
        body.addWidget(self.build_lyrics_panel())
        layout.addLayout(body, 1)

        bar = QFrame()
        bar.setObjectName('card')
        controls = QVBoxLayout(bar)
        controls.setContentsMargins(18, 14, 18, 14)
        controls.setSpacing(12)
        transport = QHBoxLayout()
        transport.setSpacing(12)
        self.play_button = PlayButton()
        self.play_button.clicked.connect(self.toggle_play)
        transport.addWidget(self.play_button)
        restart = button('', self.restart, 'round', 'restart')
        restart.setToolTip('С начала')
        transport.addWidget(restart)
        self.time_label = label('0:00', 'muted', False)
        self.time_label.setMinimumWidth(38)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        transport.addWidget(self.time_label)
        self.seek = JumpSlider(Qt.Orientation.Horizontal)
        self.seek.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.seek.setCursor(Qt.CursorShape.PointingHandCursor)
        self.seek.sliderPressed.connect(lambda: setattr(self, 'seeking', True))
        self.seek.sliderReleased.connect(self.seek_released)
        transport.addWidget(self.seek, 1)
        self.duration_label = label('0:00', 'muted', False)
        self.duration_label.setMinimumWidth(38)
        transport.addWidget(self.duration_label)
        self.volume_sliders = {}
        for title, key, initial, tip in [('Минус', 'backing_volume', 80, 'Громкость музыки'),
                                         ('Голос', 'guide_volume', 25, 'Громкость оригинального вокала-подсказки')]:
            transport.addSpacing(8)
            transport.addWidget(label(title, 'muted', False))
            slider = JumpSlider(Qt.Orientation.Horizontal)
            slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            slider.setRange(0, 100)
            slider.setFixedWidth(96)
            slider.setToolTip(tip)
            slider.valueChanged.connect(lambda value, name=key: self.set_volume(name, value))
            slider.setValue(self.settings.value(key, initial, type=int))
            self.volume_sliders[key] = slider
            transport.addWidget(slider)
        controls.addLayout(transport)

        options = QHBoxLayout()
        options.setSpacing(10)
        self.mic_button = button('Включить микрофон', self.toggle_mic, glyph='mic')
        self.mic_button.setCheckable(True)
        options.addWidget(self.mic_button)
        self.mic_devices = QComboBox()
        self.mic_devices.setFixedWidth(220)
        self.mic_devices.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mic_devices.addItem('Системный микрофон', None)
        try:
            for i, device in enumerate(sd.query_devices()):
                if device['max_input_channels']:
                    self.mic_devices.addItem(device['name'], i)
        except sd.PortAudioError:
            pass
        options.addWidget(self.mic_devices)
        self.meter = LevelMeter()
        options.addWidget(self.meter)
        options.addSpacing(8)
        self.octaves = QCheckBox('Любая октава')
        self.octaves.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.octaves.setToolTip('Засчитывать ноту, спетую на октаву выше или ниже оригинала')
        self.octaves.setChecked(self.settings.value('octaves', True, type=bool))
        self.octaves.toggled.connect(self.option_changed)
        options.addWidget(self.octaves)
        options.addStretch(1)
        options.addWidget(label('Лучше петь в наушниках', 'small', False))
        options.addSpacing(10)
        options.addWidget(label('Задержка', 'muted', False))
        self.delay = QSpinBox()
        self.delay.setRange(-500, 1000)
        self.delay.setSingleStep(10)
        self.delay.setSuffix(' мс')
        self.delay.setFixedWidth(84)
        self.delay.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.delay.setValue(self.settings.value('delay', 80, type=int))
        self.delay.setToolTip('Если линия твоего голоса запаздывает относительно нот — увеличь значение')
        self.delay.valueChanged.connect(self.option_changed)
        options.addWidget(self.delay)
        controls.addLayout(options)
        layout.addWidget(bar)
        return page

    def build_lyrics_panel(self):
        panel = QFrame()
        panel.setObjectName('lyrics')
        panel.setFixedWidth(390)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 18, 18, 18)
        layout.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(label('Текст', 'panelTitle', False), 1)
        head.addWidget(button('Изменить', self.replace_lyrics, 'ghost'))
        self.sync_button = button('Синхронизация', self.toggle_sync, 'ghost')
        self.sync_button.setCheckable(True)
        self.sync_button.setToolTip('Расставить строки вручную: включи песню и жми Пробел в начале каждой строки')
        head.addWidget(self.sync_button)
        layout.addLayout(head)
        self.lyrics_view = LyricsView()
        self.lyrics_view.lineClicked.connect(self.line_clicked)
        layout.addWidget(self.lyrics_view, 1)
        self.auto_hint = label('Строки расставлены автоматически и могут быть неточными. '
                               'Поправь через «Синхронизацию» или вставь LRC.', 'small')
        self.auto_hint.setStyleSheet('color: rgba(255,255,255,140);')
        layout.addWidget(self.auto_hint)
        self.sync_bar = QFrame()
        self.sync_bar.setObjectName('syncBar')
        sync = QHBoxLayout(self.sync_bar)
        sync.setContentsMargins(12, 8, 8, 8)
        hint = label('Жми Пробел в начале каждой строки', 'small')
        hint.setStyleSheet('color: rgba(255,255,255,200);')
        sync.addWidget(hint, 1)
        sync.addWidget(button('Отметить', self.stamp_line, 'ghost'))
        sync.addWidget(button('Готово', self.toggle_sync, 'ghost'))
        layout.addWidget(self.sync_bar)
        self.sync_bar.hide()
        return panel

    def build_busy(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(60, 40, 60, 40)
        layout.addStretch(2)
        self.busy_title = label('Готовим песню', 'heading', False)
        self.busy_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.busy_title)
        layout.addSpacing(6)
        self.busy_percent = label('', 'percent', False)
        self.busy_percent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.busy_percent)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(460)
        layout.addWidget(self.progress, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(10)
        self.status_label = label('Начинаем…', 'muted', False)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        layout.addSpacing(18)
        layout.addWidget(button('Отменить', self.cancel_job), 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(3)
        return page

    # --------------------------------------------------------------- library

    def report_error(self, message):
        QMessageBox.warning(self, 'Vocal Studio', str(message))

    def refresh_library(self):
        self.songs.clear()
        for path in sorted(self.library.glob('*/project.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if data.get('state') != 'ready':
                    continue
                item = QListWidgetItem(icon('note', MUTED, 20), f"{data['title']}\n{clock(data.get('duration', 0))}")
                item.setData(Qt.ItemDataRole.UserRole, str(path.parent))
                self.songs.addItem(item)
                if self.folder and path.parent == self.folder:
                    self.songs.setCurrentItem(item)
            except (ValueError, OSError, KeyError):
                continue
        self.empty_library.setVisible(self.songs.count() == 0)

    def song_menu(self, point):
        item = self.songs.itemAt(point)
        if item is None or self.process is not None:
            return
        menu = QMenu(self)
        remove = menu.addAction('Удалить песню')
        if menu.exec(self.songs.mapToGlobal(point)) is remove:
            self.delete_song(Path(item.data(Qt.ItemDataRole.UserRole)))

    def delete_song(self, folder: Path, confirm=True):
        if confirm and QMessageBox.question(self, 'Vocal Studio', 'Удалить песню и её дорожки с этого компьютера?') \
                != QMessageBox.StandardButton.Yes:
            return
        if self.folder == folder:
            self.audio.pause()
            self.folder = self.project = None
            self.pages.setCurrentIndex(SETUP)
        if folder.parent == self.library:
            shutil.rmtree(folder, ignore_errors=True)
        self.refresh_library()

    def show_learning(self):
        if self.process:
            return
        self.audio.pause()
        if self.audio.input is not None:
            self.toggle_mic()
        self.songs.clearSelection()
        self.pages.setCurrentIndex(LEARNING)

    def new_song(self):
        self.audio.pause()
        self.songs.clearSelection()
        self.pages.setCurrentIndex(SETUP)

    # ----------------------------------------------------------------- setup

    def update_engine_hint(self, *args):
        if not neural.available():
            self.engine_hint.setText('Нейросеть недоступна: не установлен пакет onnxruntime. Работает быстрый режим.')
        elif self.engine_neural.isChecked():
            ready = neural.model_file(self.models).exists()
            self.engine_hint.setText(
                'Нейросеть MDX-Net чисто отделяет голос от музыки. Обработка идёт на этом компьютере и занимает '
                'примерно столько же, сколько длится песня.' +
                ('' if ready else ' При первом запуске один раз скачается модель (64 МБ).'))
        else:
            self.engine_hint.setText('Простой алгоритм без нейросети: работает сразу и офлайн, но голос отделяется грубо '
                                     'и ноты могут быть неточными.')

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Выбрать песню', '', AUDIO_FILTER)
        if path:
            self.set_source(path)

    def set_source(self, path):
        path = Path(path)
        if path.suffix.lower() not in AUDIO_SUFFIXES:
            self.report_error('Это не похоже на аудиофайл. Подойдут MP3, WAV, FLAC, M4A, OGG.')
            return
        self.source = path
        self.drop.set_file(path.name)
        self.title_input.setText(re.sub(r'[_\s]+', ' ', path.stem).strip())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and self.process is None:
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if urls:
            self.new_song()
            self.set_source(urls[0])

    def find_lyrics_for_setup(self):
        dialog = LyricsDialog(self, self.lyrics_input.toPlainText(), self.title_input.text())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.lyrics_input.setPlainText(dialog.text())

    def prepare_song(self):
        if not self.source:
            self.report_error('Сначала выбери или перетащи аудиофайл.')
            return
        if not self.source.exists():
            self.report_error('Файл не найден. Выбери его заново.')
            return
        folder = create_project(self.library, self.source, self.lyrics_input.toPlainText(), self.title_input.text())
        engine = 'neural' if self.engine_neural.isChecked() else 'dsp'
        self.start_job(folder, 'separate', ['--engine', engine, '--models', str(self.models)])

    def import_stems(self):
        vocal, _ = QFileDialog.getOpenFileName(self, 'Выбрать отдельный вокал', '', AUDIO_FILTER)
        if not vocal:
            return
        backing, _ = QFileDialog.getOpenFileName(self, 'Выбрать минус той же длительности', '', AUDIO_FILTER)
        if not backing:
            return
        folder = create_project(self.library, self.source or Path(vocal), self.lyrics_input.toPlainText(),
                                self.title_input.text())
        self.start_job(folder, 'import', ['--vocal', vocal, '--backing', backing])

    def make_demo(self):
        folder = create_project(self.library, Path('Первая распевка.wav'), '')
        self.start_job(folder, 'demo')

    # ------------------------------------------------------------------ jobs

    def start_job(self, folder, mode, extra=None):
        if self.process:
            return
        self.audio.pause()
        self.job_folder = folder
        self.log_tail = ''
        self.polled = ''
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_progress)
        self.process.finished.connect(self.job_finished)
        self.process.errorOccurred.connect(self.job_error)
        for item in (self.new_button, self.demo_button, self.songs, self.learning_button):
            item.setEnabled(False)
        self.progress.setRange(0, 0)
        self.busy_percent.setText('')
        self.status_label.setText('Начинаем…')
        self.pages.setCurrentIndex(BUSY)
        arguments = [str(folder), '--mode', mode] + (extra or [])
        if getattr(sys, 'frozen', False):
            self.process.start(sys.executable, ['--worker'] + arguments)
        else:
            self.process.setWorkingDirectory(str(Path(__file__).resolve().parent.parent))
            self.process.start(sys.executable, ['-u', '-m', 'vocalstudio.worker'] + arguments)

    def read_progress(self):
        if not self.process:
            return
        text = bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self.log_tail = (self.log_tail + text)[-10000:]
        rows = text.replace('\r', '\n').strip().splitlines()
        if rows:
            self.show_progress(rows[-1][:180])

    def poll_progress(self):
        """Windowed builds may have no stdout; the worker mirrors its status into a file."""
        try:
            text = (self.job_folder / 'progress.txt').read_text(encoding='utf-8').strip()
        except (OSError, ValueError):
            return
        if text and text != self.polled:
            self.polled = text
            if text not in self.log_tail:
                self.log_tail = (self.log_tail + '\n' + text)[-10000:]
            self.show_progress(text[:180])

    def show_progress(self, last):
        match = re.search(r'(\d+)%\s*$', last)
        if match:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(match[1]))
            self.busy_percent.setText(f'{match[1]}%')
            last = last[:match.start()].rstrip()
        else:
            self.progress.setRange(0, 0)
            self.busy_percent.setText('')
        self.status_label.setText(last)

    def job_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.log_tail += '\nНе удалось запустить процесс обработки.'
            self.job_finished(1, QProcess.ExitStatus.CrashExit)

    def cancel_job(self):
        if not self.process:
            return
        process, self.process = self.process, None
        process.finished.disconnect()
        process.errorOccurred.disconnect()
        process.kill()
        process.waitForFinished(3000)
        process.deleteLater()
        shutil.rmtree(self.job_folder, ignore_errors=True)
        self.finish_job_ui()
        self.pages.setCurrentIndex(SETUP)

    def finish_job_ui(self):
        for item in (self.new_button, self.demo_button, self.songs, self.learning_button):
            item.setEnabled(True)
        self.update_engine_hint()

    def job_finished(self, code, status):
        if not self.process:
            return
        self.read_progress()
        self.poll_progress()
        self.process.deleteLater()
        self.process = None
        self.finish_job_ui()
        if code == 0:
            self.source = None
            self.drop.set_file('')
            self.title_input.clear()
            self.lyrics_input.clear()
            self.open_project(self.job_folder)
        else:
            try:
                (self.job_folder / 'processing.log').write_text(self.log_tail, encoding='utf-8')
            except OSError:
                pass
            self.pages.setCurrentIndex(SETUP)
            self.report_error('Подготовка не завершена.\n\n' + self.log_tail[-1800:])

    # ---------------------------------------------------------------- studio

    def open_item(self, item):
        folder = Path(item.data(Qt.ItemDataRole.UserRole))
        if folder != self.folder or self.pages.currentIndex() != STUDIO:
            self.open_project(folder)

    def open_project(self, folder):
        try:
            project = json.loads((folder / 'project.json').read_text(encoding='utf-8'))
            reference = json.loads((folder / 'reference.json').read_text(encoding='utf-8'))
            self.audio.load(folder)
        except (OSError, ValueError, KeyError) as error:
            self.report_error(error)
            return
        self.folder, self.project = folder, project
        self.timeline.set_reference(reference)
        self.notes, self.starts = self.timeline.notes, self.timeline.starts
        self.song_title.setText(project['title'])
        engine = {'mdx-net-kim-vocal-2': 'разделено нейросетью', 'repetition-centre-v1': 'быстрое разделение'}
        parts = [clock(self.audio.duration), f'{len(self.notes)} нот']
        if project.get('separator') in engine:
            parts.append(engine[project['separator']])
        self.song_meta.setText('  ·  '.join(parts))
        self.seek.setRange(0, int(self.audio.duration * 1000))
        self.duration_label.setText(clock(self.audio.duration))
        self.set_sync_mode(False)
        self.show_lines()
        self.reset_score()
        self.pages.setCurrentIndex(STUDIO)
        self.refresh_library()

    def show_lines(self):
        lines = self.project['lines']
        self.lyrics_view.set_lines(lines)
        self.auto_hint.setVisible(self.sync_index is None and any(line.get('auto') for line in lines))

    def save_project(self):
        atomic_json(self.folder / 'project.json', self.project)

    def set_volume(self, key, value):
        setattr(self.audio, key, value / 100)
        self.settings.setValue(key, value)

    def option_changed(self, *args):
        self.settings.setValue('octaves', self.octaves.isChecked())
        self.settings.setValue('delay', self.delay.value())
        self.reset_score()

    def reset_score(self, *args):
        self.score_hit = self.score_total = 0.
        self.recent_pitch.clear()
        self.timeline.clear_performance()
        self.score_label.setText('Попадание  —')

    def toggle_play(self):
        if not self.project:
            return
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

    def space_pressed(self):
        if self.pages.currentIndex() != STUDIO:
            return
        if self.sync_index is not None and self.audio.playing:
            self.stamp_line()
        else:
            self.toggle_play()

    def nudge(self, seconds):
        if self.pages.currentIndex() == STUDIO and self.project:
            self.seek_to(self.audio.seconds + seconds)

    def restart(self):
        self.seek_to(0)

    def seek_to(self, seconds):
        self.audio.seek(seconds)
        self.reset_score()

    def seek_released(self):
        self.seek_to(self.seek.value() / 1000)
        self.seeking = False

    def toggle_mic(self):
        try:
            if self.audio.input is None:
                self.audio.start_microphone(self.mic_devices.currentData())
            else:
                self.audio.stop_microphone()
        except (sd.PortAudioError, ValueError) as error:
            self.audio.stop_microphone()
            self.report_error(f'Не удалось открыть микрофон. Проверь подключение и разрешения системы.\n{error}')
        active = self.audio.input is not None
        self.mic_button.setChecked(active)
        self.mic_button.setText('Микрофон включён' if active else 'Включить микрофон')
        self.mic_devices.setEnabled(not active)

    # ---------------------------------------------------------------- lyrics

    def replace_lyrics(self):
        if not self.project:
            return
        dialog = LyricsDialog(self, self.project.get('lyrics', ''), self.project['title'])
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        old = self.project['lines']
        lines = parse_lyrics(dialog.text())
        if len(lines) == len(old):
            # Keep existing timing when only the wording was corrected.
            for new, previous in zip(lines, old):
                if new['time'] is None and previous.get('time') is not None:
                    new['time'] = previous['time']
                    if previous.get('auto'):
                        new['auto'] = True
        self.project['lyrics'] = dialog.text()
        self.project['lines'] = auto_align(lines, self.notes, self.audio.duration)
        self.save_project()
        self.set_sync_mode(False)
        self.show_lines()

    def toggle_sync(self):
        self.set_sync_mode(self.sync_index is None)

    def set_sync_mode(self, enabled):
        lines = self.project['lines'] if self.project else []
        enabled = bool(enabled and lines)
        if enabled:
            current = active_line(lines, self.audio.seconds)
            self.sync_index = 0 if current is None or self.audio.seconds < .5 else min(current + 1, len(lines) - 1)
        else:
            self.sync_index = None
        self.sync_button.setChecked(enabled)
        self.sync_bar.setVisible(enabled)
        self.auto_hint.setVisible(not enabled and any(line.get('auto') for line in lines))
        self.lyrics_view.set_sync(enabled, self.sync_index)

    def stamp_line(self):
        if self.sync_index is None or not self.project:
            return
        lines = self.project['lines']
        line = lines[self.sync_index]
        line['time'] = round(max(0., self.audio.seconds), 2)
        line.pop('auto', None)
        realign_following(lines, self.sync_index, self.notes, self.audio.duration)
        self.save_project()
        if self.sync_index + 1 < len(lines):
            self.sync_index += 1
            self.lyrics_view.set_sync(True, self.sync_index)
        else:
            self.set_sync_mode(False)
            self.show_lines()

    def line_clicked(self, index):
        if self.sync_index is not None:
            self.sync_index = index
            self.lyrics_view.set_sync(True, index)
            return
        moment = self.project['lines'][index].get('time')
        if moment is not None:
            self.seek_to(max(0., moment - .3))

    # ------------------------------------------------------------------ tick

    def current_pitch(self):
        samples = self.audio.microphone_samples()
        midi = detect_pitch(samples, self.audio.input_rate)[0] if samples is not None else None
        self.recent_pitch.append(midi)
        voiced = [value for value in self.recent_pitch if value is not None]
        if midi is None or len(voiced) < 2:
            return midi
        # A short median removes single-frame octave flips without adding visible lag.
        return statistics.median(voiced)

    def tick(self):
        now = time.monotonic()
        elapsed = min(.1, now - self.last_tick)
        self.last_tick = now
        if self.process is not None:
            self.poll_progress()
        if self.pages.currentIndex() != STUDIO or not self.project:
            return
        position = self.audio.seconds
        self.timeline.position = position
        if not self.seeking:
            self.seek.setValue(int(position * 1000))
        self.time_label.setText(clock(position))
        self.play_button.set_playing(self.audio.playing)
        if self.sync_index is None:
            self.lyrics_view.set_active(active_line(self.project['lines'], position))
        self.lyrics_view.advance()

        listening = self.audio.input is not None
        self.meter.set_level(self.audio.level if listening else 0.)
        midi = self.current_pitch() if listening else None
        self.pitch_label.setText(f'Твоя нота  {note_name(midi)}')
        shown, good = (self.timeline.fold(midi) if midi is not None else None), None
        if not listening:
            self.feedback.setText('Включи микрофон')
        elif not self.audio.playing:
            self.feedback.setText('Нажми ▶ и пой')
        else:
            stamp = position - self.delay.value() / 1000
            index = note_at(self.notes, self.starts, stamp)
            if index is None:
                self.feedback.setText('Пауза')
            else:
                target = self.notes[index]['midi']
                self.score_total += elapsed
                if midi is None:
                    self.feedback.setText('Пой!')
                else:
                    error = cents_error(midi, target, self.octaves.isChecked())
                    good = abs(error) <= TOLERANCE_CENTS
                    shown = target + error / 100 if self.octaves.isChecked() else midi
                    if good:
                        self.score_hit += elapsed
                        self.timeline.add_hit(index, stamp - elapsed, stamp)
                        self.feedback.setText('В ноту ✓')
                    else:
                        self.feedback.setText('Ниже ↓' if error > 0 else 'Выше ↑')
                self.score_label.setText(f'Попадание  {self.score_hit / self.score_total:.0%}')
            self.timeline.history.append((stamp, shown, good))
            if len(self.timeline.history) > 900:
                del self.timeline.history[:300]
        self.timeline.live, self.timeline.live_good = shown, good
        self.timeline.update()

    def closeEvent(self, event):
        if self.process is not None:
            if QMessageBox.question(self, 'Идёт обработка', 'Прервать подготовку песни и выйти?') \
                    != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.cancel_job()
        self.timer.stop()
        self.learning.stop_example()
        self.audio.close()
        event.accept()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--self-test':
        from .selftest import run
        sys.exit(run(Path(sys.argv[2])))
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        from .worker import main as worker_main
        worker_main(sys.argv[2:])
        return
    app = QApplication(sys.argv)
    app.setApplicationName('VocalStudio')
    app.setOrganizationName('VocalStudio')
    from .branding import app_icon
    app.setWindowIcon(app_icon())
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
