# MASTER PDF & RAG GUIDE

**One-stop handbook for the `pdf_research_pipeline` project: parsing, benchmarking, and preparing PDFs for Retrieval-Augmented Generation.**

---

## Table of Contents

- [Part 1 – Project at a Glance](#part-1--project-at-a-glance)
- [Part 2 – PDF Basics and Types](#part-2--pdf-basics-and-types)
- [Part 3 – Execution Guide](#part-3--execution-guide)
- [Part 4 – PDF Parsing Libraries](#part-4--pdf-parsing-libraries)
- [Part 5 – Common Problems in PDF Parsing and Their Best Solutions](#part-5--common-problems-in-pdf-parsing-and-their-best-solutions)
- [Part 6 – RAG-Specific Considerations](#part-6--rag-specific-considerations)
- [Part 7 – Execution Story](#part-7--execution-story)
- [Part 8 – Practical Recommendations](#part-8--practical-recommendations)
- [Appendix – Quick Reference Tables](#appendix--quick-reference-tables)

---

## Part 1 – Project at a Glance

### What This Project Does

`pdf_research_pipeline` is a modular benchmarking and data-preparation system that:

1. **Downloads** PDFs from multiple sources (arXiv, Internet Archive, FUNSD, etc.)
2. **Classifies** each PDF into one of six structural types
3. **Parses** each PDF with up to 13 different parsers
4. **Benchmarks** text quality across 12 scoring dimensions
5. **Verifies** outputs for completeness and integrity
6. **Recommends** the best parser per PDF type
7. **Logs** every operation to structured JSONL files for later analysis

The primary output is an HTML report comparing parser quality across document types, plus a structured dataset of parsed text and metadata ready for RAG ingestion.

### Architecture Overview

```
┌─────────────┐    ┌─────────────┐    ┌──────────────────┐
│  Downloaders│───▶│  Cataloger  │───▶│  Parser Registry │
│  (5 sources)│    │ (PDF typing)│    │  (13 parsers)    │
└─────────────┘    └─────────────┘    └────────┬─────────┘
                                                │
                                    ┌───────────▼──────────┐
                                    │  Benchmark Engine    │
                                    │  (12-dim scoring)    │
                                    └───────────┬──────────┘
                                                │
                            ┌───────────────────▼────────────────────┐
                            │  Verification  │  Provenance  │  HTML   │
                            │  (integrity)   │  (SHA256)    │  Report │
                            └────────────────┴──────────────┴─────────┘
```

### Project Components

| Component | Location | Purpose |
|---|---|---|
| CLI | `src/pdf_research_pipeline/cli.py` | 7 Typer commands: download, catalog, parse, benchmark, verify, recommend, run-all |
| Config | `configs/*.yaml` | 5 YAML files controlling all behaviour |
| Downloaders | `src/.../downloader/` | Source adapters per data source |
| Parsers | `src/.../parsers/` | One adapter class per library |
| Benchmark | `src/.../benchmark/` | Scoring, comparison, HTML report generation |
| Verification | `src/.../verification/` | Integrity checks on parser output |
| Provenance | `src/.../provenance.py` | SHA256, run IDs, idempotency |
| Logging | `src/.../logging_utils.py` | 8 structured JSONL log streams |

### Key Numbers

- **13 parsers**: pypdfium2, PyMuPDF, pypdf, pdftext, pdfplumber, Unstructured, EasyOCR, Tesseract, OCRmyPDF, Camelot, Tabula, Marker (optional), Nougat (optional)
- **6 PDF types**: true_digital, searchable_image, image_only_scanned, complex_layout, forms_interactive, specialized
- **5 data sources**: arxiv, internet_archive, funsd, data_gov, arxiv_specialized
- **12 scoring dimensions**: completeness, accuracy, structure, layout, tables, forms, encoding, language, speed, size, rag_suitability, ocr_quality
- **Speed range**: 88ms (pypdfium2) to 384s (EasyOCR) on the same 17-page document — a **4,000× spread**

---

## Part 2 – PDF Basics and Types

### PDF Is a Presentation Format

The most important insight for PDF parsing: **a PDF file describes where ink goes on a page, not what the content means**. The internal format is a stream of positioning commands:

```
BT                    % Begin Text
/F1 12 Tf             % Use font F1 at 12pt
100 700 Td            % Move to position (100, 700)
(Hello) Tj            % Show the string "Hello"
ET                    % End Text
```

There is no sentence, no paragraph, no column, no table in the PDF format itself. Every parser must reconstruct these structures by inferring them from character positions — and every parser makes different approximations. **This is why parser choice matters and why no parser is universally best.**

### Why PDF Type Is the Most Important Routing Signal

Sending an image-only scanned PDF to a text-layer parser returns empty strings. Sending a true digital PDF to an OCR engine wastes compute and introduces character errors. **The PDF type determines which tools are even applicable.** The pipeline routes documents by type before any parsing begins.

### The Six PDF Types

---

#### Type 1: True Digital PDF

A PDF created directly from a word processor or typesetting system (Word, LaTeX, InDesign) where text is stored as actual Unicode characters in the PDF text layer.

**Characteristics:**
- Reliable, clean text layer (no OCR needed or desired)
- Font-level character encoding is well-defined
- Selectable/copyable text in any PDF viewer
- File sizes typically modest relative to content density

**Examples:** LaTeX-generated academic papers, Word-exported reports, digitally created contracts

**Parsing difficulty:** Low — machine-readable text is already there

**Pipeline routing:**
- Primary: `pymupdf` (fast, high-quality bboxes)
- Fallback: `pypdf`
- Table extractor: `camelot`

**Common gotchas:**
- Ligatures (`ﬁ`, `ﬂ`) may not be normalised — affects character counts
- Font encoding gaps (Type 1 fonts with custom glyphs) can produce garbled output from some parsers
- Copy protection (restrictions bit) blocks text layer access in some tools

---

#### Type 2: Image-Only Scanned PDF

A PDF where all page content is stored as raster images — typically a scanned physical document. There is no text layer at all. Opening in a text extractor returns empty strings.

**Characteristics:**
- Every page is a JPEG or TIFF image embedded in a PDF wrapper
- OCR is not optional — it is the only path to text
- Quality depends heavily on scan quality (DPI, skew, contrast, paper condition)
- File sizes are large relative to text content

**Examples:** Scanned books, archival documents (Internet Archive, HathiTrust), photocopied contracts, government forms from pre-digital era

**Parsing difficulty:** High — entirely dependent on OCR accuracy and image quality

**Pipeline routing:**
- Primary: `tesseract` (fast CPU OCR, 100+ language packs)
- Fallback: `ocrmypdf` (best pre-processing pipeline: deskew, denoise)
- Table extractor: none (image-to-table detection is unreliable)

**Common gotchas:**
- Below 200 DPI, Tesseract accuracy drops significantly; render at ≥300 DPI
- Handwritten text is outside the capability of Tesseract/OCRmyPDF (requires specialised HTR models)
- Diacritics and non-Latin scripts require explicit language pack installation (`tessdata-best`)

---

#### Type 3: Searchable Image PDF (aka PDF+Text)

A hybrid: the page appears as a scanned image, but a hidden text layer was added (likely by OCRmyPDF or Adobe Acrobat during a prior scan-to-PDF workflow). The text may or may not be accurate.

**Characteristics:**
- Visually identical to an image-only scan
- Text layer exists but may contain OCR errors from the original scan
- Double-layer: image for display, text for search/copy
- Text quality ranges from excellent (a clean, high-res scan) to poor (degraded original)

**Examples:** Court filings processed through Acrobat; digitised books with auto-OCR (Google Books); modern scanners with built-in OCR

**Parsing difficulty:** Medium — text layer exists but cannot be trusted blindly

**Pipeline routing:**
- Primary: `pymupdf` (extract existing text layer; it is usually faster and good enough)
- Fallback: `tesseract` (re-OCR from image if text layer is low quality)
- Table extractor: `pdfplumber`

**Deciding whether to use the text layer or re-OCR:** run both, compare character counts. If re-OCR returns significantly more characters (>20% difference), the text layer was low-quality. If they converge, trust the text layer.

---

#### Type 4: Complex Layout PDF

A born-digital PDF with multiple columns, figures, captions, sidebars, pull-quotes, footnotes, or other non-linear reading-order elements. Text is available in the PDF layer but appears in reading order that is not linear — a naive left-to-right extraction interleaves columns and produces gibberish.

**Characteristics:**
- Text layer is clean and accurate
- Reading order is non-trivial (multi-column, sidebars, footnotes)
- Contains tables, figures, equations
- Requires layout understanding to extract coherently

**Examples:** Academic papers (two-column), newspaper pages, magazine layouts, technical manuals, formal reports with sidebars

**Parsing difficulty:** High for reading order; medium for raw text

**Pipeline routing:**
- Primary: `unstructured` (hi_res strategy: layout model → typed elements in reading order)
- Fallback: `pymupdf` (fast, acceptable for keyword search; reading order may be wrong)
- Table extractor: `camelot` (for bordered tables) / `pdfplumber` (for borderless)

**Recommended upgrade path:** If GPU is available, use `marker` instead of `unstructured` — it produces correct Markdown with proper column ordering.

---

#### Type 5: Forms / Interactive PDF

A PDF created with form fields — interactive elements like text boxes, checkboxes, dropdown lists, and radio buttons. The structure includes both static labels (non-interactive text) and field values (stored in form annotations, not the text layer).

**Characteristics:**
- Two distinct content types: label text (in text layer) and field values (in annotations)
- Field values may not appear in `page.get_text()` results
- AcroForm or XFA form technology
- Often filled by users electronically or printed and scanned

**Examples:** Tax forms (IRS 1040), job applications, insurance claim forms (FUNSD dataset), government data entry forms

**Parsing difficulty:** Medium — text layer parsing misses field values unless annotations are explicitly read

**Pipeline routing:**
- Primary: `unstructured` (understands form structure, outputs elements with context)
- Fallback: `pdfplumber` (can extract words near field regions)
- Table extractor: `tabula` (for tabular data in forms)

**Key requirement:** A form-aware parser must read both the text layer (`page.extract_words()`) **and** the annotation layer (`page.annots()`) and correlate them. Generic text extractors miss filled-in values entirely.

---

#### Type 6: Specialized PDF

PDFs with domain-specific content that goes beyond text: scientific papers with mathematical equations typeset in LaTeX, patents with chemical structure diagrams, technical drawings with vector art, musical scores. Standard text extraction captures the alphanumeric content but loses the domain semantics.

**Characteristics:**
- Text layer usually present and clean
- Domain-specific non-text elements heavily important to meaning
- Standard text extraction produces incomplete or meaningless results for some content types
- Requires domain-aware models or post-processing

**Examples:** arXiv papers with equations, patent documents with molecular diagrams, engineering drawings, sheet music

**Parsing difficulty:** Very high for semantic fidelity; low for raw text

**Pipeline routing:**
- Primary: `nougat` (if installed — Math/LaTeX equation preservation)
- Fallback: `marker` (if installed — best readable Markdown)
- Secondary fallback: `pymupdf` (raw text, equations lost)

---

### PDF Type Quick Reference

| Type | Text Layer? | Needs OCR? | Layout Complexity | Primary Parser | Table Extractor |
|---|---|---|---|---|---|
| True Digital | ✅ Clean | ❌ | Low | pymupdf | camelot |
| Image-Only Scanned | ❌ None | ✅ Required | Low–Medium | tesseract | — |
| Searchable Image | ⚠️ May have errors | Optional | Low–Medium | pymupdf | pdfplumber |
| Complex Layout | ✅ Good | ❌ | High | unstructured | camelot/pdfplumber |
| Forms / Interactive | ⚠️ Labels only | ❌ | Medium | unstructured | tabula |
| Specialized | ✅ + domain content | ❌ | High + domain | nougat/marker | — |

### How the Pipeline Determines Type

PDF type is assigned at **catalog time** based on the directory path: `data/raw/<pdf_type>/<source>/`. The source configuration in `configs/sources.yaml` specifies `pdf_type` per source. Files downloaded from the arxiv source land in `data/raw/complex_layout_pdf/arxiv/`; files from internet_archive land in `data/raw/image_only_scanned_pdf/internet_archive/`. There is no automated content-based detection — the source determines the type.

---

## Part 3 – Execution Guide

### System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| Python | 3.11 | 3.12.x |
| RAM | 4 GB | 16 GB |
| Disk | 2 GB | 20 GB (for full benchmark) |
| Tesseract | Optional | 5.x |
| Java JRE | Optional | 11+ (for Tabula) |
| Ghostscript | Optional | Latest (for Camelot/OCRmyPDF) |

### Installation

```bash
# Clone and enter the project
git clone <repo-url>
cd pdf_research_pipeline

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS

# Install the project with all dev/benchmark dependencies
pip install -e ".[dev]"

# Verify entry-point works
pdf-pipeline --help
```

#### Tesseract (Windows)

Download the installer from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and install to the default path. The pipeline auto-detects `C:\Users\<user>\AppData\Local\Programs\Tesseract-OCR\tesseract.exe`. Verify:

```bash
tesseract --version   # Should print: tesseract 5.x.x
```

If you see `TesseractNotFoundError`, check `configs/parsers.yaml` and set the absolute path under the `tesseract` parser config.

#### Java / Tabula (optional)

Download JRE 11+ and ensure `java` is on PATH:

```bash
java -version   # Should print version string
```

If Java is missing, the pipeline disables Tabula automatically and logs `PARSER_SKIPPED`.

#### Ghostscript (required for Camelot and OCRmyPDF)

- Linux: `sudo apt-get install ghostscript`
- macOS: `brew install ghostscript`
- Windows: download from [ghostscript.com](https://www.ghostscript.com/releases/)

---

### Configuration Files

All pipeline behaviour is controlled by five YAML files in `configs/`.

#### `configs/sources.yaml` — What to Download

```yaml
sources:
  - id: arxiv
    enabled: true
    pdf_type: complex_layout_pdf
    max_pdfs: 10
    query: "large language models"
    categories: ["cs.CL", "cs.AI"]

  - id: internet_archive
    enabled: true
    pdf_type: image_only_scanned_pdf
    max_pdfs: 5
```

Each source entry controls one downloader. Set `enabled: false` to skip a source. `pdf_type` drives the directory path and determines which parsers run.

#### `configs/parsers.yaml` — Which Parsers Run and How

```yaml
parsers:
  pymupdf:
    enabled: true
    max_pages: null      # null = no limit
    timeout_seconds: 30
    pdf_type_hints:
      primary: [true_digital_pdf, searchable_image_pdf]
      fallback: [complex_layout_pdf]
      table_extractor: []

  tesseract:
    enabled: true
    max_pages: 10         # hard cap for OCR parsers
    timeout_seconds: 300
    pdf_type_hints:
      primary: [image_only_scanned_pdf]
      fallback: [searchable_image_pdf]
```

`max_pages` is the single most important performance control. OCR parsers without a page cap on 30-page documents can run for an hour. `pdf_type_hints` drives the primary/fallback/table_extractor routing.

#### `configs/pipeline.yaml` — Execution Behaviour

```yaml
stages:
  - download
  - catalog
  - parse
  - benchmark
  - verify
  - recommend

parallel_downloads: 4
parallel_parsers: 2
skip_existing: true
```

#### `configs/scoring.yaml` — How Results Are Evaluated

Twelve quality dimensions, each with a default weight. The weights sum to 1.0:

| Dimension | Default Weight | What It Measures |
|---|---|---|
| completeness | 0.20 | Characters extracted vs expected |
| accuracy | 0.18 | Character error rate (where ground truth exists) |
| structure | 0.12 | Heading/paragraph/section detection |
| layout | 0.10 | Reading order and column handling |
| tables | 0.10 | Tables extracted vs tables present |
| forms | 0.05 | Form field coverage |
| encoding | 0.08 | Character encoding errors, garbled text |
| language | 0.04 | Language detection confidence |
| speed | 0.07 | Inverse of parse duration |
| size | 0.02 | Output size vs original |
| rag_suitability | 0.03 | Chunk quality for downstream RAG |
| ocr_quality | 0.01 | OCR confidence scores (OCR parsers only) |

Per-type weight overrides are defined in the same file. For `image_only_scanned_pdf`, `ocr_quality` is boosted from 0.01 to 0.35 and `structure` reduced, since OCR accuracy dominates everything else for scanned documents.

> **Note:** The default `rag_suitability` weight of 3% is too low for RAG-focused workloads. If your goal is RAG document ingestion (rather than general benchmarking), increase `rag_suitability` to 0.20–0.30 in your type-specific overrides.

#### `configs/logging.yaml` — Log Routing

Eight structured JSONL streams, one concern per file:

| File | Content |
|---|---|
| `logs/run.log.jsonl` | Pipeline lifecycle events (start/end of each stage) |
| `logs/download.log.jsonl` | Per-file download completions and skips |
| `logs/extraction.log.jsonl` | Per-parser parse events and results |
| `logs/errors.log.jsonl` | All errors and exceptions with stack context |
| `logs/metrics.log.jsonl` | Numeric scores per parser per dimension |
| `logs/parser_selection.log.jsonl` | Which parser was chosen and why |
| `logs/provenance.log.jsonl` | SHA256 checksums and file identity |
| `logs/verification.log.jsonl` | Verification check results |

Query any log with standard CLI tools:

```bash
# All errors from the last run
jq 'select(.level == "error")' logs/errors.log.jsonl

# Per-parser timing
jq '{parser: .parser, duration_ms: .duration_ms}' logs/extraction.log.jsonl

# All skipped downloads
jq 'select(.event == "download_skipped")' logs/download.log.jsonl
```

---

### Folder Structure

```
pdf_research_pipeline/
├── configs/          # 5 YAML configuration files
├── data/
│   ├── raw/
│   │   ├── complex_layout_pdf/arxiv/       # Downloaded PDFs by type
│   │   ├── image_only_scanned_pdf/internet_archive/
│   │   ├── forms_interactive_pdf/funsd/
│   │   └── ...
│   ├── catalog/
│   │   └── pdf_catalog.jsonl               # Central registry (one entry per PDF)
│   ├── parsed/
│   │   └── <type>/<sha256_prefix>_<arxiv_id>/<parser>/
│   │       ├── result.json                 # ParseResult (metadata + tables + scores)
│   │       └── text.txt                    # Extracted plain text
│   └── text_exports/                       # Flat text exports per PDF
├── logs/             # 8 structured JSONL log files
├── reports/          # Working reports directory
├── artifacts/
│   └── reports/
│       └── accuracy_report.html           # Main benchmark HTML report
└── src/pdf_research_pipeline/             # Source code
```

---

### CLI Reference

All commands are accessed via the `pdf-pipeline` entry-point.

#### Stage 1: Download

```bash
pdf-pipeline download                    # All enabled sources
pdf-pipeline download --source arxiv     # Single source
pdf-pipeline download --dry-run          # Preview without downloading
```

Saves PDFs to `data/raw/<pdf_type>/<source>/`. Skips files that already exist on disk (idempotent). Logs to `download.log.jsonl`.

#### Stage 2: Catalog

```bash
pdf-pipeline catalog
```

Scans `data/raw/` recursively, computes SHA256 for each file, and writes `data/catalog/pdf_catalog.jsonl`. Runs in milliseconds (no network, no parsing). Re-run after adding new PDFs.

> **Tip:** If a PDF shows the wrong type in the benchmark, it means the file was placed in the wrong `data/raw/<type>/` subfolder or `sources.yaml` has the wrong `pdf_type`. The catalog reads the directory path — there is no content-detection step.

#### Stage 3: Parse

```bash
pdf-pipeline parse                               # All PDFs, all enabled parsers
pdf-pipeline parse --pdf-id 194dfc73             # One PDF, all parsers
pdf-pipeline parse --parser pymupdf              # All PDFs, one parser
pdf-pipeline parse --max-ocr-pages 5            # Override OCR page cap for this run
```

Writes `result.json` and `text.txt` to `data/parsed/<type>/<id>/<parser>/`. Skips combinations that already have results (idempotent). Logs to `extraction.log.jsonl`.

#### Stage 4: Benchmark

```bash
pdf-pipeline benchmark
```

Reads all `result.json` files, scores each against the 12 dimensions, computes per-type leaderboards, and generates `artifacts/reports/accuracy_report.html`. Open in a browser.

#### Stage 5: Verify

```bash
pdf-pipeline verify
```

Checks every parse result for known failure signals:

| Signal | Description |
|---|---|
| `EMPTY_TEXT` | Parser returned 0 characters (type mismatch or parse error) |
| `TRUNCATED_OUTPUT` | Character count implies max_pages cap was hit |
| `CHECKSUM_MISMATCH` | result.json hash doesn't match the source PDF |
| `TIMEOUT_EXCEEDED` | Parse exceeded the configured `timeout_seconds` |

Logs to `verification.log.jsonl`. Any `EMPTY_TEXT` for a non-OCR parser on a supposedly born-digital PDF is a strong signal of PDF type misclassification.

#### Stage 6: Recommend

```bash
pdf-pipeline recommend
```

Reads benchmark scores and prints the top-ranked parser per PDF type with justification.

#### Run Everything

```bash
pdf-pipeline run-all                   # Full pipeline: download → recommend
```

---

### Execution Timing Reference

Measured on a CPU workstation (no GPU) with a 17-page two-column arXiv paper:

| Parser | Duration | Characters | Notes |
|---|---|---|---|
| pypdfium2 | ~90ms | 55,036 | Fastest; Chrome-quality |
| pymupdf | ~400ms | 54,353 | Fast; rich bbox data |
| pypdf | ~900ms | 54,232 | Pure-Python baseline |
| pdftext | ~1.3s | 52,232 | Reading-order aware |
| pdfplumber | ~48s | 49,125 | Accurate; very slow |
| ocrmypdf | ~50s (10pp) | 34,144 | Best image pre-processing |
| unstructured | ~61s | 55,113 | Semantic typed elements |
| tesseract | ~74s (10pp) | 34,093 | Reliable batch OCR |
| camelot | ~122s | 160 + 1 table | Table extractor, not text |
| easyocr | ~379s (10pp) | 33,934 | Deep-learning OCR |

OCR parsers marked `(10pp)` ran with `max_pages=10` — full-document times would scale proportionally.

---

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `TesseractNotFoundError` | Binary not found on PATH | Set absolute path in parsers.yaml or add `C:\...\Tesseract-OCR` to PATH |
| `tabula.errors.JavaNotFoundError` | Java not on PATH | Install JRE 11+, or set `enabled: false` for Tabula in parsers.yaml |
| EasyOCR stalls indefinitely | No page cap; GPU OOM | Set `max_pages: 5` in parsers.yaml for easyocr |
| All parse results are empty strings | PDF is image-only; text-layer parser used | Check `pdf_type` in catalog; move file to `image_only_scanned_pdf/` |
| Catalog shows wrong PDF type | File placed in wrong source directory | Move file to correct `data/raw/<type>/` and re-run catalog |
| OOM during benchmark | pdfplumber + Unstructured concurrently | Set `parallel_parsers: 1` in pipeline.yaml |

---

## Part 4 – PDF Parsing Libraries

This section covers all 13 parsers used by the pipeline — what each one is, how it works internally, what it is good and bad at, and how the pipeline uses it.

### How to Choose a Parser (Decision Tree)

```
Is the PDF born-digital (has a text layer)?
│
├─ YES → Does reading order matter?
│         ├─ YES (multi-column, sidebars) → unstructured (hi_res) or marker (GPU)
│         ├─ NO (keywords, bulk ingestion) → pypdfium2 (fastest) or pymupdf (with bboxes)
│         └─ Are there tables to extract? → camelot (bordered) or pdfplumber (borderless)
│
└─ NO (image-only or uncertain) → Is image quality good?
          ├─ YES (clean scan) → tesseract (fast) or easyocr (multilingual)
          └─ NO (skewed/noisy) → ocrmypdf (deskew + denoise → tesseract)
```

---

### 1. PyMuPDF (fitz)

**Version**: 1.27.2.2 | **Install**: `pymupdf>=1.24.0` | **System deps**: none

**Architecture**

PyMuPDF is a Python binding for **MuPDF**, a C-based PDF rendering library. It is the lowest-overhead option that retains full structural richness (bounding boxes, fonts, page structure). Text is extracted as a stream of positioned character blocks.

```
Python → fitz (Cython) → MuPDF (C) → PDF text layer → positioned glyphs
```

**How the pipeline uses it**

- Primary parser for `true_digital_pdf` and `searchable_image_pdf`
- Fallback for `complex_layout_pdf` when Unstructured is too slow
- Page renderer (to PIL images) for Tesseract and EasyOCR — eliminates Poppler/pdftoppm dependency

Key API: `page.get_text("blocks")` for text blocks with bboxes; `page.get_text("words")` for word-level positioning.

**Strengths**: Fastest C-backed extractor with bboxes (200–500ms per 20-page doc); pixel-accurate word positions; no system dependencies; multi-format support (EPUB, XPS, CBZ).

**Limitations**: Extracts text in stream order — multi-column documents have columns interleaved; no inherent table detection; no form field value access.

**Best for**: True digital PDFs, bulk text extraction, rendering pages for downstream OCR.

---

### 2. pdfplumber

**Version**: 0.11.9 | **Install**: `pdfplumber>=0.11.0` | **System deps**: none

**Architecture**

Built on `pdfminer.six`, pdfplumber exposes character-level positions and implements geometric analysis for table detection (whitespace gap analysis).

```
Python → pdfplumber → pdfminer.six → PDF text layer → char-level positions
       → table detection (whitespace/line geometry) → DataFrames
```

**How the pipeline uses it**

Table extractor for `searchable_image_pdf` and `forms_interactive_pdf`. Falls back for borderless tables in complex layouts.

Key API: `page.extract_words()` for word-level text; `page.extract_tables()` for whitespace-based table detection.

**Strengths**: Best table extraction for borderless tables (financial filings, government data); character-level position accuracy; widely validated against real-world documents in data journalism.

**Limitations**: Very slow (48s per 17-page doc, up to 143s for content-dense 12-page docs); runtime depends on character density, not page count; same column-interleaving problem as PyMuPDF for multi-column layouts.

**Real-world usage**: OCCRP (Organised Crime Reporting Project), ProPublica, ONS, BLS for government data extraction.

**Best for**: Borderless table extraction; cases where character-level positional accuracy justifies the runtime.

---

### 3. pypdf

**Version**: 5.9.0 | **Install**: `pypdf>=5.0.0` | **System deps**: none

**Architecture**

Pure-Python PDF library. Minimal external dependencies. Parses PDF object streams directly.

```
Python → pypdf → PDF object graph → text layer → string assembly
```

**How the pipeline uses it**

Fallback for `true_digital_pdf` when PyMuPDF fails. Also used for PDF metadata (page count, encryption status) during catalog.

**Strengths**: Zero external dependencies (pip-only install); good for PDF manipulation (merge, split, rotate, encrypt); reasonable speed (~900ms per 17-page doc); broad compatibility.

**Limitations**: Text quality varies — encoding issues on Type 1 fonts with non-standard glyph maps; no bounding boxes; column interleaving; table detection absent.

**Best for**: Lightweight environments (Lambda, containers with no system packages); PDF file operations; metadata extraction.

---

### 4. pypdfium2

**Version**: 4.30.0 | **Install**: `pypdfium2>=4.0.0` | **System deps**: none (bundled)

**Architecture**

Python bindings for **PDFium**, the PDF rendering engine used in Google Chrome. Ships as a self-contained wheel (~30 MB) with the compiled PDFium library included.

```
Python → pypdfium2 (ctypes/CFFI) → PDFium (C++) → PDF text layer → Unicode characters
```

**How the pipeline uses it**

Primary parser for `true_digital_pdf`. Also the rendering backend for `pdftext`.

Key API: `page.get_textpage().get_text_range()` for contiguous text; the basic API does not expose per-word bboxes.

**Strengths**: Fastest non-OCR parser in the benchmark — **88ms** for a 17-page PDF (4× faster than PyMuPDF); Chrome-quality Unicode handling including ligatures and complex encoding; no system dependencies; handles the widest range of valid PDF variants (follows Chrome's parser).

**Limitations**: Basic text API does not expose bounding boxes (character positions require a lower-level CFFI call); largest binary size of the text-layer parsers.

**Real-world usage**: Search indexing at scale; LLM pre-training dataset pipelines; serverless/Lambda functions.

**Best for**: High-throughput born-digital PDF ingestion where bboxes are not needed.

---

### 5. pdftext

**Version**: 0.6.3 | **Install**: `pdftext>=0.3.0` | **System deps**: none

**Architecture**

Uses PDFium via ctypes (same underlying engine as pypdfium2) but adds a reading-order reconstruction layer on top: character clusters are sorted by reading order heuristics rather than raw stream order.

```
Python (pdftext) → PDFium via ctypes → char-level positions
               → reading order heuristics → ordered text output
```

**How the pipeline uses it**

One of the text-layer parsers in the benchmark. Also the internal text extraction engine used by **Marker**.

**Strengths**: Reading-order aware (better than raw pypdfium2 for some multi-column documents); character-level output; fast (~1.3s per 17-page doc).

**Limitations**: Newer library — less tested on edge cases; no table detection; reading-order heuristics are not as sophisticated as a full layout model.

**Best for**: Cases needing better reading order than raw text extraction but without the overhead of a layout model.

---

### 6. Unstructured

**Version**: 0.18.32 | **Install**: `unstructured[pdf]>=0.16.0` | **System deps**: Tesseract (for hi_res)

**Architecture**

Three extraction strategies depending on document characteristics:

| Strategy | When Used | Method |
|---|---|---|
| `fast` | Born-digital PDFs | pdfminer text extraction |
| `hi_res` | Complex layouts, scanned (default) | YOLOv8/DiT layout detection → Tesseract for images |
| `ocr_only` | Forced OCR | Tesseract on all pages |

Output is a list of **typed elements**: `Title`, `NarrativeText`, `ListItem`, `Table`, `Image`, `Header`, `Footer`. This semantic element typing is unique among the parsers.

```
Python → unstructured → strategy selector
       → [hi_res] layout model (YOLOv8/DiT) → region classification
                   → Tesseract (for image regions) → text
                   → reading-order model → element sequence
```

**How the pipeline uses it**

Primary parser for `complex_layout_pdf` and `forms_interactive_pdf`. The typed elements (Title, NarrativeText, Table) feed directly into RAG chunking strategies.

**Strengths**: Best reading order for multi-column documents (uses an explicit layout model); typed element output maps naturally to RAG chunking; handles mixed content (text + scanned images) in the same document.

**Limitations**: Slow in `hi_res` mode (~60s per 17-page doc); large dependency footprint (YOLOv8 model + Tesseract); memory-hungry (2–4 GB peak during layout inference); API evolves quickly between versions.

**Real-world usage**: Enterprise RAG pipelines; LangChain and LlamaIndex document loaders.

**Best for**: Complex multi-column layouts where correct reading order is required; documents mixing text and images.

---

### 7. EasyOCR

**Version**: 1.7.2 | **Install**: `easyocr>=1.7.0` | **System deps**: PyTorch (~500 MB)

**Architecture**

Deep-learning OCR using CRAFT (for text region detection) + CRNN (for text recognition). Downloads model weights on first use. The pipeline renders pages via PyMuPDF before passing to EasyOCR.

```
Python → PyMuPDF (render page at 150 dpi) → PIL image
      → EasyOCR [CRAFT detector → text region boxes]
               [CRNN recogniser → text per region]
               → text + confidence scores
```

The `Reader` object is expensive to initialise (loads PyTorch models) — the pipeline creates it once per process and reuses it across pages.

**How the pipeline uses it**

Benchmark participant for `image_only_scanned_pdf`. In practice, the OCR page cap limits runtime.

**Strengths**: 80+ supported languages from a single model; per-word confidence scores; good accuracy on multilingual and mixed-script documents; handles low-quality images better than Tesseract on some scripts.

**Limitations**: Very slow on CPU (~379s for 10 pages); requires PyTorch (~500 MB install); model weights download on first use; not designed for long-form document batch processing; 150 dpi render quality is lower than Tesseract's 300 dpi default.

**Real-world usage**: KYC/ID verification (Korean/Japanese/Chinese IDs); receipt processing in expense management apps; multilingual archive digitisation.

**Best for**: Short documents in non-Latin scripts; cases needing confidence scores per word.

---

### 8. Tesseract / pytesseract

**Version**: pytesseract 0.3.13 / Tesseract 5.5.0 (system install) | **System deps**: tesseract binary, tessdata files

**Architecture**

Python wrapper that calls the `tesseract` binary via subprocess. The pipeline renders each PDF page to a PIL image using PyMuPDF, then passes it to pytesseract.

```
Python (pytesseract) → subprocess → tesseract binary (LSTM recogniser)
                                  → tessdata language model
                                  → TSV / hOCR / plain text
```

Path auto-detection includes the Windows default: `C:\Users\<user>\AppData\Local\Programs\Tesseract-OCR\tesseract.exe`.

**How the pipeline uses it**

Primary OCR parser for `image_only_scanned_pdf`. Also the OCR backbone used by Unstructured (hi_res) and OCRmyPDF.

Key parameters: `lang="eng"`, `config="--psm 1"` (auto page segmentation with OSD), `dpi=300` rendering.

**Strengths**: Production-grade OCR used worldwide; faster than deep-learning alternatives on CPU (~74s for 10 pages vs ~379s for EasyOCR); 100+ language packs available; PSM options cover single-block, single-line, and column layouts; mature and stable.

**Limitations**: System-level binary install required (complicates containerisation); resolution-sensitive (below 200 dpi, accuracy drops sharply); `image_to_string` does not preserve table structure (use hOCR output for that); subprocess-based (not thread-safe without careful design).

**Real-world usage**: Internet Archive, HathiTrust, e-discovery platforms, Paperless-ngx document management.

**Best for**: Batch OCR of image-only scanned documents; situations where speed on CPU is more important than multilingual script support.

---

### 9. OCRmyPDF

**Version**: 17.4.1 | **Install**: `ocrmypdf>=16.0.0` | **System deps**: Ghostscript + Tesseract binaries

**Architecture**

Does not extract text directly from PDFs — instead, it **creates a searchable PDF** by adding a hidden text layer, then the pipeline reads that text layer with PyMuPDF.

```
Input PDF → Ghostscript (rasterise pages)
          → unpaper (optional: deskew, denoise)
          → Tesseract (OCR → hOCR per page)
          → Ghostscript (reassemble PDF with text layer)
Output: searchable PDF → PyMuPDF → extracted text
```

**How the pipeline uses it**

Fallback OCR parser for challenging `image_only_scanned_pdf` where Tesseract alone fails (skewed scans, low-contrast originals). The `OCRmyPDFParser` creates a temp PDF, runs the full pipeline, then extracts via PyMuPDF.

**Strengths**: Best image pre-processing pipeline of all parsers — deskew, denoise, and contrast normalisation happen before OCR, significantly improving accuracy on difficult scans; permanent searchable output; handles encrypted PDFs; detailed audit log.

**Limitations**: Two heavy system dependencies (Ghostscript + Tesseract); slow (~50s for 10 pages); disk-I/O heavy (temp PDF creation); subprocess-based.

**Real-world usage**: Law firms (iManage), healthcare EHR systems, FOIA document production, enterprise document management.

**Best for**: Challenging scanned documents with skew, noise, or low contrast; workflows that need the permanent searchable PDF as an artifact.

---

### 10. Camelot

**Version**: 1.0.9 | **Install**: `camelot-py[cv]>=0.11.0` | **System deps**: Ghostscript

**Architecture**

Table-extraction specialist. Implements two detection algorithms:

- **Lattice mode**: Ghostscript renders the page as an image → OpenCV detects grid lines (Hough transform) → cell boundaries reconstructed → pdfminer provides text within cells
- **Stream mode**: pdfminer provides character-level positions → column/row boundaries inferred from whitespace gaps

```
Lattice: Ghostscript → image → OpenCV line detection → cell grid → pdfminer text
Stream:  pdfminer → char positions → whitespace analysis → inferred table
```

**How the pipeline uses it**

Table extractor for `true_digital_pdf` and `complex_layout_pdf`. The `CamelotExtractor` tries lattice first, falls back to stream, and exports DataFrames as structured lists in `ParseResult.tables`.

**Benchmark observation**: Camelot spent 122s on a 17-page arXiv paper and found **1 table**. On a different 12-page paper, it found **2 tables** in 184s. The majority of that time is Ghostscript rendering, which happens regardless of how many tables are found.

**Strengths**: Best quality for bordered tables (lattice mode uses actual line geometry); output is Pandas DataFrames (immediately analysis-ready); built-in per-table confidence metrics; widely validated on government and financial PDFs.

**Limitations**: Requires Ghostscript; slow (122+s, dominated by Ghostscript); fails on rotated or overlapping tables; stream mode unreliable on unusual column spacing.

**Real-world usage**: ICIJ (Panama Papers), newsroom data desks, RegTech, Eurostat.

**Best for**: Extracting structured data from tables with visible borders; financial filings, government reports, any PDF where tables are the primary content.

> **Important:** Do not run Camelot on every document universally. Pre-check for table presence (e.g., look for line elements in the PDF metadata) before invoking it. Two minutes of Ghostscript overhead per table-free document adds up immediately in batch processing.

---

### 11. Tabula-py

**Version**: optional | **Install**: `tabula-py>=2.9.0` | **System deps**: Java JRE 11+

**Architecture**

Python wrapper around the Tabula Java library, which uses PDFBox for PDF parsing and its own heuristic table detection.

```
Python (tabula-py) → subprocess → JVM → Tabula.jar → PDFBox → table detection → CSV/JSON
```

**How the pipeline uses it**

Alternative table extractor for `forms_interactive_pdf`. Disabled automatically if Java is absent.

**Strengths**: Different algorithm from Camelot — catches tables Camelot misses; handles some merged-cell cases better; battle-tested in data journalism; no OpenCV dependency.

**Limitations**: Requires Java (container/cloud friction); ~500ms JVM startup per call; worse at bordered tables than Camelot lattice mode; numeric formatting can garble currency and negative signs.

**Real-world usage**: NGOs, data journalism (ICIJ, ProPublica), budget monitoring platforms.

**Best for**: Forms and financial PDFs where Camelot fails; as a complementary second-pass table extractor.

---

### 12. Marker

**Version**: not installed (graceful stub) | **Install**: `marker-pdf` | **System deps**: PyTorch (GPU recommended)

**Architecture**

ML-based PDF-to-Markdown pipeline combining pdftext (text extraction) with layout, reading-order, and table recognition models.

```
pdftext → character extraction + positions
       → Layout model (PyTorch) → region classification
       → Reading-order model → correct sequence
       → Table recognition model → Markdown tables
       → Post-processing → final Markdown string
```

**How the pipeline uses it**

Registered but disabled (`enabled: false`). Activating requires installing `marker-pdf` and a GPU.

**Strengths**: Best open-source Markdown output for multi-column academic PDFs; reading order is correct (layout model explicitly detects columns); tables as `| col |` Markdown; equation preservation; designed for RAG — output is clean, structured Markdown.

**Limitations**: Requires GPU for practical use (CPU is very slow); large install (PyTorch + model weights, several GB); API evolves quickly; not ideal for scanned PDFs.

**Real-world usage**: arXiv corpus processing for LLM pre-training; research paper Q&A systems.

**Best for**: When you need production-quality Markdown from complex academic or technical PDFs and have GPU access.

---

### 13. Nougat

**Version**: not installed (graceful stub) | **Install**: `nougat-ocr` | **System deps**: PyTorch + GPU (required)

**Architecture**

Swin Transformer encoder + BART decoder — a fully visual model that reads page images and generates text token-by-token, similar to image captioning.

```
PDF pages → rasterised images (896×672px) → Swin Transformer encoder
                                           → BART decoder → mmd (Modified Markdown) string
```

No dependency on the PDF text layer whatsoever. Works equally on born-digital and scanned scientific documents.

**How the pipeline uses it**

Registered but disabled. Primary parser for `specialized_pdf` if activated.

**Strengths**: Best equation extraction of all parsers (trained on arXiv LaTeX source — outputs `\frac{a}{b}`, `\sum_{i=0}^n`, etc.); fully image-based (immune to text layer corruption); end-to-end ML pipeline.

**Limitations**: Very slow on CPU (transformer inference); hallucinates on degraded pages; decoder can enter repetition loops; only trained on scientific papers (poor on general document types); requires ~8 GB VRAM.

**Real-world usage**: Scientific NLP, math formula extraction, Minerva/Galactica-style math reasoning models.

**Best for**: Specialized scientific PDFs with dense equations where equation fidelity is critical.

---

### Parser Summary Table

| Parser | Speed | Tables | Reading Order | OCR | RAG Quality | Install Complexity |
|---|---|---|---|---|---|---|
| pypdfium2 | ⚡⚡⚡⚡⚡ | ❌ | Stream | ❌ | Good | pip only |
| pymupdf | ⚡⚡⚡⚡ | ❌ | Stream | ❌ | Good | pip only |
| pypdf | ⚡⚡⚡ | ❌ | Stream | ❌ | Fair | pip only |
| pdftext | ⚡⚡⚡ | ❌ | Heuristic | ❌ | Good | pip only |
| pdfplumber | ⚡⚡ | ✅ borderless | Stream | ❌ | Good | pip only |
| unstructured | ⚡ | ✅ (hi_res) | ✅ Layout model | ⚠️ (hi_res) | Excellent | Large + Tesseract |
| tesseract | ⚡ | ❌ | Mediocre | ✅ | Fair | System binary |
| ocrmypdf | ⚡ | ❌ | Mediocre | ✅ | Fair | System GS + Tesseract |
| easyocr | 🐢 | ❌ | Poor | ✅ | Fair | pytorch |
| camelot | 🐢 | ✅ bordered | N/A | ❌ | N/A (tables only) | System GS + OpenCV |
| tabula | 🐢 | ✅ | N/A | ❌ | N/A (tables only) | Java JRE |
| marker | ⚡⚡ (GPU) | ✅ Markdown | ✅ Layout model | ❌ | Excellent | PyTorch + GPU |
| nougat | 🐢🐢 (CPU) | ❌ | ✅ Visual | ✅ (visual) | Excellent (sci) | PyTorch + GPU |

---

## Part 5 – Common Problems in PDF Parsing and Their Best Solutions

This section is a practical problem catalogue. Each entry names the problem, explains why it occurs at the PDF format level, and provides the best solutions available in or compatible with this pipeline.

---

### Problem 1: Repeated Headers, Footers, and Page Numbers

**Symptom**: Every extracted text chunk begins with "Company Name — Confidential — Page N of M" or ends with a URL and a footer legal notice. These strings appear on every page and pollute chunked text with noise that has no retrieval value.

**Why it happens**: PDF headers and footers are positioned text boxes. Most parsers extract them as regular text because at the character-position level, they look identical to content text. There is no PDF standard field marking a text block as "header" or "footer."

**Solutions:**

1. **Bounding-box filtering** (works with PyMuPDF): Define a vertical strip exclusion zone — skip any text block whose `y0` coordinate falls within the top 5–7% or bottom 5–7% of the page height. This removes most running headers and footers geometrically.

   ```python
   page_height = page.rect.height
   for block in page.get_text("blocks"):
       y0, y1 = block[1], block[3]
       if y0 < page_height * 0.07 or y1 > page_height * 0.93:
           continue  # skip header/footer region
   ```

2. **Frequency-based n-gram filtering**: Collect all text blocks across all pages. Any string appearing on ≥80% of pages is a header or footer. Remove it from all pages before further processing.

3. **Unstructured element types**: In `hi_res` mode, Unstructured labels elements as `Header` and `Footer`. Filter by element type before chunking — no geometric heuristics needed.

4. **Tagged PDF artifacts**: Well-structured tagged PDFs mark headers/footers as `Artifact` in the PDF tag tree. PyMuPDF can read the tag tree and skip artifact elements, though most real-world PDFs are not fully tagged.

**Recommended approach for this pipeline**: Use the Unstructured parser for complex-layout documents and filter on element type. For text-layer parsers (PyMuPDF, pypdfium2), apply bounding-box exclusion with a configurable margin.

---

### Problem 2: Broken Reading Order and Multi-Column Layouts

**Symptom**: Extracted text interleaves content from both columns of a two-column paper — end of a sentence from column 1 page 2 followed immediately by the middle of a different sentence from column 2 page 1.

**Root cause**: PDF text objects are stored in drawing order, not reading order. In a two-column paper, LaTeX typically populates column 1 and column 2 independently. The PDF stream contains them in page-layout order (e.g., column 1 top → column 2 top → column 1 middle → column 2 middle). A naive extractor following stream order produces interleaved text.

**Benchmark evidence**: On the arXiv papers tested, PyMuPDF (stream order) and pypdfium2 produced similar character counts to Unstructured (layout-aware) — the interleaving does not cause character loss, it causes **ordering errors**. For keyword search, ordering errors are tolerable. For RAG or LLM context, they are catastrophic — the model receives semantically incoherent text.

**Solutions (ordered by quality):**

1. **Unstructured (hi_res)** — uses a YOLOv8/DiT layout model to detect column regions explicitly, then outputs elements in reading order. Best quality; ~60s overhead.

2. **Marker** (if GPU available) — pdftext + reading-order model. Correct column ordering; clean Markdown output. Fastest among layout-aware options with GPU.

3. **pdftext** — PDFium characters + reading-order heuristics. Not as accurate as a full layout model but significantly better than raw stream order; ~1.3s.

4. **Bounding-box sorting** — general approach: extract all character blocks with their `(x0, y0, x1, y1)` coordinates, cluster into columns by x-range, sort within each column by descending y. Works reasonably well for clean two-column layouts; fails on documents with figures spanning both columns.

   ```python
   # Simplified column-sort heuristic
   blocks = sorted(page.get_text("blocks"), key=lambda b: (round(b[0]/200), -b[1]))
   ```

5. **Nougat** — for scientific PDFs, the visual decoder produces inherently correct reading order because it reads the rendered page like a human.

**Recommendation**: For RAG pipelines consuming multi-column documents, the reading-order cost of using PyMuPDF (stream order) is not acceptable. Use Unstructured or Marker. For keyword-based search where order doesn't matter, stream-order extraction is fine.

---

### Problem 3: OCR Noise and Image-Only PDFs

**Symptom**: Extracted text contains garbled words (`"rn" → "m"`, `"cl" → "d"`, random punctuation), inconsistent spacing, or numbers that don't match the visual page.

**Root cause**: OCR recovery of text from scanned images is inherently lossy. Common failure modes:
- **Low DPI**: scans below 200 DPI have insufficient pixel resolution for character recognition
- **Skew**: physical document tilted when scanned; OCR engines work best on horizontal text
- **Noise**: scanner artifacts (speckling, shadows from page curl, bleed-through from reverse side)
- **Font type**: handwriting, unusual typefaces, or dense small-point text
- **Compression artifacts**: aggressive JPEG compression destroys character edges

**Solutions:**

1. **Render at 300 DPI minimum** — the pipeline renders via PyMuPDF at 300 DPI for Tesseract and 150 DPI for EasyOCR. For challenging documents, increase Tesseract rendering to 400 DPI in parsers.yaml.

2. **OCRmyPDF over raw Tesseract for poor scans** — OCRmyPDF runs `unpaper` (deskew, denoise, border cleanup) before Tesseract. On a skewed scan, this step alone can improve word accuracy by 15–30%.

3. **Confidence thresholding with EasyOCR** — EasyOCR returns a confidence score (0–1) per detected region. Discard low-confidence regions (e.g., `< 0.6`) for downstream processing.

4. **Do not OCR born-digital PDFs** — this is a critical anti-pattern. Tesseract introduces character errors on text that was already perfect in the PDF layer. The pipeline routes by type specifically to prevent this.

5. **Language pack selection** — Tesseract's accuracy on non-English Latin script languages (French, German, Portuguese) improves significantly with language-specific tessdata. Verify the tessdata pack is installed: `tesseract --list-langs`.

6. **Re-OCR vs trust the text layer** (for searchable image PDFs): run PyMuPDF and Tesseract on the same document. If character counts diverge by more than 20%, the existing text layer is low-quality — discard it and use the re-OCR result.

**Key trade-off**: Tesseract (~74s/10pp) vs EasyOCR (~379s/10pp) on CPU. Tesseract is the right default for Latin-script documents. EasyOCR is worth the cost only for CTJ (Chinese/Thai/Japanese) or documents where per-word confidence scores are needed.

---

### Problem 4: Tables and Forms

**Symptom A (tables)**: The extracted text contains what was a table on the page, but the cell boundaries are lost — all values appear as a single column of text or a flat sequence of numbers without apparent structure.

**Symptom B (forms)**: The extracted text shows all the field labels ("First Name:", "Social Security Number:") but none of the filled-in values.

**Root cause A (tables)**: Table cells in a PDF are just positioned text elements. Without explicit line geometry (borders), parsers have no way to know that "42" and "67" and "83" in adjacent x-positions belong to a three-column row.

**Root cause B (forms)**: Form field values in a PDF are stored as AcroForm or XFA annotations, separate from the page's text content stream. `page.get_text()` returns only the text content stream — it does not read annotations.

**Solutions for tables:**

1. **Bordered tables → Camelot lattice mode**: If the table has visible grid lines, Camelot's OpenCV line detection finds the exact cell boundaries. This is the most accurate table extraction method available.

2. **Borderless tables → pdfplumber `extract_tables()`**: Uses whitespace gap analysis to infer column boundaries. Works well on financial statements, government data, and any document where columns are separated by consistent whitespace.

3. **Tables in complex layouts → Unstructured**: Hi_res strategy returns `Table` elements as pre-structured text; the table structure is preserved as part of the element metadata.

4. **LaTeX academic tables (arXiv papers)**: Most academic paper tables are borderless LaTeX arrays. In the benchmark, Camelot found 1–2 tables across 17–12 page arXiv papers that did have borders; it found nothing in papers using booktabs-style borderless tables. For these, pdfplumber stream mode or Unstructured is more reliable.

**Solutions for forms:**

1. **Unstructured hi_res** with form-aware element types reads both text layer and annotation-adjacent context. Best overall for interactive form PDFs.

2. **PyMuPDF widget access**: `page.widgets()` returns the form field objects with `.field_value` attribute — the filled value.

   ```python
   for widget in page.widgets():
       print(widget.field_name, ":", widget.field_value)
   ```

3. **pdfplumber near-text matching**: Extract field label positions, then scan for text objects in the adjacent right/below area. Fragile but works when field values bleed into the text layer.

**Recommendation**: For any document type where structured data matters, run both a text parser (for reading order) and a table/form extractor (for structure). The pipeline implements this as primary + table_extractor routing.

---

### Problem 5: Long Documents and Cross-References

**Symptom**: Parsed text from a 200-page technical manual is available, but the context window for chunking is too small to include full sections; references like "see Table 3.4" or "refer to section 6.2" lose their target because sections are in different chunks.

**Root cause**: Standard chunking strategies (fixed-size tokenizer splits) don't respect document structure. Cross-references only make sense within the structural context of the document (section → subsection → figure hierarchy).

**Solutions:**

1. **Section-aware chunking via Unstructured element types** — Unstructured's output includes `Title` and `NarrativeText` elements. Use `Title` elements as section boundary signals. Each chunk spans from one `Title` to the next, keeping all content within a section together.

2. **Hierarchical metadata** — store the section path with each chunk: `{"chunk_id": "doc123:s3.2:p4", "section_path": "Chapter 3 / Section 3.2 / Paragraph 4", "page": 47}`. This allows retrieval to surface not just the chunk but its location in the document hierarchy.

3. **Overlap chunking** — when fixed-size splits are unavoidable, use 10–20% overlap between consecutive chunks to ensure cross-reference context survives at chunk boundaries.

4. **Late chunking** (conceptual) — embed the full section as a single embedding, then retrieve and chunk at query time based on semantic similarity to the question. Avoids the boundary problem entirely at the cost of larger embeddings.

5. **Figure and table ID preservation** — when chunking, include the caption text (which usually contains the table/figure ID) in the same chunk as the surrounding text that references it. Unstructured's `FigureCaption` and `Table` elements help identify these boundaries.

---

### Problem 6: Language, Encoding, and Font Issues

**Symptom A (encoding)**: Specific characters are missing or replaced by garbage (`â€™` instead of `'`; boxes or question marks for Unicode characters). Certain words lose their accents.

**Symptom B (language)**: OCR output looks phonetically correct but uses the wrong script (Latin OCR applied to Greek text produces gibberish transliterations).

**Symptom C (ligatures)**: Word processor ligatures (`ﬁ` for "fi", `ﬂ` for "fl", `ﬀ` for "ff") are not normalised — character count benchmarks show 5–10% variation between parsers that normalise ligatures and those that don't.

**Root causes:**
- PDF font encoding is defined by an internal CMap (character map). If the CMap is incomplete or uses non-standard glyph names, parsers must guess the Unicode equivalents — and they guess differently.
- OCR language models are trained on specific scripts; applying English-trained Tesseract to Cyrillic or Arabic text produces noise.
- OpenType ligature glyphs are not always decomposed to their ASCII equivalents.

**Solutions:**

1. **Parser selection for encoding** — pypdfium2 and PyMuPDF both use mature C-level CMap handling; pypdf (pure Python) struggles more with non-standard CMaps. For documents with known font issues, prefer pypdfium2.

2. **Language detection before OCR** — use `langdetect` or `lingua` to identify the document language, then pass the correct tessdata language code: `lang="deu"` for German, `lang="chi_sim"` for Simplified Chinese.

3. **Ligature normalisation** — `unicodedata.normalize("NFKD", text)` handles many ligatures; for PDF-specific ones, use a custom replacement table:

   ```python
   LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
   text = text.translate(str.maketrans(LIGATURES))
   ```

4. **Multilingual OCR**: EasyOCR supports 80+ languages from a single model and is the better choice over Tesseract for non-Latin scripts. Tesseract requires a separate tessdata pack per language.

5. **Character count discrepancies** — when two parsers return character counts within 10%, the difference is likely ligature normalisation or whitespace handling, not content loss. Only treat discrepancies >20% as meaningful quality differences.

---

### Problem 7: Speed as a Hard Constraint

**Symptom**: The benchmark shows a 4,000× speed gap between the fastest parser (pypdfium2 at 88ms) and the slowest (EasyOCR at 379s) on the same document. For batch processing pipelines, parser choice is not just a quality decision — it can be the difference between a 30-second job and a 20-hour job.

**Root cause**: The speed hierarchy reflects fundamental architectural differences, not implementation quality:
- Native C (PDFium, MuPDF): sub-second text extraction
- Python geometry analysis (pdfminer, pdfplumber): tens of seconds
- System subprocess (Ghostscript, Tesseract): tens of seconds + startup overhead
- Deep learning inference (Unstructured hi_res, EasyOCR, Nougat): minutes on CPU

**Solutions:**

1. **Route by PDF type first** — OCR parsers should never run on born-digital PDFs. Text-layer parsers should never run on image-only PDFs. Correct routing eliminates the largest source of wasted compute.

2. **`max_pages` caps are mandatory for OCR** — without a page cap, EasyOCR on a 200-page scan would run for over 2 hours. The pipeline enforces `max_pages=10` by default. Adjust based on your throughput requirements.

3. **Two-tier strategy** — run a fast baseline first, then invoke quality parsers selectively:
   - Tier 1 (always): pypdfium2 or pymupdf — sub-second, provides character count baseline
   - Tier 2 (conditional): Unstructured — only when reading order matters; Camelot — only when table presence is confirmed; OCR parsers — only for image-only type

4. **Pre-check heuristics for Camelot** — before invoking Camelot (122s+ per document), check for line elements in the PDF metadata. If there are no line-type objects, skip lattice mode entirely and save 2 minutes per document.

5. **Treat speed as a scoring dimension, not an afterthought** — the pipeline's scoring.yaml includes `speed` as one of 12 dimensions (7% weight by default). For production pipelines where throughput is critical, increase this weight.

---

## Part 6 – RAG-Specific Considerations

### Why PDF Quality Affects Retrieval Accuracy

In a Retrieval-Augmented Generation pipeline, the retrievable unit is a text chunk embedded into a vector database. The quality of that embedding depends directly on the quality of the extracted text. Poor parsing has downstream effects:

| Parsing Problem | RAG Impact |
|---|---|
| Wrong reading order (interleaved columns) | Embedding encodes incoherent text; retrieval poor |
| Repeated headers/footers in every chunk | Every chunk shares boilerplate; cosine similarity is artificially inflated across chunks from the same document |
| OCR noise in chunks | Misspelled terms are not retrieved by correctly-spelled queries |
| Flattened table data | Numerical data invisible to semantic search |
| Missing section context | Retrieved chunk lacks hierarchy context; LLM cannot locate it in the document |

### Chunking Strategies by PDF Type

| PDF Type | Recommended Chunking Strategy |
|---|---|
| True Digital | Recursive character chunking by paragraph (strip headers/footers first) |
| Image-Only Scanned | Page-level chunks (OCR provides no structural signals) |
| Searchable Image | Same as true digital if text layer is clean; page-level if re-OCR'd |
| Complex Layout | Element-type chunking via Unstructured: one chunk per `NarrativeText` element under a `Title` boundary |
| Forms | One chunk per form section; include field label + value pairs as key-value text |
| Specialized | Section-level with equation context preserved (use Nougat/Marker output) |

### Element-Type Chunking with Unstructured

Unstructured's element-type output is the most natural source for RAG chunking. Each `NarrativeText` element is a coherent paragraph; `Title` elements mark section boundaries; `Table` elements can be converted to markdown tables for structured retrieval.

```python
from unstructured.partition.pdf import partition_pdf
from unstructured.chunking.title import chunk_by_title

elements = partition_pdf("document.pdf", strategy="hi_res")
chunks = chunk_by_title(elements, max_characters=1000, overlap=200)
for chunk in chunks:
    print(chunk.metadata.section, ":", chunk.text[:100])
```

The pipeline's parse results for Unstructured include the element type list — this can drive a similar chunking implementation on top of existing parsed output.

### Metadata Design for RAG

Every chunk should carry structured metadata alongside its embedding:

```json
{
  "chunk_id": "sha256prefix_arxiv_2501.05032v2:page12:block3",
  "source_pdf": "194dfc73f757_arxiv_2501.05032v2",
  "pdf_type": "complex_layout_pdf",
  "parser": "unstructured",
  "page": 12,
  "section_path": "Related Work / Transformer Architectures",
  "element_type": "NarrativeText",
  "char_count": 743,
  "parse_timestamp": "2026-04-15T13:04:07Z"
}
```

The `pdf_type` field is especially valuable — it allows filtering at query time: "only search chunks from true-digital documents" gives a precision boost in corpora mixing scan quality.

### The `rag_suitability` Scoring Dimension

The pipeline's scoring system includes `rag_suitability` as one of the 12 dimensions. By default it carries only **3% weight** — effectively invisible in the overall score. For a RAG-specific deployment:

1. Open `configs/scoring.yaml`
2. Find the `weights` block
3. Increase `rag_suitability` to `0.20`–`0.30`
4. Reduce `speed` or `size` proportionally (weights must sum to 1.0)
5. Add a type-specific override for `complex_layout_pdf` that boosts `rag_suitability` to `0.35` (correct reading order is critical for that type)

### Four Practical Recipes by PDF Type

#### Recipe 1: Born-Digital Research Papers (Complex Layout) for RAG

```
parse: unstructured (hi_res)
chunk: chunk_by_title() with max_characters=800, overlap=150
metadata: include section_path, page, element_type
filter: discard Header, Footer, PageBreak elements
enrich: run pymupdf on same doc to extract bboxes for figure references
```

#### Recipe 2: Scanned Government Documents for RAG

```
parse: ocrmypdf (for noisy scans) or tesseract (for clean scans)
chunk: page-level (no structural signals available from OCR output)
metadata: include page, source_type="image_only_scanned", confidence (from EasyOCR if used)
filter: discard pages with avg OCR confidence < 0.5
enrich: manual section labelling if document structure is known
```

#### Recipe 3: Financial Reports with Tables for RAG

```
parse (text): pdfplumber (borderless tables + paragraphs)
parse (tables): camelot lattice (bordered tables) — run only if line elements detected
chunk: combine table rows as key-value text; regular paragraphs separately
metadata: include table_id, row_index for table chunks; section_path for text chunks
filter: strip repeated headers/footers via bounding-box exclusion
```

#### Recipe 4: Scientific Papers with Equations for RAG

```
parse: nougat (if GPU available) → mmd format; marker (fallback) → markdown
chunk: section-level (headers denote sections in mmd/markdown)
metadata: include equation_count per chunk (count LaTeX delimiters)
filter: no special filtering needed — nougat output is already structured
note: hallucination risk on degraded pages — cross-check equation regions against pymupdf char count
```

---

## Part 7 – Execution Story

*A narrative reconstruction of what actually happened when this research pipeline ran, drawn from structured log files.*

### Chapter 1: The First Attempt (and Clean Failure)

**2026-04-14, 12:53:59 UTC**

The pipeline's download stage fired for the first time. The arxiv downloader initialised, queried the arXiv API, and got nothing:

```
2026-04-14T12:53:59.323935Z  download_start
2026-04-14T12:53:59.484003Z  downloader_start  source=arxiv
2026-04-14T12:54:03.250059Z  downloader_end    source=arxiv  downloaded_count=0  duration_ms=3765
```

Zero results — a clean, successful empty run. The API returned no matching papers for the initial query configuration. No crash, no half-written files, no broken state. The idempotent design held: events were logged and the pipeline exited cleanly.

This matters: **"graceful no-results" is a first-class outcome**, not an error state.

### Chapter 2: Day 1 — Seven Papers Downloaded

**2026-04-14, 12:55:37 UTC — 89 seconds later**

With an adjusted query, the arxiv downloader returned results. Over the next 7.6 seconds, seven arXiv PDFs arrived:

```
12:55:39.153  download_complete  arxiv  (paper 1)
12:55:39.935  download_complete  arxiv  (paper 2)
...
12:55:42.035  download_complete  arxiv  (paper 7)
12:55:45.150  downloader_end    downloaded_count=7  duration_ms=7563
```

The seven papers that defined the entire benchmark:

| Short ID | arXiv ID | Size | Pages |
|---|---|---|---|
| `194dfc73` | 2501.05032v2 | 1.04 MB | 17 |
| `95dbd349` | 2402.14679v2 | 660 KB | 12 |
| `3392c74d` | 2405.11357v3 | 263 KB | 11 |
| `7027fa5b` | 2403.09676v1 | 211 KB | 7 |
| `8a406e53` | 2407.01505v1 | 709 KB | 16 |
| `b2517cd3` | 2309.02144v1 | ~623 KB | — |
| `50e0c431` | 2312.05434v1 | 5.4 MB | 30+ |

All seven: `complex_layout_pdf` — two-column academic papers with equations, figures, and references. This is the hardest type for reading-order extraction.

### Chapter 3: Day 1 Afternoon — Parser Exploration

**2026-04-14, 12:58 – 16:05 UTC**

Multiple individual parse runs throughout the afternoon. Log scan shows parse durations ranging from 7s to 63s:

```
16:04:15  parse_start
16:05:18  parse_end    chars=63,337  duration=63s
```

A 63-second run returning 63,337 characters — characteristic of Unstructured or pdfplumber on a larger paper. These were individual parser tests, not the full sweep. The pipeline was being calibrated.

### Chapter 4: Day 2 — Expanding the Dataset

**2026-04-15, 12:58:25 UTC**

The download stage ran again across all five sources:

**arxiv** — all seven papers already on disk:
```
download_skipped (×7)  "idempotent re-run: file present"
```

SHA256 checksums matched — no files re-downloaded. The idempotency design paid off immediately.

**internet_archive** — one historical scan:
```
downloader_end  source=internet_archive  downloaded_count=1
```

The pipeline's first `image_only_scanned_pdf` sample — a document with no text layer whatsoever.

**funsd** — three form PDFs:
```
downloader_end  source=funsd  downloaded_count=3  duration_ms=3376
```

FUNSD's `forms_interactive_pdf` test samples, downloaded in 3.4 seconds.

**data_gov** — zero results:
```
downloader_end  source=data_gov  downloaded_count=0  duration_ms=1458
```

Honest placeholder adapter. No crash, no fake data.

**arxiv_specialized** — two more papers, bringing the total catalog to 13+ documents.

**Catalog stage** — ran in under 1 millisecond (local filesystem scan only).

### Chapter 5: The Great Benchmark Sweep

After catalog completion, the ten-parser benchmark ran against the available PDFs.

**PDF 1: `2501.05032v2` (17 pages)**

| Parser | Duration | Characters | Tables |
|---|---|---|---|
| pypdfium2 | **88ms** | 55,036 | 0 |
| pymupdf | 384ms | 54,353 | 0 |
| pypdf | 860ms | 54,232 | 0 |
| pdftext | 1,310ms | 52,232 | 0 |
| pdfplumber | 48,123ms | 49,125 | 0 |
| ocrmypdf | 49,870ms | 34,144 (10pp) | 0 |
| unstructured | 61,430ms | 55,113 | 0 |
| tesseract | 74,296ms | 34,093 (10pp) | 0 |
| camelot | 121,654ms | 160 | **1** |
| easyocr | 378,886ms | 33,934 (10pp) | 0 |

The four text-layer parsers (pypdfium2, pymupdf, pypdf, pdftext) all converged around 52,000–55,000 characters — a strong reliability signal. OCR parsers returned ~34,000 characters (10 of 17 pages — expected with the page cap).

Camelot spent 2 minutes to find one table in 17 pages. Most arXiv tables are borderless LaTeX arrays; Camelot's lattice mode requires visible grid lines.

**PDF 2: `2402.14679v2` (12 pages)**

Camelot found **2 tables** in 184s — the only parser to return structured data. Those 3,978 extracted characters represent meaningful table cell values that no other parser surfaced.

pdfplumber took 143 seconds on 12 pages vs 48 seconds on 17 pages — runtime depends on character density, not page count.

**PDF 3: `2405.11357v3` (11 pages)**

pypdf returned the most characters (59,454) — more than pypdfium2 (56,769) or pymupdf (56,293). On this specific PDF, pypdf resolved font encoding differently, likely expanding ligatures that other parsers left as single characters.

### Chapter 6: Patterns Across the Run

**Speed stratification:**

| Tier | Parsers | Avg Duration | Multiplier vs pypdfium2 |
|---|---|---|---|
| Tier 1 (sub-second) | pypdfium2, pymupdf, pypdf, pdftext | 137ms – 2.3s | 1× – 17× |
| Tier 2 (tens of seconds) | ocrmypdf, pdfplumber, tesseract, unstructured | 43s – 80s | 315× – 583× |
| Tier 3 (minutes) | camelot, easyocr | 123s – 384s | 900× – 2,804× |

EasyOCR is **2,804× slower** than pypdfium2. For a 190-document, 10-parser benchmark, EasyOCR alone without page caps would have taken **~20 hours**.

**Text-layer parsers converge; OCR parsers fall short of the page cap:**
- Born-digital: all four text-layer parsers within 10% of each other → content is reliably extracted
- OCR parsers capped at 10 pages → ~60% of characters of a 17-page doc → expected and correct behaviour

**Camelot: high cost, unique value:**
Camelot is the only parser that returned structured table data. For documents with bordered tables, this unique output justifies the 2+ minute runtime. For documents without, it wastes that time entirely. Trigger Camelot conditionally.

### Chapter 7: Design Decisions Made During Build

From `generation_decisions.log.jsonl`:

| Decision | Reasoning |
|---|---|
| structlog for JSON logging | "JSON logs are easier to filter, query, and centralize than free-text logs." This enabled every timing measurement in the benchmark. |
| pydantic v2 for data schemas | "Built-in validation, serialization to JSON, and ecosystem compatibility." The `ParseResult` schema flowed directly from this. |
| SHA256 checksums on downloads | "Enables idempotent reruns — skip re-downloading if checksum matches." Enabled Day 2's silent skip of all 7 existing files. |
| Placeholder adapters for unavailable sources | "Do not pretend unavailable APIs are fully implemented." data_gov returning 0 PDFs was an honest result, not a failure. |
| Page-level OCR timeout enforcement | The `max_pages=10` cap that bounded EasyOCR to 6 minutes instead of 20+ hours was designed in from the start. |

### Chapter 8: Eight Lessons from the Actual Run

1. **A clean failure is a feature.** The arxiv downloader returning 0 results without corrupting state validated the idempotent design before a single PDF was downloaded.

2. **Downloads are the easy part.** 7 papers in 7.6 seconds. The benchmark sweep for those same 7 papers took hours. Time investment is inversely proportional to pipeline stage.

3. **OCR page caps are not optional in batch processing.** Without `max_pages=10`, EasyOCR alone would have consumed 20+ hours of compute on 7 papers.

4. **EasyOCR is a specialist tool, not a general-purpose batch parser.** At 384s/10pp on CPU, it belongs in KYC or multilingual archive workflows — not in a bulk born-digital benchmark.

5. **Camelot should be triggered, not polled.** Running it on every document regardless of table presence wastes 2 minutes per document. Pre-scan for line elements before invoking lattice mode.

6. **pypdfium2 is the right baseline for born-digital PDFs.** For documents where reading order is not critical (keyword search, tokenisation), it provides Chrome-quality extraction at negligible cost.

7. **Character count convergence is a reliability signal.** When four independent parsers all return within 10% of each other on the same document, that is independent mutual validation of the result.

8. **The structured logs are the product.** Every timing, character count, and table count in the benchmark came from log entries. The log design was an architectural choice — and it paid off as the primary benchmark data source.

---

## Part 8 – Practical Recommendations

### If You Are Extending This Pipeline

1. **Add a new parser by implementing the `BaseParser` interface** — all parsers must return a `ParseResult` pydantic model with `raw_text_full`, `pages`, `tables`, `char_count`, `duration_ms`. Register the class in `parsers/__init__.py`.

2. **Add a new source by implementing a downloader adapter** — downloaders must implement a `download()` method that takes a config dict and returns a list of `DownloadResult` objects. The file path structure (`data/raw/<pdf_type>/<source_id>/`) drives the type classification, so get the directory right.

3. **Segment your benchmarks by PDF type** — a single aggregate score across all types is meaningless. PyMuPDF is first-rank for born-digital and last-rank for image-only scans. Always report per-type.

4. **Re-run the benchmark after library updates** — `pymupdf` and `pypdfium2` release updates that change low-level CMap handling and Unicode normalisation. A library update can silently change character counts by 2–5%.

5. **The `rag_suitability` weight is 3%** — if your use case is RAG, update `configs/scoring.yaml` to give this dimension 20–30% weight, or re-interpret benchmark scores manually.

6. **Enable Marker or Nougat** when GPU is available — for complex-layout or specialized documents, these models produce substantially better output than any CPU-based parser.

7. **Test with `--max-ocr-pages 2` for quick validation runs** — before committing to a full benchmark with OCR parsers on large documents, verify the pipeline routing is correct by capping at 2 pages. Full runs with Tesseract/EasyOCR should be scheduled overnight.

### If You Are Building a Similar Pipeline

8. **Start with PDF type classification** — the biggest mistake in PDF processing is applying one parser to all document types. Build type classification before building parsers.

9. **Two parsers per type is better than one** — a fast baseline (pypdfium2 or pymupdf) plus a quality parser (unstructured for complex layouts, ocrmypdf for scans) covers 90% of use cases. Exotic parsers (Nougat, Camelot) cover the remaining 10%.

10. **Structured logging is mandatory, not optional** — every parse event should include `pdf_id`, `parser`, `duration_ms`, `char_count`, `page_count`. You cannot retrospectively reconstruct performance data from free-text logs.

11. **SHA256 checksums and idempotency from day one** — without these, re-runs corrupt datasets, duplicate rows appear in catalogs, and debugging across runs becomes impossible.

12. **Never equate character count with quality** — pypdf returned the most characters on PDF 3 because it expanded ligatures differently, not because it extracted more content. Design scoring metrics around multiple dimensions.

13. **OCR timeouts are not latency SLAs — they are data correctness controls** — a parse that runs forever on an image-only PDF with max_pages=None is not "extracting more content"; it is accumulating noise across hundreds of pages with no quality bound.

14. **The table problem is often the real problem** — most enterprise PDFs contain structured data in tables that plain text extraction cannot surface. Design your pipeline to handle table extraction as a first-class concern, not an afterthought. Camelot or pdfplumber for tables should be in every production pipeline.

15. **Benchmark before deploying** — every library has edge cases where it fails completely on specific PDFs. Run your actual corpus through the benchmark stage before committing to a parser as production default.

---

## Appendix – Quick Reference Tables

### A. PDF Types × Parser Suitability

| | true_digital | image_scanned | searchable_img | complex_layout | forms | specialized |
|---|---|---|---|---|---|---|
| pypdfium2 | ⭐⭐⭐⭐⭐ | ❌ | ⭐⭐⭐ | ⭐⭐ (order) | ⭐⭐ | ⭐⭐⭐ |
| pymupdf | ⭐⭐⭐⭐⭐ | ❌ | ⭐⭐⭐⭐ | ⭐⭐ (order) | ⭐⭐ | ⭐⭐⭐ |
| pypdf | ⭐⭐⭐ | ❌ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐ |
| pdftext | ⭐⭐⭐⭐ | ❌ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| pdfplumber | ⭐⭐⭐ | ❌ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| unstructured | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| tesseract | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| ocrmypdf | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ |
| easyocr | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ |
| camelot | ⭐⭐⭐⭐⭐ (tables) | ⭐ | ⭐⭐ | ⭐⭐⭐⭐ (tables) | ⭐⭐⭐⭐ | ⭐ |
| tabula | ⭐⭐⭐⭐ (tables) | ⭐ | ⭐⭐ | ⭐⭐⭐ (tables) | ⭐⭐⭐ | ⭐ |
| marker | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| nougat | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |

### B. Problem → Solution Map

| Problem | Primary Solution | Alternative |
|---|---|---|
| Headers/footers everywhere | Unstructured element-type filter | PyMuPDF bbox exclusion (top/bottom 7%) |
| Multi-column reading order | Unstructured hi_res | Marker (GPU) |
| Image-only scan | Tesseract (clean) / OCRmyPDF (noisy) | EasyOCR (multilingual) |
| Bordered table extraction | Camelot (lattice) | — |
| Borderless table extraction | pdfplumber | Camelot (stream) |
| Form field values missing | Unstructured / PyMuPDF `page.widgets()` | pdfplumber near-text |
| OCR noise | OCRmyPDF (deskew+denoise) | Re-render at 400 DPI |
| Ligature/encoding errors | pypdfium2 (Chrome CMap) | unicodedata NFKD normalisation |
| Slow Camelot on every doc | Pre-check for line elements; trigger conditionally | — |
| EasyOCR timeout | max_pages cap in parsers.yaml | Switch to Tesseract |
| LaTeX equations lost | Nougat (GPU) | Marker |
| Poor RAG chunking | Unstructured + `chunk_by_title()` | Section-header-guided splits |

### C. Pipeline Routing by PDF Type

| PDF Type | Primary Parser | Fallback Parser | Table Extractor |
|---|---|---|---|
| true_digital_pdf | pymupdf | pypdf | camelot |
| image_only_scanned_pdf | tesseract | ocrmypdf | — |
| searchable_image_pdf | pymupdf | tesseract | pdfplumber |
| complex_layout_pdf | unstructured | pymupdf | camelot |
| forms_interactive_pdf | unstructured | pdfplumber | tabula |
| specialized_pdf | nougat | marker | — |

### D. Speed Tiers (CPU, 17-page document)

| Tier | Parser(s) | Typical Duration |
|---|---|---|
| Tier 1 — Sub-second | pypdfium2, pymupdf, pypdf, pdftext | 88ms – 2.3s |
| Tier 2 — Tens of seconds | ocrmypdf, pdfplumber, tesseract, unstructured | 37s – 143s |
| Tier 3 — Minutes | camelot, easyocr | 122s – 384s (10pp cap) |

### E. Five Anti-Patterns to Avoid

| Anti-Pattern | Why It Fails | Correct Approach |
|---|---|---|
| One parser for all PDF types | Image-only PDFs return empty for text parsers; born-digital gets OCR errors | Route by type first |
| Equating character count with quality | Different ligature handling causes ±10% variance with no content difference | Score on multiple dimensions |
| OCR on born-digital PDFs | Introduces character errors in text that was already machine-readable | Check for text layer before OCR |
| Ignoring table structure | Tables flattened to text lose row/column relationships | Use Camelot or pdfplumber as dedicated table extractor |
| No page timeout on OCR parsers | EasyOCR without cap = 20+ hours on a small corpus | Always set max_pages in parsers.yaml |

---

*This guide consolidates `EXECUTION_GUIDE.md`, `PDF_TYPES_EXPLAINED.md`, `PDF_LIBRARIES_OVERVIEW.md`, `PDF_LIBRARIES_REALWORLD_USAGE.md`, `PDF_INSIGHTS_AND_BEST_PRACTICES.md`, and `PIPELINE_EXECUTION_STORY.md` into a single reference document.*
