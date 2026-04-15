"""
src/pdf_research_pipeline/parsers/pdftext_parser.py

pdftext fast text extraction parser adapter.

Decision: pdftext (by VikParuchuri) is purpose-built for high-speed,
high-fidelity digital PDF text extraction using PDFium under the hood.
It preserves reading order, spans, and character-level positions without
requiring heavy ML inference — making it an excellent baseline alternative
to PyMuPDF for true-digital and complex-layout PDFs.

Per research.md: pdftext is the fastest CPU-based text extractor that also
preserves font information and character bounding boxes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pdf_research_pipeline.parsers.base import BaseParser, PageResult, ParseResult


class PDFTextParser(BaseParser):
    """
    High-speed text extraction using pdftext (PDFium-based).

    Extracts text with bounding boxes, font names, font sizes, and
    reading-order spans in a single pass. Suitable for any digitally
    created PDF where the text layer is embedded.

    Config keys:
      workers (int)       — parallel page workers (default: 1)
      flatten_pdf (bool)  — flatten form fields before extraction (default: False)
    """

    parser_name = "pdftext"
    library_name = "pdftext"

    def _parse_impl(self, path: Path) -> ParseResult:
        from pdftext.extraction import dictionary_output  # type: ignore[import]

        workers: int = self.config.get("workers", 1)
        flatten: bool = self.config.get("flatten_pdf", False)

        page_dicts: list[dict] = dictionary_output(
            str(path),
            workers=workers,
            flatten_pdf=flatten,
        )

        pages: list[PageResult] = []
        all_text_parts: list[str] = []

        for page_num, page_data in enumerate(page_dicts):
            blocks: list[dict] = []
            text_parts: list[str] = []

            # Structure: page → blocks → lines → spans
            # span bbox is [x0, y0, x1, y1] (list, not dict)
            for block in page_data.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        span_text: str = span.get("text", "") or ""
                        if not span_text.strip():
                            continue
                        text_parts.append(span_text)
                        bbox = span.get("bbox", [0, 0, 0, 0])
                        font_info = span.get("font", {}) or {}
                        blocks.append(
                            {
                                "type": "span",
                                "text": span_text,
                                "x": bbox[0] if len(bbox) > 0 else 0,
                                "y": bbox[1] if len(bbox) > 1 else 0,
                                "w": (bbox[2] - bbox[0]) if len(bbox) > 2 else 0,
                                "h": (bbox[3] - bbox[1]) if len(bbox) > 3 else 0,
                                "font": font_info.get("name", ""),
                                "size": font_info.get("size", 0),
                            }
                        )

            raw_text = "".join(text_parts)
            all_text_parts.append(raw_text)

            pages.append(
                PageResult(
                    page_number=page_num + 1,
                    raw_text=raw_text,
                    blocks=blocks,
                    width=float(page_data.get("width", 0)),
                    height=float(page_data.get("height", 0)),
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
