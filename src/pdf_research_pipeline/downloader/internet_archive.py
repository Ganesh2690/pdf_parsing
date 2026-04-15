"""
src/pdf_research_pipeline/downloader/internet_archive.py

Internet Archive downloader adapter.

Source: https://archive.org/details/texts
API:    https://archive.org/advancedsearch.php

Decision: The Internet Archive Advanced Search API returns JSON metadata.
We search for items with mediatype=texts and format=PDF, then download
the first available PDF file per item.

Rate-limiting: IA allows reasonable crawling. We insert a 1-second delay
between item downloads to be polite.
"""

from __future__ import annotations

import time
from typing import Any, Iterator

import requests

from pdf_research_pipeline.downloader.base import BaseDownloader, DownloadCandidate
from pdf_research_pipeline.logging_utils import get_logger

logger = get_logger(__name__)

_IA_SEARCH_URL = "https://archive.org/advancedsearch.php"
_IA_DOWNLOAD_BASE = "https://archive.org/download"
_IA_METADATA_BASE = "https://archive.org/metadata"
_DELAY_SECONDS = 1.5


class InternetArchiveDownloader(BaseDownloader):
    """
    Downloads scanned/OCR'd PDFs from the Internet Archive.

    Yields PDFs classified as:
      - image_only_scanned_pdf
      - searchable_image_pdf (if OCR layer detected)
    """

    source_name = "internet_archive"

    def list_candidates(self) -> Iterator[DownloadCandidate]:
        collections: list[str] = self.config.get("collections", ["texts"])
        per_collection = max(1, self.limit_per_type // max(len(collections), 1))

        for collection in collections:
            yielded = 0
            try:
                for candidate in self._search_collection(collection, per_collection):
                    if yielded >= per_collection:
                        break
                    yield candidate
                    yielded += 1
                    time.sleep(_DELAY_SECONDS)
            except Exception as exc:
                logger.warning(
                    "ia_collection_error",
                    event_type="ia_collection_error",
                    stage="download",
                    log_category="errors",
                    source_name=self.source_name,
                    collection=collection,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    status="failed",
                )

    def _search_collection(
        self, collection: str, max_results: int
    ) -> Iterator[DownloadCandidate]:
        """
        Query Internet Archive search API for PDF items in a collection.
        """
        params: dict[str, Any] = {
            "q": f"collection:{collection} AND mediatype:texts AND format:PDF",
            "fl[]": ["identifier", "title", "format"],
            "rows": max_results,
            "page": 1,
            "output": "json",
        }

        logger.info(
            "ia_search_request",
            event_type="ia_search_request",
            stage="download",
            log_category="download",
            source_name=self.source_name,
            collection=collection,
            max_results=max_results,
            status="requesting",
        )

        resp = requests.get(
            _IA_SEARCH_URL,
            params=params,
            timeout=self.timeout_seconds,
            headers={"User-Agent": "pdf-research-pipeline/0.1"},
        )
        resp.raise_for_status()
        data = resp.json()
        docs = data.get("response", {}).get("docs", [])

        logger.info(
            "ia_search_response",
            event_type="ia_search_response",
            stage="download",
            log_category="download",
            source_name=self.source_name,
            collection=collection,
            docs_returned=len(docs),
            status="received",
        )

        for doc in docs:
            identifier = doc.get("identifier", "")
            if not identifier:
                continue

            pdf_url, filename = self._find_pdf_url(identifier)
            if not pdf_url:
                continue

            # Decision: classify as image_only unless we can confirm a text layer
            pdf_type_list: list[str] = self.config.get(
                "pdf_types", ["image_only_scanned_pdf"]
            )
            pdf_type = pdf_type_list[0]
            subfolder = self.config.get("subfolders", {}).get(pdf_type, "")

            yield DownloadCandidate(
                url=pdf_url,
                filename=filename,
                pdf_type=pdf_type,
                source_name=self.source_name,
                subfolder=subfolder,
                extra={"ia_identifier": identifier, "collection": collection},
            )

    def _find_pdf_url(self, identifier: str) -> tuple[str, str]:
        """
        Fetch the item metadata to find the direct PDF download URL.
        Returns (url, filename) or ("", "") if not found.
        """
        try:
            meta_url = f"{_IA_METADATA_BASE}/{identifier}"
            resp = requests.get(
                meta_url,
                timeout=self.timeout_seconds,
                headers={"User-Agent": "pdf-research-pipeline/0.1"},
            )
            resp.raise_for_status()
            data = resp.json()
            files = data.get("files", [])
            for f in files:
                name = f.get("name", "")
                if name.lower().endswith(".pdf"):
                    url = f"{_IA_DOWNLOAD_BASE}/{identifier}/{name}"
                    return url, name
        except Exception as exc:
            logger.warning(
                "ia_metadata_error",
                event_type="ia_metadata_error",
                stage="download",
                log_category="errors",
                source_name=self.source_name,
                ia_identifier=identifier,
                error_message=str(exc),
                status="failed",
            )
        return "", ""
