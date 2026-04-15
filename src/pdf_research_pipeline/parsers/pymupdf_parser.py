"""
src/pdf_research_pipeline/parsers/pymupdf_parser.py

PyMuPDF (fitz) parser adapter.

Decision: PyMuPDF is used as the primary baseline parser because it is
fast, reliable, and widely used for text extraction on digital and complex
PDFs. It provides word-level bounding boxes and block-level structure.

Per prompt.md section 13: Use PyMuPDF for general digital PDFs as the
default starting point. Its coordinate-rich block output is also useful
for layout analysis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pdf_research_pipeline.parsers.base import BaseParser, PageResult, ParseResult


class PyMuPDFParser(BaseParser):
    """
    Extracts text, blocks, and optionally images using PyMuPDF (fitz).

    Config keys:
      extract_text (bool)    — extract text per page
      extract_images (bool)  — extract images per page
      extract_blocks (bool)  — extract block-level coordinates
      extract_words (bool)   — extract word-level coordinates
      dpi (int)              — DPI for image rendering
    """

    parser_name = "pymupdf"
    library_name = "pymupdf"

    def _parse_impl(self, path: Path) -> ParseResult:
        import fitz  # type: ignore[import]

        doc = fitz.open(str(path))
        pages: list[PageResult] = []
        all_text_parts: list[str] = []

        extract_blocks: bool = self.config.get("extract_blocks", True)
        extract_words: bool = self.config.get("extract_words", True)

        for page_num, page in enumerate(doc):
            width = page.rect.width
            height = page.rect.height

            # Text extraction
            raw_text = page.get_text("text") or ""
            all_text_parts.append(raw_text)

            # Block extraction (includes bounding boxes)
            blocks: list[dict[str, Any]] = []
            if extract_blocks:
                for block in page.get_text("blocks"):
                    # block = (x0, y0, x1, y1, text, block_no, block_type)
                    blocks.append(
                        {
                            "x0": block[0],
                            "y0": block[1],
                            "x1": block[2],
                            "y1": block[3],
                            "text": block[4],
                            "block_no": block[5],
                            "block_type": block[6],  # 0=text, 1=image
                        }
                    )

            # Word extraction (finer granularity)
            words: list[dict[str, Any]] = []
            if extract_words:
                for word in page.get_text("words"):
                    # word = (x0, y0, x1, y1, word, block_no, line_no, word_no)
                    words.append(
                        {
                            "x0": word[0],
                            "y0": word[1],
                            "x1": word[2],
                            "y1": word[3],
                            "word": word[4],
                            "block_no": word[5],
                            "line_no": word[6],
                            "word_no": word[7],
                        }
                    )
                if words:
                    # Attach words as a sub-key in the block list context
                    blocks.append({"type": "words", "words": words})

            pages.append(
                PageResult(
                    page_number=page_num + 1,
                    raw_text=raw_text,
                    blocks=blocks,
                    width=width,
                    height=height,
                    is_empty=not bool(raw_text.strip()),
                )
            )

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
