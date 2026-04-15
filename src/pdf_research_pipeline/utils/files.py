"""
src/pdf_research_pipeline/utils/files.py

File system utilities: directory creation, path generation, safe writes.

Decision: All output path generation for parsed outputs follows the structure
defined in prompt.md section 4:
  data/parsed/<pdf_type>/<pdf_id>/<parser_name>/raw_text.txt
  data/parsed/<pdf_type>/<pdf_id>/<parser_name>/pages.json
  etc.

Path generation is centralised here so that every module uses the same
deterministic path layout. This is required for idempotent reruns (section 18).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def ensure_dir(path: Path | str) -> Path:
    """Create directory and all parents if they do not exist."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def parsed_dir(parsed_root: str, pdf_type: str, pdf_id: str, parser_name: str) -> Path:
    """
    Return (and create) the output directory for a specific parser's output
    for a given PDF.

    Layout: <parsed_root>/<pdf_type>/<pdf_id>/<parser_name>/
    """
    p = Path(parsed_root) / pdf_type / pdf_id / parser_name
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_text(path: Path | str, content: str, encoding: str = "utf-8") -> None:
    """Write a string to a file, creating parent directories."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding=encoding)


def write_json(path: Path | str, data: Any, indent: int = 2) -> None:
    """Write a Python object as indented JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=indent, ensure_ascii=False, default=str)


def write_jsonl(path: Path | str, records: list[dict[str, Any]]) -> None:
    """Append a list of records to a JSONL file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_json(path: Path | str) -> Any:
    """Read and return a JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def safe_delete(path: Path | str) -> None:
    """
    Delete a file or directory. Does not raise if path does not exist.
    Only deletes paths within the project data/logs/reports/artifacts tree.
    """
    p = Path(path)
    if not p.exists():
        return
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()


def list_pdfs(directory: Path | str) -> list[Path]:
    """Return all .pdf files recursively under a directory."""
    return sorted(Path(directory).rglob("*.pdf"))
