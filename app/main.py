"""Pied Piper — Desktop Application Entry Point.

Instantiates mock services, injects them into the controller,
and launches the main window. Replace MockBackendClient and
MockTransferEngine with real implementations to integrate
the actual backend and transfer engine.
"""

import sys
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from app.services.mock_backend_client import MockBackendClient
from app.services.mock_transfer_engine import MockTransferEngine
from app.controllers.transfer_controller import TransferController
from app.ui.main_window import MainWindow


def load_stylesheet() -> str:
    """Load the QSS stylesheet from resources."""
    qss_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "resources", "styles", "dark_theme.qss",
    )
    if os.path.isfile(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def main():
    app = QApplication(sys.argv)

    # Set application-wide font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Load dark theme
    stylesheet = load_stylesheet()
    if stylesheet:
        app.setStyleSheet(stylesheet)

    # --- Service layer (swap these for real implementations later) ---
    backend_client = MockBackendClient()
    transfer_engine = MockTransferEngine()

    # --- Controller (depends on interfaces, not implementations) ---
    controller = TransferController(backend_client, transfer_engine)

    # --- UI ---
    window = MainWindow(controller)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
