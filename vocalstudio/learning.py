from __future__ import annotations

from html import escape

import numpy as np
import sounddevice as sd
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QRadioButton, QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .curriculum import LESSONS


def example_audio(notes, rate=44100):
    chunks = []
    t = np.arange(int(rate * .55)) / rate
    envelope = np.minimum(t / .025, 1) * np.minimum((.55 - t) / .05, 1)
    for note in notes:
        hz = 440 * 2 ** ((note - 69) / 12)
        chunks.extend([(.12 * envelope * np.sin(2 * np.pi * hz * t)).astype('float32'),
                       np.zeros(int(rate * .12), dtype='float32')])
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype='float32')


class LearningPage(QWidget):
    practice_requested = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        saved = settings.value('learning/completed', [])
        self.completed = set(saved if isinstance(saved, list) else [saved]) & {lesson.id for lesson in LESSONS}
        self.index = 0
        self.passed = False
        self.example_playing = False
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        title = QLabel('Обучение')
        title.setObjectName('heading')
        root.addWidget(title)
        intro = QLabel('От первых нот до осознанной практики · 14 коротких уроков · прогресс сохраняется')
        intro.setObjectName('muted')
        intro.setWordWrap(True)
        root.addWidget(intro)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(LESSONS))
        root.addWidget(self.progress)
        body = QHBoxLayout()
        body.setSpacing(24)
        root.addLayout(body, 1)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFixedWidth(260)
        self.tree.setWordWrap(True)
        self.tree.setStyleSheet('QTreeWidget { background: #13151f; border: 1px solid #252938; border-radius: 10px; } QTreeWidget::item { padding: 10px 4px; } QTreeWidget::item:selected { background: #342c55; }')
        body.addWidget(self.tree)
        right = QVBoxLayout()
        body.addLayout(right, 1)
        self.reader = QTextBrowser()
        self.reader.setOpenExternalLinks(False)
        self.reader.setStyleSheet('QTextBrowser { background: #13151f; border: 1px solid #252938; border-radius: 10px; padding: 14px; }')
        right.addWidget(self.reader, 1)
        self.listen = QPushButton('Послушать пример')
        self.listen.clicked.connect(self.play_example)
        right.addWidget(self.listen)
        self.question = QLabel()
        self.question.setWordWrap(True)
        right.addWidget(self.question)
        self.answers = QButtonGroup(self)
        for index in range(3):
            answer = QRadioButton()
            self.answers.addButton(answer, index)
            right.addWidget(answer)
        self.check = QPushButton('Проверить ответ')
        self.check.clicked.connect(self.check_answer)
        right.addWidget(self.check)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setMinimumHeight(40)
        right.addWidget(self.feedback)
        nav = QHBoxLayout()
        self.previous = QPushButton('← Назад')
        self.previous.clicked.connect(lambda: self.select(self.index - 1))
        self.complete = QPushButton('Отметить пройденным')
        self.complete.setObjectName('primary')
        self.complete.clicked.connect(self.mark_complete)
        self.next = QPushButton('Далее →')
        self.next.clicked.connect(lambda: self.select(self.index + 1))
        for widget in (self.previous, self.complete, self.next):
            nav.addWidget(widget)
        right.addLayout(nav)
        practice = QPushButton('Перейти к распевке')
        practice.clicked.connect(self.practice_requested.emit)
        right.addWidget(practice)
        groups = {}
        self.items = []
        for index, lesson in enumerate(LESSONS):
            if lesson.module not in groups:
                group = QTreeWidgetItem(self.tree, [lesson.module])
                group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                groups[lesson.module] = group
            item = QTreeWidgetItem(groups[lesson.module])
            item.setData(0, Qt.ItemDataRole.UserRole, index)
            self.items.append(item)
        self.tree.expandAll()
        self.tree.currentItemChanged.connect(self.changed)
        self.refresh_progress()
        current = settings.value('learning/current', LESSONS[0].id)
        self.select(next((i for i, lesson in enumerate(LESSONS) if lesson.id == current), 0))

    def refresh_progress(self):
        self.progress.setValue(len(self.completed))
        self.progress.setFormat(f'Пройдено {len(self.completed)} из {len(LESSONS)}')
        for index, (lesson, item) in enumerate(zip(LESSONS, self.items)):
            item.setText(0, f'{"✓" if lesson.id in self.completed else f"{index + 1:02}"}  {lesson.title}')

    def select(self, index):
        if 0 <= index < len(LESSONS):
            self.tree.setCurrentItem(self.items[index])

    def changed(self, item, previous):
        if item is None or item.data(0, Qt.ItemDataRole.UserRole) is None:
            return
        self.stop_example()
        self.index = item.data(0, Qt.ItemDataRole.UserRole)
        lesson = LESSONS[self.index]
        self.settings.setValue('learning/current', lesson.id)
        self.settings.sync()
        self.passed = False
        paragraphs = ''.join(f'<p>{escape(text)}</p>' for text in lesson.paragraphs)
        self.reader.setHtml(f'<html><head><style>body {{ color:#e7e9f3; font-size:15px; }} p {{ margin-bottom:16px; }} h2 {{ color:#c9bfff; }} </style></head><body>'
                            f'<p>{escape(lesson.module)} · {lesson.minutes} мин</p><h2>{escape(lesson.title)}</h2>{paragraphs}'
                            f'<h3>Попробуй</h3><p>{escape(lesson.practice)}</p></body></html>')
        self.reader.verticalScrollBar().setValue(0)
        self.question.setText(lesson.question)
        self.answers.setExclusive(False)
        for index, answer in enumerate(self.answers.buttons()):
            answer.setChecked(False)
            answer.setText(lesson.answers[index])
        self.answers.setExclusive(True)
        self.feedback.setText('Выбери ответ, чтобы проверить понимание.')
        self.feedback.setStyleSheet('color: #8a90a6;')
        self.listen.setVisible(bool(lesson.tones))
        self.previous.setEnabled(self.index > 0)
        self.next.setEnabled(self.index + 1 < len(LESSONS))
        self.complete.setText('Пройдено ✓' if lesson.id in self.completed else 'Отметить пройденным')
        self.complete.setEnabled(False)

    def check_answer(self):
        selected = self.answers.checkedId()
        if selected < 0:
            self.feedback.setText('Сначала выбери один из вариантов.')
            return
        lesson = LESSONS[self.index]
        self.passed = selected == lesson.correct
        self.feedback.setText(('Верно. ' if self.passed else 'Попробуй ещё. ') + lesson.explanation)
        self.feedback.setStyleSheet('color: #3fe5a6;' if self.passed else 'color: #ffb155;')
        self.complete.setEnabled(self.passed and lesson.id not in self.completed)

    def mark_complete(self):
        if not self.passed:
            return
        self.completed.add(LESSONS[self.index].id)
        self.settings.setValue('learning/completed', sorted(self.completed))
        self.settings.sync()
        self.refresh_progress()
        self.complete.setText('Пройдено ✓')
        self.complete.setEnabled(False)

    def play_example(self):
        self.stop_example()
        try:
            sd.play(example_audio(LESSONS[self.index].tones), samplerate=44100, blocking=False)
            self.example_playing = True
        except (sd.PortAudioError, OSError, ValueError):
            self.feedback.setText('Не удалось открыть аудиовыход. Проверь устройство звука; урок доступен без примера.')

    def stop_example(self):
        if self.example_playing:
            sd.stop()
            self.example_playing = False

    def hideEvent(self, event):
        self.stop_example()
        super().hideEvent(event)
