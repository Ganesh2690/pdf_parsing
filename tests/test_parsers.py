"""
tests/test_parsers.py

Comprehensive unit tests for all PDF parser adapters.

Covers:
  - ParseResult / PageResult model validation
  - PyMuPDF, pdfplumber, pypdf, pypdfium2, pdftext (digital baseline parsers)
  - Tesseract, EasyOCR, OCRmyPDF (OCR parsers)
  - Unstructured (layout-aware)
  - Camelot, Tabula (table extractors)
  - Marker (ML markdown, not installed -- skip gracefully)
  - Nougat (ML scientific, not installed -- skip gracefully)
  - Parser crash resilience (missing file -> ParseResult with error, not exception)
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

from pdf_research_pipeline.parsers.base import PageResult, ParseResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PARSED_ROOT = "data/parsed"


def _parser(cls, cfg=None, parsed_root=_PARSED_ROOT):
    return cls(parsed_root=parsed_root, config=cfg or {})


def _run(parser, path, pdf_id="test", pdf_type="true_digital_pdf"):
    return parser.run(path=path, pdf_id=pdf_id, pdf_type=pdf_type)


# ---------------------------------------------------------------------------
# Fixture: minimal valid PDF
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def minimal_pdf(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pdfs")
    pdf_path = tmp / "minimal.pdf"
    try:
        import fitz

        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), "Hello PDF extraction test.", fontsize=12)
        doc.save(str(pdf_path))
        doc.close()
    except ImportError:
        pdf_path.write_bytes(
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
            b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
            b"4 0 obj<</Length 44>>\nstream\n"
            b"BT /F1 12 Tf 72 700 Td (Hello world) Tj ET\nendstream\nendobj\n"
            b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
            b"xref\n0 6\n"
            b"0000000000 65535 f \n0000000009 00000 n \n"
            b"0000000058 00000 n \n0000000115 00000 n \n"
            b"0000000252 00000 n \n0000000350 00000 n \n"
            b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n430\n%%EOF"
        )
    return pdf_path


@pytest.fixture(scope="session")
def table_pdf(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pdfs")
    pdf_path = tmp / "table.pdf"
    try:
        import fitz

        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        rows, cols = 3, 3
        x0, y0, cw, rh = 72, 100, 100, 30
        for r in range(rows + 1):
            y = y0 + r * rh
            page.draw_line((x0, y), (x0 + cols * cw, y), color=(0, 0, 0), width=0.5)
        for c in range(cols + 1):
            x = x0 + c * cw
            page.draw_line((x, y0), (x, y0 + rows * rh), color=(0, 0, 0), width=0.5)
        for r in range(rows):
            for c in range(cols):
                page.insert_text(
                    (x0 + c * cw + 5, y0 + r * rh + 20), f"R{r}C{c}", fontsize=9
                )
        doc.save(str(pdf_path))
        doc.close()
    except ImportError:
        pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    return pdf_path


# ---------------------------------------------------------------------------
# ParseResult / PageResult models
# ---------------------------------------------------------------------------


def test_parse_result_requires_pdf_type():
    with pytest.raises(Exception):
        ParseResult(pdf_id="x", parser_name="test")


def test_parse_result_output_hash_field():
    digest = hashlib.sha256(b"Hello extraction").hexdigest()
    pr = ParseResult(
        pdf_id="x",
        pdf_type="true_digital_pdf",
        parser_name="pymupdf",
        raw_text_full="Hello extraction",
        pages=[],
        tables=[],
        page_count_detected=1,
        duration_ms=10,
        output_hash=digest,
    )
    assert len(pr.output_hash) == 64


def test_parse_result_empty_text_hash():
    digest = hashlib.sha256(b"").hexdigest()
    pr = ParseResult(
        pdf_id="empty",
        pdf_type="true_digital_pdf",
        parser_name="pymupdf",
        raw_text_full="",
        pages=[],
        tables=[],
        page_count_detected=0,
        duration_ms=0,
        output_hash=digest,
    )
    assert pr.output_hash == hashlib.sha256(b"").hexdigest()


def test_page_result_defaults():
    pg = PageResult(page_number=1)
    assert pg.raw_text == ""
    assert pg.is_empty is False
    assert pg.blocks == []


# ---------------------------------------------------------------------------
# PyMuPDF
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    importlib.util.find_spec("fitz") is None, reason="PyMuPDF not installed"
)
def test_pymupdf_parser_extracts_text(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.pymupdf_parser import PyMuPDFParser

    result = _run(
        _parser(PyMuPDFParser, parsed_root=str(tmp_path)), minimal_pdf, "pymupdf_test"
    )
    assert result.page_count_detected >= 1
    assert len(result.raw_text_full) > 0
    assert result.status == "completed"
    assert result.error_message == ""


@pytest.mark.skipif(
    importlib.util.find_spec("fitz") is None, reason="PyMuPDF not installed"
)
def test_pymupdf_parser_has_blocks(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.pymupdf_parser import PyMuPDFParser

    result = _run(
        _parser(PyMuPDFParser, {"extract_blocks": True}, parsed_root=str(tmp_path)),
        minimal_pdf,
        "pymupdf_blocks",
    )
    assert any(len(p.blocks) > 0 for p in result.pages)


@pytest.mark.skipif(
    importlib.util.find_spec("fitz") is None, reason="PyMuPDF not installed"
)
def test_pymupdf_missing_file_returns_error(tmp_path):
    from pdf_research_pipeline.parsers.pymupdf_parser import PyMuPDFParser

    result = _run(
        _parser(PyMuPDFParser, parsed_root=str(tmp_path)),
        tmp_path / "nonexistent.pdf",
        "missing",
    )
    assert result.status == "failed"
    assert result.error_message != ""


# ---------------------------------------------------------------------------
# pdfplumber
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    importlib.util.find_spec("pdfplumber") is None, reason="pdfplumber not installed"
)
def test_pdfplumber_parser_runs(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.pdfplumber_parser import PDFPlumberParser

    result = _run(
        _parser(PDFPlumberParser, parsed_root=str(tmp_path)),
        minimal_pdf,
        "pdfplumber_test",
    )
    assert result.page_count_detected >= 1
    assert result.status == "completed"
    assert result.error_message == ""


@pytest.mark.skipif(
    importlib.util.find_spec("pdfplumber") is None, reason="pdfplumber not installed"
)
def test_pdfplumber_extracts_text(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.pdfplumber_parser import PDFPlumberParser

    result = _run(
        _parser(PDFPlumberParser, {"extract_text": True}, parsed_root=str(tmp_path)),
        minimal_pdf,
        "pdfplumber_txt",
    )
    assert len(result.raw_text_full) > 0


# ---------------------------------------------------------------------------
# pypdf
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    importlib.util.find_spec("pypdf") is None, reason="pypdf not installed"
)
def test_pypdf_parser_runs(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.pypdf_parser import PyPDFParser

    result = _run(
        _parser(PyPDFParser, parsed_root=str(tmp_path)), minimal_pdf, "pypdf_test"
    )
    assert result.page_count_detected >= 1
    assert result.status == "completed"
    assert result.error_message == ""


@pytest.mark.skipif(
    importlib.util.find_spec("pypdf") is None, reason="pypdf not installed"
)
def test_pypdf_extracts_text(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.pypdf_parser import PyPDFParser

    result = _run(
        _parser(PyPDFParser, parsed_root=str(tmp_path)), minimal_pdf, "pypdf_txt"
    )
    assert len(result.raw_text_full) > 0


# ---------------------------------------------------------------------------
# pypdfium2
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    importlib.util.find_spec("pypdfium2") is None, reason="pypdfium2 not installed"
)
def test_pypdfium2_parser_runs(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.pypdfium2_parser import PyPDFium2Parser

    result = _run(
        _parser(PyPDFium2Parser, parsed_root=str(tmp_path)),
        minimal_pdf,
        "pypdfium2_test",
    )
    assert result.page_count_detected >= 1
    assert result.status == "completed"
    assert result.error_message == ""


@pytest.mark.skipif(
    importlib.util.find_spec("pypdfium2") is None, reason="pypdfium2 not installed"
)
def test_pypdfium2_extracts_text(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.pypdfium2_parser import PyPDFium2Parser

    result = _run(
        _parser(PyPDFium2Parser, parsed_root=str(tmp_path)),
        minimal_pdf,
        "pypdfium2_txt",
    )
    assert len(result.raw_text_full) > 0
    assert "Hello" in result.raw_text_full


@pytest.mark.skipif(
    importlib.util.find_spec("pypdfium2") is None, reason="pypdfium2 not installed"
)
def test_pypdfium2_page_dimensions(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.pypdfium2_parser import PyPDFium2Parser

    result = _run(
        _parser(PyPDFium2Parser, parsed_root=str(tmp_path)),
        minimal_pdf,
        "pypdfium2_dims",
    )
    assert result.pages[0].width > 0
    assert result.pages[0].height > 0


# ---------------------------------------------------------------------------
# pdftext
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    importlib.util.find_spec("pdftext") is None, reason="pdftext not installed"
)
def test_pdftext_parser_runs(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.pdftext_parser import PDFTextParser

    result = _run(
        _parser(PDFTextParser, parsed_root=str(tmp_path)), minimal_pdf, "pdftext_test"
    )
    assert result.page_count_detected >= 1
    assert result.status == "completed"
    assert result.error_message == ""


@pytest.mark.skipif(
    importlib.util.find_spec("pdftext") is None, reason="pdftext not installed"
)
def test_pdftext_extracts_text(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.pdftext_parser import PDFTextParser

    result = _run(
        _parser(PDFTextParser, parsed_root=str(tmp_path)), minimal_pdf, "pdftext_txt"
    )
    assert len(result.raw_text_full) > 0


# ---------------------------------------------------------------------------
# Tesseract OCR
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    importlib.util.find_spec("pytesseract") is None
    or importlib.util.find_spec("fitz") is None,
    reason="pytesseract or PyMuPDF not installed",
)
def test_tesseract_parser_runs(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.tesseract_parser import (
        TesseractParser,
        _find_tesseract_cmd,
    )

    if not _find_tesseract_cmd():
        pytest.skip("Tesseract binary not found")
    result = _run(
        _parser(TesseractParser, {"dpi": 150}, parsed_root=str(tmp_path)),
        minimal_pdf,
        "tesseract_test",
    )
    assert result.status in ("completed", "failed")
    if result.status == "completed":
        assert isinstance(result.raw_text_full, str)


@pytest.mark.skipif(
    importlib.util.find_spec("pytesseract") is None, reason="pytesseract not installed"
)
def test_tesseract_fails_gracefully_without_binary(tmp_path, minimal_pdf):
    from unittest.mock import patch
    from pdf_research_pipeline.parsers.tesseract_parser import TesseractParser

    with patch(
        "pdf_research_pipeline.parsers.tesseract_parser._find_tesseract_cmd",
        return_value=None,
    ):
        result = _run(
            _parser(TesseractParser, parsed_root=str(tmp_path)),
            minimal_pdf,
            "tess_no_bin",
        )
    assert result.status == "failed"
    assert result.error_message != ""


# ---------------------------------------------------------------------------
# EasyOCR
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    importlib.util.find_spec("easyocr") is None
    or importlib.util.find_spec("fitz") is None,
    reason="easyocr or PyMuPDF not installed",
)
def test_easyocr_parser_runs(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.easyocr_parser import EasyOCRParser

    result = _run(
        _parser(EasyOCRParser, {"dpi": 72, "gpu": False}, parsed_root=str(tmp_path)),
        minimal_pdf,
        "easyocr_test",
    )
    assert result.status == "completed"
    assert result.page_count_detected >= 1
    assert isinstance(result.raw_text_full, str)


# ---------------------------------------------------------------------------
# OCRmyPDF
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    importlib.util.find_spec("ocrmypdf") is None
    or importlib.util.find_spec("fitz") is None,
    reason="ocrmypdf or PyMuPDF not installed",
)
def test_ocrmypdf_parser_runs(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.ocrmypdf_parser import OCRmyPDFParser
    from pdf_research_pipeline.parsers.tesseract_parser import _find_tesseract_cmd

    if not _find_tesseract_cmd():
        pytest.skip("Tesseract binary required by OCRmyPDF not found")
    result = _run(
        _parser(
            OCRmyPDFParser,
            {"lang": "eng", "deskew": False, "clean": False, "optimize": 0},
            parsed_root=str(tmp_path),
        ),
        minimal_pdf,
        "ocrmypdf_test",
    )
    assert result.status in ("completed", "failed")
    if result.status == "completed":
        assert isinstance(result.raw_text_full, str)


# ---------------------------------------------------------------------------
# Unstructured
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    importlib.util.find_spec("unstructured") is None,
    reason="unstructured not installed",
)
def test_unstructured_parser_runs(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.unstructured_parser import UnstructuredParser

    result = _run(
        _parser(
            UnstructuredParser,
            {"strategy": "fast", "include_page_breaks": False},
            parsed_root=str(tmp_path),
        ),
        minimal_pdf,
        "unstructured_test",
    )
    assert result.status == "completed"
    assert isinstance(result.raw_text_full, str)


# ---------------------------------------------------------------------------
# Camelot
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    importlib.util.find_spec("camelot") is None, reason="camelot-py not installed"
)
def test_camelot_extractor_runs(table_pdf, tmp_path):
    from pdf_research_pipeline.parsers.table_extractors import CamelotExtractor

    result = _run(
        _parser(
            CamelotExtractor,
            {"flavor": "lattice", "pages": "all"},
            parsed_root=str(tmp_path),
        ),
        table_pdf,
        "camelot_test",
    )
    assert result.status == "completed"
    assert isinstance(result.tables, list)


@pytest.mark.skipif(
    importlib.util.find_spec("camelot") is None, reason="camelot-py not installed"
)
def test_camelot_stream_flavor(table_pdf, tmp_path):
    from pdf_research_pipeline.parsers.table_extractors import CamelotExtractor

    result = _run(
        _parser(
            CamelotExtractor,
            {"flavor": "stream", "pages": "all"},
            parsed_root=str(tmp_path),
        ),
        table_pdf,
        "camelot_stream",
    )
    assert result.status == "completed"


# ---------------------------------------------------------------------------
# Tabula
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    importlib.util.find_spec("tabula") is None, reason="tabula-py not installed"
)
def test_tabula_extractor_runs(table_pdf, tmp_path):
    import subprocess

    # Tabula requires a Java runtime; skip gracefully when java is absent
    try:
        java_available = (
            subprocess.run(["java", "-version"], capture_output=True).returncode == 0
        )
    except FileNotFoundError:
        java_available = False
    if not java_available:
        pytest.skip("Java runtime not found — tabula requires Java")

    from pdf_research_pipeline.parsers.table_extractors import TabulaExtractor

    result = _run(
        _parser(
            TabulaExtractor,
            {"pages": "all", "multiple_tables": True},
            parsed_root=str(tmp_path),
        ),
        table_pdf,
        "tabula_test",
    )
    assert result.status == "completed"
    assert isinstance(result.tables, list)


# ---------------------------------------------------------------------------
# Marker (absent machine -- graceful fail)
# ---------------------------------------------------------------------------


def test_marker_parser_absent_returns_failed(tmp_path, minimal_pdf):
    from pdf_research_pipeline.parsers.marker_parser import MarkerParser

    if importlib.util.find_spec("marker") is not None:
        pytest.skip("marker-pdf installed; skip absence test")
    result = _run(
        _parser(MarkerParser, parsed_root=str(tmp_path)), minimal_pdf, "marker_absent"
    )
    assert result.status == "failed"
    assert (
        "marker" in result.error_message.lower()
        or "not installed" in result.error_message.lower()
    )


# ---------------------------------------------------------------------------
# Nougat (absent machine -- graceful fail)
# ---------------------------------------------------------------------------


def test_nougat_parser_absent_returns_failed(tmp_path, minimal_pdf):
    from pdf_research_pipeline.parsers.nougat_parser import NougatParser

    if importlib.util.find_spec("nougat") is not None:
        pytest.skip("nougat-ocr installed; skip absence test")
    result = _run(
        _parser(NougatParser, parsed_root=str(tmp_path)), minimal_pdf, "nougat_absent"
    )
    assert result.status == "failed"
    assert (
        "nougat" in result.error_message.lower()
        or "not installed" in result.error_message.lower()
    )


# ---------------------------------------------------------------------------
# Parser registry completeness
# ---------------------------------------------------------------------------


def test_all_known_parsers_in_registry():
    import inspect
    from pdf_research_pipeline.parsers import build_parsers

    src = inspect.getsource(build_parsers)
    expected = [
        "pymupdf",
        "pdfplumber",
        "pypdf",
        "pypdfium2",
        "pdftext",
        "easyocr",
        "unstructured",
        "tesseract",
        "ocrmypdf",
        "marker",
        "nougat",
        "camelot",
        "tabula",
    ]
    for name in expected:
        assert f'"{name}"' in src, (
            f"Parser '{name}' missing from build_parsers registry"
        )


# ---------------------------------------------------------------------------
# Cross-parser text consistency
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    any(
        importlib.util.find_spec(m) is None
        for m in ("fitz", "pdfplumber", "pypdf", "pypdfium2")
    ),
    reason="One or more digital parsers not installed",
)
def test_digital_parsers_agree_on_text(minimal_pdf, tmp_path):
    from pdf_research_pipeline.parsers.pymupdf_parser import PyMuPDFParser
    from pdf_research_pipeline.parsers.pdfplumber_parser import PDFPlumberParser
    from pdf_research_pipeline.parsers.pypdf_parser import PyPDFParser
    from pdf_research_pipeline.parsers.pypdfium2_parser import PyPDFium2Parser

    results = {}
    for name, cls in [
        ("pymupdf", PyMuPDFParser),
        ("pdfplumber", PDFPlumberParser),
        ("pypdf", PyPDFParser),
        ("pypdfium2", PyPDFium2Parser),
    ]:
        r = _run(_parser(cls, parsed_root=str(tmp_path)), minimal_pdf, f"cross_{name}")
        results[name] = r.raw_text_full.strip().lower()

    for name, text in results.items():
        assert "hello" in text, f"{name} did not extract expected text; got: {text!r}"
