"""
src/pdf_research_pipeline/parsers/ocrmypdf_parser.py

OCRmyPDF parser adapter.

Decision: OCRmyPDF creates a searchable PDF (OCR text layer added to scanned images)
then extracts the text layer with PyMuPDF. This two-step approach is useful for
image_only and searchable_image PDFs.

Per prompt.md section 13: Use OCR pipelines for scanned PDFs with deskew/clean options.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from pdf_research_pipeline.parsers.base import BaseParser, PageResult, ParseResult


class OCRmyPDFParser(BaseParser):
    """
    Creates a searchable PDF with OCRmyPDF then extracts via PyMuPDF.

    Config keys:
      lang (str)    — OCR language code (default: eng)
      deskew (bool) — Apply deskew pre-processing
      clean (bool)  — Apply unpaper cleaning
      optimize (int) — Optimization level 0-3
    """

    parser_name = "ocrmypdf"
    library_name = "ocrmypdf"

    def _parse_impl(self, path: Path) -> ParseResult:
        import ocrmypdf  # type: ignore[import]
        import fitz  # type: ignore[import]

        lang: str = self.config.get("lang", "eng")
        deskew: bool = self.config.get("deskew", False)
        clean: bool = self.config.get("clean", False)
        optimize: int = self.config.get("optimize", 0)
        max_pages: int | None = self.config.get("max_pages", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            # If max_pages set, truncate input to first N pages
            if max_pages:
                import fitz as _fitz

                src_doc = _fitz.open(str(path))
                if src_doc.page_count > max_pages:
                    truncated = Path(tmpdir) / "truncated.pdf"
                    writer = _fitz.open()
                    writer.insert_pdf(src_doc, from_page=0, to_page=max_pages - 1)
                    writer.save(str(truncated))
                    writer.close()
                    path = truncated
                src_doc.close()

            out_path = Path(tmpdir) / "ocr_output.pdf"

            # Run OCRmyPDF — adds a hidden text layer to the PDF
            result_code = ocrmypdf.ocr(
                str(path),
                str(out_path),
                language=lang,
                deskew=deskew,
                clean=clean,
                optimize=optimize,
                force_ocr=True,
                progress_bar=False,
            )

            if result_code != 0:
                raise RuntimeError(f"OCRmyPDF returned exit code {result_code}")

            # Now extract text from the OCR'd PDF using PyMuPDF
            doc = fitz.open(str(out_path))
            pages: list[PageResult] = []
            all_text_parts: list[str] = []

            for page_num, page in enumerate(doc):
                raw_text = page.get_text("text") or ""
                all_text_parts.append(raw_text)
                pages.append(
                    PageResult(
                        page_number=page_num + 1,
                        raw_text=raw_text,
                        width=page.rect.width,
                        height=page.rect.height,
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
