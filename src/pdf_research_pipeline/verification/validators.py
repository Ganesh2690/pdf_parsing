"""
src/pdf_research_pipeline/verification/validators.py

Validates ParseResult objects to catch crashes, empty outputs, suspicious
short text, page count mismatches, and hash regressions.

Decision: Validators produce ValidationResult objects rather than raising
exceptions so callers can aggregate failures and keep running.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pdf_research_pipeline.logging_utils import get_logger
from pdf_research_pipeline.parsers.base import ParseResult

logger = get_logger(__name__)


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    code: str
    severity: Severity
    message: str
    detail: Optional[str] = None


@dataclass
class ValidationResult:
    pdf_id: str
    parser_name: str
    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]


# Minimum text length considered non-suspicious (chars per page)
_MIN_CHARS_PER_PAGE = 10
# Minimum absolute text length for a document
_MIN_TEXT_LENGTH = 20


class ParseResultValidator:
    """
    Runs sanity checks on a ParseResult.

    Checks:
    1. crash_free       — result.error_message must be None
    2. non_empty_text   — raw_text_full must have some content
    3. min_text_length  — text should not be suspiciously short
    4. page_count_match — detected page count should be > 0
    5. tables_detected  — warn if pdf_type implies tables but none found
    6. hash_stable      — if a previous hash is supplied, compare it
    """

    def validate(
        self,
        result: ParseResult,
        previous_hash: Optional[str] = None,
        pdf_type: Optional[str] = None,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []

        # 1. Crash-free
        if result.error_message:
            issues.append(
                ValidationIssue(
                    code="PARSER_CRASH",
                    severity=Severity.ERROR,
                    message="Parser terminated with an error",
                    detail=result.error_message,
                )
            )

        # 2. Non-empty text
        if not result.raw_text_full.strip():
            issues.append(
                ValidationIssue(
                    code="EMPTY_TEXT",
                    severity=Severity.ERROR,
                    message="Extracted text is empty",
                )
            )

        # 3. Suspiciously short text
        elif len(result.raw_text_full) < _MIN_TEXT_LENGTH:
            issues.append(
                ValidationIssue(
                    code="SUSPICIOUS_SHORT_TEXT",
                    severity=Severity.WARNING,
                    message="Extracted text is suspiciously short",
                    detail=f"Length={len(result.raw_text_full)} chars",
                )
            )
        elif result.page_count_detected and result.page_count_detected > 0:
            chars_per_page = len(result.raw_text_full) / result.page_count_detected
            if chars_per_page < _MIN_CHARS_PER_PAGE:
                issues.append(
                    ValidationIssue(
                        code="LOW_TEXT_DENSITY",
                        severity=Severity.WARNING,
                        message="Low text density — possible OCR miss or image-only pages",
                        detail=f"{chars_per_page:.1f} chars/page",
                    )
                )

        # 4. Page count
        if not result.page_count_detected or result.page_count_detected == 0:
            issues.append(
                ValidationIssue(
                    code="ZERO_PAGE_COUNT",
                    severity=Severity.ERROR,
                    message="Detected page count is 0 or missing",
                )
            )

        # 5. Tables expected
        TABLE_TYPES = {
            "native_digital_pdf",
            "complex_layout_pdf",
            "government_report_pdf",
        }
        if pdf_type in TABLE_TYPES and not result.tables:
            issues.append(
                ValidationIssue(
                    code="TABLES_NOT_FOUND",
                    severity=Severity.WARNING,
                    message=f"No tables extracted for {pdf_type} — tables were expected",
                )
            )

        # 6. Hash regression
        if previous_hash and result.output_hash != previous_hash:
            issues.append(
                ValidationIssue(
                    code="HASH_CHANGED",
                    severity=Severity.WARNING,
                    message="Output hash changed since last run",
                    detail=f"previous={previous_hash} current={result.output_hash}",
                )
            )

        passed = all(i.severity != Severity.ERROR for i in issues)

        vr = ValidationResult(
            pdf_id=result.pdf_id,
            parser_name=result.parser_name,
            passed=passed,
            issues=issues,
        )

        log_level = "info" if passed else "warning"
        getattr(logger, log_level)(
            "validation_result",
            event_type="validation_result",
            stage="verification",
            log_category="verification",
            pdf_id=result.pdf_id,
            parser_name=result.parser_name,
            passed=passed,
            error_count=len(vr.errors),
            warning_count=len(vr.warnings),
            issue_codes=[i.code for i in issues],
            status="completed",
        )

        return vr
