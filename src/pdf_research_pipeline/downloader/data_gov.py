"""
src/pdf_research_pipeline/downloader/data_gov.py

Data.gov PDF catalog downloader.

Source: https://catalog.data.gov/dataset/?res_format=PDF
API:    https://catalog.data.gov/api/3/action/resource_search

Decision: Use the CKAN-compatible Data.gov API to search for PDF resources.
Returns resource URLs which are downloaded directly.
"""

from __future__ import annotations

import time
from typing import Any, Iterator

import requests

from pdf_research_pipeline.downloader.base import BaseDownloader, DownloadCandidate
from pdf_research_pipeline.logging_utils import get_logger

logger = get_logger(__name__)

_DATAGOV_API = "https://catalog.data.gov/api/3/action/resource_search"
_DELAY_SECONDS = 1.0


class DataGovDownloader(BaseDownloader):
    """Downloads PDF resources from the Data.gov CKAN catalog."""

    source_name = "data_gov"

    def list_candidates(self) -> Iterator[DownloadCandidate]:
        api_url = self.config.get("api_url", _DATAGOV_API)
        pdf_types: list[str] = self.config.get("pdf_types", ["true_digital_pdf"])
        per_type = max(1, self.limit_per_type)

        logger.info(
            "datagov_search_start",
            event_type="datagov_search_start",
            stage="download",
            log_category="download",
            source_name=self.source_name,
            limit=per_type,
            status="started",
        )

        try:
            params: dict[str, Any] = {
                "query": "format:PDF",
                "limit": per_type,
                "offset": 0,
            }
            resp = requests.get(
                api_url,
                params=params,
                timeout=self.timeout_seconds,
                headers={"User-Agent": "pdf-research-pipeline/0.1"},
            )
            resp.raise_for_status()
            data = resp.json()
            resources = data.get("result", {}).get("results", [])

            logger.info(
                "datagov_search_response",
                event_type="datagov_search_response",
                stage="download",
                log_category="download",
                source_name=self.source_name,
                resources_found=len(resources),
                status="received",
            )

            for i, resource in enumerate(resources):
                url = resource.get("url", "")
                if not url or not url.lower().endswith(".pdf"):
                    continue

                filename = f"datagov_{i:04d}_{url.split('/')[-1]}"
                if not filename.lower().endswith(".pdf"):
                    filename += ".pdf"

                # Assign PDF type round-robin across configured types
                pdf_type = pdf_types[i % len(pdf_types)]

                yield DownloadCandidate(
                    url=url,
                    filename=filename,
                    pdf_type=pdf_type,
                    source_name=self.source_name,
                    subfolder="",
                    extra={
                        "datagov_id": resource.get("id", ""),
                        "title": resource.get("name", ""),
                    },
                )
                time.sleep(_DELAY_SECONDS)

        except Exception as exc:
            logger.error(
                "datagov_search_error",
                event_type="datagov_search_error",
                stage="download",
                log_category="errors",
                source_name=self.source_name,
                error_type=type(exc).__name__,
                error_message=str(exc),
                status="failed",
            )
