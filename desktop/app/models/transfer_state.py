"""
Transfer state models and data definitions for Pied Piper Desktop.
Defines the lifecycle states and transfer metadata structures.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TransferState(Enum):
    """Documented transfer lifecycle states for Pied Piper."""
    IDLE = "IDLE"
    SELECTING_FILE = "SELECTING_FILE"
    FILE_SELECTED = "FILE_SELECTED"
    CREATING_SESSION = "CREATING_SESSION"
    WAITING_FOR_RECEIVER = "WAITING_FOR_RECEIVER"
    RECEIVER_CONNECTED = "RECEIVER_CONNECTED"
    AWAITING_ACCEPTANCE = "AWAITING_ACCEPTANCE"
    CONNECTING = "CONNECTING"
    TRANSFERRING = "TRANSFERRING"
    INTERRUPTED = "INTERRUPTED"
    RESUMING = "RESUMING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class FileInfo:
    """Metadata representing a selected file for transfer."""
    file_path: str
    file_name: str
    file_size: int = 0
    sha256: Optional[str] = None


@dataclass
class TransferProgress:
    """Transfer progress information."""
    bytes_transferred: int = 0
    total_bytes: int = 0
    speed_bps: float = 0.0
    percentage: float = 0.0


@dataclass
class TransferSessionInfo:
    """State and metadata container for a transfer session."""
    state: TransferState = TransferState.IDLE
    role: Optional[str] = None  # "sender" | "receiver" | None
    session_code: Optional[str] = None
    file_info: Optional[FileInfo] = None
    progress: Optional[TransferProgress] = None
    error_message: Optional[str] = None
