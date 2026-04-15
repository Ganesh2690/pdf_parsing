"""
register_synthetic_pdfs.py — Add synthetic PDF files to the catalog.

Moves true_digital_pdf files into a 'direct' subfolder (for consistent
path depth), then appends catalog entries for all 6 synthetic PDFs.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import fitz  # PyMuPDF for page count

ROOT = Path(__file__).parent
CATALOG = ROOT / "data" / "catalog" / "pdf_catalog.jsonl"
RAW = ROOT / "data" / "raw"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def page_count(path: Path) -> int:
    try:
        doc = fitz.open(str(path))
        n = doc.page_count
        doc.close()
        return n
    except Exception:
        return 0


def page_bucket(n: int) -> str:
    if n <= 2:
        return "very_small"
    if n <= 10:
        return "short"
    if n <= 50:
        return "medium"
    return "long"


def make_entry(
    local_path: Path,
    pdf_type: str,
    source_name: str,
    source_url: str = "",
    language: str = "en",
    ocr_expected: bool = False,
    layout_complexity: str = "low",
    extra: dict | None = None,
) -> dict:
    cs = sha256(local_path)
    stem = local_path.stem
    pdf_id = f"{cs[:12]}_{source_name}_{stem}"
    n = page_count(local_path)
    rel = local_path.relative_to(ROOT).as_posix().replace("/", "\\")
    return {
        "pdf_id": pdf_id,
        "source_name": source_name,
        "source_url": source_url,
        "local_path": rel,
        "detected_pdf_type": pdf_type,
        "page_count": n,
        "file_size_bytes": local_path.stat().st_size,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "checksum_sha256": cs,
        "detected_language": language,
        "ocr_expected": ocr_expected,
        "layout_complexity": layout_complexity,
        "page_count_bucket": page_bucket(n),
        "extra": extra or {},
    }


def load_existing_paths() -> set[str]:
    if not CATALOG.exists():
        return set()
    paths: set[str] = set()
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entry = json.loads(line)
            paths.add(entry.get("local_path", "").replace("/", "\\"))
    return paths


def append_entries(entries: list[dict]) -> None:
    with CATALOG.open("a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


if __name__ == "__main__":
    existing = load_existing_paths()
    new_entries: list[dict] = []

    # ── Step 1: Move true_digital_pdf files into 'direct' subfolder ─────────
    td_src = RAW / "true_digital_pdf"
    td_dest = RAW / "true_digital_pdf" / "direct"
    td_dest.mkdir(parents=True, exist_ok=True)

    for pdf in list(td_src.glob("*.pdf")):
        target = td_dest / pdf.name
        if not target.exists():
            shutil.move(str(pdf), str(target))
            print(f"  moved → {target.relative_to(ROOT)}")
        else:
            print(f"  already in place: {target.relative_to(ROOT)}")

    # ── Step 2: Register true_digital_pdf ────────────────────────────────────
    for pdf in sorted(td_dest.glob("*.pdf")):
        rel = pdf.relative_to(ROOT).as_posix().replace("/", "\\")
        if rel in existing:
            print(f"  [already in catalog] {pdf.name}")
            continue
        entry = make_entry(
            local_path=pdf,
            pdf_type="true_digital_pdf",
            source_name="synthetic",
            source_url="",
            language="en",
            ocr_expected=False,
            layout_complexity="low",
            extra={"synthetic": True, "generator": "pymupdf"},
        )
        new_entries.append(entry)
        print(
            f"  [+catalog] {pdf.name}  ({entry['page_count']}pp, {pdf.stat().st_size // 1024}KB)"
        )

    # ── Step 3: Register searchable_image_pdf ────────────────────────────────
    si_dir = RAW / "searchable_image_pdf" / "synthetic"
    for pdf in sorted(si_dir.glob("*.pdf")):
        rel = pdf.relative_to(ROOT).as_posix().replace("/", "\\")
        if rel in existing:
            print(f"  [already in catalog] {pdf.name}")
            continue
        entry = make_entry(
            local_path=pdf,
            pdf_type="searchable_image_pdf",
            source_name="synthetic",
            source_url="",
            language="en",
            ocr_expected=True,
            layout_complexity="low",
            extra={"synthetic": True, "generator": "pymupdf", "has_text_layer": True},
        )
        new_entries.append(entry)
        print(
            f"  [+catalog] {pdf.name}  ({entry['page_count']}pp, {pdf.stat().st_size // 1024}KB)"
        )

    if new_entries:
        append_entries(new_entries)
        print(f"\nAppended {len(new_entries)} entries to catalog.")
    else:
        print("\nNo new entries to add — all already registered.")

    # Final count
    total = sum(
        1 for line in CATALOG.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    print(f"Catalog now has {total} entries.")
