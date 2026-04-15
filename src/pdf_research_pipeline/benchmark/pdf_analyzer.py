"""
src/pdf_research_pipeline/benchmark/pdf_analyzer.py

Structural analysis of each PDF using PyMuPDF and pdfplumber.
Extracts factual metadata: page count, image count, table count, word count,
paragraph count, font diversity, layout complexity, etc.

Used as input context for the OpenAI scoring agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PDFMetadata:
    """Structural facts about a single PDF."""

    pdf_id: str
    pdf_type: str
    local_path: str
    file_size_kb: float = 0.0

    # Content counts
    page_count: int = 0
    image_count: int = 0
    table_count: int = 0
    word_count: int = 0
    char_count: int = 0
    paragraph_count: int = 0
    figure_count: int = 0  # images that look like figures (large)

    # Layout complexity
    font_count: int = 0  # number of distinct fonts
    multi_column: bool = False  # any page with 2+ text columns
    has_equations: bool = False  # detected math/formula patterns
    has_headers: bool = False  # heading text blocks detected
    has_footnotes: bool = False  # small text at page bottom

    # Per-page breakdown
    pages: list[dict[str, Any]] = field(default_factory=list)

    # Text sample (first 500 chars from first page via PyMuPDF)
    text_sample: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k != "pages"}
        d["pages_summary"] = self.pages[:3]  # first 3 pages for prompt brevity
        return d


def analyze_pdf(pdf_id: str, pdf_type: str, local_path: str) -> PDFMetadata:
    """
    Run structural analysis on a single PDF.

    Uses PyMuPDF for text/image analysis and pdfplumber for tables.
    """
    meta = PDFMetadata(pdf_id=pdf_id, pdf_type=pdf_type, local_path=local_path)

    path = Path(local_path)
    if not path.exists():
        return meta

    meta.file_size_kb = round(path.stat().st_size / 1024, 1)

    _analyze_with_pymupdf(path, meta)
    _analyze_tables_pdfplumber(path, meta)

    return meta


def _analyze_with_pymupdf(path: Path, meta: PDFMetadata) -> None:
    try:
        import fitz  # type: ignore[import]
    except ImportError:
        return

    doc = fitz.open(str(path))
    meta.page_count = len(doc)

    all_text = []
    fonts_seen: set[str] = set()
    total_words = 0
    total_images = 0
    total_paragraphs = 0
    total_figures = 0
    equation_hits = 0
    header_hits = 0
    footnote_hits = 0
    multi_col_pages = 0

    # Simple column detection: if a page has blocks with x-origin clusters far apart
    _EQUATION_RE = re.compile(r"[∑∫∂∇≥≤±∞α-ωΑ-Ω]|\\frac|\\sum|\\int")
    _HEADING_RE = re.compile(r"^[A-Z][A-Z\s]{3,50}$|^\d+\.\s+[A-Z]", re.MULTILINE)

    for page_num, page in enumerate(doc):
        page_info: dict[str, Any] = {"page": page_num + 1}

        # ---- Text ----
        text = page.get_text("text") or ""
        all_text.append(text)
        words_on_page = len(text.split())
        total_words += words_on_page
        page_info["words"] = words_on_page

        # Paragraph count: count double-newlines as paragraph breaks
        paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        total_paragraphs += len(paras)
        page_info["paragraphs"] = len(paras)

        # Check for equations
        if _EQUATION_RE.search(text):
            equation_hits += 1

        # Check for headings
        if _HEADING_RE.search(text):
            header_hits += 1

        # Footnote heuristic: small text blocks near page bottom
        blocks = page.get_text(
            "blocks"
        )  # returns (x0,y0,x1,y1,text,block_no,block_type)
        page_height = page.rect.height
        small_bottom_blocks = [
            b for b in blocks if b[1] > page_height * 0.85 and len(b[4].strip()) > 10
        ]
        if small_bottom_blocks:
            footnote_hits += 1

        # Fonts
        font_data = page.get_fonts(full=True)
        page_info["fonts"] = len(font_data)
        for f in font_data:
            fonts_seen.add(f[3] or f[4] or "unknown")

        # ---- Images ----
        images = page.get_images(full=True)
        img_count = len(images)
        total_images += img_count
        page_info["images"] = img_count

        # Count large images as "figures" (> 10% page area)
        page_area = page.rect.width * page.rect.height
        for img_ref in images:
            xref = img_ref[0]
            try:
                img_rect = page.get_image_bbox(img_ref)
                img_area = img_rect.width * img_rect.height
                if img_area > page_area * 0.10:
                    total_figures += 1
            except Exception:
                pass

        # ---- Multi-column detection ----
        text_blocks = [b for b in blocks if b[6] == 0]  # block_type 0 = text
        if text_blocks:
            x_origins = [b[0] for b in text_blocks]
            x_range = max(x_origins) - min(x_origins)
            if x_range > page.rect.width * 0.3:
                multi_col_pages += 1

        meta.pages.append(page_info)

    doc.close()

    full_text = "\n".join(all_text)
    meta.word_count = total_words
    meta.char_count = len(full_text)
    meta.paragraph_count = total_paragraphs
    meta.image_count = total_images
    meta.figure_count = total_figures
    meta.font_count = len(fonts_seen)
    meta.multi_column = multi_col_pages > (meta.page_count // 3)
    meta.has_equations = equation_hits > 0
    meta.has_headers = header_hits > 0
    meta.has_footnotes = footnote_hits > 0
    meta.text_sample = full_text[:500].strip()


def _analyze_tables_pdfplumber(path: Path, meta: PDFMetadata) -> None:
    try:
        import pdfplumber  # type: ignore[import]
    except ImportError:
        return

    table_count = 0
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                try:
                    tables = page.find_tables()
                    table_count += len(tables)
                except Exception:
                    pass
    except Exception:
        pass

    meta.table_count = table_count
