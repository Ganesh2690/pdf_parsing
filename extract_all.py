"""
extract_all.py  —  Run all available parsers on every PDF in the catalog.

Usage (from the pdf_research_pipeline directory):
    python extract_all.py                 # fast parsers only (skips EasyOCR)
    python extract_all.py --include-ocr   # also run EasyOCR (slow on CPU)
    python extract_all.py --parser pymupdf
    python extract_all.py --pdf-id 194dfc73f757_arxiv_2501.05032v2
    python extract_all.py --max-pdfs 2

Results are saved to  data/parsed/<pdf_type>/<pdf_id>/<parser>/
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

# ── locate project root ────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

PARSED_ROOT = str(ROOT / "data" / "parsed")
CATALOG_PATH = ROOT / "data" / "catalog" / "pdf_catalog.jsonl"

# ── parser registry ─────────────────────────────────────────────────────────
# (name, module_path, class_name, config, category)
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
        "tabula",
        "pdf_research_pipeline.parsers.table_extractors",
        "TabulaExtractor",
        {"pages": "all", "multiple_tables": True},
        "table",
    ),
    (
        "easyocr",
        "pdf_research_pipeline.parsers.easyocr_parser",
        "EasyOCRParser",
        {"lang": ["en"], "gpu": False, "dpi": 150},
        "ocr",
    ),
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
        {},
        "ocr",
    ),
    ("marker", "pdf_research_pipeline.parsers.marker_parser", "MarkerParser", {}, "ml"),
    ("nougat", "pdf_research_pipeline.parsers.nougat_parser", "NougatParser", {}, "ml"),
]

# ── colour helpers (ANSI) ────────────────────────────────────────────────────
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_RESET = "\033[0m"
_BOLD = "\033[1m"


def _g(s):
    return f"{_GREEN}{s}{_RESET}"


def _r(s):
    return f"{_RED}{s}{_RESET}"


def _y(s):
    return f"{_YELLOW}{s}{_RESET}"


def _b(s):
    return f"{_BOLD}{s}{_RESET}"


# ── install checks ─────────────────────────────────────────────────────────

_LIB_MAP = {
    "pymupdf": "fitz",
    "pdfplumber": "pdfplumber",
    "pypdf": "pypdf",
    "pypdfium2": "pypdfium2",
    "pdftext": "pdftext",
    "unstructured": "unstructured",
    "camelot": "camelot",
    "tabula": "tabula",
    "easyocr": "easyocr",
    "tesseract": "pytesseract",
    "ocrmypdf": "ocrmypdf",
    "marker": "marker",
    "nougat": "nougat_ocr",
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
            except (KeyError, AttributeError):
                ver = "installed"
        return True, str(ver or "installed")
    except ImportError as exc:
        return False, str(exc).split("\n")[0]


def check_binary(cmd: list[str]) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        out = (r.stdout + r.stderr).split("\n")[0].strip()
        return r.returncode == 0, out
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "not on PATH"


# ── catalog loading ─────────────────────────────────────────────────────────


def load_catalog() -> list[dict]:
    entries = []
    with open(CATALOG_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


# ── parser instantiation ────────────────────────────────────────────────────


def build_parser(mod_path: str, cls_name: str, config: dict):
    mod = importlib.import_module(mod_path)
    cls = getattr(mod, cls_name)
    return cls(parsed_root=PARSED_ROOT, config=config)


# ── main ────────────────────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser(description="Run all parsers on catalog PDFs")
    ap.add_argument(
        "--include-ocr",
        action="store_true",
        help="Also run EasyOCR on every PDF (slow on CPU)",
    )
    ap.add_argument(
        "--parser", default=None, help="Only run this parser name (e.g. pymupdf)"
    )
    ap.add_argument("--pdf-id", default=None, help="Only process this pdf_id")
    ap.add_argument(
        "--max-pdfs", type=int, default=None, help="Cap the number of PDFs processed"
    )
    args = ap.parse_args()

    # ── 1. Library & binary checks ─────────────────────────────────────
    print(f"\n{_b('=' * 80)}")
    print(f"  {_b('Library & Binary Installation Check')}")
    print(f"{_b('=' * 80)}")

    tesseract_ok, tesseract_ver = check_binary(["tesseract", "--version"])
    java_ok, java_ver = check_binary(["java", "-version"])

    hdr = f"  {'Parser':<14} {'Category':<10} {'Library':<14} {'Status':<26} Notes"
    print(hdr)
    print("  " + "-" * 76)

    skip_reasons: dict[str, str] = {}

    for name, mod_path, cls_name, cfg, category in PARSER_DEFS:
        lib_ok, lib_ver = check_lib(name)
        lib_ver_short = lib_ver[:12]

        if not lib_ok:
            status = _r("[X] NOT INSTALLED")
            note = f"pip install {_LIB_MAP.get(name, name)}"
            skip_reasons[name] = "not installed"
        elif name == "tesseract" and not tesseract_ok:
            status = _y(f"[OK] lib / [X] binary")
            note = f"install Tesseract OCR ({tesseract_ver})"
            skip_reasons[name] = "binary absent"
        elif name == "tabula" and not java_ok:
            status = _y(f"[OK] lib / [X] Java")
            note = f"install Java runtime ({java_ver})"
            skip_reasons[name] = "Java absent"
        elif name == "ocrmypdf" and not tesseract_ok:
            status = _y("[OK] lib / needs Tesseract")
            note = "skipped (Tesseract binary absent)"
            skip_reasons[name] = "Tesseract absent"
        elif name == "easyocr" and not args.include_ocr:
            status = _y("[OK] installed")
            note = "skipped (digital PDFs — use --include-ocr to enable)"
            skip_reasons[name] = "ocr-skip"
        else:
            status = _g(f"[OK] {lib_ver_short}")
            note = ""

        print(f"  {name:<14} {category:<10} {lib_ver_short:<14} {status:<35} {note}")

    print()

    # ── 2. Build active parser list ────────────────────────────────────
    active = [
        (name, mod_path, cls_name, cfg, category)
        for (name, mod_path, cls_name, cfg, category) in PARSER_DEFS
        if name not in skip_reasons
    ]
    if args.parser:
        active = [(n, *rest) for n, *rest in active if n == args.parser]
        if not active:
            print(_r(f"  Parser '{args.parser}' not available or was skipped."))
            sys.exit(1)

    parser_names = [n for n, *_ in active]
    print(f"  {_b('Active parsers')} ({len(active)}): {', '.join(parser_names)}")

    # ── 3. Load catalog ────────────────────────────────────────────────
    entries = load_catalog()
    if args.pdf_id:
        entries = [e for e in entries if e["pdf_id"] == args.pdf_id]
        if not entries:
            print(_r(f"  pdf_id not found: {args.pdf_id}"))
            sys.exit(1)
    if args.max_pdfs:
        entries = entries[: args.max_pdfs]

    print(f"  {_b('PDFs to process')}: {len(entries)}")
    print(f"\n{_b('=' * 80)}")
    print(f"  {_b('Extraction Run')}  —  {len(entries)} PDFs  ×  {len(active)} parsers")
    print(f"{_b('=' * 80)}")

    # ── 4. Run extraction ──────────────────────────────────────────────
    Row = tuple  # (pdf_id, pdf_type, parser, status, pages, chars, tables, ms, err)
    all_rows: list[Row] = []
    run_start = time.perf_counter()

    for entry in entries:
        pdf_id = entry["pdf_id"]
        pdf_type = entry.get("detected_pdf_type", "unknown")
        local_path = Path(entry["local_path"])
        page_count = entry.get("page_count", "?")
        size_kb = entry.get("file_size_bytes", 0) // 1024

        print(f"\n  {_b(pdf_id)}  [{pdf_type}]  {page_count}p  {size_kb}KB")

        for name, mod_path, cls_name, cfg, category in active:
            sys.stdout.write(f"    {name:<14} … ")
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

                if result.status == "completed":
                    print(_g(f"OK   {pages}p  {chars:>9,} chars  {tables}t  {ms:>6}ms"))
                    all_rows.append(
                        (
                            pdf_id[:20],
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
                    err = (result.error_message or "unknown error")[:70]
                    print(_y(f"FAIL  {err}"))
                    all_rows.append(
                        (
                            pdf_id[:20],
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
                err = str(exc)[:70]
                print(_r(f"ERR   {err}"))
                all_rows.append(
                    (pdf_id[:20], pdf_type, name, "error", 0, 0, 0, ms, err)
                )

    total_time = int(time.perf_counter() - run_start)

    # ── 5. Summary table ───────────────────────────────────────────────
    print(f"\n{_b('=' * 80)}")
    print(f"  {_b('Summary')}  —  completed in {total_time}s")
    print(f"{_b('=' * 80)}\n")

    by_parser: dict[str, list] = defaultdict(list)
    for row in all_rows:
        by_parser[row[2]].append(row)

    hdr2 = f"  {'Parser':<14} {'Category':<10} {'OK':>4} {'FAIL':>5} {'Avg chars':>11} {'Avg ms':>8} {'Tables':>7}"
    print(hdr2)
    print("  " + "-" * 60)

    for name, mod_path, cls_name, cfg, category in PARSER_DEFS:
        rows = by_parser.get(name)
        if name in skip_reasons:
            reason = skip_reasons[name]
            print(
                f"  {name:<14} {category:<10}  {'—':>4}  {'—':>4}  {'—':>10}  {'—':>7}   skipped ({reason})"
            )
            continue
        if rows is None:
            continue
        ok_rows = [r for r in rows if r[3] == "ok"]
        fail_rows = [r for r in rows if r[3] != "ok"]
        avg_chars = int(sum(r[5] for r in ok_rows) / len(ok_rows)) if ok_rows else 0
        avg_ms = int(sum(r[7] for r in ok_rows) / len(ok_rows)) if ok_rows else 0
        total_tbl = sum(r[6] for r in ok_rows)
        ok_str = _g(f"{len(ok_rows):>4}") if ok_rows else f"{0:>4}"
        fail_str = _r(f"{len(fail_rows):>5}") if fail_rows else f"{0:>5}"
        print(
            f"  {name:<14} {category:<10} {ok_str} {fail_str} {avg_chars:>11,} {avg_ms:>8} {total_tbl:>7}"
        )

    total_ok = sum(1 for r in all_rows if r[3] == "ok")
    total_fail = sum(1 for r in all_rows if r[3] != "ok")
    total_runs = len(all_rows)
    print(
        f"\n  Total runs: {total_runs}  |  {_g(str(total_ok) + ' OK')}  |  {_r(str(total_fail) + ' failed')}"
    )
    print(f"  Results saved to: {PARSED_ROOT}\n")

    # ── 6. Per-parser failures detail ─────────────────────────────────
    fail_rows = [r for r in all_rows if r[3] != "ok"]
    if fail_rows:
        print(f"  {_b('Failures:')}")
        for row in fail_rows:
            print(f"    {row[2]:<14}  {row[0]}  →  {row[8]}")
        print()


if __name__ == "__main__":
    main()
