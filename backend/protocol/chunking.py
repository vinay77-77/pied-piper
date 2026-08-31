"""Chunk model, incremental reading, SHA-256 hashing, and filename sanitization."""

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Tuple, Union


@dataclass(frozen=True)
class Chunk:
    """Represents a discrete slice of a file with integrity digest."""
    index: int
    offset: int
    data: bytes
    sha256: str
    sha256_bytes: bytes


def sanitize_filename(filename: str) -> str:
    """Sanitize an untrusted filename to prevent path traversal attacks.

    Extracts base filename, removes path traversal elements, strips forbidden characters,
    and ensures safe filesystem storage across Linux, macOS, and Windows paths.
    """
    if not filename or not isinstance(filename, str):
        raise ValueError("Filename must be a non-empty string")

    # Remove null bytes
    cleaned = filename.replace("\0", "")

    # Normalize Windows backslashes to forward slashes for cross-platform basename extraction
    cleaned = cleaned.replace("\\", "/")

    # Extract base name (drops any leading directories or path components)
    cleaned = Path(cleaned).name

    # Remove leading dots to avoid hidden/special files like .bashrc or ..
    cleaned = cleaned.lstrip(".")

    # Strip dangerous characters (<>:"/\|?*)
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", cleaned)

    # Clean whitespace
    cleaned = cleaned.strip()

    if not cleaned or cleaned in (".", ".."):
        raise ValueError(f"Invalid or unsafe filename: {filename!r}")

    return cleaned


def compute_file_metadata(filepath: Path, chunk_size: int = 16384) -> Tuple[int, int, str]:
    """Compute file size, total number of chunks, and whole-file SHA-256 hash."""
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    file_size = path.stat().st_size
    if file_size == 0:
        return 0, 0, hashlib.sha256(b"").hexdigest()

    total_chunks = math.ceil(file_size / chunk_size)
    hasher = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk_data = f.read(chunk_size)
            if not chunk_data:
                break
            hasher.update(chunk_data)

    return file_size, total_chunks, hasher.hexdigest()


class FileChunkReader:
    """Incrementally reads a file in discrete chunks while computing running whole-file SHA-256."""

    def __init__(self, filepath: Path, chunk_size: int = 16384) -> None:
        self.filepath: Path = Path(filepath)
        self.chunk_size: int = chunk_size
        self.running_hasher = hashlib.sha256()
        self.bytes_read: int = 0
        self.chunks_read: int = 0

        if not self.filepath.is_file():
            raise FileNotFoundError(f"File not found: {self.filepath}")

    def iter_chunks(self) -> Iterator[Chunk]:
        """Yield sequential Chunk instances from the file."""
        with self.filepath.open("rb") as f:
            index = 0
            while True:
                offset = f.tell()
                data = f.read(self.chunk_size)
                if not data:
                    break

                self.running_hasher.update(data)
                self.bytes_read += len(data)
                self.chunks_read += 1

                chunk_hasher = hashlib.sha256(data)
                chunk_sha256 = chunk_hasher.hexdigest()
                chunk_sha256_bytes = chunk_hasher.digest()

                yield Chunk(
                    index=index,
                    offset=offset,
                    data=data,
                    sha256=chunk_sha256,
                    sha256_bytes=chunk_sha256_bytes,
                )
                index += 1

    @property
    def whole_file_sha256(self) -> str:
        """Return the running hex SHA-256 digest of all chunks read so far."""
        return self.running_hasher.hexdigest()


def verify_chunk_integrity(data: bytes, expected_digest: Union[str, bytes]) -> bool:
    """Verify that chunk data matches the expected SHA-256 digest (hex or raw bytes)."""
    computed = hashlib.sha256(data)
    if isinstance(expected_digest, bytes):
        return computed.digest() == expected_digest
    elif isinstance(expected_digest, str):
        return computed.hexdigest().lower() == expected_digest.lower()
    return False
