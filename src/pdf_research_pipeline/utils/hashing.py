"""
src/pdf_research_pipeline/utils/hashing.py

SHA256 checksum utilities.

Decision: SHA256 is the standard for file integrity as required by
prompt.md sections 2 and 18. All file hashes are stored hex-encoded.
hashlib is in the Python stdlib — no extra dependency.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


BLOCK_SIZE = 65536  # 64 KB read blocks for memory-efficient hashing


def sha256_file(path: Path | str) -> str:
    """
    Compute the SHA256 checksum of a file.

    Returns the hex-encoded digest string.
    Reads the file in 64KB blocks to handle large PDFs without loading
    the entire file into memory.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(BLOCK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute SHA256 of raw bytes. Used for hashing string/JSON outputs."""
    return hashlib.sha256(data).hexdigest()


def sha256_string(text: str, encoding: str = "utf-8") -> str:
    """Compute SHA256 of a string."""
    return sha256_bytes(text.encode(encoding))
