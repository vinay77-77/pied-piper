"""Transfer code view — displays the generated code and waits for receiver."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QApplication,
)
from PySide6.QtGui import QFont


class TransferCodeView(QWidget):
    """Shows the transfer code to the sender while waiting for receiver."""

    cancel_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("transferCodeView")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        outer.addStretch(2)

        # Title
        title = QLabel("Your Transfer Code")
        title.setObjectName("viewTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title)

        outer.addSpacing(24)

        # Code display — treated as opaque string from backend
        self._code_label = QLabel("------")
        self._code_label.setObjectName("transferCode")
        self._code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        code_font = QFont("Consolas", 32)
        code_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4)
        self._code_label.setFont(code_font)
        outer.addWidget(self._code_label)

        outer.addSpacing(16)

        # Copy button
        self._copy_btn = QPushButton("Copy Code")
        self._copy_btn.setObjectName("secondaryButton")
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.clicked.connect(self._copy_code)
        outer.addWidget(self._copy_btn, 0, Qt.AlignmentFlag.AlignCenter)

        outer.addSpacing(32)

        # Status message
        self._status_label = QLabel("Waiting for receiver...")
        self._status_label.setObjectName("waitingLabel")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._status_label)

        outer.addStretch(2)

        # Cancel button
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("dangerButton")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.cancel_clicked.emit)
        outer.addWidget(self._cancel_btn, 0, Qt.AlignmentFlag.AlignCenter)

        outer.addStretch(1)

    def set_code(self, code: str) -> None:
        """Display the transfer code received from the backend."""
        self._code_label.setText(code)

    def set_status(self, text: str) -> None:
        """Update the status text below the code."""
        self._status_label.setText(text)

    def _copy_code(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._code_label.text())
            self._copy_btn.setText("Copied!")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self._copy_btn.setText("Copy Code"))
