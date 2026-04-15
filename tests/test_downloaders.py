"""
tests/test_downloaders.py

Unit tests for the downloader layer.
All HTTP calls are mocked via pytest-mock / responses.
"""

from __future__ import annotations

import hashlib
import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pdf_research_pipeline.downloader.base import BaseDownloader, DownloadCandidate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_data_dir(tmp_path: Path) -> Path:
    (tmp_path / "pdfs").mkdir(parents=True)
    (tmp_path / "catalog.jsonl").write_text("")
    return tmp_path


@pytest.fixture()
def fake_pdf_bytes() -> bytes:
    """Minimal PDF-1.4 bytes that PyMuPDF can open (1 empty page)."""
    content = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n190\n%%EOF"
    )
    return content


# ---------------------------------------------------------------------------
# BaseDownloader
# ---------------------------------------------------------------------------


class ConcreteDownloader(BaseDownloader):
    """Minimal concrete subclass for testing the base class."""

    def __init__(self, candidates, **kwargs):
        super().__init__(**kwargs)
        self._candidates = candidates

    def _iter_candidates(self):
        yield from self._candidates


def test_base_downloader_skips_existing(tmp_data_dir, fake_pdf_bytes):
    """If file already exists with matching hash, skip download."""
    pdf_path = tmp_data_dir / "pdfs" / "test_skip_existing.pdf"
    pdf_path.write_bytes(fake_pdf_bytes)
    checksum = hashlib.sha256(fake_pdf_bytes).hexdigest()

    candidate = DownloadCandidate(
        url="https://example.com/test.pdf",
        pdf_id="test_skip_existing",
        pdf_type="native_digital_pdf",
        expected_checksum=checksum,
    )

    dl = ConcreteDownloader(
        candidates=[candidate],
        source_name="test",
        data_dir=str(tmp_data_dir),
        config={},
    )

    with patch.object(dl, "_stream_download", wraps=dl._stream_download) as mock_dl:
        dl.run()
        mock_dl.assert_not_called()


def test_base_downloader_writes_catalog(tmp_data_dir, fake_pdf_bytes):
    """Successful download appends a record to catalog.jsonl."""
    import json

    candidate = DownloadCandidate(
        url="https://example.com/test_catalog.pdf",
        pdf_id="catalog_test",
        pdf_type="native_digital_pdf",
        expected_checksum=None,
    )

    dl = ConcreteDownloader(
        candidates=[candidate],
        source_name="test",
        data_dir=str(tmp_data_dir),
        config={},
    )

    with patch.object(dl, "_stream_download", return_value=fake_pdf_bytes):
        with patch.object(dl, "_count_pages", return_value=1):
            with patch.object(dl, "_detect_language", return_value="en"):
                dl.run()

    catalog = (tmp_data_dir / "catalog.jsonl").read_text().strip().splitlines()
    assert len(catalog) == 1
    record = json.loads(catalog[0])
    assert record["pdf_id"] == "catalog_test"
    assert "checksum_sha256" in record


def test_sha256_checksum_mismatch_raises(tmp_data_dir, fake_pdf_bytes):
    """Checksum mismatch should log an error and not write the file."""
    candidate = DownloadCandidate(
        url="https://example.com/test_bad_hash.pdf",
        pdf_id="bad_hash_test",
        pdf_type="native_digital_pdf",
        expected_checksum="0" * 64,  # deliberately wrong
    )

    dl = ConcreteDownloader(
        candidates=[candidate],
        source_name="test",
        data_dir=str(tmp_data_dir),
        config={},
    )

    with patch.object(dl, "_stream_download", return_value=fake_pdf_bytes):
        dl.run()

    pdf_path = tmp_data_dir / "pdfs" / "bad_hash_test.pdf"
    assert not pdf_path.exists(), "File should not be written on checksum mismatch"


# ---------------------------------------------------------------------------
# arXiv downloader
# ---------------------------------------------------------------------------


def test_arxiv_parse_atom_feed():
    """ArXivDownloader._parse_feed returns candidate URLs from valid Atom XML."""
    from pdf_research_pipeline.downloader.arxiv import ArXivDownloader

    atom_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>Sample paper</title>
    <link rel="related" href="http://arxiv.org/pdf/2301.00001v1"/>
  </entry>
</feed>"""

    dl = ArXivDownloader.__new__(ArXivDownloader)
    candidates = list(dl._parse_feed(atom_xml))
    assert len(candidates) == 1
    assert "2301.00001" in candidates[0].pdf_id
