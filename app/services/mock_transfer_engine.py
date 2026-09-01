"""Mock transfer engine for UI demonstration.

Uses QTimer to simulate transfer progress. All speed/timing values
are purely for demonstration — the real engine will provide actual
bytes_transferred, speed_bps, and ETA from the transfer layer.

This mock is clearly isolated so it can be replaced with the real
aiortc-based implementation without any UI changes.
"""

import random
from PySide6.QtCore import QTimer

from app.services.transfer_engine_interface import TransferEngineInterface
from app.models.transfer_state import TransferState
from app.models.transfer_progress import TransferProgress
from app.models.transfer_result import TransferResult
from app.models.transfer_context import TransferContext


class MockTransferEngine(TransferEngineInterface):
    """Simulates transfer progress for UI testing."""

    # --- Demo configuration ---
    SIMULATED_SPEED_BPS = 32 * 1024 * 1024  # 32 MB/s
    TICK_INTERVAL_MS = 100  # Progress update interval
    CONNECT_DELAY_MS = 1200  # Simulated connection setup time
    INTERRUPT_PROBABILITY = 0.08  # Chance of simulated interruption
    RESUME_DELAY_MS = 1500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(self.TICK_INTERVAL_MS)
        self._progress_timer.timeout.connect(self._on_tick)

        self._bytes_transferred = 0
        self._total_bytes = 0
        self._session_id: str | None = None
        self._interrupted = False
        self._interrupt_tested = False  # Only interrupt once per session

    def start_send(self, file_path: str, session_id: str) -> None:
        self._start_transfer(session_id)

    def start_receive(self, save_path: str, session_id: str) -> None:
        self._start_transfer(session_id)

    def cancel(self) -> None:
        self._progress_timer.stop()
        self.state_changed.emit(TransferState.CANCELLED)
        self._reset()

    def resume(self, context: TransferContext) -> None:
        """Resume from the interrupted point using the transfer context.

        The TransferContext carries the session ID, file info, and role.
        This mock only checks session_id for demonstration purposes.
        """
        if self._session_id != context.session_id:
            self.transfer_failed.emit("Cannot resume: session mismatch.")
            return
        self.state_changed.emit(TransferState.RESUMING)
        self._interrupted = False
        QTimer.singleShot(self.RESUME_DELAY_MS, self._begin_transfer)

    # --- Internal ---

    def _start_transfer(self, session_id: str) -> None:
        self._session_id = session_id
        self._interrupted = False
        self._interrupt_tested = False
        self.state_changed.emit(TransferState.CONNECTING)
        QTimer.singleShot(self.CONNECT_DELAY_MS, self._begin_transfer)

    def _begin_transfer(self) -> None:
        self.state_changed.emit(TransferState.TRANSFERRING)
        self._progress_timer.start()

    def _on_tick(self) -> None:
        # Simulate bytes transferred per tick
        chunk = int(self.SIMULATED_SPEED_BPS * (self.TICK_INTERVAL_MS / 1000))
        self._bytes_transferred = min(
            self._bytes_transferred + chunk, self._total_bytes
        )

        remaining = self._total_bytes - self._bytes_transferred
        speed = self.SIMULATED_SPEED_BPS
        eta = remaining / speed if speed > 0 else 0

        progress = TransferProgress(
            bytes_transferred=self._bytes_transferred,
            total_bytes=self._total_bytes,
            speed_bps=speed,
            eta_seconds=eta,
        )
        self.progress_changed.emit(progress)

        # Check for simulated interruption (once, between 30%-70%)
        pct = progress.percentage
        if (
            not self._interrupt_tested
            and 30 < pct < 70
            and random.random() < self.INTERRUPT_PROBABILITY
        ):
            self._interrupt_tested = True
            self._progress_timer.stop()
            self._interrupted = True
            self.state_changed.emit(TransferState.INTERRUPTED)
            return

        # Check for completion
        if self._bytes_transferred >= self._total_bytes:
            self._progress_timer.stop()
            result = TransferResult(
                success=True,
                total_bytes_transferred=self._total_bytes,
                integrity_verified=True,
                integrity_algorithm="SHA-256",
                file_hash="mock-hash-placeholder",
            )
            self.transfer_completed.emit(result)

    def set_file_size(self, total_bytes: int) -> None:
        """Set expected file size before starting. Called by controller."""
        self._total_bytes = total_bytes
        self._bytes_transferred = 0

    def _reset(self) -> None:
        self._bytes_transferred = 0
        self._total_bytes = 0
        self._session_id = None
        self._interrupted = False
        self._interrupt_tested = False
