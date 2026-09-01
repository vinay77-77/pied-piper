"""Main window — application shell with view routing and state machine.

Routes TransferState changes to the appropriate view, accounting for
the session role (is_sender) when the same state requires different
UI behavior for sender vs receiver.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget,
)

from app.controllers.transfer_controller import TransferController
from app.models.transfer_state import TransferState
from app.models.transfer_session import TransferSession
from app.models.transfer_progress import TransferProgress
from app.models.transfer_result import TransferResult

from app.ui.home_view import HomeView
from app.ui.send_view import SendView
from app.ui.transfer_code_view import TransferCodeView
from app.ui.receive_view import ReceiveView
from app.ui.receiver_confirmation_view import ReceiverConfirmationView
from app.ui.transfer_view import TransferView
from app.ui.transfer_complete_view import TransferCompleteView
from app.ui.transfer_interrupted_view import TransferInterruptedView
from app.ui.error_view import ErrorView
from app.ui.settings_dialog import SettingsDialog
from app.ui.widgets.status_bar import StatusBarWidget


class MainWindow(QMainWindow):
    """Application main window with QStackedWidget-based view routing."""

    def __init__(self, controller: TransferController, parent=None):
        super().__init__(parent)
        self._controller = controller

        # Track latest progress for interrupted view
        self._last_progress: TransferProgress | None = None
        self._current_file_name: str = ""

        self.setWindowTitle("Pied Piper")
        self.setMinimumSize(900, 620)
        self.resize(960, 660)

        # --- Central widget ---
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Header ---
        main_layout.addWidget(self._build_header())

        # --- Stacked views ---
        self._stack = QStackedWidget()
        self._stack.setObjectName("viewStack")
        main_layout.addWidget(self._stack, 1)

        # --- Status bar ---
        self._status_bar = StatusBarWidget()
        main_layout.addWidget(self._status_bar)

        # --- Create all views ---
        self._home_view = HomeView()
        self._send_view = SendView()
        self._transfer_code_view = TransferCodeView()
        self._receive_view = ReceiveView()
        self._confirmation_view = ReceiverConfirmationView()
        self._transfer_view = TransferView()
        self._complete_view = TransferCompleteView()
        self._interrupted_view = TransferInterruptedView()
        self._error_view = ErrorView()

        for view in [
            self._home_view,
            self._send_view,
            self._transfer_code_view,
            self._receive_view,
            self._confirmation_view,
            self._transfer_view,
            self._complete_view,
            self._interrupted_view,
            self._error_view,
        ]:
            self._stack.addWidget(view)

        # --- Connect view signals → controller/navigation ---
        self._home_view.send_clicked.connect(self._show_send)
        self._home_view.receive_clicked.connect(self._show_receive)

        self._send_view.back_clicked.connect(self._go_home)
        self._send_view.generate_code_clicked.connect(self._controller.send_file)

        self._transfer_code_view.cancel_clicked.connect(self._cancel_and_home)

        self._receive_view.back_clicked.connect(self._go_home)
        self._receive_view.connect_clicked.connect(self._controller.join_session)

        self._confirmation_view.accept_clicked.connect(self._controller.accept_transfer)
        self._confirmation_view.reject_clicked.connect(self._reject_and_home)

        self._transfer_view.cancel_clicked.connect(self._cancel_and_home)

        self._complete_view.done_clicked.connect(self._done_and_home)

        self._interrupted_view.resume_clicked.connect(self._controller.resume_transfer)
        self._interrupted_view.cancel_clicked.connect(self._cancel_and_home)

        self._error_view.retry_clicked.connect(self._go_home)
        self._error_view.cancel_clicked.connect(self._go_home)

        # --- Connect controller signals → view updates ---
        self._controller.state_changed.connect(self._on_state_changed)
        self._controller.progress_updated.connect(self._on_progress)
        self._controller.session_created.connect(self._on_session_created)
        self._controller.session_joined.connect(self._on_session_joined)
        self._controller.transfer_completed.connect(self._on_transfer_completed)
        self._controller.error_occurred.connect(self._on_error)

        # Start at home
        self._stack.setCurrentWidget(self._home_view)

    # --- Header ---

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("headerBar")
        header.setFixedHeight(72)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 0, 24, 0)

        # Title + subtitle
        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        app_title = QLabel("Pied Piper")
        app_title.setObjectName("appTitle")

        app_subtitle = QLabel("Secure peer-to-peer file transfer")
        app_subtitle.setObjectName("appSubtitle")

        title_col.addWidget(app_title)
        title_col.addWidget(app_subtitle)

        layout.addLayout(title_col)
        layout.addStretch()

        # Settings button
        settings_btn = QPushButton("⚙")
        settings_btn.setObjectName("settingsButton")
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setFixedSize(36, 36)
        settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(settings_btn)

        return header

    # --- Navigation helpers ---

    def _show_send(self) -> None:
        self._send_view.reset()
        self._stack.setCurrentWidget(self._send_view)

    def _show_receive(self) -> None:
        self._receive_view.reset()
        self._stack.setCurrentWidget(self._receive_view)

    def _go_home(self) -> None:
        self._controller.reset()
        self._last_progress = None
        self._current_file_name = ""
        self._stack.setCurrentWidget(self._home_view)

    def _cancel_and_home(self) -> None:
        self._controller.cancel_transfer()
        self._go_home()

    def _reject_and_home(self) -> None:
        self._controller.reject_transfer()
        self._go_home()

    def _done_and_home(self) -> None:
        self._controller.reset()
        self._last_progress = None
        self._stack.setCurrentWidget(self._home_view)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()

    # --- Controller signal handlers ---

    def _on_state_changed(self, state: TransferState) -> None:
        """Route state changes to views, accounting for is_sender role."""
        self._status_bar.update_state(state)
        is_sender = self._controller.is_sender

        if state == TransferState.IDLE:
            self._stack.setCurrentWidget(self._home_view)

        elif state == TransferState.CREATING_SESSION:
            # Stay on send view (shows loading feel)
            pass

        elif state == TransferState.WAITING_FOR_RECEIVER:
            # Sender: show transfer code view
            self._transfer_code_view.set_status("Waiting for receiver...")
            self._stack.setCurrentWidget(self._transfer_code_view)

        elif state == TransferState.RECEIVER_CONNECTED:
            # Sender: update status on transfer code view
            if is_sender:
                self._transfer_code_view.set_status("Receiver connected — waiting for acceptance...")

        elif state == TransferState.AWAITING_ACCEPTANCE:
            if is_sender:
                # Sender: still on transfer code view, waiting
                self._transfer_code_view.set_status("Waiting for receiver to accept...")
            else:
                # Receiver: show confirmation view
                self._stack.setCurrentWidget(self._confirmation_view)

        elif state == TransferState.CONNECTING:
            self._transfer_view.set_connection_status("● Connecting...")
            self._stack.setCurrentWidget(self._transfer_view)

        elif state == TransferState.TRANSFERRING:
            label = "● Sending..." if is_sender else "● Receiving..."
            self._transfer_view.set_connection_status(label)
            self._stack.setCurrentWidget(self._transfer_view)

        elif state == TransferState.INTERRUPTED:
            self._show_interrupted()

        elif state == TransferState.RESUMING:
            self._transfer_view.set_connection_status("● Resuming...")
            self._stack.setCurrentWidget(self._transfer_view)

        elif state == TransferState.COMPLETED:
            # Handled by _on_transfer_completed
            pass

        elif state == TransferState.FAILED:
            # Handled by _on_error
            pass

        elif state == TransferState.CANCELLED:
            self._go_home()

    def _on_session_created(self, session: TransferSession) -> None:
        """Sender: display the transfer code from the backend."""
        self._current_file_name = session.file_name
        self._transfer_code_view.set_code(session.transfer_code)
        self._transfer_view.set_file_name(session.file_name)

    def _on_session_joined(self, session: TransferSession) -> None:
        """Receiver: display incoming file info for acceptance."""
        self._current_file_name = session.file_name
        self._confirmation_view.set_file_info(session.file_name, session.file_size)
        self._transfer_view.set_file_name(session.file_name)

    def _on_progress(self, progress: TransferProgress) -> None:
        """Forward progress to transfer view; keep latest for interrupted."""
        self._last_progress = progress
        self._transfer_view.update_progress(progress)

    def _on_transfer_completed(self, result: TransferResult) -> None:
        self._complete_view.set_result(result, self._current_file_name)
        self._stack.setCurrentWidget(self._complete_view)

    def _on_error(self, title: str, message: str) -> None:
        self._error_view.set_error(title, message)
        self._stack.setCurrentWidget(self._error_view)

    def _show_interrupted(self) -> None:
        session = self._controller.current_session
        bt = self._last_progress.bytes_transferred if self._last_progress else 0
        tb = self._last_progress.total_bytes if self._last_progress else 0
        fn = session.file_name if session else self._current_file_name
        self._interrupted_view.set_info(fn, bt, tb)
        self._stack.setCurrentWidget(self._interrupted_view)
