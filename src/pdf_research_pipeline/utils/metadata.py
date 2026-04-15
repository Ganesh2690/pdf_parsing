"""
src/pdf_research_pipeline/utils/metadata.py

PDFMetadata pydantic model and catalog I/O.

Decision: Pydantic v2 model is used for PDFMetadata because it provides
built-in JSON serialisation, field validation, and documentation of all
fields required by prompt.md section 2.

Required catalog fields per prompt.md:
  source_name, source_url, local_path, detected_pdf_type, page_count,
  file_size_bytes, downloaded_at, checksum_sha256, detected_language,
  ocr_expected, layout_complexity
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PDFMetadata(BaseModel):
    """Schema for a single PDF entry in the catalog."""

    pdf_id: str = Field(
        ..., description="Unique identifier: SHA256 prefix + source name slug"
    )
    source_name: str = Field(
        ..., description="Human-readable source name, e.g. 'arxiv'"
    )
    source_url: str = Field(
        ..., description="Original URL the file was downloaded from"
    )
    local_path: str = Field(..., description="Absolute or relative local file path")
    detected_pdf_type: str = Field(
        ..., description="PDF type folder name, e.g. 'complex_layout_pdf'"
    )
    page_count: int = Field(default=0, description="Number of pages detected")
    file_size_bytes: int = Field(default=0, description="File size in bytes")
    downloaded_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp of download",
    )
    checksum_sha256: str = Field(
        default="", description="SHA256 hex digest of the file"
    )
    detected_language: str = Field(
        default="unknown", description="ISO 639-1 language code or 'unknown'"
    )
    ocr_expected: bool = Field(
        default=False, description="True if OCR is expected to be needed"
    )
    layout_complexity: str = Field(
        default="low",
        description="Estimated layout complexity: low | medium | high",
    )
    page_count_bucket: str = Field(
        default="unknown",
        description="Size bucket: very_small | short | medium | long | very_long | unknown",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict, description="Additional source-specific metadata"
    )


def page_count_bucket(n: int) -> str:
    """
    Classify a page count into the size bucket used by the pipeline.
    Matches the bucket definitions in pipeline.yaml.
    """
    if n <= 3:
        return "very_small"
    elif n <= 10:
        return "short"
    elif n <= 50:
        return "medium"
    elif n <= 200:
        return "long"
    else:
        return "very_long"


def append_to_catalog_jsonl(path: Path | str, entry: PDFMetadata) -> None:
    """Append one catalog entry to the JSONL catalog file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


def load_catalog_jsonl(path: Path | str) -> list[PDFMetadata]:
    """Load all catalog entries from a JSONL file."""
    p = Path(path)
    if not p.exists():
        return []
    entries = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(PDFMetadata.model_validate_json(line))
    return entries


_CATALOG_CSV_FIELDS = [
    "pdf_id",
    "source_name",
    "source_url",
    "local_path",
    "detected_pdf_type",
    "page_count",
    "file_size_bytes",
    "downloaded_at",
    "checksum_sha256",
    "detected_language",
    "ocr_expected",
    "layout_complexity",
    "page_count_bucket",
]


def write_catalog_csv(
    entries: list[dict[str, Any] | PDFMetadata], path: Path | str
) -> None:
    """Write catalog entries as a CSV file.

    Accepts either a list of PDFMetadata objects or plain dicts.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=_CATALOG_CSV_FIELDS, extrasaction="ignore"
        )
        writer.writeheader()
        for entry in entries:
            row = entry.model_dump() if isinstance(entry, PDFMetadata) else dict(entry)
            row.pop("extra", None)
            writer.writerow({k: row.get(k, "") for k in _CATALOG_CSV_FIELDS})


def load_catalog(path: Path | str) -> list[dict[str, Any]]:
    """Load all catalog entries from a JSONL file as plain dicts."""
    p = Path(path)
    if not p.exists():
        return []
    entries: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries
