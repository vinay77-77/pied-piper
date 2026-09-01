"""Receiver confirmation view — accept or reject an incoming file."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from app.utils.file_utils import format_file_size


class ReceiverConfirmationView(QWidget):
    """Shows incoming file details; receiver decides to accept or reject."""

    accept_clicked = Signal()
    reject_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("confirmationView")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        outer.addStretch(2)

        # Title
        title = QLabel("Incoming File")
        title.setObjectName("viewTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title)

        outer.addSpacing(24)

        # File info
        self._file_icon = QLabel("📄")
        self._file_icon.setObjectName("largeIcon")
        self._file_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._file_icon)

        self._file_name = QLabel("")
        self._file_name.setObjectName("fileName")
        self._file_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._file_name)

        outer.addSpacing(8)

        self._file_size = QLabel("")
        self._file_size.setObjectName("fileSize")
        self._file_size.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._file_size)

        outer.addSpacing(20)

        # Message
        msg = QLabel("Sender is ready to transfer this file.")
        msg.setObjectName("infoText")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(msg)

        outer.addSpacing(32)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(16)

        self._accept_btn = QPushButton("Accept Transfer")
        self._accept_btn.setObjectName("primaryButton")
        self._accept_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._accept_btn.clicked.connect(self.accept_clicked.emit)

        self._reject_btn = QPushButton("Reject")
        self._reject_btn.setObjectName("dangerButton")
        self._reject_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reject_btn.clicked.connect(self.reject_clicked.emit)

        btn_row.addWidget(self._accept_btn)
        btn_row.addWidget(self._reject_btn)
        outer.addLayout(btn_row)

        outer.addStretch(3)

    def set_file_info(self, file_name: str, file_size: int) -> None:
        self._file_name.setText(file_name)
        self._file_size.setText(format_file_size(file_size))
