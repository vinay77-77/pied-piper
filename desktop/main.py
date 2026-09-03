import sys
from pathlib import Path

# Ensure the desktop directory is in sys.path
desktop_dir = Path(__file__).resolve().parent
if str(desktop_dir) not in sys.path:
    sys.path.insert(0, str(desktop_dir))

from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
