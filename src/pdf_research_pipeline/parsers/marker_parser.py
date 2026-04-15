"""
src/pdf_research_pipeline/parsers/marker_parser.py

marker-pdf parser adapter.

Decision: marker-pdf is a learning-based layout-aware parser that produces
Markdown output with strong heading and section preservation. It is the
recommended primary parser for complex_layout_pdf when installed.

Per prompt.md section 13: test learning-based approaches for difficult scientific layouts.

Installation: pip install marker-pdf  (not in default requirements.txt due to large ML deps)

TODO: This adapter requires `marker-pdf` to be installed separately.
"""

from __future__ import annotations

from pathlib import Path

from pdf_research_pipeline.logging_utils import get_logger
from pdf_research_pipeline.parsers.base import BaseParser, PageResult, ParseResult

logger = get_logger(__name__)


class MarkerParser(BaseParser):
    """
    High-quality Markdown extraction using marker-pdf.

    Produces:
      - Markdown text with heading hierarchy
      - Page-level text blocks
      - Tables in Markdown format

    Requires: pip install marker-pdf
    """

    parser_name = "marker"
    library_name = "marker-pdf"

    def _parse_impl(self, path: Path) -> ParseResult:
        try:
            # marker-pdf >= 0.3 uses PdfConverter API
            from marker.converters.pdf import PdfConverter  # type: ignore[import]
            from marker.models import create_model_dict  # type: ignore[import]
            from marker.output import text_from_rendered  # type: ignore[import]

            _NEW_API = True
        except ImportError:
            _NEW_API = False

        if not _NEW_API:
            try:
                # marker-pdf < 0.3 (legacy API)
                from marker.convert import convert_single_pdf  # type: ignore[import]
                from marker.models import load_all_models  # type: ignore[import]

                _LEGACY_API = True
            except ImportError:
                _LEGACY_API = False
            else:
                pass
        else:
            _LEGACY_API = False

        if not _NEW_API and not _LEGACY_API:
            raise RuntimeError(
                "marker-pdf is not installed. "
                "Install it with: pip install marker-pdf\n"
                "Then re-enable it in configs/parsers.yaml"
            )

        logger.info(
            "marker_loading_models",
            event_type="marker_loading_models",
            stage="extraction",
            log_category="extraction",
            parser_name=self.parser_name,
            observation="Loading marker models — this may take time on first run",
            status="loading",
        )

        full_text: str = ""
        metadata: dict = {}

        if _NEW_API:
            # marker-pdf >= 0.3
            model_dict = create_model_dict()
            converter = PdfConverter(
                artifact_dict=model_dict,
                config={"output_format": "markdown"},
            )
            rendered = converter(str(path))
            full_text, _, metadata = text_from_rendered(rendered)
        else:
            # marker-pdf < 0.3 (legacy)
            from marker.convert import convert_single_pdf  # type: ignore[import]
            from marker.models import load_all_models  # type: ignore[import]

            models = load_all_models()
            full_text, _images, metadata = convert_single_pdf(str(path), models)

        # Build page results — marker works at document level; split by page_stats
        pages: list[PageResult] = []
        page_stats = metadata.get("page_stats", [])

        if page_stats:
            for i, _stat in enumerate(page_stats):
                pages.append(
                    PageResult(
                        page_number=i + 1,
                        raw_text=full_text,
                        markdown=full_text,
                        is_empty=not bool(full_text.strip()),
                    )
                )
        else:
            pages.append(
                PageResult(
                    page_number=1,
                    raw_text=full_text,
                    markdown=full_text,
                    is_empty=not bool(full_text.strip()),
                )
            )

        return ParseResult(
            pdf_id="",
            pdf_type="",
            parser_name=self.parser_name,
            pages=pages,
            page_count_detected=len(pages),
            raw_text_full=full_text,
            status="completed",
        )
