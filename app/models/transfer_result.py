"""Transfer result data model.

Designed to be extensible. The UI should handle missing/None fields
gracefully rather than assuming only a boolean integrity result.
The transfer engine may provide additional information in the future
(algorithm, hash, detailed error info, etc.).
"""

from dataclasses import dataclass


@dataclass
class TransferResult:
    """Result of a completed transfer, provided by the transfer engine."""

    success: bool
    total_bytes_transferred: int = 0

    # Integrity verification — separable from completion
    #integrity_verified: bool | None = None
    integrity_algorithm: str | None = None  # e.g. "SHA-256"
    file_hash: str | None = None

    # Error details (populated on failure)
    error_message: str | None = None
