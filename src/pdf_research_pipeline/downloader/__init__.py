"""
src/pdf_research_pipeline/downloader/__init__.py
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pdf_research_pipeline.downloader.base import BaseDownloader


def build_downloaders(cfg: Any) -> list["BaseDownloader"]:
    """
    Instantiate all enabled downloaders from config.
    Returns an empty list for disabled sources.
    """
    from pdf_research_pipeline.downloader.arxiv import ArXivDownloader
    from pdf_research_pipeline.downloader.internet_archive import (
        InternetArchiveDownloader,
    )
    from pdf_research_pipeline.downloader.funsd import FUNSDDownloader
    from pdf_research_pipeline.downloader.data_gov import DataGovDownloader
    from pdf_research_pipeline.downloader.loc_gov import LOCGovDownloader
    from pdf_research_pipeline.downloader.placeholder import PlaceholderDownloader

    sources_cfg = (
        cfg.get_enabled_sources() if hasattr(cfg, "get_enabled_sources") else {}
    )
    data_dir = cfg.pipeline.data_root if hasattr(cfg, "pipeline") else "data"

    raw_root = str(Path(data_dir) / "raw")
    catalog_path = str(Path(data_dir) / "catalog" / "pdf_catalog.jsonl")
    # Ensure catalog directory exists
    Path(catalog_path).parent.mkdir(parents=True, exist_ok=True)

    _REGISTRY = {
        "arxiv": ArXivDownloader,
        "internet_archive": InternetArchiveDownloader,
        "funsd": FUNSDDownloader,
        "data_gov": DataGovDownloader,
        "loc_gov": LOCGovDownloader,
    }
    _PLACEHOLDER_SOURCES = {"doclaynet", "open_rag_bench", "rvl_cdip", "kg_rag"}

    downloaders: list[BaseDownloader] = []
    for name, source_cfg in sources_cfg.items():
        enabled = (
            source_cfg.get("enabled", False)
            if isinstance(source_cfg, dict)
            else getattr(source_cfg, "enabled", False)
        )
        if not enabled:
            continue
        # Use the "adapter" field if present so a source like "arxiv_math"
        # with adapter="arxiv" correctly resolves to ArXivDownloader.
        adapter_key = (
            source_cfg.get("adapter", name)
            if isinstance(source_cfg, dict)
            else getattr(source_cfg, "adapter", name)
        )
        if name in _PLACEHOLDER_SOURCES or adapter_key == "placeholder":
            downloaders.append(
                PlaceholderDownloader(
                    raw_root=raw_root, catalog_path=catalog_path, config=source_cfg
                )
            )
        elif adapter_key in _REGISTRY:
            downloaders.append(
                _REGISTRY[adapter_key](
                    raw_root=raw_root, catalog_path=catalog_path, config=source_cfg
                )
            )
    return downloaders
