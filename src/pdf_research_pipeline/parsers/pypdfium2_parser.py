"""
src/pdf_research_pipeline/parsers/pypdfium2_parser.py

pypdfium2 direct parser adapter.

Decision: pypdfium2 provides Python bindings directly to the PDFium C++ library,
giving the most faithful low-level text extraction from PDFium. Unlike pdftext
(which wraps PDFium via a higher-level API), this parser uses PDFium's text-page
API directly — exposing per-character positions, font sizes, and search primitives.

Per prompt.md section 3: pypdfium2 is the direct PDFium binding and is used as
a precise cross-validation baseline alongside PyMuPDF and pdftext.

Library: pypdfium2>=4.20.0 (included in requirements.txt)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pdf_research_pipeline.parsers.base import BaseParser, PageResult, ParseResult


class PyPDFium2Parser(BaseParser):
    """
    Text extraction using pypdfium2 (direct PDFium Python bindings).

    Extracts text and per-character bounding boxes from each page using
    PDFium's FPDFTextPage API.

    Config keys:
      extract_chars (bool)  — include per-character bounding boxes (default: False,
                              expensive on large docs)
      extract_links (bool)  — include hyperlink targets (default: False)
    """

    parser_name = "pypdfium2"
    library_name = "pypdfium2"

    def _parse_impl(self, path: Path) -> ParseResult:
        import pypdfium2 as pdfium  # type: ignore[import]

        extract_chars: bool = self.config.get("extract_chars", False)
        extract_links: bool = self.config.get("extract_links", False)

        doc = pdfium.PdfDocument(str(path))
        pages: list[PageResult] = []
        all_text_parts: list[str] = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            width, height = page.get_width(), page.get_height()

            text_page = page.get_textpage()
            raw_text: str = text_page.get_text_bounded() or ""
            all_text_parts.append(raw_text)

            blocks: list[dict[str, Any]] = []

            if extract_chars and raw_text:
                # Extract per-character bounding boxes
                char_count = text_page.count_chars()
                chars: list[dict[str, Any]] = []
                for ci in range(min(char_count, 2000)):  # cap to avoid huge output
                    try:
                        rect = text_page.get_charbox(ci, loose=False)
                        chars.append(
                            {
                                "index": ci,
                                "char": text_page.get_text_bounded(
                                    left=rect.x0,
                                    bottom=rect.y0,
                                    right=rect.x1,
                                    top=rect.y1,
                                )[:1]
                                if rect
                                else "",
                                "x0": rect.x0,
                                "y0": rect.y0,
                                "x1": rect.x1,
                                "y1": rect.y1,
                            }
                        )
                    except Exception:
                        continue
                if chars:
                    blocks.append({"type": "chars", "chars": chars})

            if extract_links:
                # Extract hyperlinks from the page
                links: list[dict[str, Any]] = []
                try:
                    link_annot = page.get_links()
                    for lnk in link_annot:
                        links.append({"action": str(lnk)})
                except Exception:
                    pass
                if links:
                    blocks.append({"type": "links", "links": links})

            pages.append(
                PageResult(
                    page_number=page_num + 1,
                    raw_text=raw_text,
                    blocks=blocks,
                    width=float(width),
                    height=float(height),
                    is_empty=not bool(raw_text.strip()),
                )
            )

            text_page.close()

        doc.close()

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
