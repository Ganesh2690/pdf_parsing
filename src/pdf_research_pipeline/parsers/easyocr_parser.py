"""
src/pdf_research_pipeline/parsers/easyocr_parser.py

EasyOCR deep-learning parser adapter.

Decision: EasyOCR uses a CRAFT text detector + CRNN recogniser trained on
large corpora. It handles stylised text, mixed languages, and rotated text
better than Tesseract, making it a strong second OCR option.

Per research.md: Deep-learning OCR (EasyOCR) provides superior accuracy on
complex PDFs with unusual fonts/layouts compared to classical Tesseract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pdf_research_pipeline.parsers.base import BaseParser, PageResult, ParseResult


class EasyOCRParser(BaseParser):
    """
    OCR-based extraction using EasyOCR deep-learning model.

    Converts each PDF page to a PIL image via pdf2image, then runs
    EasyOCR to produce text with bounding boxes and confidence scores.

    Config keys:
      lang (list[str])  — EasyOCR language codes (default: ["en"])
      dpi (int)         — Rendering DPI for page images (default: 200)
      gpu (bool)        — Use GPU if available (default: False)
      paragraph (bool)  — Group words into paragraphs (default: True)
    """

    parser_name = "easyocr"
    library_name = "easyocr"

    # Cache reader across pages to avoid re-loading model weights each call
    _reader: Any = None
    _reader_langs: list[str] = []

    def _parse_impl(self, path: Path) -> ParseResult:
        import easyocr  # type: ignore[import]
        import fitz  # PyMuPDF — already installed, no poppler needed  # type: ignore[import]
        import numpy as np  # type: ignore[import]
        import io

        lang_cfg = self.config.get("lang", ["en"])
        if isinstance(lang_cfg, str):
            lang_cfg = [lang_cfg]
        langs: list[str] = lang_cfg

        dpi: int = self.config.get("dpi", 200)
        use_gpu: bool = self.config.get("gpu", False)
        paragraph: bool = self.config.get("paragraph", True)

        # Re-use cached reader only when language list is identical
        if EasyOCRParser._reader is None or EasyOCRParser._reader_langs != langs:
            EasyOCRParser._reader = easyocr.Reader(langs, gpu=use_gpu, verbose=False)
            EasyOCRParser._reader_langs = langs
        reader = EasyOCRParser._reader

        max_pages: int | None = self.config.get("max_pages", None)

        # Use PyMuPDF to render pages to numpy arrays (no poppler dependency)
        pdf_doc = fitz.open(str(path))
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        pages: list[PageResult] = []
        all_text_parts: list[str] = []

        page_limit = min(len(pdf_doc), max_pages) if max_pages else len(pdf_doc)
        for page_num in range(page_limit):
            fitz_page = pdf_doc[page_num]
            # Force RGB colorspace (n=3) to ensure a clean 3-channel array
            pix = fitz_page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, 3
            )

            # Use detail=1 WITHOUT paragraph grouping so we always get [bbox,text,conf]
            ocr_results: list[Any] = reader.readtext(
                img_array, detail=1, paragraph=False
            )

            text_parts: list[str] = []
            blocks: list[dict[str, Any]] = []
            confidences: list[float] = []

            for item in ocr_results:
                # detail=1, paragraph=False → always (bbox, text, conf)
                if len(item) < 2:
                    continue
                bbox = item[0]
                text = str(item[1]).strip()
                conf = float(item[2]) if len(item) > 2 else 1.0
                if not text:
                    continue
                text_parts.append(text)
                confidences.append(conf)
                # bbox is [[x1,y1],[x2,y1],[x2,y2],[x1,y2]] polygon
                try:
                    xs = [float(pt[0]) for pt in bbox]
                    ys = [float(pt[1]) for pt in bbox]
                except (TypeError, IndexError):
                    xs = [float(bbox[0]), float(bbox[2])]
                    ys = [float(bbox[1]), float(bbox[3])]
                blocks.append(
                    {
                        "type": "word",
                        "text": text,
                        "x": min(xs),
                        "y": min(ys),
                        "w": max(xs) - min(xs),
                        "h": max(ys) - min(ys),
                        "conf": round(conf, 4),
                    }
                )

            raw_text = "\n".join(text_parts)
            all_text_parts.append(raw_text)
            mean_conf = sum(confidences) / len(confidences) if confidences else None

            pages.append(
                PageResult(
                    page_number=page_num + 1,
                    raw_text=raw_text,
                    blocks=blocks,
                    width=float(fitz_page.rect.width),
                    height=float(fitz_page.rect.height),
                    ocr_confidence=mean_conf,
                    is_empty=not bool(raw_text.strip()),
                )
            )

        pdf_doc.close()
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
