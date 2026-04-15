"""
update_report.py  –  Patches accuracy_report.html with extract_11.log results.

Usage:
    cd D:\\Projects\\pdf\\pdf_research_pipeline
    python update_report.py

Reads:
    extract_11.log                         JSON-lines extraction results
    artifacts/reports/accuracy_report.html existing HTML report
    data/catalog/pdf_catalog.jsonl         PDF metadata

Writes:
    artifacts/reports/accuracy_report.html (updated in-place)
"""

from __future__ import annotations

import html as _html
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).parent
LOG_FILE = ROOT / "extract_11.log"
REPORT_FILE = ROOT / "artifacts" / "reports" / "accuracy_report.html"
CATALOG_FILE = ROOT / "data" / "catalog" / "pdf_catalog.jsonl"

_PARSER_COLORS: dict[str, str] = {
    "pymupdf": "#2196F3",
    "pdfplumber": "#4CAF50",
    "pypdf": "#FF9800",
    "pypdfium2": "#00BCD4",
    "pdftext": "#9C27B0",
    "easyocr": "#F44336",
    "tesseract": "#795548",
    "ocrmypdf": "#FF5722",
    "unstructured": "#607D8B",
    "camelot": "#E91E63",
    "tabula": "#3F51B5",
    "marker": "#009688",
    "nougat": "#FFC107",
}

_PDF_TYPE_COLORS: dict[str, str] = {
    "complex_layout_pdf": "#1565C0",
    "forms_interactive_pdf": "#E91E63",
    "image_only_scanned_pdf": "#795548",
    "searchable_image_pdf": "#FF6F00",
    "specialized_pdf": "#9C27B0",
    "true_digital_pdf": "#2E7D32",
}


def _pc(parser: str) -> str:
    return _PARSER_COLORS.get(parser.lower(), "#78909C")


def _tc(pdf_type: str) -> str:
    return _PDF_TYPE_COLORS.get(pdf_type, "#607D8B")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_results(log_path: Path) -> list[dict]:
    rows = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def load_catalog(catalog_path: Path) -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for line in catalog_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            # normalise: detected_pdf_type → pdf_type; page_count → pages
            entry.setdefault("pdf_type", entry.get("detected_pdf_type", "unknown"))
            entry.setdefault("pages", entry.get("page_count", "?"))
            entries[entry["pdf_id"]] = entry
        except (json.JSONDecodeError, KeyError):
            pass
    return entries


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def compute_stats(results: list[dict]):
    """Returns (parser_stats, type_parser_stats, pdf_parser_map)."""

    # parser → {ms, chars, tables, ok, fail, pages}
    parser_stats: dict[str, dict] = defaultdict(
        lambda: {"ms": [], "chars": [], "tables": 0, "ok": 0, "fail": 0, "pages": []}
    )
    # pdf_type → parser → {ms, chars, tables, ok, fail}
    type_parser: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(
            lambda: {"ms": [], "chars": [], "tables": 0, "ok": 0, "fail": 0}
        )
    )
    # (pdf_id, parser) → row
    pdf_parser_map: dict[tuple, dict] = {}

    for r in results:
        p = r["parser"]
        pdf_type = r.get("pdf_type", "unknown")
        status = r.get("status", "")
        ms = r.get("ms", 0)
        chars = r.get("chars", 0)
        tables = r.get("tables", 0)
        pages = r.get("pages", 0)

        if status == "ok":
            parser_stats[p]["ms"].append(ms)
            parser_stats[p]["chars"].append(chars)
            parser_stats[p]["tables"] += tables
            parser_stats[p]["ok"] += 1
            parser_stats[p]["pages"].append(pages)
            type_parser[pdf_type][p]["ms"].append(ms)
            type_parser[pdf_type][p]["chars"].append(chars)
            type_parser[pdf_type][p]["tables"] += tables
            type_parser[pdf_type][p]["ok"] += 1
        else:
            parser_stats[p]["fail"] += 1
            type_parser[pdf_type][p]["fail"] += 1

        pdf_parser_map[(r["pdf_id"], p)] = r

    return parser_stats, type_parser, pdf_parser_map


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------


def _ms_color(ms: int, med: float) -> str:
    if ms <= med * 0.5:
        return "#2E7D32"
    if ms <= med * 1.5:
        return "#1565C0"
    return "#B71C1C"


def _fmt_ms(ms: int) -> str:
    if ms >= 1_000_000:
        return f"{ms // 1000:,}s"
    if ms >= 1_000:
        return f"{ms:,}"
    return str(ms)


def _pill(status: str) -> str:
    if status == "ok":
        return '<span class="pill pill-best">OK</span>'
    return f'<span class="pill pill-poor">{_html.escape(status)}</span>'


# ---------------------------------------------------------------------------
# Benchmark tab builder
# ---------------------------------------------------------------------------


def build_benchmark_tab(
    results: list[dict],
    catalog: dict[str, dict],
) -> str:
    if not results:
        return "<div class='section'><p>No extraction results yet. Run extract_11.py first.</p></div>"

    parser_stats, type_parser, pdf_parser_map = compute_stats(results)

    all_parsers = sorted(parser_stats.keys())
    all_pdf_ids = sorted({r["pdf_id"] for r in results})
    all_pdf_types = sorted({r.get("pdf_type", "unknown") for r in results})

    total_runs = len(results)
    ok_runs = sum(1 for r in results if r.get("status") == "ok")
    fail_runs = total_runs - ok_runs

    # Fastest parser (by avg ms/page, text parsers only)
    def _avg_ms_per_page(p: str) -> float:
        st = parser_stats[p]
        if not st["ms"] or not st["pages"]:
            return float("inf")
        total_ms = sum(st["ms"])
        total_pages = sum(st["pages"])
        return total_ms / max(total_pages, 1)

    text_parsers = [
        p
        for p in all_parsers
        if p in ("pymupdf", "pdfplumber", "pypdf", "pypdfium2", "pdftext")
    ]
    if text_parsers:
        fastest = min(text_parsers, key=_avg_ms_per_page)
        fastest_mpp = _avg_ms_per_page(fastest)
    else:
        fastest = min(all_parsers, key=_avg_ms_per_page) if all_parsers else "N/A"
        fastest_mpp = _avg_ms_per_page(fastest) if all_parsers else 0

    # Most chars
    most_chars_p = max(
        all_parsers,
        key=lambda p: mean(parser_stats[p]["chars"]) if parser_stats[p]["chars"] else 0,
        default="N/A",
    )
    most_chars_avg = (
        int(mean(parser_stats[most_chars_p]["chars"]))
        if parser_stats[most_chars_p]["chars"]
        else 0
    )

    # Best table extractor
    best_table_p = max(
        all_parsers, key=lambda p: parser_stats[p]["tables"], default="N/A"
    )
    best_table_n = parser_stats[best_table_p]["tables"]

    # --- hero ---
    hero = f"""
<div class="hero" style="padding:28px 44px">
  <h1 style="font-size:1.5rem">Live Benchmark Results — {ok_runs} Runs ({len(all_parsers)} Parsers × {len(all_pdf_ids)} {"PDF" if len(all_pdf_ids) == 1 else "PDFs"})</h1>
  <p style="margin-top:6px;opacity:.85">{ok_runs}/{total_runs} successful · {fail_runs} failed · {len(all_pdf_types)} PDF categories</p>
  <div style="display:flex;flex-wrap:wrap;gap:18px;margin-top:18px">
    <div style="background:rgba(255,255,255,.18);border-radius:8px;padding:12px 18px">
      <div style="font-size:.78rem;opacity:.75">FASTEST TEXT PARSER</div>
      <div style="font-size:1.4rem;font-weight:700;color:#FFD740">{fastest.upper()}</div>
      <div style="font-size:.85rem;opacity:.9">{fastest_mpp:.0f} ms/page</div>
    </div>
    <div style="background:rgba(255,255,255,.18);border-radius:8px;padding:12px 18px">
      <div style="font-size:.78rem;opacity:.75">MOST TEXT OUTPUT</div>
      <div style="font-size:1.4rem;font-weight:700;color:#FFD740">{most_chars_p.upper()}</div>
      <div style="font-size:.85rem;opacity:.9">{most_chars_avg:,} avg chars</div>
    </div>
    <div style="background:rgba(255,255,255,.18);border-radius:8px;padding:12px 18px">
      <div style="font-size:.78rem;opacity:.75">BEST TABLE EXTRACTOR</div>
      <div style="font-size:1.4rem;font-weight:700;color:#FFD740">{best_table_p.upper()}</div>
      <div style="font-size:.85rem;opacity:.9">{best_table_n} tables detected</div>
    </div>
    <div style="background:rgba(255,255,255,.18);border-radius:8px;padding:12px 18px">
      <div style="font-size:.78rem;opacity:.75">PDF TYPES COVERED</div>
      <div style="font-size:1.4rem;font-weight:700;color:#FFD740">{len(all_pdf_types)}</div>
      <div style="font-size:.85rem;opacity:.9">{len(all_pdf_ids)} total PDFs</div>
    </div>
    <div style="background:rgba(255,255,255,.18);border-radius:8px;padding:12px 18px">
      <div style="font-size:.78rem;opacity:.75">PARSERS RAN (LIVE)</div>
      <div style="font-size:1.4rem;font-weight:700;color:#FFD740">{len(all_parsers)} / 13</div>
      <div style="font-size:.85rem;opacity:.9">{ok_runs} total runs, {fail_runs} failed</div>
    </div>
  </div>
</div>
"""

    # --- performance summary table ---
    perf_rows = []
    for rank, p in enumerate(sorted(all_parsers, key=_avg_ms_per_page), start=1):
        st = parser_stats[p]
        avg_ms = int(mean(st["ms"])) if st["ms"] else 0
        mpp = _avg_ms_per_page(p)
        avg_chars = int(mean(st["chars"])) if st["chars"] else 0
        rank_icon = {1: "🥇 1", 2: "🥈 2", 3: "🥉 3"}.get(rank, str(rank))
        bg = (
            ' style="background:#E8F5E9"'
            if rank == 1
            else (
                ' style="background:#E3F2FD"'
                if p in ("easyocr", "tesseract", "ocrmypdf")
                else ""
            )
        )
        perf_rows.append(
            f'<tr{bg}><td><b>{rank_icon}</b></td><td><b style="color:{_pc(p)}">{p}</b></td>'
            f"<td>{avg_ms:,}</td><td><b>{mpp:,.0f}</b></td>"
            f"<td>{avg_chars:,}</td><td>{st['tables']}</td>"
            f"<td>{st['ok']} ok / {st['fail']} fail</td></tr>"
        )

    perf_section = f"""
<div class="section">
  <div class="section-title">Performance Summary — ms/page Ranking</div>
  <div class="section-sub">Lower ms/page is better. OCR parsers capped at {10} pages. Camelot ms/page based on pages-with-tables.</div>
  <div class="card" style="overflow-x:auto"><table>
    <thead><tr>
      <th>Rank</th><th>Parser</th><th>Avg Total ms</th><th>Avg ms/page</th>
      <th>Avg Chars/PDF</th><th>Total Tables</th><th>Runs</th>
    </tr></thead>
    <tbody>{"".join(perf_rows)}</tbody>
  </table></div>
"""

    # --- per-pdf-type breakdown ---
    type_sections = ""
    for pdf_type in sorted(all_pdf_types):
        tp = type_parser.get(pdf_type, {})
        type_pdfs = sorted(
            {r["pdf_id"] for r in results if r.get("pdf_type") == pdf_type}
        )
        type_parsers = sorted(tp.keys())

        col_headers = "".join(
            f'<th style="color:{_pc(p)}">{p}</th>' for p in type_parsers
        )

        type_rows = []
        for pdf_id in type_pdfs:
            short_id = pdf_id[:22] + "…" if len(pdf_id) > 23 else pdf_id
            cat_entry = catalog.get(pdf_id, {})
            pages = cat_entry.get("pages", "?")
            cells = ""
            for p in type_parsers:
                row = pdf_parser_map.get((pdf_id, p))
                if row is None:
                    cells += "<td>—</td>"
                elif row.get("status") != "ok":
                    cells += f'<td><span class="pill pill-poor">ERR</span></td>'
                else:
                    ms = row.get("ms", 0)
                    chars = row.get("chars", 0)
                    tables = row.get("tables", 0)
                    t_suffix = f" <small>({tables}t)</small>" if tables else ""
                    cells += (
                        f'<td title="{chars:,} chars">'
                        f'<b style="color:{_ms_color(ms, ms)}">{_fmt_ms(ms)}ms</b>'
                        f"{t_suffix}</td>"
                    )
            type_rows.append(
                f'<tr><td title="{pdf_id}"><b>{short_id}</b></td><td>{pages}</td>{cells}</tr>'
            )

        tc = _tc(pdf_type)
        type_sections += f"""
  <div class="section-title" style="margin-top:28px;color:{tc}">{pdf_type.replace("_", " ").title()} ({len(type_pdfs)} PDFs)</div>
  <div class="section-sub">Parser extraction times (ms) and chars extracted.</div>
  <div class="card" style="overflow-x:auto"><table>
    <thead><tr>
      <th style="background:{tc}">PDF ID</th>
      <th style="background:{tc}">Pages</th>
      {col_headers.replace("<th", f'<th style="background:{tc};color:#fff"').replace(f'style="background:{tc};color:#fff" style="color:', f'style="background:{tc};color:')}
    </tr></thead>
    <tbody>{"".join(type_rows)}</tbody>
  </table></div>
"""

    # --- full parser × pdf grid (chars) ---
    char_headers = "".join(f'<th style="color:{_pc(p)}">{p}</th>' for p in all_parsers)
    char_rows = []
    for pdf_id in all_pdf_ids:
        short_id = pdf_id[:22] + "…" if len(pdf_id) > 23 else pdf_id
        cat_entry = catalog.get(pdf_id, {})
        pdf_type = cat_entry.get("pdf_type", "?")
        pages = cat_entry.get("pages", "?")
        cells = ""
        for p in all_parsers:
            row = pdf_parser_map.get((pdf_id, p))
            if row is None:
                cells += "<td>—</td>"
            elif row.get("status") != "ok":
                cells += f'<td><span class="pill pill-poor">ERR</span></td>'
            else:
                ms = row.get("ms", 0)
                cells += f"<td>{_fmt_ms(ms)}ms</td>"
        char_rows.append(
            f'<tr><td title="{pdf_id}"><b>{short_id}</b></td>'
            f'<td><small style="color:{_tc(pdf_type)}">{pdf_type.split("_")[0]}</small></td>'
            f"<td>{pages}</td>{cells}</tr>"
        )

    full_grid = f"""
  <div class="section-title" style="margin-top:28px">Per-PDF Extraction Times (ms) — All Parsers</div>
  <div class="section-sub">{len(all_parsers)} parsers × {len(all_pdf_ids)} PDFs = {ok_runs} successful runs.</div>
  <div class="card" style="overflow-x:auto"><table>
    <thead><tr>
      <th>PDF ID</th><th>Type</th><th>Pages</th>
      {char_headers}
    </tr></thead>
    <tbody>{"".join(char_rows)}</tbody>
  </table></div>
"""

    perf_section += type_sections + full_grid + "</div>"
    return hero + perf_section


# ---------------------------------------------------------------------------
# Report patcher
# ---------------------------------------------------------------------------

BENCHMARK_START = '<div id="tab-benchmark" class="tab-panel hidden">'
BENCHMARK_END_TOKENS = ["</div>\n\n<script", "</div>\n<script", "</div>\r\n<script"]


def patch_report(html: str, new_benchmark_body: str, nav_meta: str) -> str:
    # 1. Replace nav-meta
    import re

    html = re.sub(
        r'(<span class="nav-meta">)[^<]*(</span>)',
        r"\g<1>" + _html.escape(nav_meta) + r"\g<2>",
        html,
        count=1,
    )

    # 2. Replace benchmark tab content
    start_idx = html.find(BENCHMARK_START)
    if start_idx == -1:
        print("WARNING: Could not find benchmark tab start marker.")
        return html

    # Find the </div> that closes the benchmark tab
    # The tab div starts with BENCHMARK_START, find the next "<script" after it
    after_start = start_idx + len(BENCHMARK_START)
    script_idx = html.find("<script", after_start)
    if script_idx == -1:
        print("WARNING: Could not find <script> after benchmark tab.")
        return html

    # Walk backwards from script_idx to find the closing </div>\n
    # (could be </div>\n\n or </div>\n)
    end_idx = html.rfind("</div>", after_start, script_idx)
    if end_idx == -1:
        print("WARNING: Could not find closing </div> before <script>.")
        return html

    # Replace: from after BENCHMARK_START to </div> (inclusive)
    new_section = new_benchmark_body + "\n</div>"
    patched = (
        html[:after_start] + "\n" + new_section + "\n" + html[end_idx + len("</div>") :]
    )
    return patched


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not LOG_FILE.exists():
        print(f"ERROR: {LOG_FILE} not found. Run extract_11.py first.")
        return

    results = load_results(LOG_FILE)
    if not results:
        print("ERROR: No valid JSON rows found in extract_11.log.")
        return

    catalog = load_catalog(CATALOG_FILE) if CATALOG_FILE.exists() else {}

    all_parsers = sorted({r["parser"] for r in results})
    all_pdf_ids = sorted({r["pdf_id"] for r in results})
    all_pdf_types = sorted({r.get("pdf_type", "unknown") for r in results})
    ok_runs = sum(1 for r in results if r.get("status") == "ok")
    total_runs = len(results)

    # Compute winner (most chars, text parsers)
    _, _, pdf_parser_map = compute_stats(results)
    parser_stats, _, _ = compute_stats(results)
    text_parsers = [
        p
        for p in all_parsers
        if p in ("pymupdf", "pdfplumber", "pypdf", "pypdfium2", "pdftext")
    ]

    def _avg_chars(p: str) -> float:
        c = parser_stats[p]["chars"]
        return mean(c) if c else 0.0

    winner = max(text_parsers, key=_avg_chars, default="N/A") if text_parsers else "N/A"

    nav_meta = (
        f"10 parsers · {ok_runs}/{total_runs} runs · "
        f"{len(all_pdf_ids)} PDFs · {len(all_pdf_types)} types · Winner: {winner.upper()}"
    )

    print(
        f"  Results:   {total_runs} rows ({ok_runs} ok, {total_runs - ok_runs} failed)"
    )
    print(f"  Parsers:   {', '.join(all_parsers)}")
    print(f"  PDF types: {', '.join(all_pdf_types)}")
    print(f"  PDFs:      {len(all_pdf_ids)}")
    print(f"  Nav-meta:  {nav_meta}")

    benchmark_html = build_benchmark_tab(results, catalog)

    if not REPORT_FILE.exists():
        print(f"ERROR: {REPORT_FILE} not found.")
        return

    html = REPORT_FILE.read_text(encoding="utf-8")
    patched = patch_report(html, benchmark_html, nav_meta)

    REPORT_FILE.write_text(patched, encoding="utf-8")
    print(f"\n  Updated: {REPORT_FILE}")
    print(f"  Size:    {REPORT_FILE.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
