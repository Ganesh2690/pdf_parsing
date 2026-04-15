"""
src/pdf_research_pipeline/parsers/pdfplumber_parser.py

pdfplumber parser adapter.

Decision: pdfplumber is used as a second baseline because it provides
strong visible reading order and table extraction. Research shows it
performs well on true digital PDFs and searchable image PDFs.

Per prompt.md section 13: pdfplumber is a recommended fallback alongside
PyMuPDF for digital PDFs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pdf_research_pipeline.parsers.base import BaseParser, PageResult, ParseResult


class PDFPlumberParser(BaseParser):
    """
    Extracts text, tables, and word positions using pdfplumber.

    Config keys:
      extract_text (bool)   — extract text per page
      extract_tables (bool) — extract tables using pdfplumber's table finder
      extract_words (bool)  — extract word-level data
      extract_chars (bool)  — extract character-level data (slow)
    """

    parser_name = "pdfplumber"
    library_name = "pdfplumber"

    def _parse_impl(self, path: Path) -> ParseResult:
        import pdfplumber  # type: ignore[import]

        extract_tables: bool = self.config.get("extract_tables", True)
        extract_words: bool = self.config.get("extract_words", True)
        extract_chars: bool = self.config.get("extract_chars", False)

        pages: list[PageResult] = []
        all_text_parts: list[str] = []
        all_tables: list[dict[str, Any]] = []

        with pdfplumber.open(str(path)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Text extraction
                raw_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                all_text_parts.append(raw_text)

                blocks: list[dict[str, Any]] = []

                # Word extraction
                if extract_words:
                    words = page.extract_words()
                    if words:
                        blocks.append({"type": "words", "words": words})

                # Char extraction (optional, expensive)
                if extract_chars:
                    chars = page.chars
                    if chars:
                        blocks.append(
                            {"type": "chars", "chars": chars[:500]}
                        )  # cap for storage

                # Table extraction
                page_tables: list[dict[str, Any]] = []
                if extract_tables:
                    try:
                        tables = page.extract_tables()
                        for t_idx, table in enumerate(tables):
                            entry: dict[str, Any] = {
                                "page_number": page_num + 1,
                                "table_index": t_idx,
                                "rows": table,
                            }
                            page_tables.append(entry)
                            all_tables.append(entry)
                    except Exception:
                        pass

                pages.append(
                    PageResult(
                        page_number=page_num + 1,
                        raw_text=raw_text,
                        blocks=blocks,
                        tables=page_tables,
                        width=float(page.width),
                        height=float(page.height),
                        is_empty=not bool(raw_text.strip()),
                    )
                )

        full_text = "\n\n".join(all_text_parts)
        return ParseResult(
            pdf_id="",
            pdf_type="",
            parser_name=self.parser_name,
            pages=pages,
            page_count_detected=len(pages),
            raw_text_full=full_text,
            tables=all_tables,
            status="completed",
        )
