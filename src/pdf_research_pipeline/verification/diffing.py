"""
src/pdf_research_pipeline/verification/diffing.py

Computes structured diffs between parser outputs for the same PDF and
writes verification reports.

Decision: deepdiff for dict comparison; difflib for text.
All results appended to reports/verification_summary.md and
failed_files_report.md.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from pdf_research_pipeline.logging_utils import get_logger
from pdf_research_pipeline.parsers.base import ParseResult
from pdf_research_pipeline.utils.files import ensure_dir
from pdf_research_pipeline.verification.validators import (
    ParseResultValidator,
    ValidationResult,
)

logger = get_logger(__name__)


class OutputDiffer:
    """
    Manages per-run diff state and writes consolidated reports.

    Usage:
        differ = OutputDiffer(reports_dir="reports")
        differ.add(pdf_id, pdf_type, parser_name, parse_result, prev_hash)
        ...
        differ.write_reports()
    """

    def __init__(self, reports_dir: str) -> None:
        self.reports_dir = Path(reports_dir)
        ensure_dir(str(self.reports_dir))
        self._validator = ParseResultValidator()
        self._results: list[ValidationResult] = []
        self._diffs: list[dict[str, Any]] = []

    def add(
        self,
        pdf_id: str,
        pdf_type: str,
        parser_name: str,
        result: ParseResult,
        previous_hash: str | None = None,
    ) -> ValidationResult:
        """
        Validate a ParseResult and record it.

        Returns the ValidationResult so callers can react immediately.
        """
        vr = self._validator.validate(
            result, previous_hash=previous_hash, pdf_type=pdf_type
        )
        self._results.append(vr)

        if not vr.passed:
            self._diffs.append(
                {
                    "pdf_id": pdf_id,
                    "pdf_type": pdf_type,
                    "parser_name": parser_name,
                    "issues": [
                        {
                            "code": i.code,
                            "severity": i.severity.value,
                            "message": i.message,
                            "detail": i.detail,
                        }
                        for i in vr.issues
                    ],
                }
            )

        return vr

    def diff_two(
        self,
        result_a: ParseResult,
        result_b: ParseResult,
    ) -> dict[str, Any]:
        """
        Deep-diff two ParseResult objects and return a summary dict.
        Useful for comparing the same PDF across two parsers.
        """
        from deepdiff import DeepDiff  # type: ignore[import]
        import difflib

        text_a = result_a.raw_text_full or ""
        text_b = result_b.raw_text_full or ""
        text_ratio = difflib.SequenceMatcher(None, text_a[:8000], text_b[:8000]).ratio()

        struct_a = {
            "page_count": result_a.page_count_detected,
            "table_count": len(result_a.tables),
            "text_length": len(text_a),
        }
        struct_b = {
            "page_count": result_b.page_count_detected,
            "table_count": len(result_b.tables),
            "text_length": len(text_b),
        }
        deep_diff = DeepDiff(struct_a, struct_b, ignore_order=True)

        return {
            "pdf_id_a": result_a.pdf_id,
            "parser_a": result_a.parser_name,
            "pdf_id_b": result_b.pdf_id,
            "parser_b": result_b.parser_name,
            "text_similarity_ratio": round(text_ratio, 4),
            "structural_diff": deep_diff.to_dict() if deep_diff else {},
        }

    def write_reports(self) -> None:
        """Write all accumulated verification reports to disk."""
        self._write_verification_summary()
        self._write_failed_files_report()
        self._write_diff_report()

    def _write_verification_summary(self) -> None:
        path = self.reports_dir / "verification_summary.md"
        total = len(self._results)
        passed = sum(1 for r in self._results if r.passed)
        failed = total - passed

        buf = io.StringIO()
        buf.write("# Verification Summary\n\n")
        buf.write(
            f"Total validated: **{total}** | Passed: **{passed}** | Failed: **{failed}**\n\n"
        )

        if self._results:
            buf.write("## Details\n\n")
            buf.write("| PDF ID | Parser | Passed | Errors | Warnings |\n")
            buf.write("|--------|--------|--------|--------|----------|\n")
            for vr in self._results:
                status = "✓" if vr.passed else "✗"
                buf.write(
                    f"| {vr.pdf_id} | {vr.parser_name} | {status} | "
                    f"{len(vr.errors)} | {len(vr.warnings)} |\n"
                )

        path.write_text(buf.getvalue(), encoding="utf-8")
        logger.info(
            "report_written",
            event_type="report_written",
            stage="verification",
            log_category="verification",
            path=str(path),
            record_count=total,
            status="completed",
        )

    def _write_failed_files_report(self) -> None:
        path = self.reports_dir / "failed_files_report.md"
        failed = [r for r in self._results if not r.passed]
        buf = io.StringIO()
        buf.write("# Failed Files Report\n\n")
        if not failed:
            buf.write("No failures recorded for this run.\n")
        else:
            for vr in failed:
                buf.write(f"## {vr.pdf_id} — {vr.parser_name}\n\n")
                for issue in vr.issues:
                    icon = "❌" if issue.severity.value == "error" else "⚠️"
                    buf.write(f"- {icon} `{issue.code}`: {issue.message}")
                    if issue.detail:
                        buf.write(f" ({issue.detail})")
                    buf.write("\n")
                buf.write("\n")
        path.write_text(buf.getvalue(), encoding="utf-8")
        logger.info(
            "report_written",
            event_type="report_written",
            stage="verification",
            log_category="verification",
            path=str(path),
            failed_count=len(failed),
            status="completed",
        )

    def _write_diff_report(self) -> None:
        if not self._diffs:
            return
        path = self.reports_dir / "output_diff_report.md"
        buf = io.StringIO()
        buf.write("# Output Diff Report\n\n")
        buf.write(f"Files with issues: **{len(self._diffs)}**\n\n")
        for diff in self._diffs:
            buf.write(f"## {diff['pdf_id']} — {diff['parser_name']}\n\n")
            buf.write(f"PDF type: `{diff['pdf_type']}`\n\n")
            buf.write("```json\n")
            buf.write(json.dumps(diff["issues"], indent=2))
            buf.write("\n```\n\n")
        path.write_text(buf.getvalue(), encoding="utf-8")
        logger.info(
            "report_written",
            event_type="report_written",
            stage="verification",
            log_category="verification",
            path=str(path),
            diff_count=len(self._diffs),
            status="completed",
        )
