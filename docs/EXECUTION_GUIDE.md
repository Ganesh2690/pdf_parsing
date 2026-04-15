# PDF Research Pipeline — Execution Guide

A complete runbook for setting up and running the pipeline end-to-end: downloading PDFs, cataloguing them, parsing with up to 13 libraries, benchmarking quality, verifying output, and generating reports.

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Installation](#2-installation)
3. [Configuration Overview](#3-configuration-overview)
4. [Project Folder Structure](#4-project-folder-structure)
5. [Step-by-Step Execution](#5-step-by-step-execution)
6. [Running Everything at Once](#6-running-everything-at-once)
7. [Reading the Output](#7-reading-the-output)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. System Requirements

| Component | Required | Recommended | Notes |
|---|---|---|---|
| Python | ≥ 3.11 | 3.12.x | Tested on 3.12.10 |
| Operating System | Linux / macOS / Windows | — | Windows needs `cmd`-style Tesseract path |
| RAM | 4 GB | 16 GB | EasyOCR requires ~2 GB per worker |
| Disk | 2 GB free | 10 GB | Parsed outputs can be large |
| Tesseract OCR | Optional | 5.x | Required for `tesseract` and `ocrmypdf` parsers |
| Java JRE | Optional | 11+ | Required for `tabula-py` table extraction |
| Poppler | Optional | 23.x | Required for `pdf2image`; **not needed** if only using PyMuPDF for rendering |
| GPU | Not required | CUDA 11+ | EasyOCR is faster with GPU but works on CPU |

### Tesseract Installation

- **Windows**: Download installer from [UB Mannheim Tesseract releases](https://github.com/UB-Mannheim/tesseract/wiki). Install to `C:\Users\<you>\AppData\Local\Programs\Tesseract-OCR\` and add to `PATH`, or set `TESSERACT_CMD` environment variable.
- **macOS**: `brew install tesseract`
- **Linux (Debian/Ubuntu)**: `sudo apt-get install tesseract-ocr`

Verify: `tesseract --version`

### Java (optional, for Tabula)

- **Windows**: Download JRE from [Adoptium](https://adoptium.net/) and ensure `java` is on `PATH`.
- **macOS**: `brew install openjdk`
- **Linux**: `sudo apt-get install default-jre`

Verify: `java -version`

---

## 2. Installation

### Clone or Locate the Project

```
pdf_research_pipeline/      ← project root (all commands run from here)
  src/
  configs/
  data/
  tests/
  pyproject.toml
```

### Create and Activate a Virtual Environment

```bash
# Create
python -m venv .venv

# Activate (Linux/macOS)
source .venv/bin/activate

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Activate (Windows cmd)
.venv\Scripts\activate.bat
```

### Install the Package

```bash
# Install with all development extras
pip install -e ".[dev]"

# Production install (no test tools)
pip install -e .
```

The entry-point `pdf-pipeline` is now available:

```bash
pdf-pipeline --help
```

### Environment Variables (optional)

Create a `.env` file in the project root for any overrides:

```dotenv
# Override Tesseract binary location (Windows example)
TESSERACT_CMD=C:\Users\you\AppData\Local\Programs\Tesseract-OCR\tesseract.exe

# Limit parallel workers
MAX_WORKERS=4
```

---

## 3. Configuration Overview

All configuration lives in `configs/`. The pipeline reads these YAML files at startup.

### `configs/sources.yaml` — Download Targets

Defines which data sources to pull PDFs from and how many per source.

```yaml
sources:
  arxiv:
    enabled: true
    pdf_type: complex_layout_pdf
    max_pdfs: 10        # how many to download
    query: "large language models"
    categories: ["cs.CL", "cs.AI"]
```

Key fields per source:
- `enabled`: set to `false` to skip entirely
- `pdf_type`: which taxonomy bucket these PDFs belong to
- `max_pdfs`: cap on downloads (useful to limit during development)

Currently enabled sources: `arxiv`, `internet_archive`, `funsd`, `data_gov`, `arxiv_specialized`.

### `configs/parsers.yaml` — Parser Roster

Lists all 13 parsers and their per-parser settings.

```yaml
parsers:
  pymupdf:
    enabled: true
    extract_tables: false
    timeout_seconds: 120

  tesseract:
    enabled: true
    max_pages: 10           # cap OCR pages for speed
    dpi: 300
    lang: eng
```

Key fields:
- `enabled`: disable a parser without removing its code
- `max_pages`: for OCR parsers (tesseract, easyocr, ocrmypdf) — avoids hour-long runs on large PDFs
- `timeout_seconds`: hard wall-clock timeout per PDF
- `pdf_type_hints.primary` / `fallback` / `table_extractor`: routing hints for the benchmark

### `configs/pipeline.yaml` — Orchestration

Controls how the pipeline stages connect and run.

```yaml
pipeline:
  stages: [download, catalog, parse, benchmark, verify, report]
  parallel_downloads: 4
  parallel_parsers: 2
  stop_on_error: false
  output_dir: data/parsed
```

### `configs/scoring.yaml` — Benchmark Weights

12 quality dimensions, each with a weight (must sum to 1.0):

| Dimension | Default Weight | Boosted For |
|---|---|---|
| text_completeness | 0.20 | — |
| heading_preservation | 0.10 | — |
| paragraph_preservation | 0.10 | — |
| table_extraction_quality | 0.10 | — |
| page_ordering_quality | 0.10 | — |
| ocr_quality | 0.08 | `image_only_scanned_pdf` → 0.35 |
| coordinate_richness | 0.07 | `complex_layout_pdf` → 0.10 |
| speed | 0.05 | — |
| memory_usage | 0.05 | — |
| structural_fidelity | 0.08 | `complex_layout_pdf` → 0.12 |
| markdown_readability | 0.04 | — |
| rag_suitability | 0.03 | — |

### `configs/logging.yaml` — Log Routing

Eight structured JSONL log files under `logs/`:

| File | Purpose |
|---|---|
| `run.log.jsonl` | All events from every pipeline stage |
| `download.log.jsonl` | Download start/end/skip/error events |
| `extraction.log.jsonl` | Per-PDF per-parser extraction results |
| `errors.log.jsonl` | Any error or exception |
| `metrics.log.jsonl` | Timing and quality metric values |
| `parser_selection.log.jsonl` | Which parser was chosen and why |
| `provenance.log.jsonl` | File hashes and lineage |
| `verification.log.jsonl` | Verification pass/fail results |

---

## 4. Project Folder Structure

```
pdf_research_pipeline/
│
├── configs/                  ← YAML configuration files
│   ├── sources.yaml
│   ├── parsers.yaml
│   ├── pipeline.yaml
│   ├── scoring.yaml
│   └── logging.yaml
│
├── data/
│   ├── raw/                  ← Downloaded PDFs (organized by type and source)
│   │   ├── complex_layout_pdf/arxiv/
│   │   ├── image_only_scanned_pdf/internet_archive/
│   │   ├── forms_interactive_pdf/funsd/
│   │   ├── true_digital_pdf/
│   │   ├── searchable_image_pdf/
│   │   └── specialized_pdf/
│   │
│   ├── catalog/
│   │   └── pdf_catalog.jsonl ← Master record of all downloaded PDFs
│   │
│   ├── parsed/               ← Extraction outputs
│   │   └── <pdf_type>/<pdf_id>/<parser_name>/
│   │       ├── result.json   ← Full ParseResult
│   │       └── text.txt      ← Extracted plain text
│   │
│   └── text_exports/         ← Human-readable text exports
│
├── logs/                     ← Structured JSONL logs (one per category)
├── reports/                  ← Generated HTML/Markdown benchmark reports
├── artifacts/                ← Run manifests and environment snapshots
│
├── src/pdf_research_pipeline/
│   ├── cli.py                ← Typer CLI (main entry point)
│   ├── config.py             ← Config loading and validation
│   ├── logging_utils.py      ← structlog setup
│   ├── provenance.py         ← Hash tracking
│   ├── parsers/              ← 13 parser adapters
│   ├── downloader/           ← Source-specific downloaders
│   ├── benchmark/            ← Scoring and comparison logic
│   └── verification/         ← Output integrity checks
│
└── tests/                    ← pytest test suite
```

---

## 5. Step-by-Step Execution

Each stage below corresponds to a CLI command. Run them from the project root (where `pyproject.toml` lives).

### Stage 1 — Download PDFs

```bash
pdf-pipeline download
```

- Reads `configs/sources.yaml` for which sources to query
- Downloads up to `max_pdfs` per enabled source
- Saves raw PDFs under `data/raw/<pdf_type>/<source>/`
- Writes SHA256 checksums and metadata to `logs/download.log.jsonl`
- Skips files already present (idempotent re-run safe)

Expected output (example):

```
Downloading: arxiv ... 7 PDFs fetched in 7.6s
Downloading: funsd  ... 5 PDFs fetched in 2.1s
Download complete. 12 total PDFs saved.
```

**Common flags:**

```bash
# Download only from one source
pdf-pipeline download --source arxiv

# Dry run (show what would be downloaded)
pdf-pipeline download --dry-run
```

---

### Stage 2 — Build the Catalog

```bash
pdf-pipeline catalog
```

- Scans all files under `data/raw/`
- Detects PDF type from directory structure and metadata
- Counts pages, records file size, language, and SHA256
- Writes/updates `data/catalog/pdf_catalog.jsonl`

Each catalog entry looks like:

```json
{
  "pdf_id": "194dfc73f757",
  "local_path": "data/raw/complex_layout_pdf/arxiv/2501.05032v2.pdf",
  "pdf_type": "complex_layout_pdf",
  "pages": 17,
  "file_size_bytes": 1040532,
  "sha256": "194dfc73f757..."
}
```

---

### Stage 3 — Parse (Extract Text)

```bash
pdf-pipeline parse
```

- Reads every entry in `data/catalog/pdf_catalog.jsonl`
- Runs each enabled parser (from `configs/parsers.yaml`) against each PDF
- Saves outputs to `data/parsed/<pdf_type>/<pdf_id>/<parser_name>/result.json`
- Logs timing, character counts, and any errors to `logs/extraction.log.jsonl`

**Parse a single PDF against all parsers:**

```bash
pdf-pipeline parse --pdf-id 194dfc73f757
```

**Parse all PDFs with a specific parser only:**

```bash
pdf-pipeline parse --parser pymupdf
```

**Limit OCR pages (overrides config):**

```bash
pdf-pipeline parse --max-ocr-pages 5
```

Notable timing expectations on a modern laptop (CPU only):

| Parser | Typical Duration (17-page arXiv PDF) |
|---|---|
| pypdfium2 | ~90ms |
| pymupdf | ~400ms |
| pypdf | ~900ms |
| pdftext | ~1.3s |
| pdfplumber | ~48s |
| ocrmypdf | ~50s (10 pages) |
| tesseract | ~74s (10 pages) |
| unstructured | ~61s |
| easyocr | ~379s (10 pages) |
| camelot | ~122s |

---

### Stage 4 — Benchmark

```bash
pdf-pipeline benchmark
```

- Scores every parser output against the 12 quality dimensions in `configs/scoring.yaml`
- Weights are automatically adjusted per PDF type (e.g., `ocr_quality` weighted 4× higher for scanned PDFs)
- Outputs `artifacts/reports/accuracy_report.html` — a self-contained interactive HTML report

---

### Stage 5 — Verify

```bash
pdf-pipeline verify
```

- Checks all parsed outputs for common failure modes:
  - `EMPTY_TEXT`: parser returned 0 characters
  - `TRUNCATED_OUTPUT`: text appears cut off before end of document
  - `CHECKSUM_MISMATCH`: output hash changed since last run
  - `TIMEOUT_EXCEEDED`: parser hit the wall-clock timeout
- Results written to `logs/verification.log.jsonl`

---

### Stage 6 — Recommend

```bash
pdf-pipeline recommend
```

- Reads benchmark scores and verification results
- Produces a ranked recommendation: "for this PDF type, use parser X as primary, Y as fallback"
- Outputs a Markdown summary table

---

## 6. Running Everything at Once

```bash
pdf-pipeline run-all
```

Executes all stages in sequence: download → catalog → parse → benchmark → verify → recommend.

Configure parallelism in `configs/pipeline.yaml`:

```yaml
pipeline:
  parallel_downloads: 4   # concurrent PDF downloads
  parallel_parsers: 2     # concurrent parser workers (careful with OCR memory)
```

> **Tip**: On a machine with 16 GB RAM, `parallel_parsers: 2` is safe. With EasyOCR enabled, keep it at 1 to avoid OOM.

---

## 7. Reading the Output

### HTML Benchmark Report

Open `artifacts/reports/accuracy_report.html` in any browser. It contains:

- **Overview tab**: Total PDFs, parsers run, average scores
- **Benchmark tab**: Per-parser per-PDF scores across all 12 dimensions, colour-coded
- **Verification tab**: Any warnings or failures flagged during verify stage

### Structured Logs

All logs are JSONL (one JSON object per line). Use `jq` or PowerShell to query:

```bash
# Show all extraction errors
cat logs/errors.log.jsonl | jq .

# Show timing for all pymupdf runs
cat logs/extraction.log.jsonl | jq 'select(.parser_name == "pymupdf") | {pdf_id, duration_ms}'

# PowerShell equivalent
Get-Content logs\extraction.log.jsonl | ConvertFrom-Json | Where-Object parser_name -eq pymupdf | Select-Object pdf_id, duration_ms
```

### Parsed Text Files

Each parser's extracted text is at:

```
data/parsed/<pdf_type>/<pdf_id>/<parser_name>/text.txt
```

Compare outputs side by side:

```bash
diff data/parsed/complex_layout_pdf/194dfc73f757/pymupdf/text.txt \
     data/parsed/complex_layout_pdf/194dfc73f757/unstructured/text.txt
```

---

## 8. Troubleshooting

### `TesseractNotFoundError`

**Symptom**: `pytesseract.pytesseract.TesseractNotFoundError: tesseract is not installed`

**Fix**:
1. Install Tesseract (see Section 1)
2. Set the `TESSERACT_CMD` environment variable, or add Tesseract to system `PATH`
3. On Windows, the parsers auto-search common install locations; confirm Tesseract is at `C:\Users\<you>\AppData\Local\Programs\Tesseract-OCR\tesseract.exe`

### `java.lang.UnsupportedClassVersionError` or Tabula Fails

**Symptom**: `tabula.errors.CSVParseError` or JVM error

**Fix**: Install Java 11+ and ensure `java` is on `PATH`. If Java is unavailable, disable tabula in `configs/parsers.yaml`:

```yaml
parsers:
  tabula:
    enabled: false
```

### EasyOCR Takes Hours

**Symptom**: Extraction for a single PDF runs for 10+ minutes

**Fix**: Cap OCR pages in `configs/parsers.yaml`:

```yaml
parsers:
  easyocr:
    max_pages: 5
```

Or use Tesseract instead, which is ~5× faster on CPU.

### `EMPTY_TEXT` in Verification

**Symptom**: `verification.log.jsonl` shows `EMPTY_TEXT` for multiple parsers on the same PDF

**Likely cause**: The PDF is image-only (scanned) and was run through a text-only parser (PyMuPDF, pypdf, etc.) that cannot OCR. This is expected — those parsers will always return empty text for scanned PDFs. Use Tesseract or EasyOCR for those.

### Catalog Shows Wrong PDF Type

**Symptom**: A scanned PDF is catalogued as `true_digital_pdf`

**Fix**: Check the source directory. Catalog detection is primarily based on directory path (`data/raw/<pdf_type>/`). If you placed a PDF in the wrong folder, move it and re-run `pdf-pipeline catalog`.

### Out of Memory During Parsing

**Symptom**: Worker process killed, or `MemoryError`

**Fix**:
1. Reduce `parallel_parsers` to 1 in `configs/pipeline.yaml`
2. Reduce `max_pages` for OCR parsers
3. Disable EasyOCR and use Tesseract as the OCR fallback

### Re-running After a Failure

All stages are idempotent:
- `download`: skips existing files by SHA256 check
- `parse`: skips PDFs that already have a `result.json` for the parser
- `catalog`: rewrites from current `data/raw/` contents

Simply re-run the failing stage after fixing the issue.
