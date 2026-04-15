"""
src/pdf_research_pipeline/downloader/arxiv.py

arXiv downloader adapter.

Sources: arXiv open-access bulk data (https://info.arxiv.org/help/bulk_data.html)
         arXiv API (https://export.arxiv.org/api/query)

Decision: Use the arXiv HTTP API (no authentication required) to search for
papers matching configured query terms. Download PDFs directly from
https://arxiv.org/pdf/<arxiv_id>.

PDF types produced:
  - true_digital_pdf     (most arXiv papers)
  - complex_layout_pdf   (multi-column LaTeX papers)

Rate-limiting: arXiv API allows 1 request per 3 seconds without a key.
We insert a 3-second delay between API requests to be respectful.
"""

from __future__ import annotations

import time
from typing import Any, Iterator

import requests

from pdf_research_pipeline.downloader.base import BaseDownloader, DownloadCandidate
from pdf_research_pipeline.logging_utils import get_logger

logger = get_logger(__name__)

_ARXIV_API_BASE = "https://export.arxiv.org/api/query"
_ARXIV_PDF_BASE = "https://arxiv.org/pdf"
_API_DELAY_SECONDS = 3.1  # arXiv polite crawling rate


class ArXivDownloader(BaseDownloader):
    """
    Downloads research papers from arXiv via the public HTTP API.

    Config keys (from sources.yaml):
      search_queries: list of query strings
      limit_per_type: max PDFs to download per type
      max_retries, timeout_seconds
    """

    source_name = "arxiv"

    def list_candidates(self) -> Iterator[DownloadCandidate]:
        queries: list[str] = self.config.get("search_queries", ["machine learning"])
        per_query = max(1, self.limit_per_type // max(len(queries), 1))
        yielded = 0

        for query in queries:
            if yielded >= self.limit_per_type:
                break
            try:
                yield from self._query_arxiv(query, max_results=per_query)
                yielded += per_query
            except Exception as exc:
                logger.warning(
                    "arxiv_query_error",
                    event_type="arxiv_query_error",
                    stage="download",
                    log_category="errors",
                    source_name=self.source_name,
                    query=query,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    status="failed",
                )
            time.sleep(_API_DELAY_SECONDS)

    def _query_arxiv(self, query: str, max_results: int) -> Iterator[DownloadCandidate]:
        """
        Query arXiv API and yield DownloadCandidates.

        Decision: Use XML Atom feed from arXiv API. Parse with stdlib xml.etree.
        No external XML library required.
        """
        import xml.etree.ElementTree as ET

        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
        }

        logger.info(
            "arxiv_api_request",
            event_type="arxiv_api_request",
            stage="download",
            log_category="download",
            source_name=self.source_name,
            query=query,
            max_results=max_results,
            status="requesting",
        )

        resp = requests.get(
            _ARXIV_API_BASE,
            params=params,  # type: ignore[arg-type]
            timeout=self.timeout_seconds,
            headers={"User-Agent": "pdf-research-pipeline/0.1"},
        )
        resp.raise_for_status()

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.text)
        entries = root.findall("atom:entry", ns)

        logger.info(
            "arxiv_api_response",
            event_type="arxiv_api_response",
            stage="download",
            log_category="download",
            source_name=self.source_name,
            query=query,
            entries_returned=len(entries),
            status="received",
        )

        for entry in entries:
            arxiv_id_raw = entry.findtext("atom:id", default="", namespaces=ns)
            arxiv_id = arxiv_id_raw.split("/abs/")[-1].replace("/", "_")
            if not arxiv_id:
                continue

            pdf_url = f"{_ARXIV_PDF_BASE}/{arxiv_id}"
            filename = f"{arxiv_id}.pdf"

            # Classify as complex_layout (multi-column LaTeX) or true_digital
            # Decision: arXiv papers tend to use two-column LaTeX — complex_layout
            # is the better classification for benchmark coverage.
            pdf_type = self.config.get("pdf_types", ["complex_layout_pdf"])[0]
            subfolder = self.config.get("subfolders", {}).get(pdf_type, "arxiv")

            yield DownloadCandidate(
                url=pdf_url,
                filename=filename,
                pdf_type=pdf_type,
                source_name=self.source_name,
                subfolder=subfolder,
                extra={"arxiv_id": arxiv_id, "query": query},
            )
