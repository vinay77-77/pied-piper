"""Status bar widget — colored dot + status text at the bottom of the window."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

from app.models.transfer_state import TransferState

# Map transfer states to (color, label)
_STATE_DISPLAY = {
    TransferState.IDLE: ("#66bb6a", "Ready"),
    TransferState.CREATING_SESSION: ("#ffa726", "Creating session..."),
    TransferState.WAITING_FOR_RECEIVER: ("#ffa726", "Waiting for receiver..."),
    TransferState.RECEIVER_CONNECTED: ("#4fc3f7", "Receiver connected"),
    TransferState.AWAITING_ACCEPTANCE: ("#ffa726", "Waiting for acceptance..."),
    TransferState.CONNECTING: ("#ffa726", "Connecting..."),
    TransferState.TRANSFERRING: ("#4fc3f7", "Transferring"),
    TransferState.INTERRUPTED: ("#ffa726", "Interrupted"),
    TransferState.RESUMING: ("#ffa726", "Resuming..."),
    TransferState.COMPLETED: ("#66bb6a", "Complete"),
    TransferState.FAILED: ("#ef5350", "Error"),
    TransferState.CANCELLED: ("#8888aa", "Cancelled"),
}


class StatusDot(QWidget):
    """Small colored circle indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._color = QColor("#66bb6a")

    def set_color(self, hex_color: str) -> None:
        self._color = QColor(hex_color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 10, 10)
        painter.end()


class StatusBarWidget(QWidget):
    """Bottom status bar with colored dot and text label."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusBar")
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(8)

        self._dot = StatusDot()
        self._label = QLabel("Ready")
        self._label.setObjectName("statusText")

        layout.addWidget(self._dot)
        layout.addWidget(self._label)
        layout.addStretch()

    def update_state(self, state: TransferState) -> None:
        color, text = _STATE_DISPLAY.get(state, ("#8888aa", "Unknown"))
        self._dot.set_color(color)
        self._label.setText(text)
