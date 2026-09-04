"""
Main application window for Pied Piper Desktop.
Demonstrates the Windows 95 theme, bevel panel foundation, and TransferController integration.
"""

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)
from app.controllers.transfer_controller import TransferController
from app.models.transfer_state import TransferState
from app.ui.widgets.bevel_panel import BevelPanel, BevelStyle


class MainWindow(QMainWindow):
    """Main application window showcasing the Windows 95 visual foundation and controller."""

    def __init__(
        self,
        controller: Optional[TransferController] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller or TransferController(self)

        self.setWindowTitle("Pied Piper")
        self.resize(480, 320)
        self.setMinimumSize(400, 260)

        self._setup_ui()
        self._bind_controller()

    @property
    def controller(self) -> TransferController:
        """Return the transfer controller instance."""
        return self._controller

    def _setup_ui(self) -> None:
        central_widget = QWidget(self)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        # 1. Classic Navy Header Banner
        header_label = QLabel("Pied Piper - [Desktop Foundation]")
        header_label.setProperty("class", "Win95Header")
        root_layout.addWidget(header_label)

        # 2. Sunken Main Content Bevel Panel
        content_panel = BevelPanel(bevel_style=BevelStyle.SUNKEN, parent=self)
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(8)

        info_label = QLabel("Windows 95 visual foundation active.")
        info_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        content_layout.addWidget(info_label)

        # Inner Raised Panel demonstration
        inner_panel = BevelPanel(bevel_style=BevelStyle.RAISED, parent=content_panel)
        inner_layout = QVBoxLayout(inner_panel)
        inner_layout.setContentsMargins(8, 8, 8, 8)
        inner_desc = QLabel("3D Beveled Panel Component (Raised)")
        inner_layout.addWidget(inner_desc)
        content_layout.addWidget(inner_panel)

        content_layout.addStretch()
        root_layout.addWidget(content_panel, 1)

        # 3. Bottom Controls Row with Classic Buttons
        button_row = QHBoxLayout()
        button_row.setSpacing(6)
        button_row.addStretch()

        demo_button = QPushButton("OK")
        demo_button.setFixedWidth(75)
        button_row.addWidget(demo_button)

        close_button = QPushButton("Close")
        close_button.setFixedWidth(75)
        close_button.clicked.connect(self.close)
        button_row.addWidget(close_button)

        root_layout.addLayout(button_row)

        self.setCentralWidget(central_widget)

        # 4. Classic Status Bar
        status_bar = QStatusBar(self)
        status_bar.setSizeGripEnabled(True)
        self._status_label = QLabel("Ready")
        status_bar.addWidget(self._status_label, 1)
        self.setStatusBar(status_bar)

    def _bind_controller(self) -> None:
        """Bind controller signals to window UI elements."""
        self._controller.state_changed.connect(self._on_state_changed)
        self._update_status_display(self._controller.state)

    def _on_state_changed(self, state: TransferState) -> None:
        """Handle controller state updates."""
        self._update_status_display(state)

    def _update_status_display(self, state: TransferState) -> None:
        """Update status bar label according to state."""
        if state == TransferState.IDLE:
            self._status_label.setText("Ready")
        else:
            self._status_label.setText(state.value)
