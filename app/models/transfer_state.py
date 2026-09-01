"""Transfer state enum representing session/transfer lifecycle states.

These are engine-level states representing meaningful lifecycle transitions.
UI-only interactions (e.g. opening a file picker) are NOT represented here.
"""

from enum import Enum


class TransferState(Enum):
    """States in the transfer session lifecycle.

    The UI uses these to determine which view to display.
    The transfer engine and backend client emit these as state changes.
    """

    IDLE = "idle"
    CREATING_SESSION = "creating_session"
    WAITING_FOR_RECEIVER = "waiting_for_receiver"
    RECEIVER_CONNECTED = "receiver_connected"
    AWAITING_ACCEPTANCE = "awaiting_acceptance"
    CONNECTING = "connecting"
    TRANSFERRING = "transferring"
    INTERRUPTED = "interrupted"
    RESUMING = "resuming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
