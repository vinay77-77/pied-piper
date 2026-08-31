"""Tests for protocol message framing, binary chunk formatting, and chunk hashing."""

import hashlib
from pathlib import Path
import pytest

from backend.protocol.chunking import (
    FileChunkReader,
    compute_file_metadata,
    sanitize_filename,
    verify_chunk_integrity,
)
from backend.protocol.framing import (
    ChunkAckMessage,
    FileAcceptMessage,
    FileOfferMessage,
    FileRejectMessage,
    TransferCompleteMessage,
    TransferErrorMessage,
    pack_chunk_frame,
    parse_control_message,
    unpack_chunk_frame,
)


def test_control_messages_parsing():
    """Verify parsing and validation of all control channel message types."""
    # File offer
    offer_json = (
        '{"type": "file_offer", "filename": "test.txt", "size": 1024, '
        '"sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", '
        '"chunk_size": 16384, "total_chunks": 1}'
    )
    msg = parse_control_message(offer_json)
    assert isinstance(msg, FileOfferMessage)
    assert msg.filename == "test.txt"
    assert msg.size == 1024
    assert msg.total_chunks == 1

    # File accept
    msg = parse_control_message('{"type": "file_accept"}')
    assert isinstance(msg, FileAcceptMessage)

    # File reject
    msg = parse_control_message('{"type": "file_reject", "reason": "Disk full"}')
    assert isinstance(msg, FileRejectMessage)
    assert msg.reason == "Disk full"

    # Chunk ACK
    msg = parse_control_message('{"type": "chunk_ack", "chunk_index": 42}')
    assert isinstance(msg, ChunkAckMessage)
    assert msg.chunk_index == 42

    # Transfer complete
    msg = parse_control_message(
        '{"type": "transfer_complete", '
        '"sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}'
    )
    assert isinstance(msg, TransferCompleteMessage)

    # Transfer error
    msg = parse_control_message('{"type": "transfer_error", "reason": "Checksum mismatch"}')
    assert isinstance(msg, TransferErrorMessage)
    assert msg.reason == "Checksum mismatch"


def test_binary_chunk_frame_pack_and_unpack():
    """Verify binary chunk frame packing, header unpacking, and integrity verification."""
    payload = b"Hello, Pied Piper binary chunk payload!"
    chunk_index = 7

    packed = pack_chunk_frame(chunk_index, payload)
    # Header is 36 bytes (4 bytes uint32 index + 32 bytes SHA256 digest)
    assert len(packed) == 36 + len(payload)

    unpacked_index, expected_digest, unpacked_payload = unpack_chunk_frame(packed)
    assert unpacked_index == 7
    assert unpacked_payload == payload
    assert verify_chunk_integrity(unpacked_payload, expected_digest) is True

    # Test corrupted payload detection
    corrupted_payload = unpacked_payload + b"corrupt"
    assert verify_chunk_integrity(corrupted_payload, expected_digest) is False


def test_binary_chunk_frame_invalid_size():
    """Verify unpack_chunk_frame raises ValueError on truncated frames."""
    with pytest.raises(ValueError) as exc:
        unpack_chunk_frame(b"too_short")
    assert "smaller than required header" in str(exc.value)


def test_filename_sanitization():
    """Verify filename sanitization prevents directory traversal and forbidden characters."""
    assert sanitize_filename("document.pdf") == "document.pdf"
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\Windows\\System32\\cmd.exe") == "cmd.exe"
    assert sanitize_filename("/usr/local/bin/python") == "python"
    assert sanitize_filename("file:bad*name?.txt") == "file_bad_name_.txt"
    assert sanitize_filename(".hidden_file") == "hidden_file"

    with pytest.raises(ValueError):
        sanitize_filename("")
    with pytest.raises(ValueError):
        sanitize_filename("..")
    with pytest.raises(ValueError):
        sanitize_filename("/")


def test_chunk_reader_and_file_metadata(tmp_path: Path):
    """Verify FileChunkReader sequentially reads chunks and correctly calculates whole-file hash."""
    test_file = tmp_path / "test_sample.bin"
    content = b"0123456789ABCDEF" * 1024  # 16 KB file
    test_file.write_bytes(content)

    expected_sha256 = hashlib.sha256(content).hexdigest()
    size, total_chunks, computed_hash = compute_file_metadata(test_file, chunk_size=4096)
    assert size == len(content)
    assert total_chunks == 4
    assert computed_hash == expected_sha256

    reader = FileChunkReader(test_file, chunk_size=4096)
    chunks = list(reader.iter_chunks())
    assert len(chunks) == 4
    assert chunks[0].index == 0
    assert chunks[0].offset == 0
    assert chunks[1].index == 1
    assert chunks[1].offset == 4096
    assert reader.whole_file_sha256 == expected_sha256
