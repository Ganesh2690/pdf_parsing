"""
src/pdf_research_pipeline/cli.py

Typer-based CLI with 7 commands:
  download    — fetch PDFs from all enabled sources
  catalog     — print/export the current PDF catalog
  parse       — run parsers on downloaded PDFs
  benchmark   — score and rank parsers per PDF type
  verify      — validate parser outputs and write reports
  recommend   — print parser recommendations
  run-all     — full end-to-end pipeline

Each command:
- Calls setup_logging() + set_run_id()
- Writes a run manifest via write_run_manifest()
- Logs stage start/end events
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Optional

import typer

from pdf_research_pipeline.logging_utils import get_logger

app = typer.Typer(
    name="pdf-pipeline",
    help="Production-grade PDF research pipeline.",
    add_completion=False,
)

_logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bootstrap(cfg_path: Optional[str] = None):
    """Load config, set up logging, return config."""
    from pdf_research_pipeline.config import load_config
    from pdf_research_pipeline.logging_utils import set_run_id, setup_logging

    cfg_dir = cfg_path or "./configs"
    cfg = load_config(cfg_dir)
    setup_logging(
        log_level=cfg.logging.level,
        logs_root=cfg.pipeline.logs_root,
        json_format=(cfg.logging.format == "json"),
    )
    set_run_id(str(uuid.uuid4()))
    return cfg


def _catalog_path(cfg) -> Path:
    """Return the canonical JSONL catalog path from config."""
    return Path(cfg.pipeline.data_root) / "catalog" / "pdf_catalog.jsonl"


def _parsed_dir(cfg) -> str:
    return cfg.pipeline.parsed_root


def _reports_dir(cfg) -> str:
    return str(Path(cfg.pipeline.artifacts_root) / "reports")


def _manifest(cfg, command: str) -> None:
    from datetime import datetime, timezone
    from pdf_research_pipeline.provenance import write_run_manifest
    from pdf_research_pipeline.logging_utils import get_run_id

    now = datetime.now(timezone.utc).isoformat()
    write_run_manifest(
        run_id=get_run_id(),
        command=command,
        start_time=now,
        end_time=now,
        artifacts_dir=cfg.pipeline.artifacts_root,
    )


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


@app.command()
def download(
    config: Annotated[
        Optional[str], typer.Option("--config", "-c", help="Path to config dir")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="List candidates without downloading")
    ] = False,
) -> None:
    """Download PDFs from all enabled sources."""
    cfg = _bootstrap(config)
    from pdf_research_pipeline.logging_utils import log_stage
    from pdf_research_pipeline.downloader import build_downloaders

    with log_stage(_logger, "download", log_category="download"):
        downloaders = build_downloaders(cfg)
        _logger.info(
            "download_downloaders_ready",
            event_type="download_downloaders_ready",
            stage="download",
            log_category="download",
            downloader_count=len(downloaders),
            downloader_names=[d.__class__.__name__ for d in downloaders],
            status="info",
        )
        if dry_run:
            typer.echo(
                f"[dry-run] {len(downloaders)} downloaders configured — skipping actual downloads."
            )
            return
        total_downloaded = 0
        for dl in downloaders:
            dl_name = dl.__class__.__name__
            _logger.info(
                "download_source_start",
                event_type="download_source_start",
                stage="download",
                log_category="download",
                downloader=dl_name,
                status="started",
            )
            try:
                dl.run()
                _logger.info(
                    "download_source_end",
                    event_type="download_source_end",
                    stage="download",
                    log_category="download",
                    downloader=dl_name,
                    status="completed",
                )
            except Exception as exc:  # noqa: BLE001
                import traceback as _tb

                _logger.error(
                    "download_source_error",
                    event_type="download_source_error",
                    stage="download",
                    log_category="errors",
                    downloader=dl_name,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    traceback=_tb.format_exc(),
                    status="failed",
                )
                typer.echo(f"[error] {dl_name}: {exc}", err=True)
        _logger.info(
            "download_summary",
            event_type="download_summary",
            stage="download",
            log_category="metrics",
            downloaders_run=len(downloaders),
            status="completed",
        )

    _manifest(cfg, "download")


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------


@app.command()
def catalog(
    config: Annotated[Optional[str], typer.Option("--config", "-c")] = None,
    export_csv: Annotated[
        Optional[str], typer.Option("--export-csv", help="Path to write CSV")
    ] = None,
) -> None:
    """Print or export the PDF catalog."""
    cfg = _bootstrap(config)
    from pdf_research_pipeline.logging_utils import log_stage
    from pdf_research_pipeline.utils.metadata import load_catalog, write_catalog_csv

    cat_path = _catalog_path(cfg)
    if not cat_path.exists():
        typer.echo(f"No catalog found at {cat_path}. Run `download` first.", err=True)
        raise typer.Exit(1)

    with log_stage(_logger, "catalog"):
        rows = load_catalog(str(cat_path))
        typer.echo(f"Catalog contains {len(rows)} entries.")
        if export_csv:
            write_catalog_csv(rows, export_csv)
            typer.echo(f"Exported to {export_csv}")

    _manifest(cfg, "catalog")


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------


@app.command()
def parse(
    config: Annotated[Optional[str], typer.Option("--config", "-c")] = None,
    pdf_id: Annotated[
        Optional[str], typer.Option("--pdf-id", help="Parse a single PDF by ID")
    ] = None,
    parser_name: Annotated[
        Optional[str], typer.Option("--parser", help="Use only this parser")
    ] = None,
    all_parsers: Annotated[
        bool,
        typer.Option("--all-parsers/--no-all-parsers", help="Run every enabled parser"),
    ] = True,
) -> None:
    """Run parsers on downloaded PDFs.

    Examples:
      pdf-pipeline parse --pdf-id abc123 --all-parsers
      pdf-pipeline parse --pdf-id abc123 --parser pymupdf
    """
    cfg = _bootstrap(config)
    from pdf_research_pipeline.logging_utils import log_stage
    from pdf_research_pipeline.parsers import build_parsers
    from pdf_research_pipeline.utils.metadata import load_catalog

    with log_stage(_logger, "parse", log_category="run"):
        entries = load_catalog(str(_catalog_path(cfg)))
        _logger.info(
            "parse_catalog_loaded",
            event_type="parse_catalog_loaded",
            stage="parse",
            log_category="extraction",
            pdf_count=len(entries),
            status="info",
        )

        if pdf_id:
            entries = [e for e in entries if e.get("pdf_id") == pdf_id]
            if not entries:
                _logger.error(
                    "parse_pdf_not_found",
                    event_type="parse_pdf_not_found",
                    stage="parse",
                    log_category="errors",
                    pdf_id=pdf_id,
                    status="failed",
                )
                typer.echo(f"PDF ID not found: {pdf_id}", err=True)
                raise typer.Exit(1)

        parsers = build_parsers(cfg)
        if parser_name and not all_parsers:
            parsers = [p for p in parsers if p.parser_name == parser_name]
            if not parsers:
                _logger.error(
                    "parse_parser_not_found",
                    event_type="parse_parser_not_found",
                    stage="parse",
                    log_category="errors",
                    parser_name=parser_name,
                    status="failed",
                )
                typer.echo(f"Parser not found: {parser_name}", err=True)
                raise typer.Exit(1)

        parser_names = [p.parser_name for p in parsers]
        _logger.info(
            "parse_parsers_ready",
            event_type="parse_parsers_ready",
            stage="parse",
            log_category="extraction",
            parsers=parser_names,
            parser_count=len(parsers),
            status="info",
        )

        ok_count = 0
        fail_count = 0

        for entry in entries:
            eid = entry["pdf_id"]
            etype = entry.get("detected_pdf_type", "unknown")
            local_path = entry["local_path"]

            _logger.info(
                "parse_pdf_start",
                event_type="parse_pdf_start",
                stage="parse",
                log_category="extraction",
                pdf_id=eid,
                pdf_type=etype,
                local_path=local_path,
                parser_count=len(parsers),
                status="started",
            )

            pdf_ok = 0
            pdf_fail = 0
            for parser in parsers:
                _logger.info(
                    "parse_parser_start",
                    event_type="parse_parser_start",
                    stage="parse",
                    log_category="extraction",
                    pdf_id=eid,
                    pdf_type=etype,
                    parser_name=parser.parser_name,
                    status="started",
                )
                try:
                    result = parser.run(
                        path=Path(local_path),
                        pdf_id=eid,
                        pdf_type=etype,
                    )
                    page_count = result.page_count_detected
                    text_chars = len(result.raw_text_full or "")
                    _logger.info(
                        "parse_parser_end",
                        event_type="parse_parser_end",
                        stage="parse",
                        log_category="extraction",
                        pdf_id=eid,
                        pdf_type=etype,
                        parser_name=parser.parser_name,
                        page_count=page_count,
                        text_chars=text_chars,
                        duration_ms=result.duration_ms,
                        status="completed",
                    )
                    typer.echo(
                        f"  [ok] {parser.parser_name} → {eid[:12]}.. "
                        f"({page_count} pages, {text_chars:,} chars, {result.duration_ms}ms)"
                    )
                    pdf_ok += 1
                    ok_count += 1
                except Exception as exc:  # noqa: BLE001
                    import traceback as _tb

                    _logger.error(
                        "parse_parser_error",
                        event_type="parse_parser_error",
                        stage="parse",
                        log_category="errors",
                        pdf_id=eid,
                        pdf_type=etype,
                        parser_name=parser.parser_name,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                        traceback=_tb.format_exc(),
                        status="failed",
                    )
                    typer.echo(
                        f"  [error] {parser.parser_name} / {eid[:12]}..: {exc}",
                        err=True,
                    )
                    pdf_fail += 1
                    fail_count += 1

            _logger.info(
                "parse_pdf_end",
                event_type="parse_pdf_end",
                stage="parse",
                log_category="extraction",
                pdf_id=eid,
                pdf_type=etype,
                parsers_ok=pdf_ok,
                parsers_failed=pdf_fail,
                status="completed" if pdf_fail == 0 else "partial",
            )

        _logger.info(
            "parse_summary",
            event_type="parse_summary",
            stage="parse",
            log_category="metrics",
            total_pdfs=len(entries),
            total_parsers=len(parsers),
            extractions_ok=ok_count,
            extractions_failed=fail_count,
            status="completed",
        )
        typer.echo(
            f"Parse complete: {ok_count} ok, {fail_count} failed "
            f"across {len(entries)} PDFs x {len(parsers)} parsers."
        )

    _manifest(cfg, "parse")


# ---------------------------------------------------------------------------
# benchmark
# ---------------------------------------------------------------------------


@app.command()
def benchmark(
    config: Annotated[Optional[str], typer.Option("--config", "-c")] = None,
    pdf_type: Annotated[
        Optional[str], typer.Option("--pdf-type", help="Only benchmark this PDF type")
    ] = None,
) -> None:
    """Score and rank parsers per PDF type; write reports.

    Examples:
      pdf-pipeline benchmark --pdf-type complex_layout_pdf
    """
    cfg = _bootstrap(config)
    from pdf_research_pipeline.logging_utils import log_stage
    from pdf_research_pipeline.benchmark.scorer import ParserScorer
    from pdf_research_pipeline.benchmark.selector import ParserSelector
    from pdf_research_pipeline.utils.metadata import load_catalog
    from pdf_research_pipeline.parsers import load_parse_result

    rdir = _reports_dir(cfg)
    scorer = ParserScorer(cfg.scoring)
    selector = ParserSelector(rdir)
    scores: list = []

    with log_stage(_logger, "benchmark", log_category="run"):
        entries = load_catalog(str(_catalog_path(cfg)))
        if pdf_type:
            entries = [e for e in entries if e.get("detected_pdf_type") == pdf_type]

        _logger.info(
            "benchmark_start_scoring",
            event_type="benchmark_start_scoring",
            stage="benchmark",
            log_category="metrics",
            pdf_count=len(entries),
            filter_type=pdf_type,
            status="info",
        )

        for entry in entries:
            eid = entry["pdf_id"]
            etype = entry.get("detected_pdf_type", "unknown")
            parse_results = load_parse_result(eid, etype, _parsed_dir(cfg))
            _logger.info(
                "benchmark_pdf_start",
                event_type="benchmark_pdf_start",
                stage="benchmark",
                log_category="metrics",
                pdf_id=eid,
                pdf_type=etype,
                parsers_found=list(parse_results.keys()),
                status="started",
            )
            for pname, result in parse_results.items():
                ps = scorer.score(result)
                _logger.info(
                    "benchmark_parser_scored",
                    event_type="benchmark_parser_scored",
                    stage="benchmark",
                    log_category="metrics",
                    pdf_id=eid,
                    pdf_type=etype,
                    parser_name=pname,
                    total_score=round(ps.total_score, 2),
                    recommendation=ps.recommendation,
                    status="scored",
                )
                scores.append((etype, pname, ps))
            _logger.info(
                "benchmark_pdf_end",
                event_type="benchmark_pdf_end",
                stage="benchmark",
                log_category="metrics",
                pdf_id=eid,
                pdf_type=etype,
                parsers_scored=len(parse_results),
                status="completed",
            )

        aggregated = selector.aggregate(scores)
        selections = selector.select(aggregated)
        selector.write_reports(aggregated, selections)

        for pdf_t, sel in selections.items():
            _logger.info(
                "benchmark_recommendation",
                event_type="benchmark_recommendation",
                stage="benchmark",
                log_category="parser_selection",
                pdf_type=pdf_t,
                primary_parser=sel.get("primary"),
                fallback_parser=sel.get("fallback"),
                status="recommended",
            )

        _logger.info(
            "benchmark_summary",
            event_type="benchmark_summary",
            stage="benchmark",
            log_category="metrics",
            total_scores=len(scores),
            pdf_types=list(aggregated.keys()),
            status="completed",
        )
        typer.echo(f"Benchmark complete. Reports in {rdir}.")

    _manifest(cfg, "benchmark")


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


@app.command()
def verify(
    config: Annotated[Optional[str], typer.Option("--config", "-c")] = None,
) -> None:
    """Validate parser outputs and write verification reports."""
    cfg = _bootstrap(config)
    from pdf_research_pipeline.logging_utils import log_stage
    from pdf_research_pipeline.verification import OutputDiffer
    from pdf_research_pipeline.utils.metadata import load_catalog
    from pdf_research_pipeline.parsers import load_parse_result

    rdir = _reports_dir(cfg)
    differ = OutputDiffer(rdir)

    with log_stage(_logger, "verify", log_category="verification"):
        entries = load_catalog(str(_catalog_path(cfg)))
        _logger.info(
            "verify_start",
            event_type="verify_start",
            stage="verify",
            log_category="verification",
            pdf_count=len(entries),
            status="info",
        )
        for entry in entries:
            eid = entry["pdf_id"]
            etype = entry.get("detected_pdf_type", "unknown")
            parse_results = load_parse_result(eid, etype, _parsed_dir(cfg))
            _logger.info(
                "verify_pdf_start",
                event_type="verify_pdf_start",
                stage="verify",
                log_category="verification",
                pdf_id=eid,
                pdf_type=etype,
                parsers_found=list(parse_results.keys()),
                status="started",
            )
            for pname, result in parse_results.items():
                differ.add(eid, etype, pname, result)
            _logger.info(
                "verify_pdf_end",
                event_type="verify_pdf_end",
                stage="verify",
                log_category="verification",
                pdf_id=eid,
                pdf_type=etype,
                parsers_verified=len(parse_results),
                status="completed",
            )

        differ.write_reports()
        _logger.info(
            "verify_reports_written",
            event_type="verify_reports_written",
            stage="verify",
            log_category="verification",
            reports_dir=rdir,
            status="completed",
        )
        typer.echo(f"Verification complete. Reports in {rdir}.")

    _manifest(cfg, "verify")


# ---------------------------------------------------------------------------
# score-ai
# ---------------------------------------------------------------------------


@app.command(name="score-ai")
def score_ai(  # noqa: PLR0912
    config: Annotated[Optional[str], typer.Option("--config", "-c")] = None,
    api_key: Annotated[
        Optional[str],
        typer.Option(
            "--api-key", help="OpenAI API key (env var OPENAI_API_KEY preferred)"
        ),
    ] = None,
    model: Annotated[str, typer.Option("--model")] = "gpt-4o",
    export_txt: Annotated[bool, typer.Option("--export-txt/--no-export-txt")] = True,
    output_html: Annotated[Optional[str], typer.Option("--output")] = None,
) -> None:
    """Deep AI scoring: analyze PDFs with GPT-4o and generate HTML accuracy report."""
    import os

    # If an explicit config dir is provided, chdir to its parent so that relative
    # paths in pipeline.yaml (e.g. data_root: ./data) resolve correctly.
    if config:
        project_root = str(Path(config).resolve().parent)
        os.chdir(project_root)

    cfg = _bootstrap(config)
    from pdf_research_pipeline.logging_utils import log_stage
    from pdf_research_pipeline.benchmark.pdf_analyzer import analyze_pdf
    from pdf_research_pipeline.benchmark.openai_agent import OpenAIScoringAgent
    from pdf_research_pipeline.benchmark.html_report import generate_html_report
    from pdf_research_pipeline.parsers import load_parse_result
    from pdf_research_pipeline.utils.metadata import load_catalog

    resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not resolved_key:
        typer.echo(
            "[error] OpenAI API key required. Set OPENAI_API_KEY env var or pass --api-key.",
            err=True,
        )
        raise typer.Exit(1)

    reports_root = Path(_reports_dir(cfg))
    reports_root.mkdir(parents=True, exist_ok=True)
    txt_root = Path(cfg.pipeline.data_root) / "text_exports"

    with log_stage(_logger, "score_ai", log_category="scoring"):
        agent = OpenAIScoringAgent(api_key=resolved_key, model=model)

        catalog_entries = list(load_catalog(str(_catalog_path(cfg))))
        evaluations = []
        metadata_map: dict = {}
        all_extractions_map: dict[str, dict[str, str]] = {}

        for entry in catalog_entries:
            pdf_id = entry["pdf_id"]
            pdf_type = entry.get("detected_pdf_type", "unknown")
            local_path = entry.get("local_path", "")

            # ── 1. Structural analysis ─────────────────────────────────────
            _logger.info(
                "score_ai_analyze_start",
                event_type="score_ai_analyze_start",
                stage="score_ai",
                log_category="metrics",
                pdf_id=pdf_id,
                status="started",
            )
            meta = analyze_pdf(pdf_id, pdf_type, local_path)
            metadata_map[pdf_id] = meta
            _logger.info(
                "score_ai_analyze_end",
                event_type="score_ai_analyze_end",
                stage="score_ai",
                log_category="metrics",
                pdf_id=pdf_id,
                page_count=meta.page_count,
                word_count=meta.word_count,
                image_count=meta.image_count,
                status="completed",
            )

            # ── 2. Load parse results ──────────────────────────────────────
            results = load_parse_result(pdf_id, pdf_type, _parsed_dir(cfg))
            if not results:
                _logger.warning(
                    "score_ai_no_extractions",
                    event_type="score_ai_no_extractions",
                    stage="score_ai",
                    log_category="metrics",
                    pdf_id=pdf_id,
                    status="skipped",
                )
                typer.echo(f"[skip] {pdf_id}: no parse results found")
                continue

            extractions: dict[str, str] = {}
            for pname, res in results.items():
                if res.status != "completed":
                    continue
                # raw_text_full is not persisted in summary.json; read raw_text.txt
                raw_text = res.raw_text_full or ""
                if not raw_text:
                    txt_file = (
                        Path(_parsed_dir(cfg))
                        / pdf_type
                        / pdf_id
                        / pname
                        / "raw_text.txt"
                    )
                    if txt_file.exists():
                        raw_text = txt_file.read_text(
                            encoding="utf-8", errors="replace"
                        )
                if raw_text:
                    extractions[pname] = raw_text

            if not extractions:
                typer.echo(f"[skip] {pdf_id}: all parsers have empty text")
                continue

            # Accumulate for HTML text viewer
            all_extractions_map[pdf_id] = extractions

            # ── 3. Export plain text files ─────────────────────────────────
            if export_txt:
                pdf_txt_dir = txt_root / pdf_type / pdf_id
                pdf_txt_dir.mkdir(parents=True, exist_ok=True)
                for pname, text in extractions.items():
                    txt_path = pdf_txt_dir / f"{pname}.txt"
                    txt_path.write_text(text, encoding="utf-8")
                _logger.info(
                    "score_ai_txt_exported",
                    event_type="score_ai_txt_exported",
                    stage="score_ai",
                    log_category="metrics",
                    pdf_id=pdf_id,
                    txt_dir=str(pdf_txt_dir),
                    parser_count=len(extractions),
                    status="completed",
                )
                typer.echo(
                    f"  [txt] {pdf_id}: {len(extractions)} text files → {pdf_txt_dir}"
                )

            # ── 4. GPT-4o scoring ──────────────────────────────────────────
            typer.echo(
                f"  [ai]  {pdf_id}: scoring {len(extractions)} parsers via {model}..."
            )
            evaluation = agent.evaluate(meta, extractions)
            evaluations.append(evaluation)

            _logger.info(
                "score_ai_pdf_scored",
                event_type="score_ai_pdf_scored",
                stage="score_ai",
                log_category="metrics",
                pdf_id=pdf_id,
                best_parser=evaluation.best_parser,
                worst_parser=evaluation.worst_parser,
                tokens_used=evaluation.tokens_used,
                scores={p: s.total_score for p, s in evaluation.parser_scores.items()},
                status="completed",
            )
            typer.echo(
                f"  [✓]   {pdf_id}: best={evaluation.best_parser} "
                + " | ".join(
                    f"{p}={s.total_score}" for p, s in evaluation.parser_scores.items()
                )
            )

        if not evaluations:
            typer.echo(
                "[warn] No evaluations produced – ensure PDFs are parsed first.",
                err=True,
            )
            raise typer.Exit(1)

        # ── 5. Generate HTML report ────────────────────────────────────────
        html_path = output_html or str(reports_root / "accuracy_report.html")
        generate_html_report(
            evaluations, metadata_map, html_path, all_extractions=all_extractions_map
        )

        # Save raw evaluations JSON for debugging
        import dataclasses
        import json as _json

        eval_json = []
        for ev in evaluations:
            d = dataclasses.asdict(ev)
            eval_json.append(d)
        (reports_root / "ai_evaluations.json").write_text(
            _json.dumps(eval_json, indent=2), encoding="utf-8"
        )

        _logger.info(
            "score_ai_report_written",
            event_type="score_ai_report_written",
            stage="score_ai",
            log_category="metrics",
            html_path=html_path,
            pdf_count=len(evaluations),
            status="completed",
        )
        typer.echo(f"\n✅ HTML report written → {html_path}")
        typer.echo(f"   Raw JSON → {reports_root / 'ai_evaluations.json'}")

    _manifest(cfg, "score-ai")


# ---------------------------------------------------------------------------
# recommend
# ---------------------------------------------------------------------------


@app.command()
def recommend(
    config: Annotated[Optional[str], typer.Option("--config", "-c")] = None,
) -> None:
    """Print parser recommendations from the last benchmark run."""
    cfg = _bootstrap(config)
    md_path = Path(_reports_dir(cfg)) / "parser_recommendations.md"
    if not md_path.exists():
        typer.echo("No recommendations found. Run `benchmark` first.", err=True)
        raise typer.Exit(1)
    typer.echo(md_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# run-all
# ---------------------------------------------------------------------------


@app.command(name="run-all")
def run_all(
    config: Annotated[Optional[str], typer.Option("--config", "-c")] = None,
    skip_download: Annotated[bool, typer.Option("--skip-download")] = False,
) -> None:
    """Full end-to-end pipeline: download → parse → benchmark → verify → recommend."""
    cfg = _bootstrap(config)
    from pdf_research_pipeline.logging_utils import log_stage

    with log_stage(_logger, "run_all", log_category="run"):
        if not skip_download:
            typer.echo("Step 1/5: download")
            _logger.info(
                "run_all_step",
                event_type="run_all_step",
                stage="run_all",
                log_category="run",
                step=1,
                step_name="download",
                status="started",
            )
            from pdf_research_pipeline.downloader import build_downloaders

            for dl in build_downloaders(cfg):
                dl.run()
            _logger.info(
                "run_all_step",
                event_type="run_all_step",
                stage="run_all",
                log_category="run",
                step=1,
                step_name="download",
                status="completed",
            )

        typer.echo("Step 2/5: parse")
        _logger.info(
            "run_all_step",
            event_type="run_all_step",
            stage="run_all",
            log_category="run",
            step=2,
            step_name="parse",
            status="started",
        )
        _invoke_parse(cfg)
        _logger.info(
            "run_all_step",
            event_type="run_all_step",
            stage="run_all",
            log_category="run",
            step=2,
            step_name="parse",
            status="completed",
        )

        typer.echo("Step 3/5: benchmark")
        _logger.info(
            "run_all_step",
            event_type="run_all_step",
            stage="run_all",
            log_category="run",
            step=3,
            step_name="benchmark",
            status="started",
        )
        _invoke_benchmark(cfg)
        _logger.info(
            "run_all_step",
            event_type="run_all_step",
            stage="run_all",
            log_category="run",
            step=3,
            step_name="benchmark",
            status="completed",
        )

        typer.echo("Step 4/5: verify")
        _logger.info(
            "run_all_step",
            event_type="run_all_step",
            stage="run_all",
            log_category="run",
            step=4,
            step_name="verify",
            status="started",
        )
        _invoke_verify(cfg)
        _logger.info(
            "run_all_step",
            event_type="run_all_step",
            stage="run_all",
            log_category="run",
            step=4,
            step_name="verify",
            status="completed",
        )

        typer.echo("Step 5/5: recommend")
        _logger.info(
            "run_all_step",
            event_type="run_all_step",
            stage="run_all",
            log_category="run",
            step=5,
            step_name="recommend",
            status="started",
        )
        md = Path(_reports_dir(cfg)) / "parser_recommendations.md"
        if md.exists():
            typer.echo(md.read_text(encoding="utf-8"))
        _logger.info(
            "run_all_step",
            event_type="run_all_step",
            stage="run_all",
            log_category="run",
            step=5,
            step_name="recommend",
            status="completed",
        )

    _manifest(cfg, "run-all")


def _invoke_parse(cfg) -> None:
    from pdf_research_pipeline.parsers import build_parsers
    from pdf_research_pipeline.utils.metadata import load_catalog

    parsers = build_parsers(cfg)
    for entry in load_catalog(str(_catalog_path(cfg))):
        eid = entry["pdf_id"]
        etype = entry.get("detected_pdf_type", "unknown")
        for parser in parsers:
            _logger.info(
                "parse_parser_start",
                event_type="parse_parser_start",
                stage="parse",
                log_category="extraction",
                pdf_id=eid,
                pdf_type=etype,
                parser_name=parser.parser_name,
                status="started",
            )
            try:
                result = parser.run(
                    path=Path(entry["local_path"]),
                    pdf_id=eid,
                    pdf_type=etype,
                )
                _logger.info(
                    "parse_parser_end",
                    event_type="parse_parser_end",
                    stage="parse",
                    log_category="extraction",
                    pdf_id=eid,
                    pdf_type=etype,
                    parser_name=parser.parser_name,
                    page_count=result.page_count_detected,
                    text_chars=len(result.raw_text_full or ""),
                    duration_ms=result.duration_ms,
                    status="completed",
                )
            except Exception as exc:  # noqa: BLE001
                import traceback as _tb

                _logger.error(
                    "parse_parser_error",
                    event_type="parse_parser_error",
                    stage="parse",
                    log_category="errors",
                    pdf_id=eid,
                    pdf_type=etype,
                    parser_name=parser.parser_name,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    traceback=_tb.format_exc(),
                    status="failed",
                )
                typer.echo(f"[error] {eid}/{parser.parser_name}: {exc}", err=True)


def _invoke_benchmark(cfg) -> None:
    from pdf_research_pipeline.benchmark.scorer import ParserScorer
    from pdf_research_pipeline.benchmark.selector import ParserSelector
    from pdf_research_pipeline.parsers import load_parse_result
    from pdf_research_pipeline.utils.metadata import load_catalog

    rdir = _reports_dir(cfg)
    scorer = ParserScorer(cfg.scoring)
    selector = ParserSelector(rdir)
    scores: list = []
    for entry in load_catalog(str(_catalog_path(cfg))):
        eid, etype = entry["pdf_id"], entry.get("detected_pdf_type", "unknown")
        for pname, result in load_parse_result(eid, etype, _parsed_dir(cfg)).items():
            scores.append((etype, pname, scorer.score(result)))
    agg = selector.aggregate(scores)
    selector.write_reports(agg, selector.select(agg))


def _invoke_verify(cfg) -> None:
    from pdf_research_pipeline.verification import OutputDiffer
    from pdf_research_pipeline.parsers import load_parse_result
    from pdf_research_pipeline.utils.metadata import load_catalog

    differ = OutputDiffer(_reports_dir(cfg))
    for entry in load_catalog(str(_catalog_path(cfg))):
        eid, etype = entry["pdf_id"], entry.get("detected_pdf_type", "unknown")
        for pname, result in load_parse_result(eid, etype, _parsed_dir(cfg)).items():
            differ.add(eid, etype, pname, result)
    differ.write_reports()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    app()


if __name__ == "__main__":
    main()
