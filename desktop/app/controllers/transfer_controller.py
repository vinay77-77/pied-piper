"""
Transfer controller skeleton for Pied Piper Desktop.

Acts as the central coordination layer between the PySide6 UI and the future
underlying transfer engine / signaling backend client.
"""

import os
from typing import Optional, Set, Dict, Tuple
from PySide6.QtCore import QObject, Signal

from app.models.transfer_state import (
    FileInfo,
    TransferProgress,
    TransferSessionInfo,
    TransferState,
    validate_transfer_code,
)


class TransferController(QObject):
    """
    Central controller managing transfer state transitions, selected file metadata,
    and progress notifications for the desktop application.
    """

    # Qt Signals for UI bindings
    state_changed = Signal(object)      # Emits TransferState
    file_selected = Signal(object)      # Emits FileInfo
    progress_updated = Signal(object)   # Emits TransferProgress
    error_occurred = Signal(str)        # Emits error message
    session_reset = Signal()            # Emits on session reset
    code_validated = Signal(str)        # Emits validated transfer code

    # Explicit allowed state transitions
    _VALID_TRANSITIONS: Dict[TransferState, Set[TransferState]] = {
        TransferState.IDLE: {
            TransferState.SELECTING_FILE,
            TransferState.FILE_SELECTED,
            TransferState.CREATING_SESSION,
            TransferState.CONNECTING,
            TransferState.AWAITING_ACCEPTANCE,
            TransferState.FAILED,
        },
        TransferState.SELECTING_FILE: {
            TransferState.IDLE,
            TransferState.FILE_SELECTED,
            TransferState.FAILED,
            TransferState.CANCELLED,
        },
        TransferState.FILE_SELECTED: {
            TransferState.IDLE,
            TransferState.SELECTING_FILE,
            TransferState.CREATING_SESSION,
            TransferState.FAILED,
            TransferState.CANCELLED,
        },
        TransferState.CREATING_SESSION: {
            TransferState.WAITING_FOR_RECEIVER,
            TransferState.CONNECTING,
            TransferState.FAILED,
            TransferState.CANCELLED,
            TransferState.IDLE,
        },
        TransferState.WAITING_FOR_RECEIVER: {
            TransferState.RECEIVER_CONNECTED,
            TransferState.CONNECTING,
            TransferState.FAILED,
            TransferState.CANCELLED,
            TransferState.IDLE,
        },
        TransferState.RECEIVER_CONNECTED: {
            TransferState.AWAITING_ACCEPTANCE,
            TransferState.CONNECTING,
            TransferState.TRANSFERRING,
            TransferState.FAILED,
            TransferState.CANCELLED,
            TransferState.IDLE,
        },
        TransferState.AWAITING_ACCEPTANCE: {
            TransferState.CONNECTING,
            TransferState.TRANSFERRING,
            TransferState.FAILED,
            TransferState.CANCELLED,
            TransferState.IDLE,
        },
        TransferState.CONNECTING: {
            TransferState.TRANSFERRING,
            TransferState.FAILED,
            TransferState.CANCELLED,
            TransferState.IDLE,
        },
        TransferState.TRANSFERRING: {
            TransferState.COMPLETED,
            TransferState.INTERRUPTED,
            TransferState.FAILED,
            TransferState.CANCELLED,
        },
        TransferState.INTERRUPTED: {
            TransferState.RESUMING,
            TransferState.FAILED,
            TransferState.CANCELLED,
            TransferState.IDLE,
        },
        TransferState.RESUMING: {
            TransferState.TRANSFERRING,
            TransferState.INTERRUPTED,
            TransferState.FAILED,
            TransferState.CANCELLED,
        },
        TransferState.COMPLETED: {
            TransferState.IDLE,
        },
        TransferState.FAILED: {
            TransferState.IDLE,
        },
        TransferState.CANCELLED: {
            TransferState.IDLE,
        },
    }

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._session_info = TransferSessionInfo(state=TransferState.IDLE)

    @property
    def state(self) -> TransferState:
        """Current transfer state."""
        return self._session_info.state

    @property
    def session_info(self) -> TransferSessionInfo:
        """Current session metadata container."""
        return self._session_info

    @property
    def session_code(self) -> Optional[str]:
        """Current session / transfer code, if any."""
        return self._session_info.session_code

    @property
    def file_info(self) -> Optional[FileInfo]:
        """Selected file metadata, if any."""
        return self._session_info.file_info

    @property
    def progress(self) -> Optional[TransferProgress]:
        """Current transfer progress, if any."""
        return self._session_info.progress

    @property
    def error_message(self) -> Optional[str]:
        """Current error message, if any."""
        return self._session_info.error_message

    def can_transition_to(self, target_state: TransferState) -> bool:
        """Check if transition to target_state is allowed from current state."""
        if target_state == self._session_info.state:
            return True
        # IDLE and FAILED are always accessible for error recovery/reset
        if target_state in (TransferState.IDLE, TransferState.FAILED):
            return True
        allowed = self._VALID_TRANSITIONS.get(self._session_info.state, set())
        return target_state in allowed

    def set_state(self, new_state: TransferState) -> bool:
        """
        Transition to a new state if valid.
        Returns True if transition occurred, False otherwise.
        """
        if new_state == self._session_info.state:
            return True

        if not self.can_transition_to(new_state):
            return False

        self._session_info.state = new_state
        self.state_changed.emit(new_state)
        return True

    def select_file(
        self,
        file_path: str,
        file_size: int = 0,
        file_name: Optional[str] = None,
        sha256: Optional[str] = None,
    ) -> bool:
        """
        Set selected file information and transition to FILE_SELECTED state.
        """
        resolved_name = file_name or os.path.basename(file_path)
        info = FileInfo(
            file_path=file_path,
            file_name=resolved_name,
            file_size=file_size,
            sha256=sha256,
        )
        self._session_info.file_info = info
        self.file_selected.emit(info)
        return self.set_state(TransferState.FILE_SELECTED)

    def clear_file(self) -> None:
        """Clear the currently selected file and return to IDLE."""
        self._session_info.file_info = None
        self.set_state(TransferState.IDLE)

    def set_session_code(self, session_code: str, role: Optional[str] = None) -> None:
        """Record session coordination parameters."""
        self._session_info.session_code = session_code
        if role is not None:
            self._session_info.role = role

    def set_receiver_code(self, code: str) -> Tuple[bool, str]:
        """
        Locally validate and store the entered receiver transfer code.
        Does not transition to network states (e.g. RECEIVER_CONNECTED).
        Returns (is_valid, normalized_code_or_error_message).
        """
        is_valid, result = validate_transfer_code(code)
        if not is_valid:
            return False, result

        self._session_info.session_code = result
        self._session_info.role = "receiver"
        self.code_validated.emit(result)
        return True, result

    def clear_session_code(self) -> None:
        """Clear the registered session/transfer code and receiver role."""
        self._session_info.session_code = None
        self._session_info.role = None

    def update_progress(
        self,
        bytes_transferred: int,
        total_bytes: int,
        speed_bps: float = 0.0,
    ) -> None:
        """Update transfer progress metrics and emit notification."""
        percentage = (
            (bytes_transferred / total_bytes * 100.0) if total_bytes > 0 else 0.0
        )
        progress = TransferProgress(
            bytes_transferred=bytes_transferred,
            total_bytes=total_bytes,
            speed_bps=speed_bps,
            percentage=percentage,
        )
        self._session_info.progress = progress
        self.progress_updated.emit(progress)

    def set_error(self, message: str) -> None:
        """Record error message and transition state to FAILED."""
        self._session_info.error_message = message
        self.error_occurred.emit(message)
        self.set_state(TransferState.FAILED)

    def cancel(self) -> None:
        """Cancel the current transfer session."""
        if self._session_info.state not in (
            TransferState.IDLE,
            TransferState.COMPLETED,
            TransferState.FAILED,
            TransferState.CANCELLED,
        ):
            self.set_state(TransferState.CANCELLED)
        else:
            self.set_state(TransferState.IDLE)

    def reset(self) -> None:
        """Reset the controller to initial IDLE state and clear session data."""
        self._session_info = TransferSessionInfo(state=TransferState.IDLE)
        self.state_changed.emit(TransferState.IDLE)
        self.session_reset.emit()
