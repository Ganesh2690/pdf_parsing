"""
src/pdf_research_pipeline/parsers/__init__.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pdf_research_pipeline.parsers.base import BaseParser, ParseResult


def build_parsers(cfg: Any) -> list["BaseParser"]:
    """Instantiate all enabled parsers from config. Imports are lazy per parser."""

    # Lazy registry: name -> (module_path, class_name)
    _LAZY_REGISTRY: dict[str, tuple[str, str]] = {
        "pymupdf": ("pdf_research_pipeline.parsers.pymupdf_parser", "PyMuPDFParser"),
        "pdfplumber": (
            "pdf_research_pipeline.parsers.pdfplumber_parser",
            "PDFPlumberParser",
        ),
        "pypdf": ("pdf_research_pipeline.parsers.pypdf_parser", "PyPDFParser"),
        "pypdfium2": (
            "pdf_research_pipeline.parsers.pypdfium2_parser",
            "PyPDFium2Parser",
        ),
        "pdftext": (
            "pdf_research_pipeline.parsers.pdftext_parser",
            "PDFTextParser",
        ),
        "easyocr": (
            "pdf_research_pipeline.parsers.easyocr_parser",
            "EasyOCRParser",
        ),
        "unstructured": (
            "pdf_research_pipeline.parsers.unstructured_parser",
            "UnstructuredParser",
        ),
        "tesseract": (
            "pdf_research_pipeline.parsers.tesseract_parser",
            "TesseractParser",
        ),
        "ocrmypdf": ("pdf_research_pipeline.parsers.ocrmypdf_parser", "OCRmyPDFParser"),
        "marker": ("pdf_research_pipeline.parsers.marker_parser", "MarkerParser"),
        "nougat": ("pdf_research_pipeline.parsers.nougat_parser", "NougatParser"),
        "camelot": (
            "pdf_research_pipeline.parsers.table_extractors",
            "CamelotExtractor",
        ),
        "tabula": (
            "pdf_research_pipeline.parsers.table_extractors",
            "TabulaExtractor",
        ),
    }

    parsers_cfg = (
        cfg.get_enabled_parsers() if hasattr(cfg, "get_enabled_parsers") else {}
    )

    parsers: list[Any] = []
    for name, pcfg in parsers_cfg.items():
        enabled = (
            pcfg.get("enabled", False)
            if isinstance(pcfg, dict)
            else getattr(pcfg, "enabled", False)
        )
        if not enabled or name not in _LAZY_REGISTRY:
            continue
        mod_path, class_name = _LAZY_REGISTRY[name]
        try:
            import importlib

            mod = importlib.import_module(mod_path)
            cls = getattr(mod, class_name)
            parsed_root = getattr(
                getattr(cfg, "pipeline", None), "parsed_root", "./data/parsed"
            )
            parsers.append(
                cls(
                    parsed_root=parsed_root,
                    config=pcfg if isinstance(pcfg, dict) else {},
                )
            )
        except Exception as exc:  # noqa: BLE001
            import warnings

            warnings.warn(f"Could not load parser '{name}': {exc}", stacklevel=2)

    # Always include pymupdf as a minimum fallback
    if not parsers:
        from pdf_research_pipeline.parsers.pymupdf_parser import PyMuPDFParser

        parsed_root = getattr(
            getattr(cfg, "pipeline", None), "parsed_root", "./data/parsed"
        )
        parsers.append(PyMuPDFParser(parsed_root=parsed_root, config={}))
    return parsers


def load_parse_result(
    pdf_id: str, pdf_type: str, parsed_dir: str
) -> dict[str, "ParseResult"]:
    """
    Load saved ParseResult objects for a given pdf_id from disk.

    Looks for summary.json files under:
      <parsed_dir>/<pdf_type>/<pdf_id>/<parser_name>/summary.json

    Returns a dict mapping parser_name -> ParseResult.
    """
    from pdf_research_pipeline.parsers.base import ParseResult

    root = Path(parsed_dir) / pdf_type / pdf_id
    results: dict[str, ParseResult] = {}
    if not root.exists():
        return results
    for parser_dir in root.iterdir():
        if not parser_dir.is_dir():
            continue
        summary_path = parser_dir / "summary.json"
        if summary_path.exists():
            try:
                data = json.loads(summary_path.read_text(encoding="utf-8"))
                results[parser_dir.name] = ParseResult.model_validate(data)
            except Exception:  # noqa: BLE001
                pass
    return results
