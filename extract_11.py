"""
extract_11.py — Run 11 parsers on ALL catalog PDFs (all PDF types).

Excludes: marker, nougat, tabula  (no Java / excluded by request)
Includes: pymupdf, pdfplumber, pypdf, pypdfium2, pdftext, unstructured,
          camelot, easyocr, tesseract, ocrmypdf

OCR parsers run on ALL PDF types (not gated by --include-ocr).
EasyOCR is auto-enabled for image/scanned PDF types; for digital types it
still runs but may produce low char counts (expected behaviour).

Usage:
    python extract_11.py
    python extract_11.py --parser tesseract
    python extract_11.py --pdf-type image_only_scanned_pdf
    python extract_11.py --max-pdfs 5
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

# ── Tesseract PATH setup (must be before pytesseract import) ────────────────
TESSERACT_DIR = r"C:\Users\ganeshg\AppData\Local\Programs\Tesseract-OCR"
TESSERACT_EXE = os.path.join(TESSERACT_DIR, "tesseract.exe")
if os.path.isfile(TESSERACT_EXE):
    os.environ["PATH"] = TESSERACT_DIR + os.pathsep + os.environ.get("PATH", "")

# ── project root ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

PARSED_ROOT = str(ROOT / "data" / "parsed")
CATALOG_PATH = ROOT / "data" / "catalog" / "pdf_catalog.jsonl"
LOG_PATH = ROOT / "extract_11.log"

# ── 11-parser registry (marker, nougat, tabula excluded) ─────────────────────
# OCR parsers capped at MAX_OCR_PAGES to keep runtime tractable.
MAX_OCR_PAGES = 10

PARSER_DEFS = [
    (
        "pymupdf",
        "pdf_research_pipeline.parsers.pymupdf_parser",
        "PyMuPDFParser",
        {"extract_blocks": True, "extract_words": True},
        "text",
    ),
    (
        "pdfplumber",
        "pdf_research_pipeline.parsers.pdfplumber_parser",
        "PDFPlumberParser",
        {"extract_text": True, "extract_tables": True},
        "text",
    ),
    ("pypdf", "pdf_research_pipeline.parsers.pypdf_parser", "PyPDFParser", {}, "text"),
    (
        "pypdfium2",
        "pdf_research_pipeline.parsers.pypdfium2_parser",
        "PyPDFium2Parser",
        {},
        "text",
    ),
    (
        "pdftext",
        "pdf_research_pipeline.parsers.pdftext_parser",
        "PDFTextParser",
        {},
        "text",
    ),
    (
        "unstructured",
        "pdf_research_pipeline.parsers.unstructured_parser",
        "UnstructuredParser",
        {"strategy": "fast", "include_page_breaks": True},
        "general",
    ),
    (
        "camelot",
        "pdf_research_pipeline.parsers.table_extractors",
        "CamelotExtractor",
        {"flavor": "lattice", "pages": "all"},
        "table",
    ),
    (
        "easyocr",
        "pdf_research_pipeline.parsers.easyocr_parser",
        "EasyOCRParser",
        {"lang": ["en"], "gpu": False, "dpi": 150, "max_pages": MAX_OCR_PAGES},
        "ocr",
    ),
    (
        "tesseract",
        "pdf_research_pipeline.parsers.tesseract_parser",
        "TesseractParser",
        {"lang": "eng", "max_pages": MAX_OCR_PAGES},
        "ocr",
    ),
    (
        "ocrmypdf",
        "pdf_research_pipeline.parsers.ocrmypdf_parser",
        "OCRmyPDFParser",
        {"max_pages": MAX_OCR_PAGES},
        "ocr",
    ),
]

# OCR-heavy PDF types — run all OCR parsers fully; for other types OCR still
# runs but we expect low text yield (that itself is a valid benchmark result)
OCR_PDF_TYPES = {"image_only_scanned_pdf", "searchable_image_pdf"}

# ── ANSI colours ─────────────────────────────────────────────────────────────
_G = "\033[32m"
_R = "\033[31m"
_Y = "\033[33m"
_B = "\033[1m"
_X = "\033[0m"


def g(s):
    return f"{_G}{s}{_X}"


def r(s):
    return f"{_R}{s}{_X}"


def y(s):
    return f"{_Y}{s}{_X}"


def b(s):
    return f"{_B}{s}{_X}"


_LIB_MAP = {
    "pymupdf": "fitz",
    "pdfplumber": "pdfplumber",
    "pypdf": "pypdf",
    "pypdfium2": "pypdfium2",
    "pdftext": "pdftext",
    "unstructured": "unstructured",
    "camelot": "camelot",
    "easyocr": "easyocr",
    "tesseract": "pytesseract",
    "ocrmypdf": "ocrmypdf",
}


def check_lib(name: str) -> tuple[bool, str]:
    module = _LIB_MAP.get(name, name)
    try:
        mod = importlib.import_module(module)
        ver = getattr(mod, "__version__", None)
        if ver is None and name == "pypdfium2":
            try:
                info = getattr(mod, "PDFIUM_INFO", None)
                ver = f"build {info.V_LIBPDFIUM}" if info else "installed"
            except Exception:
                ver = "installed"
        return True, str(ver or "installed")
    except ImportError as exc:
        return False, str(exc).split("\n")[0]


def check_binary(cmd: list[str]) -> tuple[bool, str]:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return res.returncode == 0, (res.stdout + res.stderr).split("\n")[0].strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "not on PATH"


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
    return getattr(mod, cls_name)(parsed_root=PARSED_ROOT, config=config)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run 11 parsers on all catalog PDFs")
    ap.add_argument("--parser", default=None, help="Restrict to one parser name")
    ap.add_argument("--pdf-id", default=None, help="Restrict to one pdf_id")
    ap.add_argument("--pdf-type", default=None, help="Restrict to one pdf_type")
    ap.add_argument("--max-pdfs", type=int, default=None, help="Cap number of PDFs")
    args = ap.parse_args()

    # ── 1. Pre-flight checks ─────────────────────────────────────────────
    print(f"\n{b('=' * 80)}")
    print(f"  {b('extract_11.py  —  11 parsers × all PDF types')}")
    print(f"{b('=' * 80)}")

    tesseract_ok, tess_ver = check_binary(["tesseract", "--version"])

    skip_reasons: dict[str, str] = {}
    print(f"\n  {'Parser':<14} {'Cat':<8} {'Library':<14} Status")
    print("  " + "-" * 60)
    for name, _, _, _, cat in PARSER_DEFS:
        ok, ver = check_lib(name)
        ver_s = ver[:12]
        if not ok:
            skip_reasons[name] = "lib missing"
            print(f"  {name:<14} {cat:<8} {ver_s:<14} {r('[X] NOT INSTALLED')}")
        elif name in ("tesseract", "ocrmypdf") and not tesseract_ok:
            skip_reasons[name] = "tesseract binary absent"
            print(
                f"  {name:<14} {cat:<8} {ver_s:<14} {y('[OK] lib / [X] Tesseract binary')}"
            )
        else:
            print(f"  {name:<14} {cat:<8} {ver_s:<14} {g('[OK] ' + ver_s)}")

    active = [
        (n, mp, cn, cfg, cat)
        for n, mp, cn, cfg, cat in PARSER_DEFS
        if n not in skip_reasons
    ]
    if args.parser:
        active = [
            (n, mp, cn, cfg, cat) for n, mp, cn, cfg, cat in active if n == args.parser
        ]
        if not active:
            print(r(f"\n  Parser '{args.parser}' not available."))
            sys.exit(1)

    print(f"\n  Active: {', '.join(n for n, *_ in active)}  ({len(active)} parsers)")

    # ── 2. Load catalog ──────────────────────────────────────────────────
    catalog = load_catalog()
    if args.pdf_id:
        catalog = [e for e in catalog if e["pdf_id"] == args.pdf_id]
    if args.pdf_type:
        catalog = [e for e in catalog if e.get("detected_pdf_type") == args.pdf_type]
    if args.max_pdfs:
        catalog = catalog[: args.max_pdfs]

    # Group by PDF type for summary
    by_type: dict[str, int] = defaultdict(int)
    for e in catalog:
        by_type[e.get("detected_pdf_type", "unknown")] += 1

    print(f"\n  PDFs to process: {len(catalog)}")
    for pt, cnt in sorted(by_type.items()):
        print(f"    {pt}: {cnt}")

    print(f"\n{b('=' * 80)}")
    print(
        f"  {b('Extraction  —  ' + str(len(catalog)) + ' PDFs  ×  ' + str(len(active)) + ' parsers')}"
    )
    print(f"{b('=' * 80)}")

    # ── 3. Open log file ─────────────────────────────────────────────────
    log_fh = LOG_PATH.open("w", encoding="utf-8")
    log_fh.write(f"extract_11 run started {time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
    log_fh.write(f"parsers: {[n for n, *_ in active]}\n")
    log_fh.write(f"pdfs: {len(catalog)}\n\n")

    # ── 4. Extraction loop ───────────────────────────────────────────────
    Row = tuple  # (pdf_id, pdf_type, parser, status, pages, chars, tables, ms, err)
    all_rows: list[Row] = []
    run_start = time.perf_counter()

    for entry in catalog:
        pdf_id = entry["pdf_id"]
        pdf_type = entry.get("detected_pdf_type", "unknown")
        local = ROOT / Path(
            entry["local_path"]
        )  # resolve relative paths against project root
        n_pages = entry.get("page_count", "?")
        size_kb = entry.get("file_size_bytes", 0) // 1024

        print(f"\n  {b(pdf_id)}  [{pdf_type}]  {n_pages}p  {size_kb}KB")

        for name, mod_path, cls_name, cfg, cat in active:
            sys.stdout.write(f"    {name:<14} … ")
            sys.stdout.flush()
            t0 = time.perf_counter()
            try:
                parser = build_parser(mod_path, cls_name, cfg)
                result = parser.run(path=local, pdf_id=pdf_id, pdf_type=pdf_type)
                pages = result.page_count_detected
                chars = len(result.raw_text_full)
                tables = len(result.tables)
                ms = result.duration_ms or int((time.perf_counter() - t0) * 1000)

                if result.status == "completed":
                    print(g(f"OK   {pages}p  {chars:>9,} chars  {tables}t  {ms:>7}ms"))
                    all_rows.append(
                        (
                            pdf_id[:22],
                            pdf_type,
                            name,
                            "ok",
                            pages,
                            chars,
                            tables,
                            ms,
                            "",
                        )
                    )
                else:
                    err = (result.error_message or "unknown")[:80]
                    print(y(f"FAIL  {err}"))
                    all_rows.append(
                        (
                            pdf_id[:22],
                            pdf_type,
                            name,
                            "fail",
                            pages,
                            chars,
                            tables,
                            ms,
                            err,
                        )
                    )

            except Exception as exc:
                ms = int((time.perf_counter() - t0) * 1000)
                err = str(exc)[:80]
                print(r(f"ERR   {err}"))
                all_rows.append(
                    (pdf_id[:22], pdf_type, name, "error", 0, 0, 0, ms, err)
                )

            log_fh.write(
                json.dumps(
                    {
                        "pdf_id": pdf_id,
                        "pdf_type": pdf_type,
                        "parser": name,
                        "status": all_rows[-1][3],
                        "pages": all_rows[-1][4],
                        "chars": all_rows[-1][5],
                        "tables": all_rows[-1][6],
                        "ms": all_rows[-1][7],
                        "error": all_rows[-1][8],
                    }
                )
                + "\n"
            )
            log_fh.flush()

    total_time = int(time.perf_counter() - run_start)
    log_fh.close()

    # ── 5. Summary ────────────────────────────────────────────────────────
    print(f"\n{b('=' * 80)}")
    print(f"  {b('Summary')}  —  {total_time}s total runtime")
    print(f"{b('=' * 80)}\n")

    by_parser: dict[str, list] = defaultdict(list)
    for row in all_rows:
        by_parser[row[2]].append(row)

    print(
        f"  {'Parser':<14} {'Cat':<8} {'OK':>4} {'Fail':>5} {'Avg chars':>11} {'Avg ms':>8} {'Tables':>7}"
    )
    print("  " + "-" * 60)
    for name, _, _, _, cat in PARSER_DEFS:
        rows = by_parser.get(name)
        if name in skip_reasons:
            print(
                f"  {name:<14} {cat:<8}  {'—':>4}  {'—':>4}  {'—':>10}  {'—':>7}   skipped ({skip_reasons[name]})"
            )
            continue
        if not rows:
            continue
        ok_rows = [rw for rw in rows if rw[3] == "ok"]
        fail_rows = [rw for rw in rows if rw[3] != "ok"]
        avg_c = int(sum(rw[5] for rw in ok_rows) / len(ok_rows)) if ok_rows else 0
        avg_m = int(sum(rw[7] for rw in ok_rows) / len(ok_rows)) if ok_rows else 0
        ttbl = sum(rw[6] for rw in ok_rows)
        ok_s = g(f"{len(ok_rows):>4}") if ok_rows else f"{0:>4}"
        fl_s = r(f"{len(fail_rows):>5}") if fail_rows else f"{0:>5}"
        print(f"  {name:<14} {cat:<8} {ok_s} {fl_s} {avg_c:>11,} {avg_m:>8} {ttbl:>7}")

    ok_total = sum(1 for rw in all_rows if rw[3] == "ok")
    fail_total = sum(1 for rw in all_rows if rw[3] != "ok")
    print(
        f"\n  Runs: {len(all_rows)}  |  {g(str(ok_total) + ' OK')}  |  {r(str(fail_total) + ' failed')}"
    )
    print(f"  Log: {LOG_PATH}")
    print(f"  Parsed output: {PARSED_ROOT}\n")

    # ── 6. Failure detail ─────────────────────────────────────────────────
    fails = [rw for rw in all_rows if rw[3] != "ok"]
    if fails:
        print(f"  {b('Failures:')}")
        for rw in fails:
            print(f"    {rw[2]:<14}  {rw[0]}  [{rw[1]}]  →  {rw[8]}")
        print()


if __name__ == "__main__":
    main()
