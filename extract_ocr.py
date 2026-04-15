"""
extract_ocr.py — Run tesseract and ocrmypdf parsers on all catalog PDFs.
Sets PYTESSERACT_TESSERACT_CMD so pytesseract finds the installed binary.

Usage (from pdf_research_pipeline directory):
    python extract_ocr.py
    python extract_ocr.py --pdf-id 194dfc73f757_arxiv_2501.05032v2
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

# ── Tesseract setup ─────────────────────────────────────────────────────────
TESSERACT_EXE = r"C:\Users\ganeshg\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR = r"C:\Users\ganeshg\AppData\Local\Programs\Tesseract-OCR\tessdata"
os.environ["PATH"] = str(Path(TESSERACT_EXE).parent) + ";" + os.environ.get("PATH", "")
os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR

# Patch pytesseract before any import
try:
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
except ImportError:
    pass

# ── project paths ───────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

PARSED_ROOT = str(ROOT / "data" / "parsed")
CATALOG_PATH = ROOT / "data" / "catalog" / "pdf_catalog.jsonl"
LOG_PATH = ROOT / "extract_ocr.log"

# Output log file (UTF-8, structured for parse_results.py)
_log_fh = open(LOG_PATH, "w", encoding="utf-8")


def _log(msg: str):
    _log_fh.write(msg + "\n")
    _log_fh.flush()


def _print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode())


# ── parser definitions (OCR only) ───────────────────────────────────────────
OCR_PARSERS = [
    (
        "tesseract",
        "pdf_research_pipeline.parsers.tesseract_parser",
        "TesseractParser",
        {"lang": "eng"},
        "ocr",
    ),
    (
        "ocrmypdf",
        "pdf_research_pipeline.parsers.ocrmypdf_parser",
        "OCRmyPDFParser",
        {"deskew": False, "clean": False, "optimize": 0},
        "ocr",
    ),
]


def check_lib(name: str) -> tuple[bool, str]:
    lib_map = {"tesseract": "pytesseract", "ocrmypdf": "ocrmypdf"}
    module = lib_map.get(name, name)
    try:
        mod = importlib.import_module(module)
        ver = getattr(mod, "__version__", "installed")
        return True, str(ver)
    except ImportError as exc:
        return False, str(exc).split("\n")[0]


def load_catalog() -> list[dict]:
    entries = []
    with open(CATALOG_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def build_parser(mod_path: str, cls_name: str, config: dict):
    mod = importlib.import_module(mod_path)
    cls = getattr(mod, cls_name)
    return cls(parsed_root=PARSED_ROOT, config=config)


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-id", default=None)
    ap.add_argument("--max-pdfs", type=int, default=None)
    ap.add_argument(
        "--parser", default=None, help="Only run this parser (tesseract or ocrmypdf)"
    )
    args = ap.parse_args()

    _print("\n" + "=" * 72)
    _print("  OCR Extraction Run — tesseract + ocrmypdf")
    _print("  Tesseract: " + TESSERACT_EXE)
    _print("=" * 72)

    # verify Tesseract binary
    import subprocess

    r = subprocess.run([TESSERACT_EXE, "--version"], capture_output=True, text=True)
    tess_ver = (r.stdout + r.stderr).split("\n")[0].strip()
    _print(f"  Tesseract binary: {tess_ver}")
    _log(f"tesseract_binary_check version={tess_ver!r}")

    # check libs
    _print("\n  Parser library check:")
    skip = {}
    for name, *_ in OCR_PARSERS:
        ok, ver = check_lib(name)
        if ok:
            _print(f"    [OK] {name:<12} v{ver}")
        else:
            _print(f"    [X]  {name:<12} NOT INSTALLED — {ver}")
            skip[name] = ver

    active = [
        (name, m, c, cfg, cat)
        for name, m, c, cfg, cat in OCR_PARSERS
        if name not in skip
    ]
    if args.parser:
        active = [
            (name, m, c, cfg, cat)
            for name, m, c, cfg, cat in active
            if name == args.parser
        ]
        if not active:
            _print(f"  Parser '{args.parser}' not available or was skipped.")
            sys.exit(1)
    if not active:
        _print("\n  No OCR parsers available. Exiting.")
        sys.exit(1)

    entries = load_catalog()
    if args.pdf_id:
        entries = [e for e in entries if e["pdf_id"] == args.pdf_id]
    if args.max_pdfs:
        entries = entries[: args.max_pdfs]

    _print(f"\n  Active parsers: {[n for n, *_ in active]}")
    _print(f"  PDFs to process: {len(entries)}")
    _print("\n" + "=" * 72)

    all_rows = []
    run_start = time.perf_counter()

    for entry in entries:
        pdf_id = entry["pdf_id"]
        pdf_type = entry.get("detected_pdf_type", "unknown")
        local_path = ROOT / entry["local_path"]
        page_count = entry.get("page_count", "?")
        size_kb = entry.get("file_size_bytes", 0) // 1024

        _print(f"\n  {pdf_id}  [{pdf_type}]  {page_count}p  {size_kb}KB")

        for name, mod_path, cls_name, cfg, category in active:
            sys.stdout.write(f"    {name:<12} ... ")
            sys.stdout.flush()
            t0 = time.perf_counter()

            try:
                parser = build_parser(mod_path, cls_name, cfg)
                result = parser.run(
                    path=local_path,
                    pdf_id=pdf_id,
                    pdf_type=pdf_type,
                )
                pages = result.page_count_detected
                chars = len(result.raw_text_full)
                tables = len(result.tables)
                ms = result.duration_ms or int((time.perf_counter() - t0) * 1000)
                lib_ver = getattr(
                    importlib.import_module(
                        "pytesseract" if name == "tesseract" else "ocrmypdf"
                    ),
                    "__version__",
                    "?",
                )

                if result.status == "completed":
                    status = "completed"
                    print(f"OK   {pages}p  {chars:>9,} chars  {tables}t  {ms:>7}ms")
                else:
                    status = "failed"
                    err = (result.error_message or "unknown")[:80]
                    print(f"FAIL  {err}")

                _log(
                    f"extraction_end status={status} parser_name={name} "
                    f"pdf_id={pdf_id} pdf_type={pdf_type} "
                    f"duration_ms={ms} page_count_detected={pages} "
                    f"text_length={chars} table_count={tables} "
                    f"library_version={lib_ver}"
                )
                all_rows.append(
                    (pdf_id, pdf_type, name, status, pages, chars, tables, ms, "")
                )

            except Exception as exc:
                ms = int((time.perf_counter() - t0) * 1000)
                err = str(exc)[:80]
                print(f"ERR   {err}")
                _log(
                    f"extraction_end status=error parser_name={name} "
                    f"pdf_id={pdf_id} pdf_type={pdf_type} "
                    f"duration_ms={ms} page_count_detected=0 "
                    f"text_length=0 table_count=0 library_version=?"
                )
                all_rows.append((pdf_id, pdf_type, name, "error", 0, 0, 0, ms, err))

    total_time = int(time.perf_counter() - run_start)

    # ── Summary ──────────────────────────────────────────────────────────────
    _print("\n" + "=" * 72)
    _print(f"  Summary  —  completed in {total_time}s")
    _print("=" * 72)
    _print(
        f"\n  {'Parser':<14} {'OK':>4} {'FAIL':>5} {'Avg chars':>11} {'Avg ms':>8} {'Tables':>7}"
    )
    _print("  " + "-" * 56)

    for name, *_ in OCR_PARSERS:
        rows = [r for r in all_rows if r[2] == name]
        if not rows:
            _print(f"  {name:<14}  {'—':>4}  {'—':>4}  {'—':>10}  {'—':>7}")
            continue
        ok_rows = [r for r in rows if r[3] == "completed"]
        fail_rows = [r for r in rows if r[3] != "completed"]
        avg_chars = int(sum(r[5] for r in ok_rows) / len(ok_rows)) if ok_rows else 0
        avg_ms = int(sum(r[7] for r in ok_rows) / len(ok_rows)) if ok_rows else 0
        total_tbl = sum(r[6] for r in ok_rows)
        _print(
            f"  {name:<14} {len(ok_rows):>4} {len(fail_rows):>5} {avg_chars:>11,} {avg_ms:>8} {total_tbl:>7}"
        )

    total_ok = sum(1 for r in all_rows if r[3] == "completed")
    total_fail = sum(1 for r in all_rows if r[3] != "completed")
    _print(f"\n  Total runs: {len(all_rows)}  |  {total_ok} OK  |  {total_fail} failed")
    _print(f"  Log saved to: {LOG_PATH}\n")

    # print structured summary for downstream scripts
    _print("\n=== STRUCTURED SUMMARY ===")
    _print("parser,n,avg_ms,avg_chars,total_tables,avg_pages,ms_per_page,lib_ver")
    for name, *_ in OCR_PARSERS:
        rows = [r for r in all_rows if r[2] == name and r[3] == "completed"]
        if not rows:
            _print(f"{name},0,0,0,0,0,0,?")
            continue
        n = len(rows)
        avg_ms = int(sum(r[7] for r in rows) / n)
        avg_chars = int(sum(r[5] for r in rows) / n)
        total_tables = sum(r[6] for r in rows)
        avg_pages = sum(r[4] for r in rows) / n
        mpp = int(avg_ms / avg_pages) if avg_pages else 0
        lib_ver = "?"
        _print(
            f"{name},{n},{avg_ms},{avg_chars},{total_tables},{avg_pages:.1f},{mpp},{lib_ver}"
        )

    _log_fh.close()


if __name__ == "__main__":
    main()
