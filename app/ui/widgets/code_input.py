"""Transfer code input widget.

Format-agnostic: accepts any string. The backend defines the actual
transfer code format. This widget provides basic UX (monospace font,
centering, placeholder) without enforcing a specific pattern.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit
from PySide6.QtGui import QFont


class CodeInput(QLineEdit):
    """Styled text input for entering transfer codes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("codeInput")
        self.setPlaceholderText("Enter transfer code")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMaxLength(20)  # Generous limit; backend defines actual format

        font = QFont("Consolas", 18)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        self.setFont(font)
        self.setMinimumHeight(52)

    def text_stripped(self) -> str:
        """Return trimmed input text."""
        return self.text().strip()
