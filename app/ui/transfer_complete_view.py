"""Transfer complete view — success screen with integrity verification.

The integrity result is architecturally separable from completion.
The UI handles missing/None integrity fields gracefully and can
display additional info (algorithm, hash) when the engine provides it.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

from app.models.transfer_result import TransferResult
from app.utils.file_utils import format_file_size


class TransferCompleteView(QWidget):
    """Shown after a transfer completes successfully."""

    done_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("completeView")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        outer.addStretch(2)

        # Success icon
        icon = QLabel("✓")
        icon.setObjectName("successIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(icon)

        outer.addSpacing(8)

        title = QLabel("Transfer Complete")
        title.setObjectName("viewTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title)

        outer.addSpacing(24)

        self._file_name = QLabel("")
        self._file_name.setObjectName("fileName")
        self._file_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._file_name)

        self._size_label = QLabel("")
        self._size_label.setObjectName("fileSize")
        self._size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._size_label)

        outer.addSpacing(16)

        # Integrity verification — separate from completion status
        self._integrity_label = QLabel("")
        self._integrity_label.setObjectName("integrityLabel")
        self._integrity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._integrity_label)

        outer.addStretch(2)

        # Done button
        self._done_btn = QPushButton("Done")
        self._done_btn.setObjectName("primaryButton")
        self._done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._done_btn.clicked.connect(self.done_clicked.emit)
        outer.addWidget(self._done_btn, 0, Qt.AlignmentFlag.AlignCenter)

        outer.addStretch(1)

    def set_result(self, result: TransferResult, file_name: str) -> None:
        """Populate the view from a TransferResult.

        Handles missing integrity info gracefully — the engine may
        not always provide it (e.g., if verification was skipped).
        """
        self._file_name.setText(f"📄  {file_name}")
        self._size_label.setText(
            f"{format_file_size(result.total_bytes_transferred)} transferred"
        )

        # Integrity display — separable from completion
        if result.integrity_verified is True:
            algo = f" ({result.integrity_algorithm})" if result.integrity_algorithm else ""
            self._integrity_label.setText(f"✓  Integrity verified{algo}")
            self._integrity_label.setProperty("status", "success")
        elif result.integrity_verified is False:
            self._integrity_label.setText("⚠  Integrity verification failed")
            self._integrity_label.setProperty("status", "warning")
        else:
            # Verification not performed or not yet available
            self._integrity_label.setText("Integrity verification unavailable")
            self._integrity_label.setProperty("status", "neutral")

        self._integrity_label.style().unpolish(self._integrity_label)
        self._integrity_label.style().polish(self._integrity_label)
