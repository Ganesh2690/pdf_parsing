"""
src/pdf_research_pipeline/parsers/base.py

Abstract base class for all PDF parser adapters.

Design decisions:
  - All parsers return a ParseResult pydantic model (prompt.md section 4).
  - Output directory layout is deterministic: data/parsed/<type>/<id>/<parser>/
  - Duration, input_hash, and output_hash are computed and logged.
  - Parsers must NOT assume one approach is always best (prompt.md section 3).
  - Each parser saves: raw_text.txt, pages.json, blocks.json, tables/, summary.json
  - Per-page timeout is enforced to prevent hangs.
"""

from __future__ import annotations

import abc
import importlib.metadata
import time
import traceback as tb
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pdf_research_pipeline.logging_utils import get_logger
from pdf_research_pipeline.utils.files import parsed_dir, write_json, write_text
from pdf_research_pipeline.utils.hashing import sha256_file, sha256_string

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class PageResult(BaseModel):
    page_number: int
    raw_text: str = ""
    markdown: str = ""
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    width: float = 0.0
    height: float = 0.0
    ocr_confidence: float | None = None
    is_empty: bool = False


class ParseResult(BaseModel):
    """Full extraction result for one parser on one PDF."""

    pdf_id: str
    pdf_type: str
    parser_name: str
    library_version: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    pages: list[PageResult] = Field(default_factory=list)
    page_count_detected: int = 0
    raw_text_full: str = ""
    tables: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int = 0
    input_hash: str = ""
    output_hash: str = ""
    status: str = "completed"
    error_message: str = ""
    traceback_str: str = ""


# ---------------------------------------------------------------------------
# Base parser
# ---------------------------------------------------------------------------


class BaseParser(abc.ABC):
    """
    Abstract base for all parser adapters.

    Subclasses must implement:
      - _parse_impl(path, config) → ParseResult

    The run() method handles timing, hashing, logging, and file I/O.
    """

    parser_name: str = "base"
    library_name: str = "base"

    def __init__(self, parsed_root: str, config: dict[str, Any]) -> None:
        self.parsed_root = parsed_root
        self.config = config

    @abc.abstractmethod
    def _parse_impl(self, path: Path) -> ParseResult:
        """
        Core extraction logic. Must be implemented by each parser adapter.
        Should not write files — that is handled by run().
        """
        ...

    def run(
        self,
        path: Path,
        pdf_id: str,
        pdf_type: str,
        run_id: str = "",
    ) -> ParseResult:
        """
        Parse the PDF at `path` and save all outputs.

        Steps:
          1. Log start event.
          2. Compute input hash.
          3. Call _parse_impl().
          4. Save outputs.
          5. Compute output hash.
          6. Log end event with duration and hashes.
        """
        library_version = self._get_library_version()

        # Compute input hash — if the file does not exist, catch it early so
        # the error propagates through the standard result path below.
        try:
            input_hash = sha256_file(path)
        except (FileNotFoundError, OSError) as exc:
            result = ParseResult(
                pdf_id=pdf_id,
                pdf_type=pdf_type,
                parser_name=self.parser_name,
                library_version=library_version,
                config=self.config,
                status="failed",
                error_message=str(exc),
                traceback_str=tb.format_exc(),
            )
            result.output_hash = sha256_string("")
            return result

        input_hash = sha256_file(path)

        logger.info(
            "extraction_start",
            event_type="extraction_start",
            stage="extraction",
            log_category="extraction",
            pdf_id=pdf_id,
            pdf_type=pdf_type,
            parser_name=self.parser_name,
            library_version=library_version,
            local_path=str(path),
            input_hash=input_hash,
            run_id=run_id,
            status="started",
        )

        t0 = time.perf_counter()
        result = ParseResult(
            pdf_id=pdf_id,
            pdf_type=pdf_type,
            parser_name=self.parser_name,
            library_version=library_version,
            config=self.config,
            input_hash=input_hash,
        )

        try:
            result = self._parse_impl(path)
            result.pdf_id = pdf_id
            result.pdf_type = pdf_type
            result.input_hash = input_hash
            result.library_version = library_version
            result.config = self.config
            result.status = "completed"
        except Exception as exc:
            result.status = "failed"
            result.error_message = str(exc)
            result.traceback_str = tb.format_exc()
            logger.error(
                "extraction_error",
                event_type="extraction_error",
                stage="extraction",
                log_category="errors",
                pdf_id=pdf_id,
                pdf_type=pdf_type,
                parser_name=self.parser_name,
                error_type=type(exc).__name__,
                error_message=str(exc),
                traceback=result.traceback_str,
                run_id=run_id,
                status="failed",
            )

        result.duration_ms = int((time.perf_counter() - t0) * 1000)

        # Save outputs
        if result.status == "completed":
            self._save_outputs(result, pdf_id, pdf_type)

        result.output_hash = sha256_string(result.raw_text_full)

        logger.info(
            "extraction_end",
            event_type="extraction_end",
            stage="extraction",
            log_category="extraction",
            pdf_id=pdf_id,
            pdf_type=pdf_type,
            parser_name=self.parser_name,
            library_version=library_version,
            page_count_detected=result.page_count_detected,
            text_length=len(result.raw_text_full),
            table_count=len(result.tables),
            duration_ms=result.duration_ms,
            input_hash=input_hash,
            output_hash=result.output_hash,
            run_id=run_id,
            status=result.status,
        )

        return result

    def _save_outputs(self, result: ParseResult, pdf_id: str, pdf_type: str) -> None:
        """
        Save all extraction outputs to the canonical directory layout.

        Layout (per prompt.md section 4):
          data/parsed/<pdf_type>/<pdf_id>/<parser_name>/
            raw_text.txt
            pages.json
            blocks.json
            tables/
            summary.json
        """
        out_dir = parsed_dir(self.parsed_root, pdf_type, pdf_id, self.parser_name)

        # raw_text.txt
        write_text(out_dir / "raw_text.txt", result.raw_text_full)

        # pages.json
        pages_data = [p.model_dump() for p in result.pages]
        write_json(out_dir / "pages.json", pages_data)

        # blocks.json — aggregated from all pages
        all_blocks = []
        for p in result.pages:
            for block in p.blocks:
                block["page_number"] = p.page_number
                all_blocks.append(block)
        write_json(out_dir / "blocks.json", all_blocks)

        # tables/
        if result.tables:
            tables_dir = out_dir / "tables"
            tables_dir.mkdir(parents=True, exist_ok=True)
            for i, table in enumerate(result.tables):
                write_json(tables_dir / f"table_{i:03d}.json", table)

        # summary.json
        summary = {
            "pdf_id": result.pdf_id,
            "pdf_type": result.pdf_type,
            "parser_name": result.parser_name,
            "library_version": result.library_version,
            "page_count_detected": result.page_count_detected,
            "text_length": len(result.raw_text_full),
            "table_count": len(result.tables),
            "duration_ms": result.duration_ms,
            "input_hash": result.input_hash,
            "output_hash": result.output_hash,
            "status": result.status,
        }
        write_json(out_dir / "summary.json", summary)

    def _get_library_version(self) -> str:
        """Get the installed version of the backing library."""
        try:
            return importlib.metadata.version(self.library_name)
        except Exception:
            return "unknown"
