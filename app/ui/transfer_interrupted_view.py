"""Transfer interrupted view — shown when the connection drops.

Resume is available only after an interruption (not a manual pause).
The engine determines whether resumption is possible.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from app.utils.file_utils import format_file_size


class TransferInterruptedView(QWidget):
    """Shown when a transfer is interrupted — offers Resume or Cancel."""

    resume_clicked = Signal()
    cancel_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("interruptedView")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        outer.addStretch(2)

        # Title
        title = QLabel("Transfer Interrupted")
        title.setObjectName("warningTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title)

        outer.addSpacing(24)

        self._file_name = QLabel("")
        self._file_name.setObjectName("fileName")
        self._file_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._file_name)

        outer.addSpacing(8)

        self._progress_label = QLabel("")
        self._progress_label.setObjectName("transferStats")
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._progress_label)

        outer.addSpacing(20)

        msg = QLabel("The connection was interrupted.")
        msg.setObjectName("infoText")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(msg)

        outer.addSpacing(32)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(16)

        self._resume_btn = QPushButton("Resume")
        self._resume_btn.setObjectName("primaryButton")
        self._resume_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._resume_btn.clicked.connect(self.resume_clicked.emit)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("dangerButton")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.cancel_clicked.emit)

        btn_row.addWidget(self._resume_btn)
        btn_row.addWidget(self._cancel_btn)
        outer.addLayout(btn_row)

        outer.addStretch(3)

    def set_info(self, file_name: str, bytes_transferred: int, total_bytes: int) -> None:
        self._file_name.setText(f"📄  {file_name}")
        self._progress_label.setText(
            f"{format_file_size(bytes_transferred)} / "
            f"{format_file_size(total_bytes)} transferred"
        )
