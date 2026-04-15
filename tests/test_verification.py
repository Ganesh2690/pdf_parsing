"""
tests/test_verification.py

Unit tests for the verification layer: validators and diffing.
"""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock

import pytest

from pdf_research_pipeline.parsers.base import ParseResult
from pdf_research_pipeline.verification.validators import (
    ParseResultValidator,
    Severity,
    ValidationIssue,
)
from pdf_research_pipeline.verification.diffing import OutputDiffer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(**kwargs) -> ParseResult:
    defaults = dict(
        pdf_id="test_pdf",
        parser_name="pymupdf",
        raw_text_full="Sample text with enough content to pass basic validation checks.",
        pages=[],
        tables=[],
        page_count_detected=1,
        duration_ms=100.0,
        output_hash=hashlib.sha256(b"Sample text").hexdigest(),
        error_message=None,
    )
    defaults.update(kwargs)
    return ParseResult(**defaults)


# ---------------------------------------------------------------------------
# ParseResultValidator
# ---------------------------------------------------------------------------


def test_validator_passes_good_result():
    vr = ParseResultValidator().validate(_make_result())
    assert vr.passed is True
    assert len(vr.errors) == 0


def test_validator_flags_crash():
    result = _make_result(error_message="Segfault", raw_text_full="")
    vr = ParseResultValidator().validate(result)
    assert not vr.passed
    codes = [i.code for i in vr.issues]
    assert "PARSER_CRASH" in codes


def test_validator_flags_empty_text():
    result = _make_result(raw_text_full="   ")
    vr = ParseResultValidator().validate(result)
    assert not vr.passed
    codes = [i.code for i in vr.issues]
    assert "EMPTY_TEXT" in codes


def test_validator_warns_hash_changed():
    result = _make_result()
    old_hash = "a" * 64
    vr = ParseResultValidator().validate(result, previous_hash=old_hash)
    codes = [i.code for i in vr.issues]
    assert "HASH_CHANGED" in codes
    # Hash change is a warning, not an error — should still pass
    assert vr.passed is True


def test_validator_warns_tables_expected_but_missing():
    result = _make_result(tables=[])
    vr = ParseResultValidator().validate(result, pdf_type="native_digital_pdf")
    codes = [i.code for i in vr.issues]
    assert "TABLES_NOT_FOUND" in codes


def test_validator_zero_pages():
    result = _make_result(page_count_detected=0)
    vr = ParseResultValidator().validate(result)
    assert not vr.passed
    codes = [i.code for i in vr.issues]
    assert "ZERO_PAGE_COUNT" in codes


# ---------------------------------------------------------------------------
# OutputDiffer
# ---------------------------------------------------------------------------


def test_differ_accumulates_results(tmp_path):
    differ = OutputDiffer(str(tmp_path / "reports"))

    r1 = _make_result(pdf_id="doc1", parser_name="pymupdf")
    r2 = _make_result(pdf_id="doc1", parser_name="pdfplumber")

    differ.add("doc1", "native_digital_pdf", "pymupdf", r1)
    differ.add("doc1", "native_digital_pdf", "pdfplumber", r2)
    differ.write_reports()

    summary = tmp_path / "reports" / "verification_summary.md"
    assert summary.exists()
    content = summary.read_text()
    assert "doc1" in content
    assert "Total validated: **2**" in content


def test_differ_failed_report_written_on_error(tmp_path):
    differ = OutputDiffer(str(tmp_path / "reports"))
    result = _make_result(raw_text_full="", error_message="crash")
    differ.add("bad_doc", "native_digital_pdf", "pymupdf", result)
    differ.write_reports()

    failed = tmp_path / "reports" / "failed_files_report.md"
    assert failed.exists()
    assert "bad_doc" in failed.read_text()


def test_diff_two_identical(tmp_path):
    differ = OutputDiffer(str(tmp_path / "reports"))
    r = _make_result()
    diff = differ.diff_two(r, r)
    assert diff["text_similarity_ratio"] == 1.0
    assert diff["structural_diff"] == {}


def test_diff_two_different_page_counts(tmp_path):
    differ = OutputDiffer(str(tmp_path / "reports"))
    r1 = _make_result(page_count_detected=1)
    r2 = _make_result(page_count_detected=5)
    diff = differ.diff_two(r1, r2)
    assert diff["structural_diff"] != {}
