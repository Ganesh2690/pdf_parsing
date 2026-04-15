"""
src/pdf_research_pipeline/downloader/placeholder.py

Placeholder adapter for sources that require nontrivial access patterns.

Per prompt.md section 17:
  "If a source is difficult to automate or requires a nontrivial access pattern,
   implement a placeholder adapter with a clear TODO, a logged warning, a clean
   interface, and an example of how it should be extended."

Used by: DocLayNet, Open RAG Bench, RVL-CDIP, KG-RAG.
"""

from __future__ import annotations

from typing import Iterator

from pdf_research_pipeline.downloader.base import BaseDownloader, DownloadCandidate
from pdf_research_pipeline.logging_utils import get_logger

logger = get_logger(__name__)


class PlaceholderDownloader(BaseDownloader):
    """
    Placeholder for sources that require manual download or gated access.

    To extend this into a real adapter:
      1. Subclass PlaceholderDownloader (or BaseDownloader directly).
      2. Override list_candidates() to yield DownloadCandidate objects.
      3. Set source_name to the new source identifier.
      4. Add the new adapter to the source registry in cli.py.

    Example extension for DocLayNet:
        class DocLayNetDownloader(BaseDownloader):
            source_name = "doclaynet"
            def list_candidates(self) -> Iterator[DownloadCandidate]:
                # Download from HuggingFace Hub using huggingface_hub library
                from huggingface_hub import hf_hub_download
                # ... yield candidates from DocLayNet dataset files
    """

    source_name = "placeholder"

    def list_candidates(self) -> Iterator[DownloadCandidate]:
        notes: str = self.config.get("notes", "No implementation notes provided.")
        source_display = self.config.get("adapter", "unknown")

        logger.warning(
            "placeholder_source_skipped",
            event_type="placeholder_source_skipped",
            stage="download",
            log_category="download",
            source_name=source_display,
            observation="This source has no automated download implementation.",
            decision="skip",
            decision_reason=(
                "Source requires gated access, manual download, or a non-trivial "
                "access pattern that is not yet implemented."
            ),
            notes=notes,
            # TODO: Implement this source adapter — see class docstring above.
            status="skipped",
        )
        return iter([])  # yields nothing
