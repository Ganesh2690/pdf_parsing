# PDF Research Pipeline

A production-style, research-grade Python pipeline that downloads diverse PDFs from public sources, parses them with multiple extraction strategies, benchmarks parser quality, and logs every operational decision in structured JSON.

## Overview

This pipeline is designed to:

1. Download PDFs from public sources organized by PDF type.
2. Parse each PDF with multiple libraries (PyMuPDF, pdfplumber, pypdf, Unstructured, Tesseract, OCRmyPDF, marker, Nougat, Camelot, Tabula).
3. Compare extraction outputs and score parser performance per PDF family.
4. Log every action, decision, and metric in structured JSONL logs.
5. Select and recommend the best extraction strategy per PDF type.
6. Maintain full provenance and reproducibility.

## PDF Types Handled

| Folder | Description |
|--------|-------------|
| `true_digital_pdf` | Born-digital PDFs with embedded text |
| `image_only_scanned_pdf` | Scanned page images with no text layer |
| `searchable_image_pdf` | Scan + hidden OCR text layer |
| `complex_layout_pdf` | Multi-column, tables, equations, figures |
| `forms_interactive_pdf` | Form fields, checkboxes, XFA structures |
| `specialized_pdf` | PDF/A, PDF/UA, tagged PDFs |

## Public Sources

- arXiv bulk open-access research papers
- Open RAG Bench (Hugging Face)
- DocLayNet source documents
- Internet Archive OCR/scanned books
- Library of Congress .gov PDF dataset
- Data.gov PDF catalog
- FUNSD / FUNSD+ form datasets
- RVL-CDIP scanned document collection
- KG-RAG business document sets
- FinDER / LegalBench-RAG benchmarks

## Project Structure

```
pdf_research_pipeline/
  README.md
  requirements.txt
  pyproject.toml
  .env.example
  configs/
    sources.yaml
    parsers.yaml
    logging.yaml
    scoring.yaml
    pipeline.yaml
  data/
    raw/
      true_digital_pdf/
      image_only_scanned_pdf/
      searchable_image_pdf/
      complex_layout_pdf/
        arxiv/
        doclaynet/
      forms_interactive_pdf/
        funsd/
      specialized_pdf/
    catalog/
      pdf_catalog.jsonl
      pdf_catalog.csv
    parsed/
      <pdf_type>/
        <pdf_id>/
          <parser_name>/
            raw_text.txt
            pages.json
            blocks.json
            tables/
            images/
            summary.json
  logs/
    run.log.jsonl
    download.log.jsonl
    parser_selection.log.jsonl
    extraction.log.jsonl
    verification.log.jsonl
    errors.log.jsonl
    metrics.log.jsonl
    provenance.log.jsonl
  reports/
    parser_benchmark.csv
    parser_benchmark.json
    parser_recommendations.md
    verification_summary.md
    output_diff_report.md
    failed_files_report.md
  artifacts/
    run_manifest.json
    environment_snapshot.json
    file_lineage.json
  src/
    pdf_research_pipeline/
      ...
  tests/
    ...
```

## Setup

### Prerequisites

- Python 3.11+
- (Optional) Tesseract OCR installed system-wide
- (Optional) Poppler installed (for pdf2image, Camelot)
- (Optional) Java installed (for Tabula)

### Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Or using requirements.txt:

```bash
pip install -r requirements.txt
```

### Environment

Copy `.env.example` to `.env` and fill in any optional API keys:

```bash
cp .env.example .env
```

## Usage

### Download PDFs

```bash
python -m pdf_research_pipeline.cli download --source arxiv --type complex_layout_pdf --limit 20
python -m pdf_research_pipeline.cli download --source internet_archive --type image_only_scanned_pdf --limit 10
python -m pdf_research_pipeline.cli download --source funsd --type forms_interactive_pdf
```

### Build Catalog

```bash
python -m pdf_research_pipeline.cli catalog
```

### Parse PDFs

```bash
python -m pdf_research_pipeline.cli parse --pdf-id <pdf_id> --all-parsers
python -m pdf_research_pipeline.cli parse --pdf-type complex_layout_pdf --parser pymupdf
```

### Run Benchmark

```bash
python -m pdf_research_pipeline.cli benchmark --pdf-type complex_layout_pdf
python -m pdf_research_pipeline.cli benchmark --all
```

### Verify Outputs

```bash
python -m pdf_research_pipeline.cli verify
```

### Get Recommendations

```bash
python -m pdf_research_pipeline.cli recommend
```

### Run Full Pipeline

```bash
python -m pdf_research_pipeline.cli run-all
```

## Logging

All logs are written to `logs/` as JSONL (one JSON object per line). Each log event includes:

- `timestamp`, `run_id`, `event_type`, `stage`
- `pdf_id`, `pdf_type`, `source_name`, `source_url`
- `parser_name`, `library_version`, `config`
- `decision`, `decision_reason`, `observation`
- `metrics`, `status`, `error_type`, `error_message`, `traceback`
- `duration_ms`, `input_hash`, `output_hash`

## Parser Selection Logic

The pipeline does NOT hardcode a single best parser. Instead it:

1. Runs all configured parsers on each PDF.
2. Scores each parser on dimensions: text completeness, heading preservation, paragraph preservation, table extraction, page ordering, OCR quality, coordinate richness, speed, memory usage, structural fidelity, markdown readability, RAG suitability.
3. Computes a weighted score per parser per PDF.
4. Logs a `parser_decision` record with observations and reasoning.
5. Writes recommendations to `reports/parser_recommendations.md`.

## Provenance

Every run records:

- Git commit hash
- Python version and OS
- All package versions
- Config file hashes
- Input and output file hashes
- Command used
- Start and end timestamps

Stored in `artifacts/`.

## Running Tests

```bash
pytest tests/ -v
```

## Configuration

All behavior is controlled by YAML configs in `configs/`. Key options:

- Enable/disable sources and PDF types
- Set download limits per source
- Enable/disable specific parsers
- Adjust parser scoring weights
- Enable OCR, image extraction, table extraction
- Configure log levels

## Example Run Walkthrough

A step-by-step example of running the full pipeline locally from scratch.

### Step 1 — Install dependencies

```bash
pip install -e ".[dev]"
```

### Step 2 — Copy and edit environment file

```bash
cp .env.example .env
# Edit .env to set any API keys (optional for fully public sources)
```

### Step 3 — Review source config

Edit `configs/sources.yaml` to enable the sources and PDF types you want:

```yaml
sources:
  arxiv:
    enabled: true
    limit: 10
    pdf_types: [complex_layout_pdf]
  internet_archive:
    enabled: true
    limit: 5
    pdf_types: [image_only_scanned_pdf]
```

### Step 4 — Download PDFs

```bash
# Download from a single source with type filter and limit
python -m pdf_research_pipeline.cli download --source arxiv --type complex_layout_pdf --limit 5

# Or download from all enabled sources
python -m pdf_research_pipeline.cli download

# Dry run to preview what would be downloaded
python -m pdf_research_pipeline.cli download --dry-run
```

PDFs land in `data/raw/<pdf_type>/<source_name>/`. Catalog entries are appended to `data/catalog/pdf_catalog.jsonl`.

### Step 5 — Inspect the catalog

```bash
# Show catalog summary
python -m pdf_research_pipeline.cli catalog

# Export to CSV for spreadsheet analysis
python -m pdf_research_pipeline.cli catalog --export-csv
```

### Step 6 — Parse with all parsers

```bash
# Run every enabled parser against every catalogued PDF
python -m pdf_research_pipeline.cli parse --all-parsers

# Or parse with a specific parser only
python -m pdf_research_pipeline.cli parse --parser pymupdf

# Or parse a single PDF ID
python -m pdf_research_pipeline.cli parse --pdf-id arxiv_2401_00001
```

Parsed outputs are written to `data/parsed/<pdf_type>/<pdf_id>/<parser_name>/` as `raw_text.txt`, `pages.json`, `blocks.json`, `tables/`, and `summary.json`.

### Step 7 — Benchmark parsers

```bash
# Score all parsers across all PDF types
python -m pdf_research_pipeline.cli benchmark

# Filter to a specific PDF type
python -m pdf_research_pipeline.cli benchmark --pdf-type complex_layout_pdf
```

Reports written to `artifacts/reports/`:
- `parser_benchmark.csv` — per-parser scores
- `parser_benchmark.json` — full metrics
- `parser_recommendations.md` — human-readable summary

### Step 8 — Verify outputs

```bash
python -m pdf_research_pipeline.cli verify
```

Writes to `artifacts/reports/`:
- `verification_summary.md`
- `failed_files_report.md`
- `output_diff_report.md`

### Step 9 — View parser recommendations

```bash
python -m pdf_research_pipeline.cli recommend
```

Prints the top-ranked parser per PDF type with fallback options.

### One-shot: run everything

```bash
# Full pipeline: download → parse → benchmark → verify → recommend
python -m pdf_research_pipeline.cli run-all

# Skip download if PDFs are already present
python -m pdf_research_pipeline.cli run-all --skip-download
```

### Expected log output (abbreviated)

```json
{"event": "pipeline_start", "run_id": "20240115_143022", "level": "info"}
{"event": "download_complete", "source": "arxiv", "count": 5, "level": "info"}
{"event": "parse_complete", "pdf_id": "arxiv_2401_00001", "parser": "pymupdf", "pages": 12, "level": "info"}
{"event": "benchmark_score", "parser": "pymupdf", "pdf_type": "complex_layout_pdf", "score": 0.91, "level": "info"}
{"event": "verification_passed", "pdf_id": "arxiv_2401_00001", "parser": "pymupdf", "level": "info"}
{"event": "recommendation", "pdf_type": "complex_layout_pdf", "primary": "pymupdf", "fallback": "pdfplumber", "level": "info"}
{"event": "pipeline_complete", "run_id": "20240115_143022", "elapsed_s": 142.3, "level": "info"}
```

All structured logs are written to `logs/` as JSONL files — see the **Logging** section for details.

---

## Legal and Safety

- Only public-domain or open-access sources are used.
- No credentials or sensitive data are logged.
- Placeholder adapters are provided for sources that require non-trivial access patterns.
