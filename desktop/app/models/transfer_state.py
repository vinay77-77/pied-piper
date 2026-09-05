"""
Transfer state models and data definitions for Pied Piper Desktop.
Defines the lifecycle states, transfer metadata structures, and code validation.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

# Transfer rendezvous room code specification (matching signaling specification)
TRANSFER_CODE_LENGTH = 6
TRANSFER_CODE_CHARS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


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


def format_file_size(size_bytes: int) -> str:
    """
    Format an integer byte count into a standard human-readable string.
    Examples: 0 B, 512 B, 1.2 KB, 4.7 MB, 1.8 GB
    """
    if size_bytes < 0:
        return "0 B"
    if size_bytes < 1024:
        return f"{size_bytes} B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(size_bytes)
    unit_index = 0
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    formatted = f"{size:.1f}"
    if formatted.endswith(".0"):
        formatted = formatted[:-2]
    return f"{formatted} {units[unit_index]}"


def validate_transfer_code(code: str) -> Tuple[bool, str]:
    """
    Locally validate a transfer code format against the documented 6-character specification.
    Returns (is_valid, normalized_code_or_error_message).
    """
    if not code or not code.strip():
        return False, "Transfer code cannot be empty."

    normalized = code.strip().upper()
    if len(normalized) != TRANSFER_CODE_LENGTH:
        return False, f"Transfer code must be exactly {TRANSFER_CODE_LENGTH} characters."

    invalid_chars = [c for c in normalized if c not in TRANSFER_CODE_CHARS]
    if invalid_chars:
        unique_invalid = sorted(list(set(invalid_chars)))
        return (
            False,
            f"Transfer code contains invalid characters: {', '.join(unique_invalid)}. "
            f"Ambiguous characters (0, O, 1, I, L) are not used.",
        )

    return True, normalized
