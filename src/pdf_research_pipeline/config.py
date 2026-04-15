"""
src/pdf_research_pipeline/config.py

Loads and merges all YAML config files into validated pydantic settings objects.
All pipeline code accesses configuration exclusively through this module.

Decision record:
  - Use pydantic v2 models for type-safe config access with clear validation errors.
  - Load order: pipeline.yaml → sources.yaml → parsers.yaml → logging.yaml → scoring.yaml
  - Environment variables override YAML via pydantic-settings BaseSettings.
  - Config is loaded once at startup and cached as a module-level singleton.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------


class LogFileConfig(BaseModel):
    path: str
    level: str = "INFO"
    description: str = ""


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"
    include_timestamp: bool = True
    include_run_id: bool = True
    include_hostname: bool = False
    include_pid: bool = True
    log_files: dict[str, LogFileConfig] = Field(default_factory=dict)
    console_enabled: bool = True
    console_level: str = "INFO"
    console_format: str = "text"
    colorize: bool = True
    required_fields: list[str] = Field(default_factory=list)
    forbidden_fields: list[str] = Field(default_factory=list)


class PageCountTargets(BaseModel):
    very_small: int = 2
    short: int = 3
    medium: int = 3
    long: int = 2
    very_long: int = 1


class SourceConfig(BaseModel):
    enabled: bool = True
    adapter: str
    pdf_types: list[str] = Field(default_factory=list)
    subfolders: dict[str, str] = Field(default_factory=dict)
    limit_per_type: int = 10
    max_retries: int = 3
    timeout_seconds: int = 60
    notes: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class ParserConfig(BaseModel):
    enabled: bool = True
    module: str
    class_name: str = Field(alias="class", default="")
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow", "populate_by_name": True}


class ParsersConfig(BaseModel):
    parsers: dict[str, dict[str, Any]] = Field(default_factory=dict)
    pdf_type_hints: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ScoringWeights(BaseModel):
    text_completeness: float = 0.20
    heading_preservation: float = 0.10
    paragraph_preservation: float = 0.10
    table_extraction_quality: float = 0.10
    page_ordering_quality: float = 0.10
    ocr_quality: float = 0.08
    coordinate_richness: float = 0.07
    speed: float = 0.05
    memory_usage: float = 0.05
    structural_fidelity: float = 0.08
    markdown_readability: float = 0.04
    rag_suitability: float = 0.03


class ScoringConfig(BaseModel):
    global_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    pdf_type_weights: dict[str, ScoringWeights] = Field(default_factory=dict)
    minimum_acceptable_score: float = 40.0
    good_score: float = 65.0
    excellent_score: float = 80.0
    max_score: float = 100.0


class PipelineConfig(BaseModel):
    run_id_prefix: str = "pipeline"
    data_root: str = "./data"
    logs_root: str = "./logs"
    reports_root: str = "./reports"
    artifacts_root: str = "./artifacts"
    parsed_root: str = "./data/parsed"
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Top-level settings (supports env var overrides)
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """
    Top-level settings loaded from environment variables.
    These override YAML config values when set.
    """

    configs_dir: str = "./configs"
    data_root: str = "./data"
    log_level: str = "INFO"
    hf_token: str = ""
    max_download_workers: int = 4
    run_id_prefix: str = "pipeline"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# ---------------------------------------------------------------------------
# Full loaded configuration
# ---------------------------------------------------------------------------


class AppConfig:
    """Holds all loaded and validated config objects."""

    def __init__(
        self,
        settings: Settings,
        logging_cfg: LoggingConfig,
        pipeline_cfg: PipelineConfig,
        sources_raw: dict[str, Any],
        parsers_raw: dict[str, Any],
        scoring_cfg: ScoringConfig,
    ) -> None:
        self.settings = settings
        self.logging = logging_cfg
        self.pipeline = pipeline_cfg
        self.sources_raw = sources_raw
        self.parsers_raw = parsers_raw
        self.scoring = scoring_cfg

    def get_source(self, name: str) -> dict[str, Any] | None:
        return self.sources_raw.get("sources", {}).get(name)

    def get_enabled_sources(self) -> dict[str, dict[str, Any]]:
        return {
            k: v
            for k, v in self.sources_raw.get("sources", {}).items()
            if v.get("enabled", True)
        }

    def get_parser_config(self, name: str) -> dict[str, Any] | None:
        return self.parsers_raw.get("parsers", {}).get(name)

    def get_enabled_parsers(self) -> dict[str, dict[str, Any]]:
        return {
            k: v
            for k, v in self.parsers_raw.get("parsers", {}).items()
            if v.get("enabled", True)
        }

    def get_type_hint(self, pdf_type: str) -> dict[str, Any]:
        return self.parsers_raw.get("pdf_type_hints", {}).get(pdf_type, {})


@lru_cache(maxsize=1)
def load_config(configs_dir: str = "./configs") -> AppConfig:
    """
    Load and cache all config files. Called once at pipeline startup.

    Decision: lru_cache ensures config is loaded exactly once per process.
    This avoids repeated disk reads and provides a stable config snapshot
    for the entire run duration.
    """
    base = Path(configs_dir)
    settings = Settings()

    logging_raw = _load_yaml(base / "logging.yaml")
    pipeline_raw = _load_yaml(base / "pipeline.yaml")
    sources_raw = _load_yaml(base / "sources.yaml")
    parsers_raw = _load_yaml(base / "parsers.yaml")
    scoring_raw = _load_yaml(base / "scoring.yaml")

    # Build logging config
    log_section = logging_raw.get("logging", {})
    log_files_raw = log_section.pop("log_files", {})
    console_raw = log_section.pop("console", {})
    required = log_section.pop("required_fields", [])
    forbidden = log_section.pop("forbidden_fields", [])

    log_files = {k: LogFileConfig(**v) for k, v in log_files_raw.items()}
    logging_cfg = LoggingConfig(
        **log_section,
        log_files=log_files,
        console_enabled=console_raw.get("enabled", True),
        console_level=console_raw.get("level", "INFO"),
        console_format=console_raw.get("format", "text"),
        colorize=console_raw.get("colorize", True),
        required_fields=required,
        forbidden_fields=forbidden,
    )

    # Build pipeline config
    pipeline_section = pipeline_raw.get("pipeline", {})
    pipeline_cfg = PipelineConfig(**pipeline_section)

    # Build scoring config
    scoring_section = scoring_raw
    global_w = ScoringWeights(**scoring_section.get("global_weights", {}))
    pdf_type_weights = {
        k: ScoringWeights(**v)
        for k, v in scoring_section.get("pdf_type_weights", {}).items()
    }
    thresholds = scoring_section.get("thresholds", {})
    scoring_cfg = ScoringConfig(
        global_weights=global_w,
        pdf_type_weights=pdf_type_weights,
        minimum_acceptable_score=thresholds.get("minimum_acceptable_score", 40.0),
        good_score=thresholds.get("good_score", 65.0),
        excellent_score=thresholds.get("excellent_score", 80.0),
        max_score=thresholds.get("max_score", 100.0),
    )

    return AppConfig(
        settings=settings,
        logging_cfg=logging_cfg,
        pipeline_cfg=pipeline_cfg,
        sources_raw=sources_raw,
        parsers_raw=parsers_raw,
        scoring_cfg=scoring_cfg,
    )
