import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from vocalstudio.curriculum import LESSONS
from vocalstudio.learning import LearningPage, example_audio

_APP = QApplication.instance() or QApplication([])


def test_progress_requires_correct_answer_and_survives_restart(tmp_path):
    path = str(tmp_path / 'settings.ini')
    page = LearningPage(QSettings(path, QSettings.Format.IniFormat))
    page.select(2)
    page.mark_complete()
    assert not page.completed
    lesson = LESSONS[2]
    page.answers.button((lesson.correct + 1) % 3).setChecked(True)
    page.check_answer()
    assert not page.complete.isEnabled()
    page.answers.button(lesson.correct).setChecked(True)
    page.check_answer()
    assert page.complete.isEnabled()
    page.mark_complete()
    delete(page)
    reopened = LearningPage(QSettings(path, QSettings.Format.IniFormat))
    assert reopened.index == 2
    assert reopened.completed == {lesson.id}
    assert reopened.progress.value() == 1
    reopened.select(3)
    assert reopened.answers.checkedId() == -1
    assert not reopened.complete.isEnabled()
    delete(reopened)


def test_curriculum_and_tone_examples():
    assert len({lesson.id for lesson in LESSONS}) == len(LESSONS) == 14
    assert len({lesson.module for lesson in LESSONS}) == 3
    for lesson in LESSONS:
        assert len(lesson.answers) == 3 and 0 <= lesson.correct < 3
        assert lesson.practice and lesson.explanation
    tone = example_audio([69])
    assert tone.dtype == np.float32 and np.max(np.abs(tone)) <= .121
    frequencies = np.fft.rfftfreq(len(tone), 1/44100)
    dominant = frequencies[np.argmax(np.abs(np.fft.rfft(tone)))]
    assert abs(dominant - 440) < 2
    assert tone[0] == 0 and tone[-1] == 0


def test_learning_navigation_pauses_song_and_returns_to_project(tmp_path):
    from vocalstudio.app import MainWindow, LEARNING, SETUP
    window = MainWindow(tmp_path)
    window.audio.playing = True
    window.show_learning()
    assert not window.audio.playing
    assert window.pages.currentIndex() == LEARNING
    window.new_song()
    assert window.pages.currentIndex() == SETUP
    window.close()
    delete(window)
