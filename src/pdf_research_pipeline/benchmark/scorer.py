"""
src/pdf_research_pipeline/benchmark/scorer.py

Computes a weighted quality score for a parser's extraction result
across 12 dimensions as specified in prompt.md section 7.

Scoring dimensions:
  1.  text_completeness        — how much text was extracted vs expected
  2.  heading_preservation     — are headings detectable in output
  3.  paragraph_preservation   — paragraph boundaries intact
  4.  table_extraction_quality — tables extracted and non-empty
  5.  page_ordering_quality    — page numbers sequential and continuous
  6.  ocr_quality              — mean OCR confidence when applicable
  7.  coordinate_richness      — bounding box data present
  8.  speed                    — extraction time relative to thresholds
  9.  memory_usage             — estimated memory footprint
  10. structural_fidelity      — blocks/elements match document structure
  11. markdown_readability     — markdown headings/lists detectable
  12. rag_suitability          — content is RAG-usable (non-empty, structured)

Each dimension is scored 0–100. The weighted sum is the final score.

Decision: Scoring is heuristic-based, not ground-truth-based, because
ground truth is not available for all PDF types. Heuristics provide
consistent, automatable evidence. When ground truth is available,
extend this scorer with a ground_truth_match dimension.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pdf_research_pipeline.parsers.base import ParseResult


@dataclass
class DimensionScore:
    name: str
    raw_score: float  # 0.0 – 100.0
    weight: float
    weighted_score: float = field(init=False)
    evidence: str = ""

    def __post_init__(self) -> None:
        self.weighted_score = self.raw_score * self.weight


@dataclass
class ParserScore:
    pdf_id: str
    pdf_type: str
    parser_name: str
    dimensions: list[DimensionScore]
    total_score: float = field(init=False)
    recommendation: str = ""

    def __post_init__(self) -> None:
        self.total_score = sum(d.weighted_score for d in self.dimensions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pdf_id": self.pdf_id,
            "pdf_type": self.pdf_type,
            "parser_name": self.parser_name,
            "total_score": round(self.total_score, 2),
            "recommendation": self.recommendation,
            "dimensions": {
                d.name: {
                    "raw_score": round(d.raw_score, 2),
                    "weight": d.weight,
                    "weighted_score": round(d.weighted_score, 2),
                    "evidence": d.evidence,
                }
                for d in self.dimensions
            },
        }


# ---------------------------------------------------------------------------
# Default weights (overridden per PDF type from scoring.yaml)
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = {
    "text_completeness": 0.20,
    "heading_preservation": 0.10,
    "paragraph_preservation": 0.10,
    "table_extraction_quality": 0.10,
    "page_ordering_quality": 0.10,
    "ocr_quality": 0.08,
    "coordinate_richness": 0.07,
    "speed": 0.05,
    "memory_usage": 0.05,
    "structural_fidelity": 0.08,
    "markdown_readability": 0.04,
    "rag_suitability": 0.03,
}


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class ParserScorer:
    """
    Computes a multi-dimension quality score for a ParseResult.

    Decision: Weights are passed in from scoring.yaml so that they are
    fully configurable without code changes (prompt.md section 10).
    """

    SPEED_EXCELLENT_MS = 1000
    SPEED_ACCEPTABLE_MS = 5000
    SPEED_POOR_MS = 30000

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or DEFAULT_WEIGHTS

    def score(self, result: ParseResult) -> ParserScore:
        """Compute the full DimensionScore list and return a ParserScore."""
        dimensions = [
            self._score_text_completeness(result),
            self._score_heading_preservation(result),
            self._score_paragraph_preservation(result),
            self._score_table_extraction(result),
            self._score_page_ordering(result),
            self._score_ocr_quality(result),
            self._score_coordinate_richness(result),
            self._score_speed(result),
            self._score_memory(result),
            self._score_structural_fidelity(result),
            self._score_markdown_readability(result),
            self._score_rag_suitability(result),
        ]

        ps = ParserScore(
            pdf_id=result.pdf_id,
            pdf_type=result.pdf_type,
            parser_name=result.parser_name,
            dimensions=dimensions,
        )

        # Set recommendation label
        if ps.total_score >= 80:
            ps.recommendation = "recommended"
        elif ps.total_score >= 65:
            ps.recommendation = "acceptable"
        elif ps.total_score >= 40:
            ps.recommendation = "marginal"
        else:
            ps.recommendation = "not_recommended"

        return ps

    # ------------------------------------------------------------------
    # Dimension scorers
    # ------------------------------------------------------------------

    def _score_text_completeness(self, r: ParseResult) -> DimensionScore:
        text = r.raw_text_full or ""
        page_count = max(r.page_count_detected, 1)
        chars_per_page = len(text) / page_count

        # Heuristic: a typical page has ~1500–3000 chars
        if chars_per_page >= 1500:
            score = 100.0
            evidence = f"{chars_per_page:.0f} chars/page — full extraction likely"
        elif chars_per_page >= 500:
            score = 70.0
            evidence = f"{chars_per_page:.0f} chars/page — partial extraction"
        elif chars_per_page >= 100:
            score = 40.0
            evidence = f"{chars_per_page:.0f} chars/page — sparse extraction"
        else:
            score = 10.0 if text.strip() else 0.0
            evidence = f"{chars_per_page:.0f} chars/page — near-empty extraction"

        return DimensionScore(
            name="text_completeness",
            raw_score=score,
            weight=self.weights["text_completeness"],
            evidence=evidence,
        )

    def _score_heading_preservation(self, r: ParseResult) -> DimensionScore:
        text = r.raw_text_full or ""
        # Look for heading patterns: markdown headings or ALL-CAPS short lines
        md_headings = len(re.findall(r"^#{1,4}\s+\S", text, re.MULTILINE))
        caps_headings = len(re.findall(r"^[A-Z][A-Z\s]{3,50}$", text, re.MULTILINE))
        total = md_headings + caps_headings

        if total >= 5:
            score = 100.0
        elif total >= 2:
            score = 70.0
        elif total >= 1:
            score = 40.0
        else:
            score = 0.0

        return DimensionScore(
            name="heading_preservation",
            raw_score=score,
            weight=self.weights["heading_preservation"],
            evidence=f"{md_headings} markdown headings, {caps_headings} caps-style headings detected",
        )

    def _score_paragraph_preservation(self, r: ParseResult) -> DimensionScore:
        text = r.raw_text_full or ""
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        page_count = max(r.page_count_detected, 1)
        paras_per_page = len(paragraphs) / page_count

        if paras_per_page >= 3:
            score = 100.0
        elif paras_per_page >= 1.5:
            score = 70.0
        elif paras_per_page >= 0.5:
            score = 40.0
        else:
            score = 10.0

        return DimensionScore(
            name="paragraph_preservation",
            raw_score=score,
            weight=self.weights["paragraph_preservation"],
            evidence=f"{len(paragraphs)} paragraphs across {page_count} pages ({paras_per_page:.1f}/page)",
        )

    def _score_table_extraction(self, r: ParseResult) -> DimensionScore:
        tables = r.tables or []
        non_empty = [
            t for t in tables if t.get("rows") or t.get("html") or t.get("text")
        ]

        if non_empty:
            score = min(100.0, 60.0 + len(non_empty) * 10)
            evidence = f"{len(non_empty)} non-empty tables extracted"
        else:
            score = 0.0
            evidence = "No tables extracted"

        # If no tables exist in the PDF, this dimension should not penalise
        # (unknown at scoring time — we give partial credit for the attempt)
        if not tables:
            score = 50.0
            evidence = "No table extraction attempted or no tables in PDF"

        return DimensionScore(
            name="table_extraction_quality",
            raw_score=score,
            weight=self.weights["table_extraction_quality"],
            evidence=evidence,
        )

    def _score_page_ordering(self, r: ParseResult) -> DimensionScore:
        pages = r.pages
        if len(pages) <= 1:
            return DimensionScore(
                name="page_ordering_quality",
                raw_score=80.0,  # Can't evaluate on single page
                weight=self.weights["page_ordering_quality"],
                evidence="Single page — ordering not evaluable",
            )
        page_nums = [p.page_number for p in pages]
        expected = list(range(1, len(pages) + 1))
        if page_nums == expected:
            score = 100.0
            evidence = "Pages in correct sequential order"
        elif sorted(page_nums) == expected:
            score = 70.0
            evidence = "All pages present but order may be non-sequential"
        else:
            missing = set(expected) - set(page_nums)
            score = max(0.0, 100.0 - len(missing) * 10)
            evidence = f"{len(missing)} pages missing from output"

        return DimensionScore(
            name="page_ordering_quality",
            raw_score=score,
            weight=self.weights["page_ordering_quality"],
            evidence=evidence,
        )

    def _score_ocr_quality(self, r: ParseResult) -> DimensionScore:
        confs = [p.ocr_confidence for p in r.pages if p.ocr_confidence is not None]
        if not confs:
            return DimensionScore(
                name="ocr_quality",
                raw_score=100.0,  # Not an OCR parser — not applicable
                weight=self.weights["ocr_quality"],
                evidence="OCR not used — not applicable",
            )
        mean_conf = sum(confs) / len(confs)
        score = min(100.0, mean_conf)  # Tesseract confidence is 0-100
        return DimensionScore(
            name="ocr_quality",
            raw_score=score,
            weight=self.weights["ocr_quality"],
            evidence=f"Mean OCR confidence: {mean_conf:.1f} across {len(confs)} pages",
        )

    def _score_coordinate_richness(self, r: ParseResult) -> DimensionScore:
        total_blocks = sum(len(p.blocks) for p in r.pages)
        blocks_with_coords = sum(
            1
            for p in r.pages
            for b in p.blocks
            if any(k in b for k in ("x0", "x", "coordinates", "bbox"))
        )

        if total_blocks == 0:
            score = 0.0
            evidence = "No blocks extracted"
        else:
            ratio = blocks_with_coords / total_blocks
            score = ratio * 100
            evidence = f"{blocks_with_coords}/{total_blocks} blocks have coordinate data ({ratio:.0%})"

        return DimensionScore(
            name="coordinate_richness",
            raw_score=score,
            weight=self.weights["coordinate_richness"],
            evidence=evidence,
        )

    def _score_speed(self, r: ParseResult) -> DimensionScore:
        duration_ms = r.duration_ms
        page_count = max(r.page_count_detected, 1)
        ms_per_page = duration_ms / page_count

        if ms_per_page <= self.SPEED_EXCELLENT_MS:
            score = 100.0
        elif ms_per_page <= self.SPEED_ACCEPTABLE_MS:
            score = 60.0
        elif ms_per_page <= self.SPEED_POOR_MS:
            score = 20.0
        else:
            score = 0.0

        return DimensionScore(
            name="speed",
            raw_score=score,
            weight=self.weights["speed"],
            evidence=f"{ms_per_page:.0f} ms/page (total {duration_ms} ms)",
        )

    def _score_memory(self, r: ParseResult) -> DimensionScore:
        # Memory usage is not tracked at this stage (requires psutil instrumentation)
        # Return neutral score with note — future work
        return DimensionScore(
            name="memory_usage",
            raw_score=50.0,
            weight=self.weights["memory_usage"],
            evidence="Memory tracking not yet instrumented — neutral score assigned",
        )

    def _score_structural_fidelity(self, r: ParseResult) -> DimensionScore:
        total_blocks = sum(len(p.blocks) for p in r.pages)
        typed_blocks = sum(
            1
            for p in r.pages
            for b in p.blocks
            if b.get("type") not in (None, "words", "chars", "word")
        )

        if total_blocks == 0:
            score = 0.0
            evidence = "No structured blocks extracted"
        else:
            ratio = typed_blocks / total_blocks
            score = min(100.0, ratio * 100 + 20)  # +20 bias for having any blocks
            evidence = f"{typed_blocks}/{total_blocks} blocks have semantic type labels"

        return DimensionScore(
            name="structural_fidelity",
            raw_score=score,
            weight=self.weights["structural_fidelity"],
            evidence=evidence,
        )

    def _score_markdown_readability(self, r: ParseResult) -> DimensionScore:
        text = r.raw_text_full or ""
        # Check for markdown structural features
        has_headers = bool(re.search(r"^#{1,4}\s", text, re.MULTILINE))
        has_lists = bool(re.search(r"^[\-\*]\s", text, re.MULTILINE))
        has_code = bool(re.search(r"```", text))
        has_bold = bool(re.search(r"\*\*\S", text))

        features = sum([has_headers, has_lists, has_code, has_bold])
        score = min(100.0, features * 25.0)
        evidence = (
            f"headers={'yes' if has_headers else 'no'}, "
            f"lists={'yes' if has_lists else 'no'}, "
            f"code={'yes' if has_code else 'no'}, "
            f"bold={'yes' if has_bold else 'no'}"
        )

        return DimensionScore(
            name="markdown_readability",
            raw_score=score,
            weight=self.weights["markdown_readability"],
            evidence=evidence,
        )

    def _score_rag_suitability(self, r: ParseResult) -> DimensionScore:
        text = r.raw_text_full or ""
        word_count = len(text.split())
        has_structure = any(p.blocks for p in r.pages)

        if word_count >= 200 and has_structure:
            score = 100.0
            evidence = (
                f"{word_count} words extracted with structured blocks — good RAG input"
            )
        elif word_count >= 50:
            score = 60.0
            evidence = f"{word_count} words extracted — usable but limited"
        else:
            score = 10.0
            evidence = f"{word_count} words — likely too sparse for reliable RAG"

        return DimensionScore(
            name="rag_suitability",
            raw_score=score,
            weight=self.weights["rag_suitability"],
            evidence=evidence,
        )
