"""Abstract interface for the transfer engine.

The real implementation will use aiortc + WebRTC DataChannels.
The UI and TransferController depend on this interface, never on
the concrete implementation.
"""

from abc import abstractmethod
from PySide6.QtCore import QObject, Signal

from app.models.transfer_context import TransferContext


class TransferEngineInterface(QObject):
    """Abstract base for all transfer engine implementations.

    Signals:
        state_changed: Emitted when the engine transitions to a new state.
        progress_changed: Emitted with updated progress during transfer.
        transfer_completed: Emitted with a TransferResult on completion.
        transfer_failed: Emitted with an error message on failure.
    """

    # Signals — all engines must emit these
    state_changed = Signal(object)       # TransferState
    progress_changed = Signal(object)    # TransferProgress
    transfer_completed = Signal(object)  # TransferResult
    transfer_failed = Signal(str)        # error message

    def __init__(self, parent=None):
        super().__init__(parent)

    @abstractmethod
    def start_send(self, file_path: str, session_id: str) -> None:
        """Begin sending a file for the given session."""
        ...

    @abstractmethod
    def start_receive(self, save_path: str, session_id: str) -> None:
        """Begin receiving a file for the given session."""
        ...

    @abstractmethod
    def cancel(self) -> None:
        """Cancel the current transfer."""
        ...

    @abstractmethod
    def resume(self, context: TransferContext) -> None:
        """Resume an interrupted transfer identified by its context.

        The TransferContext carries the session ID, file paths, role,
        and last known progress. The engine determines whether resumption
        is possible, which chunks were transferred, and how to
        re-establish the connection.

        The UI only calls this; it does not implement the resume algorithm.
        """
        ...
