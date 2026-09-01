"""Active transfer view — progress display during file transfer.

This view only appears when an actual transfer is in progress.
It is NOT a permanent card on the home screen.

All progress values (speed, ETA, bytes) are provided by the transfer
engine — the UI displays them as-is.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from app.ui.widgets.progress_bar import TransferProgressBar
from app.models.transfer_progress import TransferProgress
from app.utils.file_utils import format_file_size, format_speed, format_eta


class TransferView(QWidget):
    """Active transfer progress screen. No pause button — only cancel."""

    cancel_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("transferView")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        outer.addStretch(2)

        # File info
        self._file_icon = QLabel("📄")
        self._file_icon.setObjectName("largeIcon")
        self._file_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._file_icon)

        self._file_name = QLabel("")
        self._file_name.setObjectName("fileName")
        self._file_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._file_name)

        outer.addSpacing(24)

        # Progress bar
        self._progress_bar = TransferProgressBar()
        outer.addWidget(self._progress_bar)

        outer.addSpacing(16)

        # Transfer stats
        self._transferred_label = QLabel("0 B / 0 B")
        self._transferred_label.setObjectName("transferStats")
        self._transferred_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._transferred_label)

        # Speed + ETA row
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 8, 0, 0)

        self._speed_label = QLabel("")
        self._speed_label.setObjectName("transferSpeed")
        self._speed_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._eta_label = QLabel("")
        self._eta_label.setObjectName("transferEta")
        self._eta_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        stats_row.addWidget(self._speed_label)
        stats_row.addStretch()
        stats_row.addWidget(self._eta_label)
        outer.addLayout(stats_row)

        outer.addSpacing(20)

        # Connection status
        self._status_label = QLabel("● Connecting...")
        self._status_label.setObjectName("connectionStatus")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._status_label)

        outer.addStretch(2)

        # Cancel button
        self._cancel_btn = QPushButton("Cancel Transfer")
        self._cancel_btn.setObjectName("dangerButton")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.cancel_clicked.emit)
        outer.addWidget(self._cancel_btn, 0, Qt.AlignmentFlag.AlignCenter)

        outer.addStretch(1)

    def set_file_name(self, name: str) -> None:
        self._file_name.setText(name)

    def set_connection_status(self, text: str) -> None:
        self._status_label.setText(text)

    def update_progress(self, progress: TransferProgress) -> None:
        """Update all progress displays from engine-provided values."""
        self._progress_bar.set_value(progress.percentage)
        self._transferred_label.setText(
            f"{format_file_size(progress.bytes_transferred)} / "
            f"{format_file_size(progress.total_bytes)}"
        )
        self._speed_label.setText(format_speed(progress.speed_bps))
        self._eta_label.setText(format_eta(progress.eta_seconds))
