"""Helper script: writes the final html_report.py content."""

import pathlib

CONTENT = '''"""
src/pdf_research_pipeline/benchmark/html_report.py

Generates a rich, tabbed HTML accuracy report comparing all PDF parsers.

Tabs:
  1. Overview         -- Winner + rankings + quick stats
  2. PDF Analysis     -- Structural metadata table + column details
  3. Accuracy Scores  -- Score matrix + AI reasoning per PDF
  4. Text Extractions -- Full text viewer with PDF + parser sub-tabs
  5. Recommendations  -- Library guide + general advice
"""

from __future__ import annotations

import html as html_lib
from collections import defaultdict
from pathlib import Path

from pdf_research_pipeline.benchmark.openai_agent import PDFAIEvaluation, ParserAIScore
from pdf_research_pipeline.benchmark.pdf_analyzer import PDFMetadata

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


def _color(parser: str) -> str:
    return _PARSER_COLORS.get(parser, "#78909C")


def generate_html_report(
    evaluations: list[PDFAIEvaluation],
    metadata_map: dict[str, PDFMetadata],
    output_path: str,
    all_extractions: dict[str, dict[str, str]] | None = None,
) -> None:
    """Generate and write the full tabbed HTML accuracy report."""
    html = _build_html(evaluations, metadata_map, all_extractions or {})
    Path(output_path).write_text(html, encoding="utf-8")


def _build_html(
    evaluations: list[PDFAIEvaluation],
    metadata_map: dict[str, PDFMetadata],
    all_extractions: dict[str, dict[str, str]],
) -> str:
    parser_totals: dict[str, list[int]] = defaultdict(list)
    type_best: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for ev in evaluations:
        for pname, ps in ev.parser_scores.items():
            parser_totals[pname].append(ps.total_score)
            type_best[ev.pdf_type][pname] += ps.total_score

    parser_avg: dict[str, float] = {
        p: sum(scores) / len(scores) for p, scores in parser_totals.items()
    }
    overall_winner = (
        max(parser_avg, key=lambda p: parser_avg[p]) if parser_avg else "N/A"
    )

    tab_overview = _tab_overview(overall_winner, parser_avg, evaluations)
    tab_analysis = _tab_analysis(metadata_map)
    tab_scores = _tab_scores(evaluations)
    tab_texts = _tab_texts(evaluations, all_extractions)
    tab_recommendations = _tab_recommendations(evaluations, type_best)

    nav = _nav_bar(overall_winner, len(evaluations), len(parser_avg))
    head = _html_head_inner()

    return (
        "<!DOCTYPE html>\\n<html lang=\\"en\\">\\n<head>\\n"
        + head
        + "\\n</head>\\n<body>\\n"
        + nav
        + \'\\n<div id="tab-overview" class="tab-panel">\' + tab_overview + "</div>\\n"
        + \'<div id="tab-analysis" class="tab-panel hidden">\' + tab_analysis + "</div>\\n"
        + \'<div id="tab-scores" class="tab-panel hidden">\' + tab_scores + "</div>\\n"
        + \'<div id="tab-texts" class="tab-panel hidden">\' + tab_texts + "</div>\\n"
        + \'<div id="tab-recommendations" class="tab-panel hidden">\' + tab_recommendations + "</div>\\n"
        + _footer_with_script()
        + "\\n</body>\\n</html>"
    )


# ---------------------------------------------------------------------------
# HTML head
# ---------------------------------------------------------------------------

CSS = """
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PDF Parser Accuracy Report</title>
<style>
:root{--primary:#1565C0;--bg:#F5F7FA;--card:#fff;--border:#E0E0E0;--text:#212121;--muted:#757575;--nav-h:56px}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:\'Segoe UI\',Arial,sans-serif;background:var(--bg);color:var(--text)}
h2{font-size:1.35rem;font-weight:600;color:var(--primary);margin-bottom:10px}
h3{font-size:1.05rem;font-weight:600;margin-bottom:6px}
.main-nav{position:sticky;top:0;z-index:200;background:#1A237E;display:flex;align-items:center;padding:0 20px;height:var(--nav-h);box-shadow:0 2px 8px rgba(0,0,0,.3)}
.nav-brand{color:#fff;font-weight:700;font-size:.95rem;margin-right:24px;white-space:nowrap}
.nav-tabs{display:flex;gap:2px;flex-wrap:wrap}
.nav-tab{background:transparent;border:none;cursor:pointer;color:rgba(255,255,255,.7);padding:7px 16px;border-radius:5px;font-size:.87rem;font-weight:500;transition:.15s}
.nav-tab:hover{background:rgba(255,255,255,.12);color:#fff}
.nav-tab.active{background:rgba(255,255,255,.22);color:#fff;font-weight:700}
.nav-meta{margin-left:auto;color:rgba(255,255,255,.6);font-size:.78rem;white-space:nowrap}
.tab-panel{min-height:calc(100vh - var(--nav-h))}
.tab-panel.hidden{display:none}
.section{padding:24px 36px}
.card{background:var(--card);border-radius:10px;padding:20px 22px;box-shadow:0 2px 8px rgba(0,0,0,.07);margin-bottom:18px}
.section-title{font-size:1.45rem;font-weight:700;color:var(--primary);margin-bottom:4px}
.section-sub{font-size:.87rem;color:var(--muted);margin-bottom:16px}
table{width:100%;border-collapse:collapse;font-size:.86rem}
thead{background:var(--primary);color:#fff}
th{padding:9px 13px;text-align:left}
td{padding:8px 13px;border-bottom:1px solid var(--border);vertical-align:middle}
tr:hover td{background:#F0F4FF}
.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:.75rem;font-weight:600}
.pill-best{background:#43A047;color:#fff}
.pill-good{background:#64B5F6;color:#fff}
.pill-acceptable{background:#FFB74D;color:#333}
.pill-poor{background:#E57373;color:#fff}
.best-chip{background:linear-gradient(90deg,#43A047,#2E7D32);color:#fff;border-radius:5px;padding:2px 9px;font-size:.78rem;font-weight:700}
.winner-badge{background:#43A047;color:#fff;padding:2px 9px;border-radius:5px;font-size:.78rem;font-weight:700}
.hero{background:linear-gradient(135deg,#1565C0 0%,#0D47A1 100%);color:#fff;padding:36px 44px}
.hero h1{font-size:1.9rem;font-weight:700}
.hero p{opacity:.85;margin-top:5px}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:14px;margin-top:20px}
.stat-box{background:#fff;border-radius:7px;padding:14px 18px;border-left:4px solid var(--primary)}
.stat-num{font-size:1.5rem;font-weight:700;color:var(--primary)}
.stat-label{font-size:.76rem;color:var(--muted);margin-top:2px}
.ranking-row{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.rank-num{font-size:1.2rem;font-weight:800;width:30px;text-align:center}
.bar-wrap{height:20px;background:#E0E0E0;border-radius:8px;overflow:hidden;flex:1}
.bar-fill{height:100%;border-radius:8px;display:flex;align-items:center;padding-left:8px;color:#fff;font-size:.78rem;font-weight:600}
.rank-score{min-width:65px;font-weight:700;text-align:right}
.score-matrix td:nth-child(n+2){text-align:center}
.score-matrix th:nth-child(n+2){text-align:center}
.dim-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:7px;margin-top:9px}
.dim-box{background:#F8F9FA;padding:8px 11px;border-radius:5px}
.dim-name{font-size:.71rem;color:var(--muted);text-transform:capitalize}
.dim-val{font-size:1rem;font-weight:700;margin-top:1px}
.observations{font-size:.86rem;line-height:1.7;color:#424242;padding:11px 14px;background:#F3F4F6;border-radius:7px;margin-top:7px}
.pdf-selector-bar{display:flex;gap:6px;flex-wrap:wrap;padding:14px 20px;background:#fff;border-bottom:1px solid var(--border)}
.pdf-sel-btn{background:#ECEFF1;border:1px solid #B0BEC5;border-radius:5px;cursor:pointer;padding:6px 15px;font-size:.83rem;font-weight:500;color:#37474F;transition:.15s}
.pdf-sel-btn:hover{background:#CFD8DC}
.pdf-sel-btn.active{background:var(--primary);color:#fff;border-color:var(--primary);font-weight:700}
.pdf-pane{display:none}
.pdf-pane.active{display:block}
.parser-tabs-bar{display:flex;gap:4px;flex-wrap:wrap;padding:10px 20px;background:#F5F5F5;border-bottom:1px solid var(--border)}
.parser-tab-btn{background:#fff;border:1px solid #CFD8DC;border-radius:5px;cursor:pointer;padding:5px 13px;font-size:.81rem;font-weight:500;color:#455A64;transition:.15s}
.parser-tab-btn:hover{background:#E3F2FD}
.parser-tab-btn.active{border-width:2px;font-weight:700}
.parser-pane{display:none;padding:14px 20px}
.parser-pane.active{display:block}
.text-stats-bar{display:flex;align-items:center;gap:14px;margin-bottom:10px;flex-wrap:wrap}
.text-stat{font-size:.81rem;color:var(--muted)}
.text-stat b{color:var(--text)}
.copy-btn{margin-left:auto;background:#E3F2FD;border:1px solid #90CAF9;border-radius:4px;font-size:.78rem;padding:4px 13px;cursor:pointer;color:#1565C0;font-weight:600}
.copy-btn:hover{background:#BBDEFB}
.text-viewer{background:#1E1E1E;color:#D4D4D4;padding:14px 16px;border-radius:7px;font-family:\'Consolas\',\'Courier New\',monospace;font-size:.8rem;line-height:1.65;overflow-x:auto;white-space:pre-wrap;max-height:540px;overflow-y:auto;border:1px solid #333}
.no-text-msg{color:var(--muted);font-style:italic;padding:20px;text-align:center}
.rec-card{border-left:5px solid var(--primary);background:#fff;border-radius:0 7px 7px 0;padding:14px 18px;margin-bottom:12px}
.note{font-size:.8rem;color:var(--muted);font-style:italic}
</style>
"""


def _html_head_inner() -> str:
    return CSS


# ---------------------------------------------------------------------------
# Nav bar
# ---------------------------------------------------------------------------

def _nav_bar(winner: str, pdf_count: int, parser_count: int) -> str:
    return (
        \'<nav class="main-nav">\'
        + \'<span class="nav-brand">PDF Parser Report</span>\'
        + \'<div class="nav-tabs">\'
        + \'<button class="nav-tab active" data-tab="overview">Overview</button>\'
        + \'<button class="nav-tab" data-tab="analysis">PDF Analysis</button>\'
        + \'<button class="nav-tab" data-tab="scores">Accuracy Scores</button>\'
        + \'<button class="nav-tab" data-tab="texts">Text Extractions</button>\'
        + \'<button class="nav-tab" data-tab="recommendations">Recommendations</button>\'
        + "</div>"
        + f\'<span class="nav-meta">{parser_count} parsers \xb7 {pdf_count} PDFs \xb7 Winner: {winner}</span>\'
        + "</nav>"
    )


# ---------------------------------------------------------------------------
# Tab 1 -- Overview
# ---------------------------------------------------------------------------

def _tab_overview(
    winner: str,
    parser_avg: dict[str, float],
    evaluations: list[PDFAIEvaluation],
) -> str:
    total_tokens = sum(ev.tokens_used for ev in evaluations)
    pdf_types = sorted({ev.pdf_type for ev in evaluations})
    winner_score = parser_avg.get(winner, 0)
    medals = ["\\U0001f947", "\\U0001f948", "\\U0001f949"]
    rows_html = ""
    for rank, (p, avg) in enumerate(sorted(parser_avg.items(), key=lambda x: -x[1])):
        medal = medals[rank] if rank < 3 else f"#{rank+1}"
        c = _color(p)
        rows_html += (
            f\'<div class="ranking-row">\'
            f\'<span class="rank-num">{medal}</span>\'
            f\'<b style="min-width:105px;color:{c}">{p}</b>\'
            f\'<div class="bar-wrap"><div class="bar-fill" style="width:{int(avg)}%;background:{c}">{avg:.1f}</div></div>\'
            f\'<span class="rank-score" style="color:{_score_color(int(avg))}">{avg:.1f}/100</span>\'
            f"</div>"
        )
    stats = (
        \'<div class="stats-grid">\'
        + f\'<div class="stat-box"><div class="stat-num">{len(evaluations)}</div><div class="stat-label">PDFs Evaluated</div></div>\'
        + f\'<div class="stat-box"><div class="stat-num">{len(parser_avg)}</div><div class="stat-label">Parsers Compared</div></div>\'
        + f\'<div class="stat-box"><div class="stat-num">{winner}</div><div class="stat-label">Overall Winner</div></div>\'
        + f\'<div class="stat-box"><div class="stat-num">{winner_score:.0f}</div><div class="stat-label">Winner Avg Score</div></div>\'
        + f\'<div class="stat-box"><div class="stat-num">{total_tokens:,}</div><div class="stat-label">GPT-4o Tokens</div></div>\'
        + "</div>"
    )
    return (
        f\'<div class="hero"><h1>PDF Parser Accuracy Report</h1>\'
        f\'<p>AI-powered comparison \xb7 Scored by GPT-4o</p>\'
        f\'<p style="margin-top:14px;font-size:1.15rem;font-weight:700">\\U0001f3c6 Overall Winner: <span style="color:#FFD740">{winner}</span> ({winner_score:.1f}/100)</p>\'
        f"</div>"
        f\'<div class="section">{stats}<br>\'
        f\'<div class="card"><h2>Parser Rankings</h2><p class="note" style="margin-bottom:14px">Average GPT-4o score across {len(evaluations)} PDFs</p>{rows_html}</div>\'
        f\'<div class="card" style="background:#E8F5E9;border:1px solid #C8E6C9"><h3>PDF Types Evaluated</h3>\'
        f\'<p style="margin-top:7px;font-size:.88rem;color:#2E7D32">{\', \'.join(pdf_types)}</p></div></div>\'
    )


# ---------------------------------------------------------------------------
# Tab 2 -- PDF Analysis
# ---------------------------------------------------------------------------

def _tab_analysis(metadata_map: dict[str, PDFMetadata]) -> str:
    rows = ""
    for pdf_id, meta in metadata_map.items():
        short_id = (pdf_id[:22] + "\\u2026") if len(pdf_id) > 23 else pdf_id
        mc = "\\u2713" if meta.multi_column else "\\u2013"
        eq = "\\u2713" if meta.has_equations else "\\u2013"
        rows += (
            f"<tr><td title=\'{pdf_id}\'>{short_id}</td>"
            f"<td>{meta.page_count}</td><td>{meta.word_count:,}</td>"
            f"<td>{meta.paragraph_count:,}</td><td>{meta.image_count}</td>"
            f"<td>{meta.figure_count}</td><td>{meta.table_count}</td>"
            f"<td>{meta.font_count}</td><td>{mc}</td><td>{eq}</td>"
            f"<td>{meta.file_size_kb:.0f} KB</td></tr>"
        )
    return (
        \'<div class="section">\'
        + \'<div class="section-title">PDF Structural Analysis</div>\'
        + \'<div class="section-sub">Metadata extracted by PyMuPDF from each evaluated PDF.</div>\'
        + \'<div class="card" style="overflow-x:auto"><table><thead><tr>\'
        + "<th>PDF ID</th><th>Pages</th><th>Words</th><th>Paragraphs</th>"
        + "<th>Images</th><th>Figures</th><th>Tables</th><th>Fonts</th>"
        + "<th>Multi-Col</th><th>Equations</th><th>Size</th>"
        + f"</tr></thead><tbody>{rows}</tbody></table></div></div>"
    )


# ---------------------------------------------------------------------------
# Tab 3 -- Accuracy Scores
# ---------------------------------------------------------------------------

def _tab_scores(evaluations: list[PDFAIEvaluation]) -> str:
    all_parsers = sorted({p for ev in evaluations for p in ev.parser_scores})
    header_cells = "".join(
        f"<th style=\'color:#FFD740\'>{p}</th>" for p in all_parsers
    ) + "<th>Best</th>"

    body_rows = ""
    for ev in evaluations:
        short_id = (ev.pdf_id[:18] + "\\u2026") if len(ev.pdf_id) > 19 else ev.pdf_id
        cells = ""
        for p in all_parsers:
            if p in ev.parser_scores:
                s = ev.parser_scores[p].total_score
                tier = ev.parser_scores[p].recommendation_tier
                bg = "#E8F5E9" if p == ev.best_parser else ""
                cells += f"<td style=\'background:{bg}\'><span class=\'pill pill-{tier}\'>{s}</span></td>"
            else:
                cells += "<td><span style=\'color:#ccc\'>\\u2013</span></td>"
        cells += f"<td><span class=\'best-chip\'>{ev.best_parser}</span></td>"
        body_rows += f"<tr><td title=\'{ev.pdf_id}\'><b>{short_id}</b></td>{cells}</tr>"

    matrix = (
        \'<div class="card" style="overflow-x:auto"><table class="score-matrix">\'
        + f"<thead><tr><th>PDF</th>{header_cells}</tr></thead>"
        + f"<tbody>{body_rows}</tbody></table></div>"
    )
    deep = _deep_analysis_cards(evaluations)
    return (
        \'<div class="section">\'
        + \'<div class="section-title">Accuracy Scores (GPT-4o)</div>\'
        + \'<div class="section-sub">Scores 0\\u2013100. Green = best parser for that PDF.</div>\'
        + matrix
        + "<h2 style=\'margin-top:6px\'>Per-PDF Deep Analysis</h2>"
        + deep
        + "</div>"
    )


def _deep_analysis_cards(evaluations: list[PDFAIEvaluation]) -> str:
    out = []
    for ev in evaluations:
        short_id = (ev.pdf_id[:24] + "\\u2026") if len(ev.pdf_id) > 25 else ev.pdf_id
        obs = ""
        if ev.observations:
            obs = f\'<div class="observations">\\U0001f4a1 <b>AI Observations:</b> {html_lib.escape(ev.observations)}</div>\'
        parser_blocks = ""
        for pname, ps in sorted(ev.parser_scores.items(), key=lambda x: -x[1].total_score):
            c = _color(pname)
            bm = " \\U0001f3c6" if pname == ev.best_parser else ""
            dims = "".join(
                f\'<div class="dim-box"><div class="dim-name">{k.replace("_"," ")}</div>\'
                f\'<div class="dim-val" style="color:{_score_color(v)}">{v}</div></div>\'
                for k, v in ps.dimensions.items()
            )
            parser_blocks += (
                f\'<div style="border-left:4px solid {c};padding:11px 15px;margin-bottom:10px;background:#FAFAFA;border-radius:0 7px 7px 0">\'
                f\'<div style="display:flex;align-items:center;gap:9px;margin-bottom:5px">\'
                f\'<b style="color:{c}">{pname.upper()}{bm}</b>\'
                f\'<span class="pill pill-{ps.recommendation_tier}">{ps.recommendation_tier}</span>\'
                f\'<span style="font-size:1.25rem;font-weight:800;color:{_score_color(ps.total_score)}">{ps.total_score}/100</span>\'
                f\'</div><div class="dim-grid">{dims}</div>\'
                f\'<p style="margin-top:7px;font-size:.84rem"><b>Strengths:</b> {html_lib.escape(ps.strengths)}</p>\'
                f\'<p style="margin-top:3px;font-size:.84rem"><b>Weaknesses:</b> {html_lib.escape(ps.weaknesses)}</p>\'
                f"</div>"
            )
        rec = ""
        if ev.recommendation:
            rec = f\'<div class="rec-card" style="margin-top:7px"><b>Recommendation:</b> {html_lib.escape(ev.recommendation)}</div>\'
        out.append(
            f\'<div class="card">\'
            f\'<h3><span title="{ev.pdf_id}">{short_id}</span>\'
            f\' <span style="font-size:.81rem;color:#888">({ev.pdf_type} \xb7 {ev.complexity})</span>\'
            f\' <span class="winner-badge">Best: {ev.best_parser}</span></h3>\'
            f\'<div style="margin-top:10px">{obs}</div>\'
            f\'<div style="margin-top:10px">{parser_blocks}</div>\'
            f"{rec}</div>"
        )
    return "\\n".join(out)


# ---------------------------------------------------------------------------
# Tab 4 -- Text Extractions
# ---------------------------------------------------------------------------

def _tab_texts(
    evaluations: list[PDFAIEvaluation],
    all_extractions: dict[str, dict[str, str]],
) -> str:
    if not all_extractions:
        return (
            \'<div class="section"><div class="section-title">Text Extractions</div>\'
            + \'<div class="card"><p class="no-text-msg">No extraction texts available. Re-run score-ai to populate.</p></div></div>\'
        )

    score_lookup: dict[str, dict[str, int]] = {}
    best_lookup: dict[str, str] = {}
    for ev in evaluations:
        score_lookup[ev.pdf_id] = {p: ps.total_score for p, ps in ev.parser_scores.items()}
        best_lookup[ev.pdf_id] = ev.best_parser

    pdf_ids = list(all_extractions.keys())

    # PDF selector buttons
    pdf_btns = ""
    for idx, pdf_id in enumerate(pdf_ids):
        short = _short_pdf_name(pdf_id)
        active = " active" if idx == 0 else ""
        pdf_btns += (
            f\'<button class="pdf-sel-btn{active}" data-pdfidx="{idx}" \'
            f\'onclick="selectPdf({idx})">{short}</button>\\n\'
        )

    # PDF panes
    pdf_panes = ""
    for idx, pdf_id in enumerate(pdf_ids):
        parsers = list(all_extractions[pdf_id].keys())
        scores = score_lookup.get(pdf_id, {})
        best = best_lookup.get(pdf_id, "")
        active_pane = " active" if idx == 0 else ""

        parser_btns = ""
        for pidx, pname in enumerate(parsers):
            sc = scores.get(pname)
            sc_txt = f" ({sc}/100)" if sc is not None else ""
            bm = " \\U0001f3c6" if pname == best else ""
            c = _color(pname)
            ap = " active" if pidx == 0 else ""
            parser_btns += (
                f\'<button class="parser-tab-btn{ap}" style="border-color:{c}" \'
                f\'data-pdfidx="{idx}" data-pidx="{pidx}" \'
                f\'onclick="selectParser({idx},{pidx})">{pname}{bm}{sc_txt}</button>\\n\'
            )

        parser_panes = ""
        for pidx, pname in enumerate(parsers):
            text = all_extractions[pdf_id].get(pname, "")
            sc = scores.get(pname)
            chars = len(text)
            words = len(text.split()) if text else 0
            sc_badge = ""
            if sc is not None:
                bm_txt = " (best!)" if pname == best else ""
                sc_badge = f\'<span class="pill {_score_tier_class(sc)}">Score: {sc}/100{bm_txt}</span>\'
            ap = " active" if pidx == 0 else ""
            pane_id = f"pp-{idx}-{pidx}"
            text_id = f"ptxt-{idx}-{pidx}"
            copy_btn = (
                f\'<button class="copy-btn" onclick="copyText(\\\'{text_id}\\\')">Copy</button>\'
                if text else ""
            )
            content = (
                f\'<pre id="{text_id}" class="text-viewer">{html_lib.escape(text)}</pre>\'
                if text
                else \'<p class="no-text-msg">No text available for this parser.</p>\'
            )
            parser_panes += (
                f\'<div id="{pane_id}" class="parser-pane{ap}">\'
                f\'<div class="text-stats-bar">\'
                f\'<span class="text-stat"><b>{chars:,}</b> chars</span>\'
                f\'<span class="text-stat"><b>{words:,}</b> words</span>\'
                f"{sc_badge}{copy_btn}</div>{content}</div>"
            )

        pdf_panes += (
            f\'<div id="pdf-pane-{idx}" class="pdf-pane{active_pane}">\'
            f\'<div class="parser-tabs-bar">{parser_btns}</div>\'
            f"{parser_panes}</div>"
        )

    return (
        \'<div style="background:#fff;border-bottom:1px solid var(--border);padding:14px 22px 0">\'
        + \'<div class="section-title" style="margin-bottom:3px">Text Extractions</div>\'
        + \'<div class="section-sub" style="margin-bottom:10px">Select a PDF then a parser tab to view full extracted text.</div>\'
        + f\'<div class="pdf-selector-bar" style="padding:0 0 10px">{pdf_btns}</div></div>\'
        + pdf_panes
    )


# ---------------------------------------------------------------------------
# Tab 5 -- Recommendations
# ---------------------------------------------------------------------------

def _tab_recommendations(
    evaluations: list[PDFAIEvaluation],
    type_best: dict[str, dict[str, int]],
) -> str:
    type_winner: dict[str, str] = {}
    for pdf_type, parser_scores in type_best.items():
        if parser_scores:
            type_winner[pdf_type] = max(parser_scores, key=lambda p: parser_scores[p])

    type_cards = ""
    for pdf_type, winner_p in type_winner.items():
        c = _color(winner_p)
        rec_text = next(
            (ev.pdf_type_recommendation for ev in evaluations
             if ev.pdf_type == pdf_type and ev.pdf_type_recommendation),
            "See per-PDF analysis for detailed reasoning.",
        )
        type_cards += (
            f\'<div style="border:1px solid {c};border-radius:7px;padding:14px;margin-bottom:12px">\'
            f\'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">\'
            f\'<span style="font-weight:700">{pdf_type}</span>\'
            f\'<span class="pill" style="background:{c};color:#fff">Best: {winner_p}</span></div>\'
            f\'<p style="font-size:.86rem;color:#444;line-height:1.65">{html_lib.escape(rec_text)}</p></div>\'
        )

    return (
        \'<div class="section">\'
        + \'<div class="section-title">Recommendations</div>\'
        + \'<div class="section-sub">Best parser by PDF type + general guidance.</div>\'
        + f\'<div class="card"><h2>Best Parser by PDF Type</h2><div style="margin-top:10px">{type_cards}</div></div>\'
        + \'<div class="card" style="background:#E8F5E9;border:1px solid #A5D6A7"><h2 style="color:#2E7D32">General Guidance</h2>\'
        + \'<ul style="margin-top:10px;padding-left:18px;font-size:.88rem;line-height:2">\'
        + "<li><b>pdftext / PyMuPDF</b> \\u2014 Best for digitally-created PDFs. Fast, accurate, preserves reading order.</li>"
        + "<li><b>pdfplumber</b> \\u2014 Best for table extraction. Use alongside PyMuPDF for table-heavy PDFs.</li>"
        + "<li><b>pypdf</b> \\u2014 Lightweight baseline. Good for simple PDFs.</li>"
        + "<li><b>EasyOCR</b> \\u2014 For image-only/scanned PDFs. Very slow on CPU.</li>"
        + "<li><b>Tesseract</b> \\u2014 Industry-standard OCR. Requires binary install for best quality.</li>"
        + "<li><b>For RAG pipelines</b> \\u2014 prefer pdftext or PyMuPDF; add pdfplumber for tables.</li>"
        + "</ul></div></div>"
    )


# ---------------------------------------------------------------------------
# Footer + JavaScript
# ---------------------------------------------------------------------------

SCRIPT = """
<div style="text-align:center;color:#9E9E9E;font-size:.78rem;padding:18px;background:#FAFAFA;border-top:1px solid #E0E0E0">
  Generated by PDF Research Pipeline &nbsp;&middot;&nbsp; AI scoring via GPT-4o
</div>
<script>
document.querySelectorAll('.nav-tab').forEach(function(btn){
  btn.addEventListener('click',function(){
    document.querySelectorAll('.nav-tab').forEach(function(t){t.classList.remove('active');});
    document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.add('hidden');});
    this.classList.add('active');
    var panel=document.getElementById('tab-'+this.dataset.tab);
    if(panel) panel.classList.remove('hidden');
  });
});
function selectPdf(idx){
  document.querySelectorAll('.pdf-sel-btn').forEach(function(b){b.classList.remove('active');});
  document.querySelectorAll('.pdf-pane').forEach(function(p){p.classList.remove('active');});
  var btn=document.querySelector('.pdf-sel-btn[data-pdfidx="'+idx+'"]');
  var pane=document.getElementById('pdf-pane-'+idx);
  if(btn) btn.classList.add('active');
  if(pane) pane.classList.add('active');
}
function selectParser(pdfIdx,pIdx){
  document.querySelectorAll('.parser-tab-btn[data-pdfidx="'+pdfIdx+'"]').forEach(function(b){b.classList.remove('active');});
  var prefix='pp-'+pdfIdx+'-';
  document.querySelectorAll('.parser-pane').forEach(function(p){if(p.id&&p.id.indexOf(prefix)===0)p.classList.remove('active');});
  var btn=document.querySelector('.parser-tab-btn[data-pdfidx="'+pdfIdx+'"][data-pidx="'+pIdx+'"]');
  var pane=document.getElementById('pp-'+pdfIdx+'-'+pIdx);
  if(btn) btn.classList.add('active');
  if(pane) pane.classList.add('active');
}
function copyText(elemId){
  var el=document.getElementById(elemId);
  if(!el) return;
  var text=el.innerText||el.textContent;
  var btn=event.currentTarget;
  var orig=btn.textContent;
  if(navigator.clipboard){
    navigator.clipboard.writeText(text).then(function(){btn.textContent='Copied!';setTimeout(function(){btn.textContent=orig;},1500);});
  } else {
    var ta=document.createElement('textarea');ta.value=text;document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);
    btn.textContent='Copied!';setTimeout(function(){btn.textContent=orig;},1500);
  }
}
</script>
"""


def _footer_with_script() -> str:
    return SCRIPT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_color(score: int) -> str:
    if score >= 80: return "#2E7D32"
    if score >= 60: return "#1565C0"
    if score >= 40: return "#E65100"
    return "#C62828"


def _score_tier_class(score: int) -> str:
    if score >= 80: return "pill-best"
    if score >= 60: return "pill-good"
    if score >= 40: return "pill-acceptable"
    return "pill-poor"


def _short_pdf_name(pdf_id: str) -> str:
    name = pdf_id.split("/")[-1].split("\\\\")[-1]
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    if len(name) > 22:
        name = name[:20] + "\\u2026"
    return name
'''

dest = pathlib.Path("src/pdf_research_pipeline/benchmark/html_report.py")
dest.write_text(CONTENT, encoding="utf-8")
print(
    f"Written {dest} — {dest.stat().st_size} bytes, {len(CONTENT.splitlines())} lines"
)
