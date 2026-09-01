"""Transfer session data model.

Represents a single transfer session between a sender and a receiver.
The transfer_code is treated as an opaque string — format is defined
by the backend, not assumed by the UI.
"""

from dataclasses import dataclass, field


@dataclass
class TransferSession:
    """Data for an active transfer session."""

    session_id: str
    transfer_code: str
    file_name: str
    file_size: int
    is_sender: bool
    error_message: str | None = None
