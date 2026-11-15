from __future__ import annotations

import bisect
import math
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QIcon, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from .core import note_name, segment_notes

BG = '#0b0c12'
SURFACE = '#13151f'
SURFACE_2 = '#1b1e2b'
BORDER = '#252938'
TEXT = '#f3f4f8'
MUTED = '#8a90a6'
ACCENT = '#8b7bff'
ACCENT_2 = '#f06bd0'
GOOD = '#3fe5a6'
WARN = '#ffb155'
FONT = 'Inter'


def font(size: float, weight=QFont.Weight.Normal) -> QFont:
    item = QFont(FONT)
    item.setFamilies([FONT, 'Segoe UI', 'SF Pro Text', 'Helvetica Neue', 'Noto Sans', 'Arial'])
    item.setPixelSize(int(size))
    item.setWeight(weight)
    return item


def colour(value: str, alpha: float = 1.) -> QColor:
    item = QColor(value)
    item.setAlphaF(max(0., min(1., alpha)))
    return item


def icon(name: str, tint: str = TEXT, size: int = 18) -> QIcon:
    """Small vector icons drawn at runtime, so the app ships without image files."""
    scale = 3
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * scale / 24, size * scale / 24)
    pen = QPen(QColor(tint), 2.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == 'plus':
        p.drawLine(QPointF(12, 5), QPointF(12, 19))
        p.drawLine(QPointF(5, 12), QPointF(19, 12))
    elif name == 'restart':
        p.drawArc(QRectF(5, 5, 14, 14), 60 * 16, 300 * 16)
        p.drawPolyline([QPointF(11.5, 2), QPointF(15.5, 5.3), QPointF(11.5, 8.6)])
    elif name == 'mic':
        p.drawRoundedRect(QRectF(9, 3, 6, 11), 3, 3)
        p.drawArc(QRectF(5.5, 5, 13, 13), 180 * 16, 180 * 16)
        p.drawLine(QPointF(12, 18), QPointF(12, 21))
    elif name == 'note':
        p.setBrush(QColor(tint))
        p.drawEllipse(QRectF(5, 14.5, 6, 5))
        p.drawLine(QPointF(11, 17), QPointF(11, 5))
        p.drawLine(QPointF(11, 5), QPointF(18, 7.5))
    elif name == 'edit':
        p.drawPolygon([QPointF(5, 19), QPointF(6, 15), QPointF(15.5, 5.5), QPointF(18.5, 8.5), QPointF(9, 18)])
    elif name == 'clock':
        p.drawEllipse(QRectF(4, 4, 16, 16))
        p.drawPolyline([QPointF(12, 8), QPointF(12, 12), QPointF(15, 14)])
    elif name == 'search':
        p.drawEllipse(QRectF(4.5, 4.5, 11, 11))
        p.drawLine(QPointF(14.5, 14.5), QPointF(19.5, 19.5))
    elif name == 'upload':
        p.drawLine(QPointF(12, 16), QPointF(12, 4))
        p.drawPolyline([QPointF(7, 9), QPointF(12, 4), QPointF(17, 9)])
        p.drawPolyline([QPointF(4, 15), QPointF(4, 20), QPointF(20, 20), QPointF(20, 15)])
    p.end()
    pixmap.setDevicePixelRatio(scale)
    return QIcon(pixmap)


class PlayButton(QAbstractButton):
    """Round gradient transport button that toggles between play and pause glyphs."""

    def __init__(self, diameter: int = 54):
        super().__init__()
        self.playing = False
        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip('Играть / пауза (Пробел)')

    def set_playing(self, playing: bool):
        if playing != self.playing:
            self.playing = playing
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        lift = .12 if self.underMouse() else 0
        gradient.setColorAt(0, QColor(ACCENT).lighter(int(100 + lift * 100)))
        gradient.setColorAt(1, QColor(ACCENT_2).lighter(int(100 + lift * 100)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(gradient) if self.isEnabled() else QColor('#2a2e3f'))
        p.drawEllipse(rect.adjusted(2, 2, -2, -2) if self.isDown() else rect)
        p.setBrush(QColor('#ffffff'))
        c, r = rect.center(), rect.width() * .2
        if self.playing:
            for dx in (-r * .95, r * .3):
                p.drawRoundedRect(QRectF(c.x() + dx, c.y() - r, r * .65, r * 2), 1.5, 1.5)
        else:
            path = QPainterPath()
            path.moveTo(c.x() - r * .7, c.y() - r * 1.05)
            path.lineTo(c.x() + r * 1.15, c.y())
            path.lineTo(c.x() - r * .7, c.y() + r * 1.05)
            path.closeSubpath()
            p.drawPath(path)
        p.end()

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()


class LevelMeter(QWidget):
    def __init__(self):
        super().__init__()
        self.level = 0.
        self.setFixedSize(74, 6)
        self.setToolTip('Уровень микрофона')

    def set_level(self, rms: float):
        # Map roughly -50..-6 dBFS onto the bar; decay slowly so it reads as a meter.
        target = 0. if rms <= 1e-5 else max(0., min(1., (20 * math.log10(rms) + 50) / 44))
        level = max(target, self.level * .88)
        if abs(level - self.level) > .005:
            self.level = level
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(self.rect())
        p.setBrush(QColor('#262a3a'))
        p.drawRoundedRect(rect, 3, 3)
        if self.level > 0:
            p.setBrush(QColor(GOOD if self.level < .9 else WARN))
            p.drawRoundedRect(QRectF(0, 0, max(6., rect.width() * self.level), rect.height()), 3, 3)
        p.end()


class DropZone(QWidget):
    """Click-or-drop target for the source audio file."""
    clicked = Signal()
    dropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.file_name = ''
        self.hover = False
        self.setAcceptDrops(True)
        self.setMinimumHeight(132)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_file(self, name: str):
        self.file_name = name
        self.update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.hover = True
            self.update()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.hover = False
        self.update()

    def dropEvent(self, event):
        self.hover = False
        self.update()
        urls = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if urls:
            self.dropped.emit(urls[0])

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def enterEvent(self, event):
        self.hover = True
        self.update()

    def leaveEvent(self, event):
        self.hover = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        chosen = bool(self.file_name)
        p.setBrush(colour(ACCENT, .13 if self.hover else .07) if not chosen else colour(GOOD, .08))
        pen = QPen(colour(GOOD, .7) if chosen else colour(ACCENT, .95 if self.hover else .55), 1.6)
        if not chosen:
            pen.setDashPattern([5, 4])
        p.setPen(pen)
        p.drawRoundedRect(rect, 16, 16)
        mark = icon('note' if chosen else 'upload', GOOD if chosen else ACCENT, 30).pixmap(QSize(30, 30))
        p.drawPixmap(int(rect.center().x() - 15), int(rect.center().y() - 40), mark)
        p.setPen(QColor(TEXT))
        p.setFont(font(16, QFont.Weight.DemiBold))
        title = self.file_name if chosen else 'Перетащи песню сюда'
        title = QFontMetricsF(p.font()).elidedText(title, Qt.TextElideMode.ElideMiddle, rect.width() - 48)
        p.drawText(QRectF(rect.left(), rect.center().y() - 2, rect.width(), 24), Qt.AlignmentFlag.AlignCenter, title)
        p.setPen(QColor(MUTED))
        p.setFont(font(13))
        hint = 'Нажми, чтобы выбрать другой файл' if chosen else 'или нажми, чтобы выбрать файл · MP3, WAV, FLAC, M4A, OGG'
        p.drawText(QRectF(rect.left(), rect.center().y() + 24, rect.width(), 20), Qt.AlignmentFlag.AlignCenter, hint)
        p.end()


class PitchTimeline(QWidget):
    """Scrolling piano roll: melody notes, the singer's pitch trace and hit highlights."""
    seekRequested = Signal(float)

    WINDOW = 6.
    HEAD = .28

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.reference = {'times': [], 'midi': []}
        self.notes: list[dict] = []
        self.starts: list[float] = []
        self.position = 0.
        self.history: list[tuple] = []
        self.hits: dict[int, list[list[float]]] = {}
        self.live = None
        self.live_good = None
        self.low, self.high = 48, 72
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_reference(self, reference):
        self.reference = reference
        notes = reference.get('notes')
        if notes is None:
            times = reference.get('times', [])
            step = times[1] - times[0] if len(times) > 1 else .02
            notes = segment_notes(times, reference.get('midi', []), step)
        self.notes = notes
        self.starts = [note['start'] for note in notes]
        self.clear_performance()
        if notes:
            pitches = sorted(note['midi'] for note in notes)
            # Ignore a few stray outliers so the roll is not squashed by one bad note.
            cut = len(pitches) // 50
            core = pitches[cut:len(pitches) - cut] or pitches
            self.low = math.floor(core[0]) - 3
            self.high = max(self.low + 14, math.ceil(core[-1]) + 3)
        else:
            self.low, self.high = 48, 72
        self.update()

    def clear_performance(self):
        self.history = []
        self.hits = {}
        self.live = None
        self.live_good = None

    def add_hit(self, index: int, start: float, end: float):
        spans = self.hits.setdefault(index, [])
        if spans and start - spans[-1][1] < .09:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])

    def fold(self, midi: float) -> float:
        """Shift a pitch by octaves until it is inside the visible range."""
        while midi > self.high:
            midi -= 12
        while midi < self.low:
            midi += 12
        return midi

    def _area(self) -> QRectF:
        return QRectF(46, 10, self.width() - 56, self.height() - 38)

    def mousePressEvent(self, event):
        area = self._area()
        if event.button() == Qt.MouseButton.LeftButton and area.contains(event.position()):
            start = self.position - self.WINDOW * self.HEAD
            self.seekRequested.emit(max(0., start + (event.position().x() - area.left()) / area.width() * self.WINDOW))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        frame = QRectF(self.rect())
        card = QPainterPath()
        card.addRoundedRect(frame, 18, 18)
        p.setClipPath(card)
        background = QLinearGradient(0, 0, 0, frame.height())
        background.setColorAt(0, QColor('#151826'))
        background.setColorAt(1, QColor('#0f111a'))
        p.fillRect(frame, background)

        area = self._area()
        span = self.high - self.low + 1
        row = area.height() / span
        start = self.position - self.WINDOW * self.HEAD

        def x(t):
            return area.left() + (t - start) / self.WINDOW * area.width()

        def y(m):
            return area.top() + (self.high + .5 - m) * row

        # Pitch rows and labels.
        p.setFont(font(11, QFont.Weight.Medium))
        label_all = row >= 15
        for midi in range(self.low, self.high + 1):
            top = y(midi) - row / 2
            if midi % 12 in (1, 3, 6, 8, 10):
                p.fillRect(QRectF(area.left(), top, area.width(), row), colour('#000000', .16))
            if midi % 12 == 0:
                p.setPen(QPen(colour('#ffffff', .09), 1))
                p.drawLine(QPointF(area.left(), top + row), QPointF(area.right(), top + row))
            natural = midi % 12 in (0, 2, 4, 5, 7, 9, 11)
            if midi % 12 == 0 or (label_all and natural) or (not label_all and row >= 8 and midi % 12 in (4, 7)):
                p.setPen(colour(TEXT, .8) if midi % 12 == 0 else colour(MUTED, .75))
                p.drawText(QRectF(0, y(midi) - 8, area.left() - 8, 16),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, note_name(midi))

        # Seconds grid.
        for second in range(max(0, math.ceil(start)), math.ceil(start + self.WINDOW) + 1):
            xs = x(second)
            if xs > area.right():
                break
            p.setPen(QPen(colour('#ffffff', .045), 1))
            p.drawLine(QPointF(xs, area.top()), QPointF(xs, area.bottom()))
            p.setPen(colour(MUTED, .7))
            p.drawText(QRectF(xs - 30, area.bottom() + 6, 60, 16), Qt.AlignmentFlag.AlignCenter,
                       f'{second // 60}:{second % 60:02}')

        p.save()
        p.setClipRect(area.adjusted(0, -6, 0, 6), Qt.ClipOperation.IntersectClip)
        head = x(self.position)
        # Already sung part of the roll is slightly dimmed.
        p.fillRect(QRectF(area.left(), area.top(), head - area.left(), area.height()), colour('#000000', .13))

        bar = max(6., min(13., row * .7))
        first = max(0, bisect.bisect_left(self.starts, start) - 4)
        last = bisect.bisect_right(self.starts, start + self.WINDOW)
        p.setPen(Qt.PenStyle.NoPen)
        for index in range(first, last):
            note = self.notes[index]
            if note['end'] < start:
                continue
            left, right = x(note['start']), x(note['end'])
            rect = QRectF(left, y(note['midi']) - bar / 2, max(bar, right - left), bar)
            active = note['start'] <= self.position < note['end']
            past = note['end'] <= self.position
            if active:
                p.setBrush(colour(ACCENT, .22))
                p.drawRoundedRect(rect.adjusted(-5, -5, 5, 5), bar / 2 + 5, bar / 2 + 5)
            gradient = QLinearGradient(rect.left(), 0, rect.right(), 0)
            if past:
                gradient.setColorAt(0, colour('#5a5490', .55))
                gradient.setColorAt(1, colour('#5a5490', .55))
            else:
                gradient.setColorAt(0, QColor('#9d8fff' if active else ACCENT))
                gradient.setColorAt(1, QColor('#c58bff' if active else '#a184ff'))
            p.setBrush(gradient)
            p.drawRoundedRect(rect, bar / 2, bar / 2)
            for a, b in self.hits.get(index, ()):
                hl, hr = max(left, x(a)), min(max(right, left + bar), x(b))
                if hr - hl < 1:
                    continue
                hit = QRectF(hl, rect.top(), max(hr - hl, bar * .6), bar)
                p.setBrush(colour(GOOD, .22))
                p.drawRoundedRect(hit.adjusted(-3, -3, 3, 3), bar / 2 + 3, bar / 2 + 3)
                p.setBrush(QColor(GOOD))
                p.drawRoundedRect(hit, bar / 2, bar / 2)

        # The singer's pitch trace.
        previous = None
        for stamp, midi, good in self.history:
            if midi is None or stamp < start - .5:
                previous = None
                continue
            age = self.position - stamp
            tint = colour(GOOD if good else (WARN if good is False else '#d7daee'), max(.25, 1 - age / 3.2))
            point = QPointF(x(stamp), y(midi))
            if previous is not None and stamp - previous[0] < .12 and abs(midi - previous[1]) < 5:
                p.setPen(QPen(tint, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(previous[2], point)
            previous = (stamp, midi, point)
        p.restore()

        # Playhead and the live pitch marker.
        line = QLinearGradient(0, area.top(), 0, area.bottom())
        line.setColorAt(0, colour('#ffffff', 0))
        line.setColorAt(.12, colour('#ffffff', .75))
        line.setColorAt(.88, colour('#ffffff', .75))
        line.setColorAt(1, colour('#ffffff', 0))
        p.setPen(QPen(QBrush(line), 1.6))
        p.drawLine(QPointF(head, area.top()), QPointF(head, area.bottom()))
        if self.live is not None:
            tint = GOOD if self.live_good else (WARN if self.live_good is False else '#ffffff')
            centre = QPointF(head, y(self.live))
            glow = QRadialGradient(centre, 22)
            glow.setColorAt(0, colour(tint, .5))
            glow.setColorAt(1, colour(tint, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(centre, 22, 22)
            p.setBrush(QColor(tint))
            p.drawEllipse(centre, 6.5, 6.5)
            p.setBrush(QColor('#ffffff'))
            p.drawEllipse(centre, 2.6, 2.6)

        if not self.notes:
            p.setPen(colour(MUTED, .9))
            p.setFont(font(15))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, 'В этой песне не нашлось вокала — нот нет')
        p.end()


class LyricsView(QWidget):
    """Spotify-style lyrics column: the current line is bright, the list scrolls with the song."""
    lineClicked = Signal(int)

    def __init__(self):
        super().__init__()
        self.lines: list[dict] = []
        self.active = None
        self.target = None  # line waiting for a tap in sync mode
        self.sync_mode = False
        self.offset = 0.
        self.goal = 0.
        self.manual_until = 0.
        self.hovered = None
        self.layout_cache = None
        self.setMouseTracking(True)
        self.setMinimumWidth(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_lines(self, lines: list[dict]):
        self.lines = lines
        self.layout_cache = None
        self.active = None
        self.offset = self.goal = 0.
        self.update()

    def set_active(self, index):
        if index != self.active:
            self.active = index
            self.update()

    def set_sync(self, enabled: bool, target=None):
        self.sync_mode, self.target = enabled, target
        self.layout_cache = None
        self.update()

    def _fonts(self):
        return font(23, QFont.Weight.Bold), font(11, QFont.Weight.DemiBold)

    def _layout(self):
        width = self.width() - 8
        if self.layout_cache and self.layout_cache[0] == width:
            return self.layout_cache[1]
        main, small = self._fonts()
        metrics = QFontMetricsF(main)
        rows, top = [], 0.
        stamp = 16 if self.sync_mode else 0
        for line in self.lines:
            text = line['text'] or '♪'
            height = metrics.boundingRect(QRectF(0, 0, width, 10000), int(Qt.TextFlag.TextWordWrap), text).height()
            rows.append((top, height + stamp))
            top += height + stamp + 18
        self.layout_cache = (width, rows)
        return rows

    def resizeEvent(self, event):
        self.layout_cache = None

    def advance(self):
        """Animate one step towards the focused line; called from the UI timer."""
        rows = self._layout()
        focus = self.target if self.sync_mode else self.active
        if rows and time.monotonic() > self.manual_until:
            if focus is not None and focus < len(rows):
                top, height = rows[focus]
                self.goal = top + height / 2 - self.height() * .38
            elif not self.sync_mode:
                self.goal = -self.height() * .12
        limit = (rows[-1][0] + rows[-1][1] - self.height() * .5) if rows else 0
        self.goal = max(-self.height() * .3, min(self.goal, max(limit, 0)))
        delta = self.goal - self.offset
        if abs(delta) > .4:
            self.offset += delta * .14
            self.update()

    def wheelEvent(self, event):
        self.goal -= event.angleDelta().y() * .6
        self.manual_until = time.monotonic() + 3.
        self.update()

    def _index_at(self, pos):
        ypos = pos.y() + self.offset
        for index, (top, height) in enumerate(self._layout()):
            if top - 8 <= ypos <= top + height + 8:
                return index
        return None

    def mouseMoveEvent(self, event):
        index = self._index_at(event.position())
        clickable = index is not None and (self.sync_mode or self.lines[index].get('time') is not None)
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)
        if index != self.hovered:
            self.hovered = index
            self.update()

    def leaveEvent(self, event):
        self.hovered = None
        self.update()

    def mouseReleaseEvent(self, event):
        index = self._index_at(event.position())
        if index is not None and event.button() == Qt.MouseButton.LeftButton:
            self.lineClicked.emit(index)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        main, small = self._fonts()
        if not self.lines:
            p.setPen(colour('#ffffff', .85))
            p.setFont(font(20, QFont.Weight.Bold))
            p.drawText(QRectF(0, self.height() * .3, self.width(), 30), Qt.AlignmentFlag.AlignHCenter, 'Текста пока нет')
            p.setPen(colour('#ffffff', .5))
            p.setFont(font(13))
            p.drawText(QRectF(10, self.height() * .3 + 38, self.width() - 20, 60),
                       Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
                       'Нажми «Изменить», чтобы вставить слова или найти их в интернете')
            p.end()
            return
        rows = self._layout()
        stamp = 16 if self.sync_mode else 0
        timed = any(line.get('time') is not None for line in self.lines)
        for index, (top, height) in enumerate(rows):
            ytop = top - self.offset
            if ytop + height < -20 or ytop > self.height() + 20:
                continue
            line = self.lines[index]
            if self.sync_mode:
                focus = index == self.target
                alpha = 1. if focus else (.55 if line.get('time') is not None and not line.get('auto') else .3)
                tint = colour(ACCENT_2 if focus else '#ffffff', alpha)
                p.setFont(small)
                p.setPen(colour(ACCENT_2 if focus else '#ffffff', .9 if focus else .4))
                moment = line.get('time')
                label = '—:——' if moment is None else f'{int(moment) // 60}:{moment % 60:04.1f}'
                if line.get('auto') and moment is not None:
                    label += '  ·  авто'
                if focus:
                    label += '  ·  жми Пробел'
                p.drawText(QRectF(0, ytop, self.width(), 14), Qt.AlignmentFlag.AlignLeft, label)
            elif not timed:
                tint = colour('#ffffff', .8)
            elif index == self.active:
                tint = colour('#ffffff', 1)
            elif self.active is not None and index < self.active:
                tint = colour('#ffffff', .3)
            else:
                tint = colour('#ffffff', .5)
            if index == self.hovered and index != self.active:
                tint = colour('#ffffff', .82)
            # Lines dissolve towards the top and bottom edges of the panel.
            middle = ytop + height / 2
            tint.setAlphaF(tint.alphaF() * max(0., min(1., min(middle + 10, self.height() - middle + 10) / 70)))
            p.setFont(main)
            p.setPen(tint)
            p.drawText(QRectF(0, ytop + stamp, self.width() - 8, height),
                       int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                       line['text'] or '♪')
        p.end()
