"""Error view — user-friendly error display with configurable actions."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton


class ErrorView(QWidget):
    """Displays a user-friendly error with action buttons.

    Never shows raw Python exceptions. The controller provides
    a title and descriptive message.
    """

    retry_clicked = Signal()
    cancel_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("errorView")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        outer.addStretch(2)

        # Error icon
        icon = QLabel("✕")
        icon.setObjectName("errorIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(icon)

        outer.addSpacing(8)

        self._title_label = QLabel("Something went wrong")
        self._title_label.setObjectName("errorTitle")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._title_label)

        outer.addSpacing(12)

        self._message_label = QLabel("")
        self._message_label.setObjectName("errorMessage")
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message_label.setWordWrap(True)
        outer.addWidget(self._message_label)

        outer.addSpacing(32)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(16)

        self._retry_btn = QPushButton("Try Again")
        self._retry_btn.setObjectName("primaryButton")
        self._retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._retry_btn.clicked.connect(self.retry_clicked.emit)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("secondaryButton")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.cancel_clicked.emit)

        btn_row.addWidget(self._retry_btn)
        btn_row.addWidget(self._cancel_btn)
        outer.addLayout(btn_row)

        outer.addStretch(3)

    def set_error(self, title: str, message: str) -> None:
        self._title_label.setText(title)
        self._message_label.setText(message)
