"""Transfer context for identifying and resuming interrupted transfers.

Provides enough information for the transfer engine to identify a specific
interrupted transfer and determine how to resume it. The UI never interprets
these fields — it passes the context to the engine as-is.
"""

from dataclasses import dataclass


@dataclass
class TransferContext:
    """Identifies a specific transfer for resume purposes.

    The transfer engine uses this to locate the interrupted transfer,
    determine which chunks were already sent, and re-establish the
    connection. The UI only creates and passes this; it does not
    implement the resume algorithm.
    """

    session_id: str
    file_name: str
    file_path: str | None = None  # Sender's local file path
    save_path: str | None = None  # Receiver's save location
    bytes_transferred: int = 0  # Last known progress
    total_bytes: int = 0
    is_sender: bool = True
