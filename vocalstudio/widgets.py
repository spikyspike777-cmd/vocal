from __future__ import annotations
import bisect
import math

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import QWidget

from .core import note_name


class PitchTimeline(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(290)
        self.reference = {'times': [], 'midi': []}
        self.position = 0.
        self.history = []
        self.low, self.high = 48, 76

    def set_reference(self, reference):
        self.reference = reference
        self.history = []
        pitches = [p for p in reference['midi'] if p is not None and math.isfinite(p)]
        if pitches:
            self.low = math.floor(min(pitches)) - 4
            self.high = max(self.low + 14, math.ceil(max(pitches)) + 4)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#141923'))
        left, top, width, height = 54, 20, self.width() - 75, self.height() - 44
        start = self.position - 2.5
        def x(t): return left + (t - start) / 10 * width
        def y(m): return top + (self.high - m) / (self.high - self.low) * height
        p.setPen(QColor('#68758b'))
        for midi in range(self.low, self.high + 1):
            if midi % 2 == 0:
                p.setPen(QColor('#232c3b'))
                p.drawLine(left, int(y(midi)), self.width() - 20, int(y(midi)))
                p.setPen(QColor('#8090a8'))
                p.drawText(8, int(y(midi)) + 4, note_name(midi))
        for second in range(max(0, math.ceil(start)), math.ceil(start + 10)):
            p.setPen(QColor('#252e3e'))
            p.drawLine(int(x(second)), top, int(x(second)), top + height)
            p.setPen(QColor('#718097'))
            p.drawText(int(x(second)) + 4, self.height() - 7, f'{second // 60}:{second % 60:02}')
        times, notes = self.reference['times'], self.reference['midi']
        first, last = bisect.bisect_left(times, start), bisect.bisect_right(times, start + 10)
        p.setClipRect(QRectF(left, top, width, height))
        p.setPen(QPen(QColor('#8c83ff'), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i in range(first, last):
            midi = notes[i]
            if midi is not None:
                p.drawLine(int(x(times[i])), int(y(midi)), int(x(times[i] + .022)), int(y(midi)))
        previous = None
        for stamp, midi, good in self.history:
            if midi is None:
                previous = None
                continue
            if start <= stamp <= start + 10:
                p.setPen(QPen(QColor('#5de1b4' if good else '#ffb86b'), 3))
                if previous and stamp - previous[0] < .16:
                    p.drawLine(int(x(previous[0])), int(y(previous[1])), int(x(stamp)), int(y(midi)))
                else:
                    p.drawEllipse(QRectF(x(stamp) - 2, y(midi) - 2, 4, 4))
                previous = (stamp, midi)
        p.setClipping(False)
        p.setPen(QPen(QColor('#eff2ff'), 2))
        p.drawLine(int(x(self.position)), top, int(x(self.position)), top + height)
        if not times:
            p.setPen(QColor('#96a4bb'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Здесь появится мелодия вокала')
        p.end()
