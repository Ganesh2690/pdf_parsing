"""
src/pdf_research_pipeline/parsers/table_extractors.py

Dedicated table extraction adapters: Camelot and Tabula.

Decision: Tables extracted by general parsers (PyMuPDF, pdfplumber) are
often incomplete or flattened. Camelot and Tabula are routed specifically
for table-heavy PDFs.

Per prompt.md section 13: Route to dedicated table extractors where appropriate.

Camelot flavors:
  - lattice: for tables with visible gridlines (most financial PDFs)
  - stream: for tables without borders (uses whitespace heuristics)

Tabula: Java-based, uses PDFBox, strong on complex merged-cell tables.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pdf_research_pipeline.parsers.base import BaseParser, PageResult, ParseResult


class CamelotExtractor(BaseParser):
    """
    Table extraction using Camelot.

    Config keys:
      flavor (str)  — lattice | stream (default: lattice)
      pages (str)   — page range string (default: 'all')
    """

    parser_name = "camelot"
    library_name = "camelot-py"

    def _parse_impl(self, path: Path) -> ParseResult:
        import camelot  # type: ignore[import]

        flavor: str = self.config.get("flavor", "lattice")
        pages: str = self.config.get("pages", "all")

        tables_raw = camelot.read_pdf(
            str(path),
            flavor=flavor,
            pages=pages,
        )

        all_tables: list[dict[str, Any]] = []
        for i, table in enumerate(tables_raw):
            df = table.df
            all_tables.append(
                {
                    "table_index": i,
                    "page": table.page,
                    "accuracy": table.accuracy,
                    "whitespace": table.whitespace,
                    "rows": df.values.tolist(),
                    "shape": {"rows": df.shape[0], "cols": df.shape[1]},
                }
            )

        full_text = "\n\n".join(
            "\t".join(str(cell) for cell in row)
            for t in all_tables
            for row in t.get("rows", [])
        )

        pages_result: list[PageResult] = [
            PageResult(
                page_number=1,
                raw_text=full_text,
                tables=all_tables,
                is_empty=not bool(full_text.strip()),
            )
        ]

        return ParseResult(
            pdf_id="",
            pdf_type="",
            parser_name=self.parser_name,
            pages=pages_result,
            page_count_detected=len({t["page"] for t in all_tables}),
            raw_text_full=full_text,
            tables=all_tables,
            status="completed",
        )


class TabulaExtractor(BaseParser):
    """
    Table extraction using Tabula-py (Java-based).

    Config keys:
      pages (str)             — page range or 'all'
      multiple_tables (bool)  — extract multiple tables per page
    """

    parser_name = "tabula"
    library_name = "tabula-py"

    def _parse_impl(self, path: Path) -> ParseResult:
        import tabula  # type: ignore[import]

        pages: str = self.config.get("pages", "all")
        multiple_tables: bool = self.config.get("multiple_tables", True)

        dfs = tabula.read_pdf(
            str(path),
            pages=pages,
            multiple_tables=multiple_tables,
            silent=True,
        )

        all_tables: list[dict[str, Any]] = []
        for i, df in enumerate(dfs):
            all_tables.append(
                {
                    "table_index": i,
                    "rows": df.fillna("").values.tolist(),
                    "columns": list(df.columns),
                    "shape": {"rows": df.shape[0], "cols": df.shape[1]},
                }
            )

        full_text = "\n\n".join(
            "\t".join(str(cell) for cell in row)
            for t in all_tables
            for row in t.get("rows", [])
        )

        pages_result: list[PageResult] = [
            PageResult(
                page_number=1,
                raw_text=full_text,
                tables=all_tables,
                is_empty=not bool(full_text.strip()),
            )
        ]

        return ParseResult(
            pdf_id="",
            pdf_type="",
            parser_name=self.parser_name,
            pages=pages_result,
            page_count_detected=1,
            raw_text_full=full_text,
            tables=all_tables,
            status="completed",
        )
