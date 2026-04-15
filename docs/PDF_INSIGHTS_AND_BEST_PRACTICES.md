# PDF Extraction — Insights and Best Practices

Advanced observations from building and running a multi-parser PDF research pipeline. This document collects hard-won lessons about what makes PDF extraction difficult, what the benchmarks reveal, and how to make practical decisions.

---

## 1. The Fundamental Challenges

### 1.1 PDF Is a Presentation Format, Not a Data Format

PDF was invented to make documents look identical on any printer. It was deliberately **not** designed as a structured data format. What this means in practice:

- Characters are positioned on a page by absolute coordinates (x, y) — there is no concept of "word", "line", or "paragraph" in the specification
- Reading order is visual, not structural: the PDF stream may store text columns in any order
- Tables are drawn as lines and characters; the spec has no table element
- Mathematical equations may be encoded as images, MathML, or a mix of both
- The same visual document can be produced by wildly different byte sequences

**Implication**: Every PDF parser is an approximation. There is no "correct" extraction — only more or less useful approximations.

### 1.2 PDF Type Is the Most Important Routing Signal

Running the wrong parser on a PDF type wastes time and produces bad results:

| Mistake | Consequence |
|---|---|
| Text-only parser on scanned PDF | Returns empty string (0 characters) |
| OCR on born-digital PDF | Re-converts perfect text → image → imperfect text; loses formatting |
| Simple parser on complex layout | Reading order garbled; columns interleaved |
| Camelot on a scanned PDF image | Finds no tables (it works on text, not pixels) |

**Best practice**: Classify every PDF before sending it to a parser. `pdf_type` in the catalog is the single most important metadata field in this pipeline.

### 1.3 The Performance Variability Is Enormous

From actual pipeline benchmarks on a 17-page arXiv paper:

| Parser | Duration | Characters |
|---|---|---|
| pypdfium2 | **88ms** | 55,036 |
| pymupdf | 384ms | 54,353 |
| pypdf | 860ms | 54,232 |
| pdftext | 1.3s | 52,232 |
| ocrmypdf | 49.9s | 34,144 |
| tesseract | 74.3s | 34,093 |
| pdfplumber | 48.1s | 49,125 |
| unstructured | 61.4s | 55,113 |
| camelot | 121.7s | 160 chars from 1 table |
| easyocr | 379s (10pp) | 33,934 |

The fastest non-OCR parser (pypdfium2) is **4,000× faster** than EasyOCR on this document. Choosing the right tool at scale is the difference between a pipeline that runs in minutes and one that runs overnight.

### 1.4 Character Count ≠ Quality

Notice that Tesseract and EasyOCR return ~34,000 characters versus 55,000 for the text-layer parsers — on the same born-digital PDF. This is not because OCR is worse; it is because:

1. This PDF has a text layer — OCR parsers are rendering the visual appearance, not reading the stored text
2. The visual appearance includes page decorations, footnotes, and header/footer strings that the OCR misses when cut off at `max_pages=10`
3. Some characters that exist in Unicode do not survive the render-to-image-to-OCR round trip

**Best practice**: Use character count as a screening metric (near-zero → extraction failure), not as a quality signal.

---

## 2. Parser Selection Framework

### 2.1 Decision Tree for Choosing a Primary Parser

```
Is the PDF born-digital (has a text layer)?
├── Yes → Is reading order critical?
│           ├── Yes → Is it a multi-column academic paper?
│           │           ├── Yes → Unstructured (hi_res) or Marker
│           │           └── No  → pdfplumber or pdftext
│           └── No  → pypdfium2 (fastest) or PyMuPDF (most versatile)
└── No  → Is it a high-quality clean scan (300+ dpi)?
            ├── Yes → Tesseract (fast, production-grade)
            └── No  → OCRmyPDF (adds deskew/denoise) or EasyOCR (multilingual)
```

### 2.2 Table Extraction Decision

```
Does the document contain tables?
├── Yes → Are tables bordered with visible lines?
│           ├── Yes → Camelot (lattice mode) — most reliable
│           └── No  → pdfplumber or Camelot (stream mode) — heuristic
└── No  → Skip table extractors (they add latency with no gain)
```

### 2.3 The "Good Enough Baseline" Stack

For most production use cases, this combination covers 90% of document types:

1. **pymupdf + pdfplumber** for born-digital PDFs (PyMuPDF for speed, pdfplumber for tables)
2. **tesseract** (via OCRmyPDF wrapper) for scanned PDFs
3. **unstructured** for any PDF where reading order matters for RAG

---

## 3. Observations From This Pipeline's Benchmarks

### 3.1 Text Parsers Capture Different Character Counts on the Same Born-Digital PDF

From the actual benchmark on arXiv paper `2501.05032v2` (17 pages):
- pypdfium2: 55,036 characters
- pymupdf: 54,353 characters
- pypdf: 54,232 characters
- pdfplumber: 49,125 characters

A ~10% spread across text parsers on the same document is normal. This can come from:
- Different treatments of ligatures (ﬁ vs "fi")
- Hyphenation handling (soft hyphens vs hard hyphens)
- Footer/header inclusion or exclusion
- Different whitespace normalisation

**Implication**: `text_completeness` scoring should tolerate ±10% character count variation and focus on key-phrase presence rather than raw counts.

### 3.2 pdfplumber Is Both Accurate and Unscalable

pdfplumber's word positions are the most reliable of any Python-native parser for data journalism use cases. But its pure-Python parsing is ~120× slower than pypdfium2 on the same document. This is a fundamental architecture constraint — pdfminer.six processes characters one by one in Python.

**Recommendation**: Use pdfplumber for high-value documents where accuracy matters, or for offline batch processing where throughput is acceptable. For real-time or high-volume pipelines, use PyMuPDF or pypdfium2 for text and run pdfplumber only when tables are detected.

### 3.3 OCR Is Not Appropriate for Born-Digital PDFs

OCR parsers on born-digital PDFs:
- Spend time rendering pages to images (PyMuPDF rendering: 30ms/page)
- OCR what was rendered (Tesseract: ~7s/page)
- Return fewer characters than the text layer (because headers, footers, and footnotes at page edges may be cut off)
- May introduce recognition errors where none existed in the text layer

**The only valid reason to run OCR on a born-digital PDF**: the text layer is corrupted, encrypted, or absent despite being visually born-digital. This happens with some malformed PDFs from legacy software.

### 3.4 Camelot's Latency Is Dominated by Ghostscript

Camelot's 122s for a 17-page PDF was almost entirely Ghostscript rendering time (lattice mode renders every page to an image to detect lines). The actual table content extracted was 160 characters from 1 table.

**Recommendation**: Run Camelot only on PDFs that are likely to have tables. Use a fast pre-check:
```python
# Quick check: look for obvious table indicators in PyMuPDF block geometry
blocks = page.get_text("blocks")
has_grid_like_layout = any(b[4].count('\n') > 3 for b in blocks if b[6] == 0)
```

---

## 4. Quality Scoring Insights

### 4.1 Weight Profiles Must Match PDF Type

Applying uniform 12-dimension weights across PDF types misleads the ranking:

- An OCR parser on a **scanned PDF** that produces 80% text completeness is excellent — but with default weights, it scores lower than a text parser that gets 95% completeness on a born-digital PDF
- The `ocr_quality` dimension is essentially meaningless for born-digital PDFs (they have perfect OCR quality by definition: the text was never an image)

The pipeline adjusts weights per PDF type in `configs/scoring.yaml`:
- `image_only_scanned_pdf`: boost `ocr_quality` from 0.08 → 0.35
- `complex_layout_pdf`: boost `coordinate_richness` from 0.07 → 0.10, `structural_fidelity` from 0.08 → 0.12

**Recommendation**: Always segment benchmark results by PDF type when comparing parsers.

### 4.2 `rag_suitability` (0.03 weight) Is Worth More Attention

The default weight of 3% for `rag_suitability` is too low for RAG-focused pipelines. For a document that will be chunked and embedded for retrieval:
- A parser that correctly preserves section headings (Marker, Unstructured) enables better semantic chunking
- A parser that merges adjacent columns (many text parsers) creates chunks that span unrelated topics
- A parser that preserves table structure (Camelot, pdfplumber) makes tabular data retrievable

If your downstream use is retrieval-augmented generation, consider boosting `rag_suitability` and `markdown_readability` dimensions significantly.

### 4.3 Speed Matters More at Scale

In the benchmark, `speed` has a 5% weight. For a document research tool processing 47 PDFs × 13 parsers = ~600 extraction calls, using unstructured (hi_res) for every PDF adds ~10 hours versus using PyMuPDF (~3 minutes total).

**Recommendation**: Use speed as a hard constraint filter, not just a scoring dimension. Define a maximum acceptable latency per PDF type and eliminate parsers that exceed it.

---

## 5. Building Production PDF Pipelines

### 5.1 Always Classify First

Never send an unknown PDF to any parser without classifying it. A minimal classifier:
1. Check if the PDF has a text layer (`pymupdf text extraction → character count > threshold`)
2. If no text: route to OCR stack
3. If text exists: check for multi-column layout (block width distribution heuristic)
4. Check for embedded tables (grid line detection or block adjacency)
5. Check for form fields (AcroForm presence)

### 5.2 Use a Two-Parser Strategy

For each PDF type, use exactly two parsers: a **fast baseline** and a **quality parser**:

| PDF Type | Fast Baseline | Quality Parser |
|---|---|---|
| True Digital | pypdfium2 | pdfplumber (tables) |
| Image-Only Scanned | tesseract | ocrmypdf (hard cases) |
| Complex Layout | pymupdf | unstructured (reading order) |
| Forms | pdfplumber | unstructured (field values) |
| Specialized | pymupdf | marker / nougat (equations) |

Run the fast baseline first. If quality metrics pass a threshold, accept the result. If they fail, promote to the quality parser. This keeps average throughput high while catching difficult documents.

### 5.3 Enforce Page-Level Timeouts for OCR

From this pipeline's implementation: any OCR call that exceeds `timeout_seconds` per page is cancelled. Without this, a single 500-page PDF sent to EasyOCR can block a worker for 12+ hours.

Practical limits from benchmarks:
- Tesseract: ~7s/page → 70s for max_pages=10 is acceptable
- EasyOCR: ~38s/page → 380s for max_pages=10 is barely acceptable
- OCRmyPDF: ~5s/page → 50s for max_pages=10 is acceptable

### 5.4 Set max_pages Globally for OCR Parsers

OCR parsers should **always** have a page cap in batch processing. A 300-page physical book sent to EasyOCR with no cap will run for ~3 hours per document.

This pipeline enforces `max_pages` at the parser level. A typical production default:
- Interactive/API use: `max_pages=5`
- Batch research: `max_pages=10`
- Full document archive: `max_pages=None` (only with dedicated OCR workers)

### 5.5 Handle `EMPTY_TEXT` as a Type-Mismatch Signal

When a parser returns 0 characters, the default assumption should not be "parser is broken" but rather "wrong parser for this PDF type". The verification stage should:
1. Log the `EMPTY_TEXT` event with the parser name and PDF type
2. Check if the PDF is scanned (attempt OCR on a sample page)
3. If scanned: route to OCR parser and retry
4. If born-digital: flag as parser bug or malformed PDF

In this pipeline, ~100% of `EMPTY_TEXT` events are expected: text-layer parsers on scanned PDFs. Zero are unexpected parser failures on born-digital content.

### 5.6 Provenance and Idempotency Are Non-Negotiable

For a research pipeline that may re-run on the same PDFs many times:
1. **SHA256 every input and output**: catch silent corruption and identify re-runs
2. **Skip if output exists**: don't re-process files that already have results
3. **Log extraction decisions**: when you revisit results 6 months later, you need to know which parser version, which config, and which run ID produced each result

The `provenance.log.jsonl` and `run_manifest.json` artifacts in this pipeline implement all three.

### 5.7 Benchmark Regularly After Library Updates

PDF library releases frequently change extraction behaviour. Examples from real library changelogs:
- PyMuPDF 1.23 changed ligature handling; text character counts changed for many documents
- pdfminer (underlying pdfplumber) 20221105 changed reading-order reconstruction
- Tesseract 5.0 LSTM engine changed accuracy on certain fonts vs. legacy engine

**Recommendation**: Re-run your benchmark suite after any dependency update that touches extraction libraries. Pin to specific versions for production.

---

## 6. Common Anti-Patterns

### Anti-pattern 1: Using one parser for all PDFs
*Symptom*: "We use PyMuPDF for everything."
*Problem*: Works fine for born-digital; returns empty for scanned; misses form fields; reading order wrong for multi-column.
*Fix*: Classify, then route.

### Anti-pattern 2: Equating character count with extraction quality
*Symptom*: Selecting the parser that returns the most characters.
*Problem*: OCR can hallucinate characters; duplicate text increases count artificially; headers/footers add characters that aren't content.
*Fix*: Score against reference text; measure key-phrase recall.

### Anti-pattern 3: Running OCR on everything "just in case"
*Symptom*: Every PDF goes through Tesseract.
*Problem*: 100× slower; may produce worse text than the existing text layer.
*Fix*: Check for text layer first; use OCR only when needed.

### Anti-pattern 4: Ignoring table structure
*Symptom*: Treating extracted table text as a blob.
*Problem*: "Alice 42 London Bob 37 Paris" becomes meaningless without the column context.
*Fix*: Use Camelot/pdfplumber for table-formatted PDFs; preserve row/column structure in ParseResult.tables.

### Anti-pattern 5: No timeout on extraction workers
*Symptom*: One large PDF stalls the entire pipeline.
*Problem*: Without timeouts, a single edge-case PDF can block a worker indefinitely.
*Fix*: Enforce page-level and document-level timeouts. Log which PDFs hit timeout and skip them.
