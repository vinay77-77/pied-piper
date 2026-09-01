"""Home view — landing screen with Send File and Receive File cards."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from app.ui.widgets.action_card import ActionCard


class HomeView(QWidget):
    """Main landing screen with two primary actions."""

    send_clicked = Signal()
    receive_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("homeView")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        # Spacer top
        outer.addStretch(2)

        # Prompt
        prompt = QLabel("What would you like to do?")
        prompt.setObjectName("homePrompt")
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(prompt)

        outer.addSpacing(36)

        # Action cards row
        cards_layout = QHBoxLayout()
        cards_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cards_layout.setSpacing(32)

        self._send_card = ActionCard(
            icon="↑",
            title="Send File",
            description="Select a file and generate a transfer code",
        )
        self._receive_card = ActionCard(
            icon="↓",
            title="Receive File",
            description="Enter a transfer code to receive a file",
        )

        self._send_card.clicked.connect(self.send_clicked.emit)
        self._receive_card.clicked.connect(self.receive_clicked.emit)

        cards_layout.addWidget(self._send_card)
        cards_layout.addWidget(self._receive_card)

        outer.addLayout(cards_layout)

        # Spacer bottom
        outer.addStretch(3)
