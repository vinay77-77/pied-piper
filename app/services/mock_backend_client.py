"""Mock backend client for UI demonstration.

Simulates session creation, joining, and signaling using QTimer delays.
The transfer code generated here is mock-specific — the real backend
will define the actual code format, entropy, expiration, and validation.
"""

import random
import string
import uuid

from PySide6.QtCore import QTimer

from app.services.backend_client_interface import BackendClientInterface
from app.models.transfer_session import TransferSession


class MockBackendClient(BackendClientInterface):
    """Simulates backend signaling for UI testing."""

    RECEIVER_CONNECT_DELAY_MS = 3000
    ACCEPT_DELAY_MS = 0  # Receiver accepts manually; sender side auto-notified

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_session: TransferSession | None = None

    def create_session(self, file_name: str, file_size: int) -> None:
        """Simulate session creation (sender side)."""
        session = TransferSession(
            session_id=str(uuid.uuid4()),
            transfer_code=self._generate_mock_code(),
            file_name=file_name,
            file_size=file_size,
            is_sender=True,
        )
        self._current_session = session

        # Emit session created after brief delay (simulates network)
        QTimer.singleShot(400, lambda: self.session_created.emit(session))

        # Simulate receiver connecting after a longer delay
        QTimer.singleShot(
            self.RECEIVER_CONNECT_DELAY_MS,
            lambda: self.receiver_connected.emit(),
        )

        # Simulate receiver accepting the transfer shortly after connecting
        QTimer.singleShot(
            self.RECEIVER_CONNECT_DELAY_MS + 1500,
            lambda: self.transfer_accepted.emit(),
        )

    def join_session(self, transfer_code: str) -> None:
        """Simulate joining a session (receiver side)."""
        if not transfer_code or len(transfer_code.strip()) < 2:
            QTimer.singleShot(
                300,
                lambda: self.error_occurred.emit(
                    "Invalid transfer code. Please check and try again."
                ),
            )
            return

        # Simulate successful join
        session = TransferSession(
            session_id=str(uuid.uuid4()),
            transfer_code=transfer_code.strip(),
            file_name="example-file.zip",  # In real backend, this comes from the sender
            file_size=1_288_490_188,  # ~1.2 GB demo size
            is_sender=False,
        )
        self._current_session = session
        QTimer.singleShot(600, lambda: self.session_joined.emit(session))

    def accept_transfer(self, session_id: str) -> None:
        """Receiver accepted — notify both sides."""
        QTimer.singleShot(300, lambda: self.transfer_accepted.emit())

    def reject_transfer(self, session_id: str) -> None:
        """Receiver rejected the transfer."""
        QTimer.singleShot(200, lambda: self.transfer_rejected.emit())

    def cancel_session(self, session_id: str) -> None:
        """Cancel / leave a session."""
        self._current_session = None

    # --- Internal ---

    @staticmethod
    def _generate_mock_code() -> str:
        """Generate a mock transfer code. Format is mock-specific."""
        part1 = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        part2 = "".join(random.choices(string.ascii_uppercase + string.digits, k=2))
        return f"{part1}-{part2}"
