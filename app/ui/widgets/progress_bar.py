"""Custom progress bar widget with rounded corners and smooth animation."""

from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QBrush, QPainterPath
from PySide6.QtWidgets import QWidget


class TransferProgressBar(QWidget):
    """Custom-painted progress bar with accent color fill."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("transferProgressBar")
        self.setFixedHeight(28)
        self.setMinimumWidth(200)

        self._value = 0.0  # 0-100
        self._bg_color = QColor("#2a2a4a")
        self._fill_color = QColor("#4fc3f7")
        self._text_color = QColor("#e0e0e0")
        self._radius = 8

        self._animation = QPropertyAnimation(self, b"animatedValue")
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def get_animated_value(self) -> float:
        return self._value

    def set_animated_value(self, val: float) -> None:
        self._value = val
        self.update()

    animatedValue = Property(float, get_animated_value, set_animated_value)

    def set_value(self, percentage: float) -> None:
        """Set progress value (0-100) with smooth animation."""
        target = max(0.0, min(100.0, percentage))
        self._animation.stop()
        self._animation.setStartValue(self._value)
        self._animation.setEndValue(target)
        self._animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        r = self._radius

        # Background track
        bg_path = QPainterPath()
        bg_path.addRoundedRect(0, 0, w, h, r, r)
        painter.fillPath(bg_path, QBrush(self._bg_color))

        # Fill
        fill_w = max(0, (self._value / 100.0) * w)
        if fill_w > 0:
            fill_path = QPainterPath()
            fill_path.addRoundedRect(0, 0, fill_w, h, r, r)
            painter.fillPath(fill_path, QBrush(self._fill_color))

        # Percentage text
        painter.setPen(self._text_color)
        painter.drawText(
            0, 0, w, h,
            Qt.AlignmentFlag.AlignCenter,
            f"{self._value:.0f}%",
        )
        painter.end()
