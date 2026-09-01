"""Send view — file selection via drag-drop or file dialog.

File selection is entirely UI-internal; it does not trigger engine
state changes. The "Generate Transfer Code" button is enabled only
when a file is selected.
"""

import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
)

from app.ui.widgets.file_drop_zone import FileDropZone
from app.utils.file_utils import format_file_size


class SendView(QWidget):
    """File selection screen for the send workflow."""

    back_clicked = Signal()
    generate_code_clicked = Signal(str)  # file_path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sendView")
        self._file_path: str | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 20, 40, 40)

        # Back button
        back_row = QHBoxLayout()
        self._back_btn = QPushButton("←  Send File")
        self._back_btn.setObjectName("backButton")
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_clicked.emit)
        back_row.addWidget(self._back_btn)
        back_row.addStretch()
        outer.addLayout(back_row)

        outer.addStretch(1)

        # Drop zone
        self._drop_zone = FileDropZone()
        self._drop_zone.file_dropped.connect(self._on_file_selected)
        outer.addWidget(self._drop_zone, 0, Qt.AlignmentFlag.AlignCenter)

        # Choose file button
        self._choose_btn = QPushButton("Choose File")
        self._choose_btn.setObjectName("secondaryButton")
        self._choose_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._choose_btn.clicked.connect(self._open_file_dialog)
        outer.addWidget(self._choose_btn, 0, Qt.AlignmentFlag.AlignCenter)

        outer.addSpacing(20)

        # File info area
        self._file_info_widget = QWidget()
        self._file_info_widget.setObjectName("fileInfoArea")
        file_info_layout = QVBoxLayout(self._file_info_widget)
        file_info_layout.setContentsMargins(0, 0, 0, 0)
        file_info_layout.setSpacing(6)

        self._file_name_label = QLabel("")
        self._file_name_label.setObjectName("fileName")
        self._file_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._file_size_label = QLabel("")
        self._file_size_label.setObjectName("fileSize")
        self._file_size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        file_info_layout.addWidget(self._file_name_label)
        file_info_layout.addWidget(self._file_size_label)

        self._file_info_widget.setVisible(False)
        outer.addWidget(self._file_info_widget)

        outer.addSpacing(20)

        # Generate code button
        self._generate_btn = QPushButton("Generate Transfer Code")
        self._generate_btn.setObjectName("primaryButton")
        self._generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._generate_btn.setEnabled(False)
        self._generate_btn.clicked.connect(self._on_generate)
        outer.addWidget(self._generate_btn, 0, Qt.AlignmentFlag.AlignCenter)

        outer.addStretch(2)

    def reset(self) -> None:
        """Clear file selection."""
        self._file_path = None
        self._file_info_widget.setVisible(False)
        self._file_name_label.setText("")
        self._file_size_label.setText("")
        self._generate_btn.setEnabled(False)

    def _open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select File to Send")
        if path:
            self._on_file_selected(path)

    def _on_file_selected(self, path: str) -> None:
        if not os.path.isfile(path):
            return
        self._file_path = path
        self._file_name_label.setText(f"📄  {os.path.basename(path)}")
        self._file_size_label.setText(format_file_size(os.path.getsize(path)))
        self._file_info_widget.setVisible(True)
        self._generate_btn.setEnabled(True)

    def _on_generate(self) -> None:
        if self._file_path:
            self.generate_code_clicked.emit(self._file_path)
