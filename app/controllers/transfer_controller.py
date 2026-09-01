"""Transfer controller — central orchestrator between UI and services.

The controller depends on BackendClientInterface and TransferEngineInterface
(injected at construction). It never imports concrete implementations.
It tracks the session role (is_sender) and routes state transitions
appropriately so the UI can display role-appropriate views.
"""

import os

from PySide6.QtCore import QObject, Signal

from app.models.transfer_state import TransferState
from app.models.transfer_session import TransferSession
from app.models.transfer_progress import TransferProgress
from app.models.transfer_result import TransferResult
from app.models.transfer_context import TransferContext
from app.services.transfer_engine_interface import TransferEngineInterface
from app.services.backend_client_interface import BackendClientInterface
from app.config.settings import AppSettings


class TransferController(QObject):
    """Orchestrates communication between the UI and service layers.

    Signals emitted to the UI:
        state_changed(TransferState): Current engine/session state.
        progress_updated(TransferProgress): Transfer progress snapshot.
        session_created(TransferSession): A new session was created (sender).
        session_joined(TransferSession): Joined an existing session (receiver).
        transfer_completed(TransferResult): Transfer finished.
        error_occurred(str, str): (title, message) for user-friendly errors.
    """

    state_changed = Signal(object)
    progress_updated = Signal(object)
    session_created = Signal(object)
    session_joined = Signal(object)
    transfer_completed = Signal(object)
    error_occurred = Signal(str, str)

    def __init__(
        self,
        backend_client: BackendClientInterface,
        transfer_engine: TransferEngineInterface,
        parent=None,
    ):
        super().__init__(parent)
        self._backend = backend_client
        self._engine = transfer_engine
        self._settings = AppSettings()

        self._current_session: TransferSession | None = None
        self._current_state = TransferState.IDLE
        self._file_path: str | None = None
        self._last_progress: TransferProgress | None = None

        # --- Wire backend signals ---
        self._backend.session_created.connect(self._on_session_created)
        self._backend.session_joined.connect(self._on_session_joined)
        self._backend.receiver_connected.connect(self._on_receiver_connected)
        self._backend.transfer_accepted.connect(self._on_transfer_accepted)
        self._backend.transfer_rejected.connect(self._on_transfer_rejected)
        self._backend.error_occurred.connect(self._on_backend_error)

        # --- Wire engine signals ---
        self._engine.state_changed.connect(self._on_engine_state_changed)
        self._engine.progress_changed.connect(self._on_engine_progress)
        self._engine.transfer_completed.connect(self._on_transfer_completed)
        self._engine.transfer_failed.connect(self._on_transfer_failed)

    # --- Public properties ---

    @property
    def is_sender(self) -> bool:
        return self._current_session.is_sender if self._current_session else False

    @property
    def current_session(self) -> TransferSession | None:
        return self._current_session

    @property
    def current_state(self) -> TransferState:
        return self._current_state

    @property
    def file_path(self) -> str | None:
        return self._file_path

    # --- Public actions (called by UI) ---

    def send_file(self, file_path: str) -> None:
        """Initiate sending: create a session via the backend."""
        self._file_path = file_path
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        # Tell engine the expected file size (for progress tracking)
        if hasattr(self._engine, "set_file_size"):
            self._engine.set_file_size(file_size)

        self._set_state(TransferState.CREATING_SESSION)
        self._backend.create_session(file_name, file_size)

    def join_session(self, transfer_code: str) -> None:
        """Join a session using a transfer code (receiver side)."""
        self._backend.join_session(transfer_code)

    def accept_transfer(self) -> None:
        """Receiver accepts the incoming transfer."""
        if self._current_session:
            self._backend.accept_transfer(self._current_session.session_id)

    def reject_transfer(self) -> None:
        """Receiver rejects the incoming transfer."""
        if self._current_session:
            self._backend.reject_transfer(self._current_session.session_id)
            self._set_state(TransferState.CANCELLED)

    def cancel_transfer(self) -> None:
        """Cancel the current transfer from either side."""
        self._engine.cancel()
        if self._current_session:
            self._backend.cancel_session(self._current_session.session_id)
        self._set_state(TransferState.CANCELLED)

    def resume_transfer(self) -> None:
        """Resume an interrupted transfer.

        Builds a TransferContext from the current session state
        and passes it to the engine. The engine determines whether
        resumption is possible.
        """
        if (
            self._current_session
            and self._current_state == TransferState.INTERRUPTED
        ):
            context = TransferContext(
                session_id=self._current_session.session_id,
                file_name=self._current_session.file_name,
                file_path=self._file_path,
                save_path=None,  # Would be set for receiver
                bytes_transferred=(
                    self._last_progress.bytes_transferred
                    if self._last_progress else 0
                ),
                total_bytes=self._current_session.file_size,
                is_sender=self._current_session.is_sender,
            )
            self._engine.resume(context)

    def reset(self) -> None:
        """Return to idle state, clearing all session data."""
        self._current_session = None
        self._file_path = None
        self._last_progress = None
        self._set_state(TransferState.IDLE)

    # --- Internal state management ---

    def _set_state(self, state: TransferState) -> None:
        self._current_state = state
        self.state_changed.emit(state)

    # --- Backend signal handlers ---

    def _on_session_created(self, session: TransferSession) -> None:
        self._current_session = session
        self.session_created.emit(session)
        self._set_state(TransferState.WAITING_FOR_RECEIVER)

    def _on_session_joined(self, session: TransferSession) -> None:
        self._current_session = session

        # Tell engine the file size for progress tracking
        if hasattr(self._engine, "set_file_size"):
            self._engine.set_file_size(session.file_size)

        self.session_joined.emit(session)
        self._set_state(TransferState.AWAITING_ACCEPTANCE)

    def _on_receiver_connected(self) -> None:
        self._set_state(TransferState.RECEIVER_CONNECTED)

    def _on_transfer_accepted(self) -> None:
        """Transfer accepted — start the engine on both sides."""
        if not self._current_session:
            return

        self._set_state(TransferState.CONNECTING)

        if self._current_session.is_sender and self._file_path:
            self._engine.start_send(
                self._file_path, self._current_session.session_id
            )
        elif not self._current_session.is_sender:
            save_dir = self._settings.download_directory
            save_path = os.path.join(
                save_dir, self._current_session.file_name
            )
            self._engine.start_receive(
                save_path, self._current_session.session_id
            )

    def _on_transfer_rejected(self) -> None:
        self.error_occurred.emit(
            "Transfer Rejected",
            "The receiver rejected the file transfer.",
        )
        self._set_state(TransferState.CANCELLED)

    def _on_backend_error(self, message: str) -> None:
        self.error_occurred.emit("Connection Error", message)
        self._set_state(TransferState.FAILED)

    # --- Engine signal handlers ---

    def _on_engine_state_changed(self, state: TransferState) -> None:
        self._set_state(state)

    def _on_engine_progress(self, progress: TransferProgress) -> None:
        self._last_progress = progress
        self.progress_updated.emit(progress)

    def _on_transfer_completed(self, result: TransferResult) -> None:
        self._set_state(TransferState.COMPLETED)
        self.transfer_completed.emit(result)

    def _on_transfer_failed(self, message: str) -> None:
        self.error_occurred.emit("Transfer Failed", message)
        self._set_state(TransferState.FAILED)
