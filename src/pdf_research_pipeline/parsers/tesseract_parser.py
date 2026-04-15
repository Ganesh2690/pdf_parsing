"""
src/pdf_research_pipeline/parsers/tesseract_parser.py

Tesseract OCR parser adapter.

Uses PyMuPDF to render pages (no poppler dependency) then pytesseract for OCR.
Automatically searches common Windows/Linux installation paths for the binary.

Config keys:
  lang (str)          — Tesseract language code (default: eng)
  dpi (int)           — Rendering DPI for page images (default: 300)
  psm (int)           — Page segmentation mode (default: 3 = auto)
  oem (int)           — OCR engine mode (default: 3 = LSTM)
  tesseract_cmd (str) — Override path to tesseract binary
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pdf_research_pipeline.parsers.base import BaseParser, PageResult, ParseResult

_TESSERACT_SEARCH_PATHS = [
    r"C:\Users\ganeshg\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\tools\tesseract\tesseract.exe",
    r"C:\ProgramData\chocolatey\bin\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
]


def _find_tesseract_cmd(override: str | None = None) -> str | None:
    """Return first valid tesseract binary path, or None if not found."""
    if override:
        return override if Path(override).exists() else None
    for p in _TESSERACT_SEARCH_PATHS:
        if Path(p).exists():
            return p
    try:
        import subprocess

        result = subprocess.run(["where", "tesseract"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0]
    except Exception:
        pass
    try:
        import subprocess

        result = subprocess.run(["which", "tesseract"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


class TesseractParser(BaseParser):
    """
    OCR-based extraction using Tesseract via pytesseract + PyMuPDF rendering.
    No poppler/pdf2image dependency — pages are rendered with fitz (PyMuPDF).

    Config keys:
      lang (str)          — Tesseract language code (default: eng)
      dpi (int)           — Rendering DPI for page images (default: 300)
      psm (int)           — Page segmentation mode (default: 3 = auto)
      oem (int)           — OCR engine mode (default: 3 = LSTM)
      tesseract_cmd (str) — Override path to tesseract binary
    """

    parser_name = "tesseract"
    library_name = "pytesseract"

    def _parse_impl(self, path: Path) -> ParseResult:
        import pytesseract  # type: ignore[import]
        import fitz  # PyMuPDF  # type: ignore[import]
        import numpy as np  # type: ignore[import]
        from PIL import Image  # type: ignore[import]

        lang: str = self.config.get("lang", "eng")
        dpi: int = self.config.get("dpi", 300)
        psm: int = self.config.get("psm", 3)
        oem: int = self.config.get("oem", 3)
        cmd_override: str | None = self.config.get("tesseract_cmd", None)

        # Locate tesseract binary
        tess_cmd = _find_tesseract_cmd(cmd_override)
        if not tess_cmd:
            raise FileNotFoundError(
                "Tesseract binary not found. Install from https://github.com/UB-Mannheim/tesseract "
                "and ensure it is on PATH, or set tesseract_cmd in parsers.yaml."
            )
        pytesseract.pytesseract.tesseract_cmd = tess_cmd

        custom_config = f"--oem {oem} --psm {psm}"

        max_pages: int | None = self.config.get("max_pages", None)

        # Render pages with PyMuPDF (no poppler needed)
        pdf_doc = fitz.open(str(path))
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        pages: list[PageResult] = []
        all_text_parts: list[str] = []

        page_limit = min(len(pdf_doc), max_pages) if max_pages else len(pdf_doc)
        for page_num in range(page_limit):
            fitz_page = pdf_doc[page_num]
            # Render to RGB pixmap
            pix = fitz_page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, 3
            )
            img = Image.fromarray(img_array)

            # OCR with confidence data
            ocr_data: dict[str, Any] = pytesseract.image_to_data(
                img,
                lang=lang,
                config=custom_config,
                output_type=pytesseract.Output.DICT,
            )

            # Extract text
            raw_text = pytesseract.image_to_string(img, lang=lang, config=custom_config)
            all_text_parts.append(raw_text)

            # Compute mean OCR confidence (exclude -1 confidence values)
            confs = [c for c in ocr_data.get("conf", []) if c != -1]
            mean_conf = sum(confs) / len(confs) if confs else None

            # Build word-level blocks with coordinates
            blocks: list[dict[str, Any]] = []
            n_boxes = len(ocr_data.get("text", []))
            for i in range(n_boxes):
                word_text = ocr_data["text"][i]
                if not word_text.strip():
                    continue
                blocks.append(
                    {
                        "type": "word",
                        "text": word_text,
                        "x": ocr_data["left"][i],
                        "y": ocr_data["top"][i],
                        "w": ocr_data["width"][i],
                        "h": ocr_data["height"][i],
                        "conf": ocr_data["conf"][i],
                    }
                )

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
