"""
src/pdf_research_pipeline/downloader/loc_gov.py

Library of Congress .gov PDF dataset downloader.

Source: https://www.loc.gov/item/2020445568/
Note: This is the LoC curated 1,000 .gov PDFs dataset.

Decision: The LoC dataset page lists PDF URLs. We scrape the item page
to find resource links. This is a best-effort adapter; actual link discovery
depends on the page structure at the time of download.

If direct link parsing fails, we fall back to a placeholder warning.
"""

from __future__ import annotations

from typing import Iterator

import requests

from pdf_research_pipeline.downloader.base import BaseDownloader, DownloadCandidate
from pdf_research_pipeline.logging_utils import get_logger

logger = get_logger(__name__)

_LOC_ITEM_URL = "https://www.loc.gov/item/2020445568/"


class LOCGovDownloader(BaseDownloader):
    """
    Downloads PDFs from the Library of Congress 1,000 .gov PDF dataset.

    TODO: Implement full link extraction from the LoC catalog page.
    This is a best-effort adapter — the exact CSV/manifest URL may change.
    Currently attempts to find PDF links on the item page.
    """

    source_name = "loc_gov"

    def list_candidates(self) -> Iterator[DownloadCandidate]:
        collection_url: str = self.config.get("collection_url", _LOC_ITEM_URL)
        pdf_types: list[str] = self.config.get("pdf_types", ["true_digital_pdf"])

        logger.warning(
            "loc_gov_partial_implementation",
            event_type="loc_gov_partial_implementation",
            stage="download",
            log_category="download",
            source_name=self.source_name,
            observation=(
                "LoC .gov PDF dataset requires browsing the item page and finding "
                "the actual data manifest URL. This adapter does a best-effort "
                "scrape. For reliable access, download manually from: " + collection_url
            ),
            decision="attempt_page_scrape",
            decision_reason="No stable direct download API available; page scrape is best-effort",
            status="warning",
        )

        try:
            resp = requests.get(
                collection_url,
                timeout=self.timeout_seconds,
                headers={"User-Agent": "pdf-research-pipeline/0.1"},
            )
            resp.raise_for_status()

            # Simple link extraction — find .pdf hrefs
            import re

            pdf_links = re.findall(
                r'href=["\']([^"\']+\.pdf)["\']', resp.text, re.IGNORECASE
            )
            pdf_links = list(dict.fromkeys(pdf_links))  # deduplicate, preserve order

            logger.info(
                "loc_gov_links_found",
                event_type="loc_gov_links_found",
                stage="download",
                log_category="download",
                source_name=self.source_name,
                links_found=len(pdf_links),
                status="found",
            )

            for i, link in enumerate(pdf_links[: self.limit_per_type]):
                # Make absolute URL if relative
                if link.startswith("/"):
                    link = "https://www.loc.gov" + link

                filename = f"loc_gov_{i:04d}_{link.split('/')[-1]}"
                pdf_type = pdf_types[i % len(pdf_types)]

                yield DownloadCandidate(
                    url=link,
                    filename=filename,
                    pdf_type=pdf_type,
                    source_name=self.source_name,
                    subfolder="",
                    extra={"loc_item": collection_url},
                )

        except Exception as exc:
            logger.error(
                "loc_gov_scrape_failed",
                event_type="loc_gov_scrape_failed",
                stage="download",
                log_category="errors",
                source_name=self.source_name,
                error_type=type(exc).__name__,
                error_message=str(exc),
                # TODO: Implement a more robust manifest-based download
                next_action="Manually download the dataset from " + collection_url,
                status="failed",
            )
