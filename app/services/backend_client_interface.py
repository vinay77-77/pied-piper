"""Abstract interface for the backend client.

The real implementation will use FastAPI + WebSocket for signaling.
The UI and TransferController depend on this interface, never on
the concrete implementation.

The transfer_code is treated as an opaque string — format, entropy,
expiration, validation, and collision handling are all backend concerns.
"""

from abc import abstractmethod
from PySide6.QtCore import QObject, Signal


class BackendClientInterface(QObject):
    """Abstract base for all backend client implementations.

    Signals:
        session_created: Emitted with TransferSession after creating a session.
        session_joined: Emitted with TransferSession after joining a session.
        receiver_connected: Emitted when the receiver connects to the sender's session.
        transfer_accepted: Emitted when the receiver accepts the transfer.
        transfer_rejected: Emitted when the receiver rejects the transfer.
        error_occurred: Emitted with a user-friendly error message.
    """

    session_created = Signal(object)   # TransferSession
    session_joined = Signal(object)    # TransferSession
    receiver_connected = Signal()
    transfer_accepted = Signal()
    transfer_rejected = Signal()
    error_occurred = Signal(str)       # user-friendly error message

    def __init__(self, parent=None):
        super().__init__(parent)

    @abstractmethod
    def create_session(self, file_name: str, file_size: int) -> None:
        """Create a new transfer session (sender side)."""
        ...

    @abstractmethod
    def join_session(self, transfer_code: str) -> None:
        """Join an existing session using a transfer code (receiver side)."""
        ...

    @abstractmethod
    def accept_transfer(self, session_id: str) -> None:
        """Accept an incoming transfer (receiver side)."""
        ...

    @abstractmethod
    def reject_transfer(self, session_id: str) -> None:
        """Reject an incoming transfer (receiver side)."""
        ...

    @abstractmethod
    def cancel_session(self, session_id: str) -> None:
        """Cancel / leave a session."""
        ...
