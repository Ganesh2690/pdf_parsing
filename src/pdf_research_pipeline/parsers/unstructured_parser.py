"""
src/pdf_research_pipeline/parsers/unstructured_parser.py

Unstructured.io parser adapter.

Decision: Unstructured provides layout-aware element extraction with
hi_res strategy leveraging document detection models. It is the primary
parser for complex_layout_pdf and forms_interactive_pdf per prompt.md
section 13.

The hi_res strategy uses detectron2-based inference when available,
providing better section block separation than rule-based parsers on
multi-column and table-heavy PDFs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pdf_research_pipeline.parsers.base import BaseParser, PageResult, ParseResult


class UnstructuredParser(BaseParser):
    """
    Extracts structured elements using the Unstructured library.

    Config keys:
      strategy (str)             — fast | hi_res | ocr_only
      include_page_breaks (bool) — include PageBreak elements
      extract_images (bool)      — extract embedded images
    """

    parser_name = "unstructured"
    library_name = "unstructured"

    def _parse_impl(self, path: Path) -> ParseResult:
        from unstructured.partition.pdf import partition_pdf  # type: ignore[import]

        strategy: str = self.config.get("strategy", "hi_res")
        include_page_breaks: bool = self.config.get("include_page_breaks", True)

        elements = partition_pdf(
            filename=str(path),
            strategy=strategy,
            include_page_breaks=include_page_breaks,
        )

        # Group elements by page
        pages_map: dict[int, list[dict[str, Any]]] = {}
        all_text_parts: list[str] = []
        tables: list[dict[str, Any]] = []

        for elem in elements:
            page_num: int = getattr(elem.metadata, "page_number", 1) or 1
            if page_num not in pages_map:
                pages_map[page_num] = []

            elem_type = type(elem).__name__
            text = str(elem) if elem else ""

            block: dict[str, Any] = {
                "type": elem_type,
                "text": text,
            }

            # Capture coordinates if available
            coords = getattr(elem.metadata, "coordinates", None)
            if coords:
                block["coordinates"] = {
                    "points": getattr(coords, "points", None),
                    "system": getattr(coords, "system", None),
                }

            pages_map[page_num].append(block)
            all_text_parts.append(text)

            # Capture tables
            if elem_type == "Table":
                tables.append(
                    {
                        "page_number": page_num,
                        "html": getattr(elem.metadata, "text_as_html", text),
                        "text": text,
                    }
                )

        # Build PageResult list
        page_results: list[PageResult] = []
        for page_num in sorted(pages_map.keys()):
            blocks = pages_map[page_num]
            page_text = "\n".join(b["text"] for b in blocks if b.get("text"))
            page_results.append(
                PageResult(
                    page_number=page_num,
                    raw_text=page_text,
                    blocks=blocks,
                    tables=[t for t in tables if t["page_number"] == page_num],
                    is_empty=not bool(page_text.strip()),
                )
            )

        full_text = "\n\n".join(all_text_parts)
        return ParseResult(
            pdf_id="",
            pdf_type="",
            parser_name=self.parser_name,
            pages=page_results,
            page_count_detected=len(page_results),
            raw_text_full=full_text,
            tables=tables,
            status="completed",
        )
