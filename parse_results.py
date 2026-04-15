import json, re
from collections import defaultdict

data = []
with open("extract_run.log", encoding="utf-16") as f:
    for line in f:
        if "extraction_end" not in line or "status=completed" not in line:
            continue

        def g(pat, line=line):
            m = re.search(pat, line)
            return m.group(1) if m else ""

        data.append(
            {
                "parser": g(r"parser_name=(\w+)"),
                "pdf_id": g(r"pdf_id=([^ ]+)"),
                "ms": int(g(r"duration_ms=(\d+)") or 0),
                "pages": int(g(r"page_count_detected=(\d+)") or 1),
                "chars": int(g(r"text_length=(\d+)") or 0),
                "tables": int(g(r"table_count=(\d+)") or 0),
                "lib_ver": g(r"library_version=([^ ]+)"),
            }
        )

catalog = []
with open("data/catalog/pdf_catalog.jsonl", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            catalog.append(json.loads(line))

print("=== CATALOG ===")
for c in catalog:
    kb = c.get("file_size_bytes", 0) // 1024
    print(
        f"{c['pdf_id']} pages={c.get('page_count', '?')} {kb}KB title={c.get('title', '')[:60]}"
    )

print()
print("=== PER PDF x PARSER ===")
by_pdf = defaultdict(dict)
for r in data:
    by_pdf[r["pdf_id"]][r["parser"]] = r

for pdf_id, parsers in sorted(by_pdf.items()):
    pages = list(parsers.values())[0]["pages"]
    print(f"{pdf_id}: {len(parsers)} parsers ~{pages}p")
    for p, r in sorted(parsers.items()):
        print(
            f"  {p:<14} {r['ms']:>8}ms  {r['chars']:>8} chars  {r['tables']}t  v{r['lib_ver']}"
        )

print()
print("=== PARSER SUMMARY ===")
print("parser,n,avg_ms,avg_chars,total_tables,avg_pages,ms_per_page,lib_ver")
for parser in [
    "pymupdf",
    "pdfplumber",
    "pypdf",
    "pypdfium2",
    "pdftext",
    "unstructured",
    "camelot",
]:
    rows = [r for r in data if r["parser"] == parser]
    if not rows:
        print(f"{parser},0,0,0,0,0,0,?")
        continue
    n = len(rows)
    avg_ms = int(sum(r["ms"] for r in rows) / n)
    avg_chars = int(sum(r["chars"] for r in rows) / n)
    total_tables = sum(r["tables"] for r in rows)
    avg_pages = sum(r["pages"] for r in rows) / n
    # Use real page counts from catalog for ms/page
    mpp = int(avg_ms / avg_pages) if avg_pages else 0
    lib_ver = rows[0]["lib_ver"]
    print(
        f"{parser},{n},{avg_ms},{avg_chars},{total_tables},{avg_pages:.1f},{mpp},{lib_ver}"
    )
