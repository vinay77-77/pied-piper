"""File transfer receiver implementation for Phase 5 foundational protocol."""

import asyncio
import hashlib
import logging
import time
from pathlib import Path
from typing import Callable, Optional

from backend.protocol.chunking import sanitize_filename, verify_chunk_integrity
from backend.protocol.framing import (
    ChunkAckMessage,
    FileAcceptMessage,
    FileOfferMessage,
    FileRejectMessage,
    TransferCompleteMessage,
    TransferErrorMessage,
    parse_control_message,
    unpack_chunk_frame,
)
from backend.transfer.sender import IntegrityError, TransferError, TransferSummary
from backend.transport.data_channels import DataChannelError, DataChannelManager

logger = logging.getLogger(__name__)


class FileReceiver:
    """Orchestrates receiving and verifying files streamed over WebRTC DataChannels."""

    def __init__(
        self,
        channels: DataChannelManager,
        output_dir: Path,
        progress_callback: Optional[Callable[[float, int, int], None]] = None,
    ) -> None:
        self.channels: DataChannelManager = channels
        self.output_dir: Path = Path(output_dir)
        self.progress_callback: Optional[Callable[[float, int, int], None]] = progress_callback

    async def receive(self, timeout: float = 60.0) -> TransferSummary:
        """Execute the complete file receive and verification workflow."""
        start_time = time.time()

        # 1. Await FileOfferMessage on control channel
        offer_str = await self.channels.receive_control(timeout=timeout)
        offer_msg = parse_control_message(offer_str)

        if not isinstance(offer_msg, FileOfferMessage):
            error_msg = f"Expected FileOfferMessage, received: {offer_msg}"
            self.channels.send_control(TransferErrorMessage(reason=error_msg).model_dump())
            raise TransferError(error_msg)

        # 2. Sanitize filename to prevent path traversal
        try:
            sanitized_name = sanitize_filename(offer_msg.filename)
        except ValueError as err:
            logger.error("Path traversal or invalid filename rejected: %s (%s)", offer_msg.filename, err)
            self.channels.send_control(
                FileRejectMessage(reason=f"Rejected unsafe filename: {err}").model_dump()
            )
            raise TransferError(f"Rejected unsafe filename: {offer_msg.filename}") from err

        self.output_dir.mkdir(parents=True, exist_ok=True)
        final_path = self.output_dir / sanitized_name
        part_path = self.output_dir / f".{sanitized_name}.part"

        logger.info(
            "Accepting file offer '%s' -> '%s' (%d bytes, %d chunks, expected SHA-256: %s)",
            offer_msg.filename,
            final_path,
            offer_msg.size,
            offer_msg.total_chunks,
            offer_msg.sha256,
        )

        # 3. Accept file offer
        self.channels.send_control(FileAcceptMessage().model_dump())

        # 4. Stream and verify chunks
        running_hasher = hashlib.sha256()
        bytes_received = 0
        chunks_received = 0

        try:
            with part_path.open("wb") as part_file:
                for expected_index in range(offer_msg.total_chunks):
                    # Receive binary chunk frame from data channel
                    frame_bytes = await self.channels.receive_data(timeout=timeout)
                    chunk_index, expected_digest, payload = unpack_chunk_frame(frame_bytes)

                    # Verify chunk index sequence
                    if chunk_index != expected_index:
                        err_reason = f"Chunk sequence error: expected {expected_index}, got {chunk_index}"
                        self.channels.send_control(TransferErrorMessage(reason=err_reason).model_dump())
                        raise TransferError(err_reason)

                    # Verify per-chunk SHA-256 integrity
                    if not verify_chunk_integrity(payload, expected_digest):
                        err_reason = f"Per-chunk integrity verification failed on chunk {chunk_index}"
                        logger.error(err_reason)
                        self.channels.send_control(TransferErrorMessage(reason=err_reason).model_dump())
                        raise IntegrityError(err_reason)

                    # Write verified chunk to part file and update running hash
                    part_file.write(payload)
                    running_hasher.update(payload)
                    bytes_received += len(payload)
                    chunks_received += 1

                    # Send ChunkAckMessage on control channel
                    ack = ChunkAckMessage(chunk_index=chunk_index)
                    self.channels.send_control(ack.model_dump())

                    percent = (chunks_received / offer_msg.total_chunks) * 100.0
                    if self.progress_callback:
                        self.progress_callback(percent, chunks_received, offer_msg.total_chunks)

            # 5. Await TransferCompleteMessage on control channel
            complete_str = await self.channels.receive_control(timeout=timeout)
            complete_msg = parse_control_message(complete_str)

            if not isinstance(complete_msg, TransferCompleteMessage):
                raise TransferError(f"Expected TransferCompleteMessage, got: {complete_msg}")

            computed_sha256 = running_hasher.hexdigest()

            # Verify whole-file integrity against offer and completion hash
            if computed_sha256.lower() != offer_msg.sha256.lower():
                raise IntegrityError(
                    f"Whole-file SHA-256 mismatch: expected {offer_msg.sha256}, computed {computed_sha256}"
                )
            if computed_sha256.lower() != complete_msg.sha256.lower():
                raise IntegrityError(
                    f"Whole-file SHA-256 mismatch with sender completion: expected {complete_msg.sha256}, computed {computed_sha256}"
                )

            # 6. Atomically promote temporary part file to final file
            part_path.replace(final_path)
            logger.info("Transfer verified! Promoted '%s' to '%s'", part_path.name, final_path)

        except Exception:
            if part_path.exists():
                part_path.unlink(missing_ok=True)
            raise

        duration = max(time.time() - start_time, 0.001)
        throughput_mbps = (bytes_received * 8) / (duration * 1_000_000)

        return TransferSummary(
            filename=sanitized_name,
            size_bytes=bytes_received,
            total_chunks=chunks_received,
            sha256=computed_sha256,
            duration_seconds=duration,
            throughput_mbps=throughput_mbps,
            filepath=final_path,
        )
