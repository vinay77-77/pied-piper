from PySide6.QtWidgets import QMainWindow, QLabel, QWidget, QVBoxLayout
from PySide6.QtCore import Qt


class MainWindow(QMainWindow):
    """Main application window for Pied Piper Desktop."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pied Piper")
        self.resize(640, 480)

        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel("Pied Piper Desktop Foundation", central_widget)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        self.setCentralWidget(central_widget)
