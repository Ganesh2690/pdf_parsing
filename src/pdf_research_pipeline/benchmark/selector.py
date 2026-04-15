"""
src/pdf_research_pipeline/benchmark/selector.py

Aggregates ParserScore objects per PDF type and selects the best primary
and fallback parsers. Writes benchmark reports.

Decision: Aggregate by mean total_score across all PDFs of each type.
Ties broken by speed_score (faster is better). Primary = highest scorer,
fallback = second highest.
"""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pdf_research_pipeline.benchmark.scorer import ParserScore
from pdf_research_pipeline.logging_utils import get_logger
from pdf_research_pipeline.utils.files import ensure_dir

logger = get_logger(__name__)


class ParserSelector:
    """
    Reads scored results and writes:
      reports/parser_benchmark.csv
      reports/parser_benchmark.json
      reports/parser_recommendations.md
    """

    def __init__(self, reports_dir: str) -> None:
        self.reports_dir = Path(reports_dir)
        ensure_dir(str(self.reports_dir))

    def aggregate(
        self, scores: list[tuple[str, str, ParserScore]]
    ) -> dict[str, dict[str, Any]]:
        """
        Aggregate parser scores by PDF type.

        Args:
            scores: list of (pdf_type, parser_name, ParserScore)

        Returns:
            aggregated: {pdf_type: {parser_name: {"mean_score": float, ...}}}
        """
        # Accumulate raw scores: {pdf_type: {parser_name: [total_score, ...]}}
        raw: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        speed_scores: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for pdf_type, parser_name, score in scores:
            raw[pdf_type][parser_name].append(score.total_score)
            for dim in score.dimensions:
                if dim.name == "speed":
                    speed_scores[pdf_type][parser_name].append(dim.raw_score)

        aggregated: dict[str, dict[str, Any]] = {}
        for pdf_type, parser_scores in raw.items():
            agg: dict[str, Any] = {}
            for parser_name, score_list in parser_scores.items():
                mean = sum(score_list) / len(score_list)
                speed_vals = speed_scores[pdf_type][parser_name]
                mean_speed = sum(speed_vals) / len(speed_vals) if speed_vals else 0
                agg[parser_name] = {
                    "mean_score": round(mean, 2),
                    "mean_speed_score": round(mean_speed, 2),
                    "sample_count": len(score_list),
                }
            aggregated[pdf_type] = agg

        return aggregated

    def select(
        self, aggregated: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, str]]:
        """
        Select primary and fallback parsers per PDF type.

        Returns:
            {pdf_type: {"primary": parser_name, "fallback": parser_name}}
        """
        selections: dict[str, dict[str, str]] = {}
        for pdf_type, parser_scores in aggregated.items():
            ranked = sorted(
                parser_scores.items(),
                key=lambda kv: (kv[1]["mean_score"], kv[1]["mean_speed_score"]),
                reverse=True,
            )
            primary = ranked[0][0] if len(ranked) >= 1 else "pymupdf"
            fallback = ranked[1][0] if len(ranked) >= 2 else primary

            selections[pdf_type] = {"primary": primary, "fallback": fallback}

            logger.info(
                "parser_decision",
                event_type="parser_decision",
                stage="benchmark",
                log_category="parser_selection",
                pdf_type=pdf_type,
                primary_parser=primary,
                fallback_parser=fallback,
                primary_score=parser_scores.get(primary, {}).get("mean_score", 0),
                fallback_score=parser_scores.get(fallback, {}).get("mean_score", 0),
                observation=f"Selected {primary} as primary, {fallback} as fallback for {pdf_type}",
                status="completed",
            )

        return selections

    def write_reports(
        self,
        aggregated: dict[str, dict[str, Any]],
        selections: dict[str, dict[str, str]],
    ) -> None:
        """Write CSV, JSON, and Markdown reports to reports_dir."""
        self._write_csv(aggregated, selections)
        self._write_json(aggregated, selections)
        self._write_markdown(aggregated, selections)

    def _write_csv(
        self,
        aggregated: dict[str, dict[str, Any]],
        selections: dict[str, dict[str, str]],
    ) -> None:
        csv_path = self.reports_dir / "parser_benchmark.csv"
        rows = []
        for pdf_type, parser_scores in aggregated.items():
            sel = selections.get(pdf_type, {})
            for parser_name, stats in parser_scores.items():
                role = (
                    "primary"
                    if parser_name == sel.get("primary")
                    else "fallback"
                    if parser_name == sel.get("fallback")
                    else "evaluated"
                )
                rows.append(
                    {
                        "pdf_type": pdf_type,
                        "parser_name": parser_name,
                        "mean_score": stats["mean_score"],
                        "mean_speed_score": stats["mean_speed_score"],
                        "sample_count": stats["sample_count"],
                        "role": role,
                    }
                )
        if not rows:
            return
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        logger.info(
            "report_written",
            event_type="report_written",
            stage="benchmark",
            log_category="parser_selection",
            path=str(csv_path),
            row_count=len(rows),
            status="completed",
        )

    def _write_json(
        self,
        aggregated: dict[str, dict[str, Any]],
        selections: dict[str, dict[str, str]],
    ) -> None:
        json_path = self.reports_dir / "parser_benchmark.json"
        payload = {"aggregated": aggregated, "selections": selections}
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info(
            "report_written",
            event_type="report_written",
            stage="benchmark",
            log_category="parser_selection",
            path=str(json_path),
            status="completed",
        )

    def _write_markdown(
        self,
        aggregated: dict[str, dict[str, Any]],
        selections: dict[str, dict[str, str]],
    ) -> None:
        md_path = self.reports_dir / "parser_recommendations.md"
        buf = io.StringIO()
        buf.write("# Parser Recommendations\n\n")
        buf.write(
            "Auto-generated by `ParserSelector`. "
            "Scores are weighted averages over all PDFs of each type.\n\n"
        )
        for pdf_type in sorted(aggregated):
            sel = selections.get(pdf_type, {})
            primary = sel.get("primary", "?")
            fallback = sel.get("fallback", "?")
            buf.write(f"## {pdf_type}\n\n")
            buf.write(f"**Primary:** `{primary}` | **Fallback:** `{fallback}`\n\n")
            buf.write("| Parser | Mean Score | Mean Speed Score | Samples |\n")
            buf.write("|--------|-----------|-----------------|--------|\n")
            ranked = sorted(
                aggregated[pdf_type].items(),
                key=lambda kv: kv[1]["mean_score"],
                reverse=True,
            )
            for parser_name, stats in ranked:
                tag = ""
                if parser_name == primary:
                    tag = " ✓ primary"
                elif parser_name == fallback:
                    tag = " fallback"
                buf.write(
                    f"| `{parser_name}`{tag} | "
                    f"{stats['mean_score']} | "
                    f"{stats['mean_speed_score']} | "
                    f"{stats['sample_count']} |\n"
                )
            buf.write("\n")
        md_path.write_text(buf.getvalue(), encoding="utf-8")
        logger.info(
            "report_written",
            event_type="report_written",
            stage="benchmark",
            log_category="parser_selection",
            path=str(md_path),
            status="completed",
        )
