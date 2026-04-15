"""
src/pdf_research_pipeline/provenance.py

Captures and logs full provenance for every pipeline run.

Decision: Provenance tracking is mandated by prompt.md section 9.
Every run must record: git commit hash, Python version, OS, package versions,
config file hashes, input file hashes, output file hashes, command, timestamps.

Stored in artifacts/run_manifest.json, environment_snapshot.json, file_lineage.json.

Security: No secrets or credentials are written to provenance files.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pdf_research_pipeline.utils.hashing import sha256_file
from pdf_research_pipeline.utils.files import ensure_dir


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git_commit() -> str:
    """Return the current git HEAD commit hash, or 'unavailable' on error."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unavailable"


def _git_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unavailable"


# ---------------------------------------------------------------------------
# Package version capture
# ---------------------------------------------------------------------------

_TRACKED_PACKAGES = [
    "pymupdf",
    "pdfplumber",
    "pypdf",
    "pypdfium2",
    "unstructured",
    "pytesseract",
    "ocrmypdf",
    "pdf2image",
    "camelot-py",
    "tabula-py",
    "structlog",
    "pydantic",
    "typer",
    "tenacity",
    "tqdm",
    "pandas",
    "langdetect",
    "deepdiff",
    "pillow",
]


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for pkg in _TRACKED_PACKAGES:
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = "not_installed"
    return versions


# ---------------------------------------------------------------------------
# Environment snapshot
# ---------------------------------------------------------------------------


def capture_environment() -> dict[str, Any]:
    """
    Capture a full environment snapshot for reproducibility.
    Logged to artifacts/environment_snapshot.json.
    """
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "os_name": os.name,
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "git_commit": _git_commit(),
        "git_branch": _git_branch(),
        "package_versions": _package_versions(),
    }


# ---------------------------------------------------------------------------
# Config file hashes
# ---------------------------------------------------------------------------


def hash_config_files(configs_dir: str = "./configs") -> dict[str, str]:
    """
    Compute SHA256 checksums of all YAML config files.
    Stored in run_manifest.json so that config changes are detectable between runs.
    """
    base = Path(configs_dir)
    hashes: dict[str, str] = {}
    for yaml_file in sorted(base.glob("*.yaml")):
        hashes[yaml_file.name] = sha256_file(yaml_file)
    return hashes


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def write_run_manifest(
    run_id: str,
    command: str,
    start_time: str,
    end_time: str,
    artifacts_dir: str = "./artifacts",
    configs_dir: str = "./configs",
    input_files: list[str] | None = None,
    output_files: list[str] | None = None,
) -> Path:
    """
    Write artifacts/run_manifest.json with full provenance.

    Decision: run_manifest.json is the top-level provenance record.
    It links to environment_snapshot.json and file_lineage.json.
    """
    ensure_dir(artifacts_dir)

    env = capture_environment()
    config_hashes = hash_config_files(configs_dir)

    input_hashes: dict[str, str] = {}
    if input_files:
        for f in input_files:
            p = Path(f)
            if p.exists():
                input_hashes[f] = sha256_file(p)

    output_hashes: dict[str, str] = {}
    if output_files:
        for f in output_files:
            p = Path(f)
            if p.exists():
                output_hashes[f] = sha256_file(p)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "command": command,
        "start_time": start_time,
        "end_time": end_time,
        "python_version": env["python_version"],
        "platform": env["platform"],
        "git_commit": env["git_commit"],
        "git_branch": env["git_branch"],
        "package_versions": env["package_versions"],
        "config_hashes": config_hashes,
        "input_file_hashes": input_hashes,
        "output_file_hashes": output_hashes,
    }

    manifest_path = Path(artifacts_dir) / "run_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, default=str)

    env_path = Path(artifacts_dir) / "environment_snapshot.json"
    with env_path.open("w", encoding="utf-8") as fh:
        json.dump(env, fh, indent=2, default=str)

    return manifest_path


def append_file_lineage(
    artifacts_dir: str,
    pdf_id: str,
    source_url: str,
    local_path: str,
    parser_name: str,
    output_paths: list[str],
    input_hash: str,
    run_id: str,
) -> None:
    """
    Append a lineage record to artifacts/file_lineage.json.
    Decision: File lineage records are appended (not replaced) so that the
    full history of which outputs came from which inputs is preserved on reruns.
    """
    ensure_dir(artifacts_dir)
    lineage_path = Path(artifacts_dir) / "file_lineage.json"

    records: list[dict[str, Any]] = []
    if lineage_path.exists():
        with lineage_path.open("r", encoding="utf-8") as fh:
            try:
                records = json.load(fh)
            except json.JSONDecodeError:
                records = []

    output_hashes = {}
    for op in output_paths:
        p = Path(op)
        if p.exists():
            output_hashes[op] = sha256_file(p)

    records.append(
        {
            "run_id": run_id,
            "pdf_id": pdf_id,
            "source_url": source_url,
            "local_path": local_path,
            "input_hash": input_hash,
            "parser_name": parser_name,
            "output_paths": output_paths,
            "output_hashes": output_hashes,
        }
    )

    with lineage_path.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2, default=str)
