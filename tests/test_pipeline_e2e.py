"""
tests/test_pipeline_e2e.py

End-to-end smoke test: download (mocked) → parse → benchmark → verify.
Uses a real minimal PDF so all parsing calls are genuine.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(scope="module")
def e2e_workspace(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("e2e")
    (root / "pdfs").mkdir()
    (root / "parsed").mkdir()
    (root / "reports").mkdir()
    (root / "artifacts").mkdir()
    (root / "catalog.jsonl").write_text("")
    return root


@pytest.fixture(scope="module")
def sample_pdf(e2e_workspace: Path) -> Path:
    pdf_path = e2e_workspace / "pdfs" / "e2e_sample.pdf"
    try:
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 100), "End-to-end test document. Page one.", fontsize=12)
        doc.save(str(pdf_path))
        doc.close()
    except ImportError:
        pdf_path.write_bytes(
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f \n"
            b"0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
            b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
        )
    # Write catalog entry
    catalog_path = e2e_workspace / "catalog.jsonl"
    with open(catalog_path, "a") as f:
        f.write(
            json.dumps(
                {
                    "pdf_id": "e2e_sample",
                    "local_path": str(pdf_path),
                    "detected_pdf_type": "native_digital_pdf",
                    "source_name": "test",
                    "page_count": 1,
                }
            )
            + "\n"
        )
    return pdf_path


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("fitz"),
    reason="PyMuPDF not installed",
)
def test_e2e_parse_benchmark_verify(e2e_workspace, sample_pdf):
    """Parse with pymupdf → score → verify. All steps should succeed."""
    from pdf_research_pipeline.parsers.pymupdf_parser import PyMuPDFParser
    from pdf_research_pipeline.benchmark.scorer import ParserScorer
    from pdf_research_pipeline.benchmark.selector import ParserSelector
    from pdf_research_pipeline.verification import OutputDiffer

    # Parse
    parser = PyMuPDFParser()
    result = parser.run(
        pdf_path=str(sample_pdf),
        pdf_id="e2e_sample",
        pdf_type="native_digital_pdf",
        output_base_dir=str(e2e_workspace / "parsed"),
    )
    assert result.page_count_detected >= 1
    assert result.error_message is None

    # Score — use a minimal ScoringConfig stub
    scoring_cfg = MagicMock()
    scoring_cfg.weights = {}
    scoring_cfg.score_thresholds = {"recommended": 80, "acceptable": 65, "marginal": 40}
    scoring_cfg.pdf_type_weights = {}

    scorer = ParserScorer(scoring_cfg)
    score = scorer.score(result)
    assert score.total_score >= 0

    # Selector — build aggregated scores and write reports
    selector = ParserSelector(str(e2e_workspace / "reports"))
    aggregated = selector.aggregate([("native_digital_pdf", "pymupdf", score)])
    selections = selector.select(aggregated)
    selector.write_reports(aggregated, selections)

    rec_md = e2e_workspace / "reports" / "parser_recommendations.md"
    assert rec_md.exists()
    assert "pymupdf" in rec_md.read_text()

    # Verify
    differ = OutputDiffer(str(e2e_workspace / "reports"))
    vr = differ.add("e2e_sample", "native_digital_pdf", "pymupdf", result)
    differ.write_reports()

    summary = e2e_workspace / "reports" / "verification_summary.md"
    assert summary.exists()
    assert "e2e_sample" in summary.read_text()
