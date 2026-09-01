"""Transfer progress data model.

All values (bytes_transferred, speed_bps, eta_seconds) are provided
by the transfer engine. The UI displays them as-is — it does not
compute speed or ETA on its own.
"""

from dataclasses import dataclass


@dataclass
class TransferProgress:
    """Progress snapshot provided by the transfer engine."""

    bytes_transferred: int
    total_bytes: int
    speed_bps: float  # Bytes per second, provided by engine
    eta_seconds: float  # Estimated time remaining, provided by engine

    @property
    def percentage(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(100.0, (self.bytes_transferred / self.total_bytes) * 100.0)
