"""Application settings backed by QSettings for persistence."""

import os
from PySide6.QtCore import QSettings, QStandardPaths


class AppSettings:
    """Wrapper around QSettings for Pied Piper user preferences."""

    def __init__(self):
        self._settings = QSettings("PiedPiper", "PiedPiper")

    @property
    def download_directory(self) -> str:
        default = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DownloadLocation
        )
        return self._settings.value("general/download_directory", default, str)

    @download_directory.setter
    def download_directory(self, path: str):
        self._settings.setValue("general/download_directory", path)

    @property
    def ask_before_accepting(self) -> bool:
        return self._settings.value("transfer/ask_before_accepting", True, bool)

    @ask_before_accepting.setter
    def ask_before_accepting(self, value: bool):
        self._settings.setValue("transfer/ask_before_accepting", value)

    @property
    def enable_logging(self) -> bool:
        return self._settings.value("diagnostics/enable_logging", False, bool)

    @enable_logging.setter
    def enable_logging(self, value: bool):
        self._settings.setValue("diagnostics/enable_logging", value)
