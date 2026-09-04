"""
Main application window for Pied Piper Desktop.
Serves as the application shell providing navigation between Home, Send, and Receive views.
"""

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)
from app.controllers.transfer_controller import TransferController
from app.models.transfer_state import TransferState
from app.ui.widgets.bevel_panel import BevelPanel, BevelStyle


class MainWindow(QMainWindow):
    """
    Main application shell for Pied Piper.
    Manages top-level menus, status bar, and central view stack.
    """

    # View Stack Indices
    VIEW_HOME = 0
    VIEW_SEND = 1
    VIEW_RECEIVE = 2

    def __init__(
        self,
        controller: Optional[TransferController] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller or TransferController(self)

        self.setWindowTitle("Pied Piper")
        self.resize(520, 360)
        self.setMinimumSize(440, 280)

        self._create_menus()
        self._setup_ui()
        self._bind_controller()

    @property
    def controller(self) -> TransferController:
        """Return the transfer controller instance."""
        return self._controller

    def _create_menus(self) -> None:
        """Initialize the classic Windows 95 menu bar."""
        menu_bar = self.menuBar()

        # --- File Menu ---
        file_menu = menu_bar.addMenu("&File")

        home_action = QAction("&Home", self)
        home_action.setShortcut(QKeySequence("Ctrl+H"))
        home_action.triggered.connect(self.navigate_to_home)
        file_menu.addAction(home_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Alt+F4"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- Transfer Menu ---
        transfer_menu = menu_bar.addMenu("&Transfer")

        send_action = QAction("&Send File...", self)
        send_action.setShortcut(QKeySequence("Ctrl+S"))
        send_action.triggered.connect(self.navigate_to_send)
        transfer_menu.addAction(send_action)

        receive_action = QAction("&Receive File...", self)
        receive_action.setShortcut(QKeySequence("Ctrl+R"))
        receive_action.triggered.connect(self.navigate_to_receive)
        transfer_menu.addAction(receive_action)

        # --- Help Menu ---
        help_menu = menu_bar.addMenu("&Help")

        about_action = QAction("&About Pied Piper", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

    def _setup_ui(self) -> None:
        """Construct the central window layout and view stack."""
        central_widget = QWidget(self)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(6)

        # 1. Top Navy Header Banner
        self._header_label = QLabel("Pied Piper — Peer-to-Peer File Transfer")
        self._header_label.setProperty("class", "Win95Header")
        root_layout.addWidget(self._header_label)

        # 2. Central View Stack
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._create_home_view())
        self._stack.addWidget(self._create_send_view())
        self._stack.addWidget(self._create_receive_view())
        root_layout.addWidget(self._stack, 1)

        self.setCentralWidget(central_widget)

        # 3. Status Bar
        status_bar = QStatusBar(self)
        status_bar.setSizeGripEnabled(True)
        self._status_label = QLabel("Ready")
        status_bar.addWidget(self._status_label, 1)
        self.setStatusBar(status_bar)

    def _create_home_view(self) -> QWidget:
        """Create the Home / Landing view."""
        panel = BevelPanel(bevel_style=BevelStyle.SUNKEN, parent=self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Title and Subtitle
        title_label = QLabel("Pied Piper")
        title_font = title_label.font()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        subtitle_label = QLabel("Secure peer-to-peer file transfer with zero-retention architecture.")
        layout.addWidget(subtitle_label)

        prompt_label = QLabel("What would you like to do?")
        layout.addWidget(prompt_label)

        # Primary Action Buttons
        button_row = QHBoxLayout()
        button_row.setSpacing(12)

        send_btn = QPushButton("Send File")
        send_btn.setMinimumHeight(28)
        send_btn.setMinimumWidth(110)
        send_btn.clicked.connect(self.navigate_to_send)
        button_row.addWidget(send_btn)

        recv_btn = QPushButton("Receive File")
        recv_btn.setMinimumHeight(28)
        recv_btn.setMinimumWidth(110)
        recv_btn.clicked.connect(self.navigate_to_receive)
        button_row.addWidget(recv_btn)

        button_row.addStretch()
        layout.addLayout(button_row)

        # Architecture Highlights in Inner Raised Panel
        info_panel = BevelPanel(bevel_style=BevelStyle.RAISED, parent=panel)
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(10, 8, 10, 8)
        info_layout.setSpacing(4)

        info_header = QLabel("System Architecture:")
        info_h_font = info_header.font()
        info_h_font.setBold(True)
        info_header.setFont(info_h_font)
        info_layout.addWidget(info_header)

        desc1 = QLabel("• Direct peer-to-peer WebRTC Data Channels")
        desc2 = QLabel("• Centralized signaling coordination without server file retention")
        desc3 = QLabel("• SHA-256 chunk integrity verification and resumable transfers")
        info_layout.addWidget(desc1)
        info_layout.addWidget(desc2)
        info_layout.addWidget(desc3)

        layout.addWidget(info_panel)
        layout.addStretch()
        return panel

    def _create_send_view(self) -> QWidget:
        """Create the Send File placeholder view."""
        panel = BevelPanel(bevel_style=BevelStyle.SUNKEN, parent=self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Back Navigation Row
        nav_row = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.setFixedWidth(75)
        back_btn.clicked.connect(self.navigate_to_home)
        nav_row.addWidget(back_btn)

        title = QLabel("Send File")
        t_font = title.font()
        t_font.setBold(True)
        title.setFont(t_font)
        nav_row.addWidget(title)
        nav_row.addStretch()
        layout.addLayout(nav_row)

        # Placeholder Body
        body_panel = BevelPanel(bevel_style=BevelStyle.RAISED, parent=panel)
        body_layout = QVBoxLayout(body_panel)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(6)

        desc = QLabel("File selection and transfer initialization will be implemented in Step 5.")
        body_layout.addWidget(desc)
        body_layout.addStretch()

        layout.addWidget(body_panel, 1)
        return panel

    def _create_receive_view(self) -> QWidget:
        """Create the Receive File placeholder view."""
        panel = BevelPanel(bevel_style=BevelStyle.SUNKEN, parent=self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Back Navigation Row
        nav_row = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.setFixedWidth(75)
        back_btn.clicked.connect(self.navigate_to_home)
        nav_row.addWidget(back_btn)

        title = QLabel("Receive File")
        t_font = title.font()
        t_font.setBold(True)
        title.setFont(t_font)
        nav_row.addWidget(title)
        nav_row.addStretch()
        layout.addLayout(nav_row)

        # Placeholder Body
        body_panel = BevelPanel(bevel_style=BevelStyle.RAISED, parent=panel)
        body_layout = QVBoxLayout(body_panel)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(6)

        desc = QLabel("Transfer-code entry and reception workflow will be implemented in Step 6.")
        body_layout.addWidget(desc)
        body_layout.addStretch()

        layout.addWidget(body_panel, 1)
        return panel

    def navigate_to_home(self) -> None:
        """Switch central view to Home."""
        self._stack.setCurrentIndex(self.VIEW_HOME)

    def navigate_to_send(self) -> None:
        """Switch central view to Send File."""
        self._stack.setCurrentIndex(self.VIEW_SEND)

    def navigate_to_receive(self) -> None:
        """Switch central view to Receive File."""
        self._stack.setCurrentIndex(self.VIEW_RECEIVE)

    def _show_about_dialog(self) -> None:
        """Display native About dialog with accurate technical description."""
        QMessageBox.about(
            self,
            "About Pied Piper",
            "Pied Piper v1.0\n\n"
            "A secure peer-to-peer file transfer system with zero-retention architecture.\n\n"
            "• Direct peer-to-peer WebRTC Data Channels\n"
            "• Centralized signaling without server file storage\n"
            "• SHA-256 chunk integrity verification\n"
            "• Interrupted transfer recovery and resume\n",
        )

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
