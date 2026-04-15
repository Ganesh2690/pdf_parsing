"""
src/pdf_research_pipeline/parsers/pypdf_parser.py

pypdf parser adapter (formerly PyPDF2).

Decision: pypdf is included as a pure-baseline parser. It requires no
system-level dependencies and represents the simplest possible text
extraction path. Per prompt.md section 3: used for baseline comparison.
It is not expected to win benchmarks but establishes a floor for scoring.
"""

from __future__ import annotations

from pathlib import Path

from pdf_research_pipeline.parsers.base import BaseParser, PageResult, ParseResult


class PyPDFParser(BaseParser):
    """
    Baseline text extraction using pypdf.
    No coordinate output — text only.
    """

    parser_name = "pypdf"
    library_name = "pypdf"

    def _parse_impl(self, path: Path) -> ParseResult:
        from pypdf import PdfReader  # type: ignore[import]

        reader = PdfReader(str(path))
        pages: list[PageResult] = []
        all_text_parts: list[str] = []

        for page_num, page in enumerate(reader.pages):
            raw_text = page.extract_text() or ""
            all_text_parts.append(raw_text)
            pages.append(
                PageResult(
                    page_number=page_num + 1,
                    raw_text=raw_text,
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
            status="completed",
        )
