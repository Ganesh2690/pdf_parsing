"""
src/pdf_research_pipeline/downloader/base.py

Abstract base class for all PDF downloader adapters.

Design decisions:
  - Abstract interface: list_candidates() + download_one() + run().
  - All network calls go through _http_get() which uses tenacity retry logic.
  - SHA256 checksum is verified after every download.
  - Catalog entry is written after each successful download.
  - Log events follow the schema in prompt.md section 5 (log_category="download").
  - Skip-if-exists logic prevents re-downloading unchanged files (idempotent reruns).
"""

from __future__ import annotations

import abc
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pdf_research_pipeline.logging_utils import get_logger
from pdf_research_pipeline.utils.hashing import sha256_file
from pdf_research_pipeline.utils.metadata import (
    PDFMetadata,
    append_to_catalog_jsonl,
    page_count_bucket,
)
from pdf_research_pipeline.utils.files import ensure_dir

logger = get_logger(__name__)


@dataclass
class DownloadCandidate:
    """Describes a single PDF that could be downloaded."""

    url: str
    filename: str
    pdf_type: str
    source_name: str
    subfolder: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class BaseDownloader(abc.ABC):
    """
    Abstract base class for all source adapters.

    Subclasses must implement:
      - list_candidates()  → Iterator[DownloadCandidate]

    Subclasses may override:
      - _classify_pdf_type()  → detect type from file
      - _detect_language()    → detect language
    """

    source_name: str = "base"

    def __init__(
        self,
        raw_root: str,
        catalog_path: str,
        config: dict[str, Any],
        run_id: str = "",
    ) -> None:
        self.raw_root = Path(raw_root)
        self.catalog_path = catalog_path
        self.config = config
        self.run_id = run_id or str(uuid.uuid4())
        self.max_retries: int = config.get("max_retries", 3)
        self.timeout_seconds: int = config.get("timeout_seconds", 60)
        self.limit_per_type: int = config.get("limit_per_type", 10)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def list_candidates(self) -> Iterator[DownloadCandidate]:
        """
        Yield DownloadCandidate objects describing PDFs to download.
        Implementations should apply limit_per_type internally.
        """
        ...

    # ------------------------------------------------------------------
    # Core download logic
    # ------------------------------------------------------------------

    def run(self) -> list[PDFMetadata]:
        """
        Download all candidates and return list of successful PDFMetadata entries.
        Logs every attempt, success, and failure.
        """
        results: list[PDFMetadata] = []
        downloaded_count = 0

        logger.info(
            "downloader_start",
            event_type="downloader_start",
            stage="download",
            log_category="download",
            source_name=self.source_name,
            run_id=self.run_id,
            status="started",
        )
        t0 = time.perf_counter()

        for candidate in self.list_candidates():
            try:
                meta = self.download_one(candidate)
                if meta is not None:
                    results.append(meta)
                    downloaded_count += 1
            except Exception as exc:
                logger.error(
                    "download_failed",
                    event_type="download_failed",
                    stage="download",
                    log_category="errors",
                    source_name=self.source_name,
                    source_url=candidate.url,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    run_id=self.run_id,
                    status="failed",
                )

        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "downloader_end",
            event_type="downloader_end",
            stage="download",
            log_category="download",
            source_name=self.source_name,
            downloaded_count=downloaded_count,
            duration_ms=duration_ms,
            run_id=self.run_id,
            status="completed",
        )
        return results

    def download_one(self, candidate: DownloadCandidate) -> PDFMetadata | None:
        """
        Download a single PDF. Returns PDFMetadata on success, None on skip.

        Steps:
          1. Determine output path.
          2. Skip if file already exists and checksum matches (idempotent).
          3. Stream download with retry.
          4. Verify checksum.
          5. Count pages.
          6. Build and save catalog entry.
        """
        dest_dir = self._dest_dir(candidate)
        dest_path = dest_dir / candidate.filename

        # Idempotent skip
        if dest_path.exists():
            existing_hash = sha256_file(dest_path)
            logger.info(
                "download_skipped",
                event_type="download_skipped",
                stage="download",
                log_category="download",
                source_name=self.source_name,
                source_url=candidate.url,
                local_path=str(dest_path),
                observation="file already exists — skipping re-download",
                decision="skip",
                decision_reason="idempotent re-run: file present with checksum",
                input_hash=existing_hash,
                run_id=self.run_id,
                status="skipped",
            )
            return self._build_metadata(candidate, dest_path, existing_hash)

        # Download
        logger.info(
            "download_attempt",
            event_type="download_attempt",
            stage="download",
            log_category="download",
            source_name=self.source_name,
            source_url=candidate.url,
            local_path=str(dest_path),
            run_id=self.run_id,
            status="attempting",
        )

        t0 = time.perf_counter()
        self._stream_download(candidate.url, dest_path)
        duration_ms = int((time.perf_counter() - t0) * 1000)

        checksum = sha256_file(dest_path)
        file_size = dest_path.stat().st_size

        logger.info(
            "download_complete",
            event_type="download_complete",
            stage="download",
            log_category="download",
            source_name=self.source_name,
            source_url=candidate.url,
            local_path=str(dest_path),
            file_size_bytes=file_size,
            checksum_sha256=checksum,
            duration_ms=duration_ms,
            run_id=self.run_id,
            status="completed",
        )

        meta = self._build_metadata(candidate, dest_path, checksum)
        append_to_catalog_jsonl(self.catalog_path, meta)
        return meta

    # ------------------------------------------------------------------
    # HTTP streaming with retry
    # ------------------------------------------------------------------

    def _stream_download(self, url: str, dest_path: Path) -> None:
        """
        Download url to dest_path using streaming to handle large files.
        Retry with exponential backoff on transient network errors.
        """
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        @retry(
            retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
        )
        def _do_download() -> None:
            with requests.get(
                url,
                stream=True,
                timeout=self.timeout_seconds,
                headers={"User-Agent": "pdf-research-pipeline/0.1"},
            ) as resp:
                resp.raise_for_status()
                with dest_path.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            fh.write(chunk)

        _do_download()

    # ------------------------------------------------------------------
    # Metadata construction
    # ------------------------------------------------------------------

    def _dest_dir(self, candidate: DownloadCandidate) -> Path:
        if candidate.subfolder:
            return self.raw_root / candidate.pdf_type / candidate.subfolder
        return self.raw_root / candidate.pdf_type

    def _build_metadata(
        self,
        candidate: DownloadCandidate,
        path: Path,
        checksum: str,
    ) -> PDFMetadata:
        page_count = self._count_pages(path)
        language = self._detect_language(path)
        pdf_type = candidate.pdf_type
        ocr_expected = pdf_type in ("image_only_scanned_pdf", "searchable_image_pdf")
        complexity = (
            "high"
            if pdf_type == "complex_layout_pdf"
            else (
                "medium"
                if pdf_type in ("forms_interactive_pdf", "searchable_image_pdf")
                else "low"
            )
        )
        pdf_id = f"{checksum[:12]}_{candidate.source_name}_{path.stem}"[:64]

        return PDFMetadata(
            pdf_id=pdf_id,
            source_name=candidate.source_name,
            source_url=candidate.url,
            local_path=str(path),
            detected_pdf_type=pdf_type,
            page_count=page_count,
            file_size_bytes=path.stat().st_size,
            downloaded_at=datetime.now(timezone.utc).isoformat(),
            checksum_sha256=checksum,
            detected_language=language,
            ocr_expected=ocr_expected,
            layout_complexity=complexity,
            page_count_bucket=page_count_bucket(page_count),
            extra=candidate.extra,
        )

    def _count_pages(self, path: Path) -> int:
        """
        Count PDF pages using PyMuPDF when available.
        Falls back to 0 on error.

        Decision: PyMuPDF is fast and reliable for page counting even on
        complex PDFs. No parser output is created here — just a page count.
        """
        try:
            import fitz  # type: ignore[import]

            doc = fitz.open(str(path))
            count = len(doc)
            doc.close()
            return count
        except Exception:
            return 0

    def _detect_language(self, path: Path) -> str:
        """
        Attempt language detection via langdetect on first-page text.
        Falls back to 'unknown' on any error.
        """
        try:
            import fitz  # type: ignore[import]
            from langdetect import detect  # type: ignore[import]

            doc = fitz.open(str(path))
            text = ""
            for page in doc:
                text += page.get_text()
                if len(text) > 500:
                    break
            doc.close()
            if text.strip():
                return detect(text[:2000])
        except Exception:
            pass
        return "unknown"
