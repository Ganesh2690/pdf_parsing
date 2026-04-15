"""
src/pdf_research_pipeline/logging_utils.py

Structured JSON logging setup using structlog + Python standard logging.

Design decisions:
  - structlog processes log records into JSON lines.
  - Each of the 8 log categories (run, download, parser_selection, extraction,
    verification, errors, metrics, provenance) gets its own FileHandler.
  - A RoutingFilter on each handler ensures events are routed to the correct file
    based on the 'log_category' field set in the event.
  - The master run.log.jsonl receives ALL events.
  - Console output uses plain-text renderer for human readability during development.
  - Secrets are stripped by a processor before any output is written.
  - run_id is injected into every event automatically via a context var.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import traceback as tb
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Generator

import structlog

# ---------------------------------------------------------------------------
# Run-ID context variable — shared across all loggers in the same run
# ---------------------------------------------------------------------------

_run_id_var: ContextVar[str] = ContextVar("run_id", default="unset")


def set_run_id(run_id: str) -> None:
    """Call once at pipeline start to inject run_id into all log events."""
    _run_id_var.set(run_id)


def get_run_id() -> str:
    return _run_id_var.get()


# ---------------------------------------------------------------------------
# Forbidden fields processor — strips secrets before any output
# ---------------------------------------------------------------------------

_FORBIDDEN_FIELDS = {
    "password",
    "secret",
    "token",
    "api_key",
    "credential",
    "authorization",
    "hf_token",
    "ia_access_key",
    "ia_secret_key",
}


def _strip_forbidden_fields(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Remove any fields matching the forbidden-fields security list."""
    for field in _FORBIDDEN_FIELDS:
        event_dict.pop(field, None)
    return event_dict


# ---------------------------------------------------------------------------
# Run-ID injector processor
# ---------------------------------------------------------------------------


def _inject_run_id(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    event_dict.setdefault("run_id", _run_id_var.get())
    return event_dict


# ---------------------------------------------------------------------------
# Category routing — routes events to the correct log file
# ---------------------------------------------------------------------------

_CATEGORY_FILES: dict[str, str] = {
    "download": "logs/download.log.jsonl",
    "parser_selection": "logs/parser_selection.log.jsonl",
    "extraction": "logs/extraction.log.jsonl",
    "verification": "logs/verification.log.jsonl",
    "errors": "logs/errors.log.jsonl",
    "metrics": "logs/metrics.log.jsonl",
    "provenance": "logs/provenance.log.jsonl",
}
_MASTER_LOG = "logs/run.log.jsonl"

_file_handlers: dict[str, logging.FileHandler] = {}


class _CategoryFilter(logging.Filter):
    """
    Allow only records whose 'log_category' extra field matches
    this filter's category name. The master handler has no filter.
    """

    def __init__(self, category: str) -> None:
        super().__init__()
        self.category = category

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "log_category", "run") == self.category


def _ensure_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _get_or_create_file_handler(path: str) -> logging.FileHandler:
    if path not in _file_handlers:
        _ensure_dir(path)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        _file_handlers[path] = handler
    return _file_handlers[path]


# ---------------------------------------------------------------------------
# Setup function — call once at pipeline startup
# ---------------------------------------------------------------------------


def setup_logging(
    log_level: str = "INFO",
    logs_root: str = "./logs",
    json_format: bool = True,
) -> None:
    """
    Configure structlog and Python logging.

    Decision: Called once from cli.py before any other code runs.
    Subsequent calls are safe (handlers are not duplicated due to guard check).
    """
    Path(logs_root).mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)

    # Build structlog processor chain
    shared_processors: list[Any] = [
        _inject_run_id,
        _strip_forbidden_fields,
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_format:
        final_processor: Any = structlog.processors.JSONRenderer()
    else:
        final_processor = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Python root logger
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return  # Already configured

    root_logger.setLevel(level)

    # Formatter for structlog output
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            final_processor,
        ],
        foreign_pre_chain=shared_processors,
    )

    # Master handler — receives all events
    master_path = str(Path(logs_root) / "run.log.jsonl")
    master_handler = _get_or_create_file_handler(master_path)
    master_handler.setLevel(level)
    master_handler.setFormatter(formatter)
    root_logger.addHandler(master_handler)

    # Per-category handlers
    for category, rel_path in _CATEGORY_FILES.items():
        cat_path = str(Path(logs_root) / Path(rel_path).name)
        cat_handler = _get_or_create_file_handler(cat_path)
        cat_handler.setLevel(level)
        cat_handler.setFormatter(formatter)
        cat_handler.addFilter(_CategoryFilter(category))
        root_logger.addHandler(cat_handler)

    # Console handler — text format for human readability
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        foreign_pre_chain=shared_processors,
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)


# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to the given name."""
    return structlog.get_logger(name)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Convenience: log a decision record in the format specified by prompt.md
# ---------------------------------------------------------------------------


def log_decision(
    logger: structlog.stdlib.BoundLogger,
    pdf_id: str,
    pdf_type: str,
    candidate_parsers: list[str],
    observation: dict[str, Any],
    decision: str,
    decision_reason: str,
    stage: str = "parser_selection",
) -> None:
    """
    Emit a structured parser_decision event.

    Decision record format per prompt.md section 6:
      event_type, pdf_id, pdf_type, candidate_parsers, observation,
      decision, decision_reason, status
    """
    logger.info(
        "parser_decision",
        event_type="parser_decision",
        stage=stage,
        log_category="parser_selection",
        pdf_id=pdf_id,
        pdf_type=pdf_type,
        candidate_parsers=candidate_parsers,
        observation=observation,
        decision=decision,
        decision_reason=decision_reason,
        status="selected",
    )


# ---------------------------------------------------------------------------
# Context manager: log stage start/end with duration
# ---------------------------------------------------------------------------


@contextmanager
def log_stage(
    logger: structlog.stdlib.BoundLogger,
    stage: str,
    log_category: str = "run",
    **extra: Any,
) -> Generator[None, None, None]:
    """
    Context manager that logs a stage_start event, measures duration,
    and logs a stage_end event with duration_ms and status.

    Usage:
        with log_stage(logger, "download", pdf_id="abc", source="arxiv"):
            ...
    """
    import time

    logger.info(
        f"{stage}_start",
        event_type=f"{stage}_start",
        stage=stage,
        log_category=log_category,
        status="started",
        **extra,
    )
    t0 = time.perf_counter()
    try:
        yield
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            f"{stage}_end",
            event_type=f"{stage}_end",
            stage=stage,
            log_category=log_category,
            status="completed",
            duration_ms=duration_ms,
            **extra,
        )
    except Exception as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.error(
            f"{stage}_error",
            event_type=f"{stage}_error",
            stage=stage,
            log_category="errors",
            status="failed",
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
            error_message=str(exc),
            traceback=tb.format_exc(),
            **extra,
        )
        raise
