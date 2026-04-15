"""
src/pdf_research_pipeline/benchmark/comparator.py

Compares extraction outputs across parsers for the same PDF.

Decision: deepdiff is used for structured comparison of JSON outputs.
Diffs are computed on the raw_text_full to show text-level differences
and on the structured page/block JSON to show structural differences.

Output: reports/output_diff_report.md (human-readable) + JSONL diffs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pdf_research_pipeline.logging_utils import get_logger
from pdf_research_pipeline.parsers.base import ParseResult
from pdf_research_pipeline.utils.files import ensure_dir, write_json

logger = get_logger(__name__)


class ParserComparator:
    """
    Compares ParseResult outputs across multiple parsers for the same PDF.

    Decision: Use deepdiff for dict/list comparison. Fall back to character-level
    diff for raw text comparison. This provides both structural and content diffs.
    """

    def __init__(self, reports_dir: str) -> None:
        self.reports_dir = Path(reports_dir)
        ensure_dir(str(self.reports_dir))

    def compare(
        self,
        pdf_id: str,
        pdf_type: str,
        results: dict[str, ParseResult],
        baseline_parser: str = "pymupdf",
    ) -> dict[str, Any]:
        """
        Compare all parser results against a baseline parser.

        Returns a dict of comparison results logged to extraction log.
        """
        from deepdiff import DeepDiff  # type: ignore[import]

        if baseline_parser not in results:
            baseline_parser = next(iter(results), "")

        if not baseline_parser or baseline_parser not in results:
            logger.warning(
                "comparator_no_baseline",
                event_type="comparator_no_baseline",
                stage="benchmark",
                log_category="verification",
                pdf_id=pdf_id,
                observation="No baseline parser available for comparison",
                status="skipped",
            )
            return {}

        baseline = results[baseline_parser]
        comparison_results: dict[str, Any] = {}

        for parser_name, result in results.items():
            if parser_name == baseline_parser:
                continue

            # Text-level diff
            text_diff = self._text_diff(baseline.raw_text_full, result.raw_text_full)

            # Structural diff (page count, table count)
            structural = {
                "baseline_page_count": baseline.page_count_detected,
                "comparison_page_count": result.page_count_detected,
                "baseline_table_count": len(baseline.tables),
                "comparison_table_count": len(result.tables),
                "baseline_text_length": len(baseline.raw_text_full),
                "comparison_text_length": len(result.raw_text_full),
            }

            # DeepDiff on summary fields
            baseline_summary = {
                "page_count": baseline.page_count_detected,
                "table_count": len(baseline.tables),
                "text_length": len(baseline.raw_text_full),
            }
            compare_summary = {
                "page_count": result.page_count_detected,
                "table_count": len(result.tables),
                "text_length": len(result.raw_text_full),
            }
            deep_diff = DeepDiff(baseline_summary, compare_summary, ignore_order=True)

            comparison = {
                "pdf_id": pdf_id,
                "pdf_type": pdf_type,
                "baseline_parser": baseline_parser,
                "comparison_parser": parser_name,
                "text_similarity_ratio": text_diff["similarity_ratio"],
                "text_length_delta": text_diff["length_delta"],
                "structural": structural,
                "deep_diff": deep_diff.to_dict() if deep_diff else {},
                "observation": self._observe(structural),
            }

            comparison_results[parser_name] = comparison

            logger.info(
                "parser_comparison",
                event_type="parser_comparison",
                stage="benchmark",
                log_category="verification",
                pdf_id=pdf_id,
                pdf_type=pdf_type,
                baseline_parser=baseline_parser,
                comparison_parser=parser_name,
                similarity_ratio=text_diff["similarity_ratio"],
                structural=structural,
                observation=self._observe(structural),
                status="completed",
            )

        # Save diff report
        if comparison_results:
            diff_path = self.reports_dir / f"diff_{pdf_id}.json"
            write_json(str(diff_path), comparison_results)

        return comparison_results

    def _text_diff(self, baseline: str, compare: str) -> dict[str, Any]:
        """
        Compute text similarity ratio and length delta.
        Uses difflib SequenceMatcher for a quick similarity estimate.
        """
        import difflib

        b = baseline or ""
        c = compare or ""
        ratio = difflib.SequenceMatcher(None, b[:5000], c[:5000]).ratio()
        return {
            "similarity_ratio": round(ratio, 4),
            "length_delta": len(c) - len(b),
        }

    def _observe(self, structural: dict[str, Any]) -> str:
        """Generate a human-readable observation from structural diff."""
        parts = []
        pc_delta = (
            structural["comparison_page_count"] - structural["baseline_page_count"]
        )
        tbl_delta = (
            structural["comparison_table_count"] - structural["baseline_table_count"]
        )
        txt_delta = (
            structural["comparison_text_length"] - structural["baseline_text_length"]
        )

        if pc_delta != 0:
            parts.append(f"page_count differs by {pc_delta:+d}")
        if tbl_delta != 0:
            parts.append(f"table_count differs by {tbl_delta:+d}")
        if abs(txt_delta) > 500:
            parts.append(f"text_length differs by {txt_delta:+d} chars")

        return "; ".join(parts) if parts else "no significant structural differences"
