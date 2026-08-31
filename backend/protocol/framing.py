"""Message framing and binary wire format definitions for file transfer."""

import hashlib
import json
import struct
from typing import Annotated, Any, Dict, Literal, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# Header format: uint32 (4 bytes chunk_index) + 32-byte SHA-256 raw digest
CHUNK_HEADER_FORMAT = "!I32s"
CHUNK_HEADER_SIZE = struct.calcsize(CHUNK_HEADER_FORMAT)  # 36 bytes


# -----------------------------------------------------------------------------
# Control Channel Messages (JSON)
# -----------------------------------------------------------------------------

class FileOfferMessage(BaseModel):
    """Sender offers a file for transfer to the receiver."""
    model_config = ConfigDict(extra="ignore")
    type: Literal["file_offer"] = "file_offer"
    filename: str = Field(..., min_length=1)
    size: int = Field(..., ge=0)
    sha256: str = Field(..., min_length=64, max_length=64)
    chunk_size: int = Field(default=16384, gt=0)
    total_chunks: int = Field(..., ge=0)


class FileAcceptMessage(BaseModel):
    """Receiver accepts the offered file."""
    model_config = ConfigDict(extra="ignore")
    type: Literal["file_accept"] = "file_accept"


class FileRejectMessage(BaseModel):
    """Receiver rejects the offered file (e.g. invalid filename or unauthorized)."""
    model_config = ConfigDict(extra="ignore")
    type: Literal["file_reject"] = "file_reject"
    reason: str


class ChunkAckMessage(BaseModel):
    """Receiver acknowledges receipt and integrity of a specific chunk."""
    model_config = ConfigDict(extra="ignore")
    type: Literal["chunk_ack"] = "chunk_ack"
    chunk_index: int = Field(..., ge=0)


class TransferCompleteMessage(BaseModel):
    """Sender indicates all chunks have been transmitted with final whole-file SHA-256."""
    model_config = ConfigDict(extra="ignore")
    type: Literal["transfer_complete"] = "transfer_complete"
    sha256: str = Field(..., min_length=64, max_length=64)


class TransferErrorMessage(BaseModel):
    """Notification of a fatal transfer or integrity error."""
    model_config = ConfigDict(extra="ignore")
    type: Literal["transfer_error"] = "transfer_error"
    reason: str


ControlMessage = Annotated[
    Union[
        FileOfferMessage,
        FileAcceptMessage,
        FileRejectMessage,
        ChunkAckMessage,
        TransferCompleteMessage,
        TransferErrorMessage,
    ],
    Field(discriminator="type"),
]

_control_message_adapter = TypeAdapter(ControlMessage)


def parse_control_message(data: Union[str, Dict[str, Any]]) -> ControlMessage:
    """Parse raw JSON string or dictionary into a validated ControlMessage."""
    if isinstance(data, str):
        parsed = json.loads(data)
    else:
        parsed = data
    return _control_message_adapter.validate_python(parsed)


# -----------------------------------------------------------------------------
# Data Channel Binary Chunk Framing
# -----------------------------------------------------------------------------

def pack_chunk_frame(chunk_index: int, payload: bytes) -> bytes:
    """Pack a chunk index and payload into a binary wire frame with a SHA-256 header.

    Wire layout:
    [ 4 bytes: uint32 chunk_index ][ 32 bytes: sha256_digest ][ N bytes: payload ]
    """
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if chunk_index < 0:
        raise ValueError("chunk_index must be non-negative")

    digest = hashlib.sha256(payload).digest()
    header = struct.pack(CHUNK_HEADER_FORMAT, chunk_index, digest)
    return header + payload


def unpack_chunk_frame(raw_frame: bytes) -> Tuple[int, bytes, bytes]:
    """Unpack a binary chunk frame into (chunk_index, expected_sha256_digest, payload).

    Raises ValueError if frame is shorter than header size.
    """
    if len(raw_frame) < CHUNK_HEADER_SIZE:
        raise ValueError(
            f"Frame size ({len(raw_frame)} bytes) is smaller than required header ({CHUNK_HEADER_SIZE} bytes)"
        )

    header_bytes = raw_frame[:CHUNK_HEADER_SIZE]
    payload = raw_frame[CHUNK_HEADER_SIZE:]
    chunk_index, expected_digest = struct.unpack(CHUNK_HEADER_FORMAT, header_bytes)

    return chunk_index, expected_digest, payload
