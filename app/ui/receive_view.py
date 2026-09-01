"""Receive view — enter a transfer code to join a session."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)

from app.ui.widgets.code_input import CodeInput


class ReceiveView(QWidget):
    """Screen for entering a transfer code (receiver side)."""

    back_clicked = Signal()
    connect_clicked = Signal(str)  # transfer_code

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("receiveView")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 20, 40, 40)

        # Back button
        back_row = QHBoxLayout()
        self._back_btn = QPushButton("←  Receive File")
        self._back_btn.setObjectName("backButton")
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_clicked.emit)
        back_row.addWidget(self._back_btn)
        back_row.addStretch()
        outer.addLayout(back_row)

        outer.addStretch(2)

        # Instruction
        instruction = QLabel("Enter the transfer code\nprovided by the sender.")
        instruction.setObjectName("viewSubtitle")
        instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(instruction)

        outer.addSpacing(24)

        # Code input
        self._code_input = CodeInput()
        self._code_input.setMaximumWidth(320)
        self._code_input.returnPressed.connect(self._on_connect)
        outer.addWidget(self._code_input, 0, Qt.AlignmentFlag.AlignCenter)

        # Error label (hidden by default)
        self._error_label = QLabel("")
        self._error_label.setObjectName("errorLabel")
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label.setVisible(False)
        outer.addWidget(self._error_label)

        outer.addSpacing(24)

        # Connect button
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setObjectName("primaryButton")
        self._connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._connect_btn.clicked.connect(self._on_connect)
        outer.addWidget(self._connect_btn, 0, Qt.AlignmentFlag.AlignCenter)

        outer.addStretch(3)

    def reset(self) -> None:
        self._code_input.clear()
        self._error_label.setVisible(False)

    def show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def _on_connect(self) -> None:
        code = self._code_input.text_stripped()
        if not code:
            self.show_error("Please enter a transfer code.")
            return
        self._error_label.setVisible(False)
        self.connect_clicked.emit(code)
