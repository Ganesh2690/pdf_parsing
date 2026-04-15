"""
src/pdf_research_pipeline/benchmark/openai_agent.py

OpenAI-powered deep scoring agent for PDF parser evaluation.

Uses GPT-4o to compare text extractions from multiple parsers against
the same PDF, scoring each parser 0-100 across quality dimensions and
generating detailed reasoning about which parser is best suited for
each PDF type and why.

Security: API key is always read from the OPENAI_API_KEY environment variable.
Never hardcode credentials.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pdf_research_pipeline.logging_utils import get_logger

logger = get_logger(__name__)

_SCORING_SYSTEM_PROMPT = """\
You are an expert PDF parsing evaluator and document analysis AI.

You will receive:
1. Structural metadata for a PDF (page count, image count, table count, word count, paragraphs, fonts, layout info)
2. Extracted text from multiple PDF parsing libraries

Your task is to:
- Score each parser's extraction quality from 0 to 100
- Provide dimension-level scores (0-100) for: text_completeness, structure_preservation, formatting_quality, table_quality, readability, rag_suitability, ocr_accuracy
- Write a detailed analysis (2-4 sentences) explaining each parser's strengths/weaknesses
- Recommend the best parser for this specific PDF type and explain why
- Identify which parser performed worst and why

Scoring guide:
  90-100: Near-perfect extraction matching document structure
  75-89:  Good extraction with minor loss of formatting
  55-74:  Acceptable text but significant structure loss
  30-54:  Partial extraction, meaningful content missing
  0-29:   Poor extraction, garbled or near-empty text

Key evaluation criteria:
- Does the extracted text contain all the information visible in the PDF?
- Are headings, sections, and paragraphs correctly delimited?
- Are tables represented in a usable (even if not perfect) form?
- Is the text ordered logically (top-to-bottom, left-to-right)?
- Would this text be suitable for downstream RAG/LLM usage?
- For OCR parsers (tesseract, easyocr): evaluate character accuracy and word correctness

Return ONLY valid JSON with this structure (no markdown fences):
{
  "pdf_type": "<detected type>",
  "complexity": "<simple|moderate|complex>",
  "parser_scores": {
    "<parser_name>": {
      "total_score": <0-100 integer>,
      "dimensions": {
        "text_completeness": <0-100>,
        "structure_preservation": <0-100>,
        "formatting_quality": <0-100>,
        "table_quality": <0-100>,
        "readability": <0-100>,
        "rag_suitability": <0-100>,
        "ocr_accuracy": <0-100>
      },
      "strengths": "<1-2 sentence strengths>",
      "weaknesses": "<1-2 sentence weaknesses>",
      "recommendation_tier": "<best|good|acceptable|poor>"
    }
  },
  "best_parser": "<parser_name>",
  "worst_parser": "<parser_name>",
  "recommendation": "<2-4 sentence explanation of best parser choice and why>",
  "pdf_type_recommendation": "<which parser is best for this PDF type in general and why>",
  "observations": "<3-5 sentences about the document structure, challenges, notable features>"
}
"""


@dataclass
class ParserAIScore:
    parser_name: str
    total_score: int
    dimensions: dict[str, int]
    strengths: str
    weaknesses: str
    recommendation_tier: str  # best | good | acceptable | poor


@dataclass
class PDFAIEvaluation:
    pdf_id: str
    pdf_type: str
    complexity: str
    parser_scores: dict[str, ParserAIScore]
    best_parser: str
    worst_parser: str
    recommendation: str
    pdf_type_recommendation: str
    observations: str
    raw_response: str = ""
    error: str = ""
    tokens_used: int = 0


class OpenAIScoringAgent:
    """
    Uses GPT-4o to deeply evaluate and compare PDF parser outputs.

    The agent receives structured metadata + extracted text snippets for each
    parser and returns scored, reasoned evaluations similar to a human expert.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        max_chars_per_parser: int = 8000,
    ) -> None:
        from openai import OpenAI  # type: ignore[import]

        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "OpenAI API key not found. Set the OPENAI_API_KEY environment variable."
            )

        self.client = OpenAI(api_key=resolved_key)
        self.model = model
        self.max_chars_per_parser = max_chars_per_parser

        logger.info(
            "openai_agent_init",
            event_type="openai_agent_init",
            stage="benchmark",
            log_category="metrics",
            model=model,
            status="info",
        )

    def evaluate(
        self,
        pdf_metadata: Any,  # PDFMetadata from pdf_analyzer
        extractions: dict[str, str],  # {parser_name: raw_text_full}
    ) -> PDFAIEvaluation:
        """
        Send metadata + extractions to GPT-4o and return a scored evaluation.

        Args:
            pdf_metadata: PDFMetadata object with structural facts
            extractions: dict of {parser_name: extracted_text}

        Returns:
            PDFAIEvaluation with per-parser scores and recommendations
        """
        pdf_id = pdf_metadata.pdf_id
        logger.info(
            "openai_eval_start",
            event_type="openai_eval_start",
            stage="benchmark",
            log_category="metrics",
            pdf_id=pdf_id,
            parsers=list(extractions.keys()),
            status="started",
        )

        user_content = self._build_user_prompt(pdf_metadata, extractions)

        t0 = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SCORING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,  # low temperature for consistent scoring
                response_format={"type": "json_object"},
            )
            duration_ms = int((time.perf_counter() - t0) * 1000)
            raw_json = response.choices[0].message.content or "{}"
            tokens = response.usage.total_tokens if response.usage else 0

            logger.info(
                "openai_eval_end",
                event_type="openai_eval_end",
                stage="benchmark",
                log_category="metrics",
                pdf_id=pdf_id,
                duration_ms=duration_ms,
                tokens_used=tokens,
                status="completed",
            )

            return self._parse_response(pdf_id, pdf_metadata.pdf_type, raw_json, tokens)

        except Exception as exc:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            import traceback as _tb

            logger.error(
                "openai_eval_error",
                event_type="openai_eval_error",
                stage="benchmark",
                log_category="errors",
                pdf_id=pdf_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
                duration_ms=duration_ms,
                traceback=_tb.format_exc(),
                status="failed",
            )
            return PDFAIEvaluation(
                pdf_id=pdf_id,
                pdf_type=pdf_metadata.pdf_type,
                complexity="unknown",
                parser_scores={},
                best_parser="",
                worst_parser="",
                recommendation="",
                pdf_type_recommendation="",
                observations="",
                error=str(exc),
            )

    def _build_user_prompt(self, pdf_metadata: Any, extractions: dict[str, str]) -> str:
        """Build the user message with metadata + extraction samples."""
        meta_dict = pdf_metadata.to_dict()
        # Remove large fields from prompt to save tokens
        meta_dict.pop("text_sample", None)

        sections = [
            "=== PDF METADATA ===",
            json.dumps(meta_dict, indent=2),
            "",
            "=== EXTRACTED TEXT BY PARSER ===",
        ]

        for parser_name, text in extractions.items():
            trimmed = text[: self.max_chars_per_parser].strip() if text else ""
            char_count = len(text or "")
            sections.append(
                f"\n--- {parser_name.upper()} ({char_count:,} total chars, showing first {len(trimmed):,}) ---"
            )
            sections.append(trimmed if trimmed else "[EMPTY — parser returned no text]")

        sections.append("")
        sections.append(
            "Evaluate each parser shown above. Return your JSON response now."
        )

        return "\n".join(sections)

    def _parse_response(
        self, pdf_id: str, pdf_type: str, raw_json: str, tokens: int
    ) -> PDFAIEvaluation:
        """Parse the JSON response from GPT-4o into a PDFAIEvaluation."""
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            return PDFAIEvaluation(
                pdf_id=pdf_id,
                pdf_type=pdf_type,
                complexity="unknown",
                parser_scores={},
                best_parser="",
                worst_parser="",
                recommendation="",
                pdf_type_recommendation="",
                observations="",
                raw_response=raw_json,
                error=f"JSON parse error: {e}",
                tokens_used=tokens,
            )

        parser_scores: dict[str, ParserAIScore] = {}
        for pname, pdata in data.get("parser_scores", {}).items():
            parser_scores[pname] = ParserAIScore(
                parser_name=pname,
                total_score=int(pdata.get("total_score", 0)),
                dimensions={k: int(v) for k, v in pdata.get("dimensions", {}).items()},
                strengths=pdata.get("strengths", ""),
                weaknesses=pdata.get("weaknesses", ""),
                recommendation_tier=pdata.get("recommendation_tier", ""),
            )

        return PDFAIEvaluation(
            pdf_id=pdf_id,
            pdf_type=data.get("pdf_type", pdf_type),
            complexity=data.get("complexity", "unknown"),
            parser_scores=parser_scores,
            best_parser=data.get("best_parser", ""),
            worst_parser=data.get("worst_parser", ""),
            recommendation=data.get("recommendation", ""),
            pdf_type_recommendation=data.get("pdf_type_recommendation", ""),
            observations=data.get("observations", ""),
            raw_response=raw_json,
            tokens_used=tokens,
        )
