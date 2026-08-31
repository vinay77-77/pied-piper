"""File transfer sender implementation for Phase 5 foundational protocol."""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from backend.protocol.chunking import FileChunkReader, compute_file_metadata
from backend.protocol.framing import (
    ChunkAckMessage,
    FileAcceptMessage,
    FileOfferMessage,
    FileRejectMessage,
    TransferCompleteMessage,
    TransferErrorMessage,
    pack_chunk_frame,
    parse_control_message,
)
from backend.transport.data_channels import DataChannelError, DataChannelManager

logger = logging.getLogger(__name__)


class TransferError(Exception):
    """Exception raised when a file transfer protocol error occurs."""
    pass


class IntegrityError(TransferError):
    """Exception raised when a chunk or whole-file checksum mismatch is detected."""
    pass


@dataclass
class TransferSummary:
    """Summary metrics of a completed file transfer."""
    filename: str
    size_bytes: int
    total_chunks: int
    sha256: str
    duration_seconds: float
    throughput_mbps: float
    filepath: Optional[Path] = None


class FileSender:
    """Orchestrates single-file streaming over WebRTC DataChannels using stop-and-wait ACK."""

    def __init__(
        self,
        channels: DataChannelManager,
        filepath: Path,
        chunk_size: int = 16384,
        progress_callback: Optional[Callable[[float, int, int], None]] = None,
    ) -> None:
        self.channels: DataChannelManager = channels
        self.filepath: Path = Path(filepath)
        self.chunk_size: int = chunk_size
        self.progress_callback: Optional[Callable[[float, int, int], None]] = progress_callback

    async def send(self, timeout: float = 60.0) -> TransferSummary:
        """Execute the complete file transfer send workflow."""
        if not self.filepath.is_file():
            raise FileNotFoundError(f"File not found: {self.filepath}")

        start_time = time.time()
        file_size, total_chunks, file_sha256 = compute_file_metadata(self.filepath, self.chunk_size)
        logger.info(
            "Starting transfer offer for '%s' (%d bytes, %d chunks, SHA-256: %s)",
            self.filepath.name,
            file_size,
            total_chunks,
            file_sha256,
        )

        # 1. Dispatch FileOfferMessage on control channel
        offer = FileOfferMessage(
            filename=self.filepath.name,
            size=file_size,
            sha256=file_sha256,
            chunk_size=self.chunk_size,
            total_chunks=total_chunks,
        )
        self.channels.send_control(offer.model_dump())

        # 2. Await receiver acceptance on control channel
        resp_str = await self.channels.receive_control(timeout=timeout)
        resp_msg = parse_control_message(resp_str)

        if isinstance(resp_msg, FileRejectMessage):
            raise TransferError(f"Receiver rejected file offer: {resp_msg.reason}")
        if isinstance(resp_msg, TransferErrorMessage):
            raise TransferError(f"Transfer error from receiver: {resp_msg.reason}")
        if not isinstance(resp_msg, FileAcceptMessage):
            raise TransferError(f"Unexpected response to file offer: {resp_msg}")

        logger.info("File offer accepted by receiver. Streaming chunks...")

        # 3. Stream sequential chunks
        chunks_sent = 0
        if total_chunks > 0:
            reader = FileChunkReader(self.filepath, self.chunk_size)
            for chunk in reader.iter_chunks():
                # Pack binary frame [index + sha256 + payload]
                frame = pack_chunk_frame(chunk.index, chunk.data)
                self.channels.send_data(frame)

                # Await ACK on control channel
                ack_str = await self.channels.receive_control(timeout=timeout)
                ack_msg = parse_control_message(ack_str)

                if isinstance(ack_msg, TransferErrorMessage):
                    raise IntegrityError(f"Receiver reported error on chunk {chunk.index}: {ack_msg.reason}")
                if not isinstance(ack_msg, ChunkAckMessage):
                    raise TransferError(f"Expected ChunkAckMessage for chunk {chunk.index}, got: {ack_msg}")
                if ack_msg.chunk_index != chunk.index:
                    raise TransferError(
                        f"Chunk index mismatch in ACK: expected {chunk.index}, got {ack_msg.chunk_index}"
                    )

                chunks_sent += 1
                percent = (chunks_sent / total_chunks) * 100.0

                if self.progress_callback:
                    self.progress_callback(percent, chunks_sent, total_chunks)

        # 4. Dispatch TransferCompleteMessage
        complete_msg = TransferCompleteMessage(sha256=file_sha256)
        self.channels.send_control(complete_msg.model_dump())

        # Allow final control frame to flush across SCTP transport
        await asyncio.sleep(0.2)

        duration = max(time.time() - start_time, 0.001)
        throughput_mbps = (file_size * 8) / (duration * 1_000_000)

        logger.info(
            "Transfer of '%s' complete: %d bytes in %.2fs (%.2f Mbps)",
            self.filepath.name,
            file_size,
            duration,
            throughput_mbps,
        )

        return TransferSummary(
            filename=self.filepath.name,
            size_bytes=file_size,
            total_chunks=total_chunks,
            sha256=file_sha256,
            duration_seconds=duration,
            throughput_mbps=throughput_mbps,
            filepath=self.filepath,
        )
