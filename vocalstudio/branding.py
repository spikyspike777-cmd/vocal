"""Resolution-independent app icon, also exported into the Windows executable."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def app_icon():
    icon = QIcon()
    for size in (16, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 64, size / 64)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#171526'))
        painter.drawRoundedRect(QRectF(0, 0, 64, 64), 14, 14)
        painter.setBrush(QColor('#a18bff'))
        painter.drawRoundedRect(QRectF(25, 10, 14, 28), 7, 7)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#f0eaff'), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(QRectF(18, 17, 28, 28), 180 * 16, 180 * 16)
        painter.drawLine(32, 45, 32, 53)
        painter.drawLine(24, 53, 40, 53)
        painter.end()
        icon.addPixmap(pixmap)
    return icon
