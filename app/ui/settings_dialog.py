"""Settings dialog — modal dialog for application preferences."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QFileDialog, QFrame,
)

from app.config.settings import AppSettings


class SettingsDialog(QDialog):
    """Modal settings dialog with General, Transfer, and Diagnostics sections."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setObjectName("settingsDialog")
        self.setMinimumSize(480, 400)
        self.setModal(True)

        self._settings = AppSettings()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(20)

        title = QLabel("Settings")
        title.setObjectName("settingsTitle")
        outer.addWidget(title)

        # --- General Section ---
        outer.addWidget(self._section_label("General"))

        # Download directory
        dir_row = QHBoxLayout()
        dir_label = QLabel("Default download location:")
        dir_label.setObjectName("settingLabel")
        self._dir_value = QLabel(self._settings.download_directory)
        self._dir_value.setObjectName("settingValue")
        self._dir_value.setWordWrap(True)
        dir_browse = QPushButton("Browse")
        dir_browse.setObjectName("secondaryButton")
        dir_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        dir_browse.clicked.connect(self._browse_directory)
        dir_row.addWidget(dir_label)
        dir_row.addWidget(self._dir_value, 1)
        dir_row.addWidget(dir_browse)
        outer.addLayout(dir_row)

        outer.addWidget(self._separator())

        # --- Transfer Section ---
        outer.addWidget(self._section_label("Transfer"))

        self._ask_checkbox = QCheckBox("Ask before accepting files")
        self._ask_checkbox.setObjectName("settingCheckbox")
        self._ask_checkbox.setChecked(self._settings.ask_before_accepting)
        outer.addWidget(self._ask_checkbox)

        outer.addWidget(self._separator())

        # --- Diagnostics Section ---
        outer.addWidget(self._section_label("Diagnostics"))

        self._log_checkbox = QCheckBox("Enable logging")
        self._log_checkbox.setObjectName("settingCheckbox")
        self._log_checkbox.setChecked(self._settings.enable_logging)
        outer.addWidget(self._log_checkbox)

        outer.addStretch()

        # Save / Close
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        save_btn = QPushButton("Save")
        save_btn.setObjectName("primaryButton")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save_and_close)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        outer.addLayout(btn_row)

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setObjectName("separator")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        return line

    def _browse_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Download Directory", self._settings.download_directory
        )
        if path:
            self._dir_value.setText(path)

    def _save_and_close(self) -> None:
        self._settings.download_directory = self._dir_value.text()
        self._settings.ask_before_accepting = self._ask_checkbox.isChecked()
        self._settings.enable_logging = self._log_checkbox.isChecked()
        self.accept()
