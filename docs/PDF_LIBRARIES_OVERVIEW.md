# PDF Libraries Overview

A detailed technical profile of every library integrated into this pipeline. Each section covers architecture, strengths, limitations, and exactly how the pipeline adapter uses the library.

---

## Library Index

| # | Library | Role | Installed | PyPI Package |
|---|---|---|---|---|
| 1 | [PyMuPDF](#1-pymupdf-fitz) | Text + structure extraction | ✅ | `pymupdf` |
| 2 | [pdfplumber](#2-pdfplumber) | Text + tables | ✅ | `pdfplumber` |
| 3 | [pypdf](#3-pypdf) | Lightweight text extraction | ✅ | `pypdf` |
| 4 | [pypdfium2](#4-pypdfium2) | Fastest text baseline | ✅ | `pypdfium2` |
| 5 | [pdftext](#5-pdftext) | Fast PDFium character extraction | ✅ | `pdftext` |
| 6 | [Unstructured](#6-unstructured) | Layout-aware element extraction | ✅ | `unstructured[pdf]` |
| 7 | [EasyOCR](#7-easyocr) | Deep-learning OCR (no Java/C deps) | ✅ | `easyocr` |
| 8 | [Tesseract](#8-tesseract--pytesseract) | Production OCR engine | ✅ | `pytesseract` |
| 9 | [OCRmyPDF](#9-ocrmypdf) | Searchable PDF creator + extractor | ✅ | `ocrmypdf` |
| 10 | [Camelot](#10-camelot) | PDF table extraction | ✅ | `camelot-py[cv]` |
| 11 | [Tabula](#11-tabula-py) | Java-based table extraction | Optional | `tabula-py` |
| 12 | [Marker](#12-marker) | ML layout-aware Markdown | Optional | `marker-pdf` |
| 13 | [Nougat](#13-nougat) | Scientific paper ML parser | Optional | `nougat-ocr` |

---

## 1. PyMuPDF (`fitz`)

**Version in project**: 1.27.2.2 (`pymupdf>=1.23.0`)

### What It Is

PyMuPDF is Python bindings for MuPDF — a lightweight, high-performance PDF and XPS rendering library written in C. It is maintained by Artifex (the company behind Ghostscript). The `fitz` module name is historical (MuPDF was forked from a codebase called Fitz).

### Architecture

```
Python (fitz) → MuPDF C library → PDF stream parser
                                 → Text extraction (Unicode)
                                 → Page renderer (raster image)
                                 → Font subsystem
```

PyMuPDF operates directly on the PDF stream without spawning subprocesses. It uses MuPDF's own content-stream interpreter to locate text objects and extract Unicode characters with precise bounding boxes.

### How the Pipeline Uses It

The `PyMuPDFParser` iterates pages and calls `page.get_text("blocks")` to retrieve text in rectangular block order, and `page.get_text("words")` for word-level bounding boxes. Tables are detected by block adjacency heuristics (not dedicated table logic — use Camelot for real table extraction).

Key output fields:
- `raw_text_full`: full page text joined across all text blocks
- `pages[n].blocks`: list of `{text, bbox, block_no}` per page
- `pages[n].words`: word-level `{text, x0, y0, x1, y1}` bounding boxes
- `coordinate_richness` score: high, because every word has a precise bbox

### Strengths

- **Fastest text extractor** for born-digital PDFs — typically 200–500ms for a 20-page paper
- **Rich coordinate data** — word and block bounding boxes are pixel-accurate
- **No external dependencies** — pure Python + compiled C; no Java, no system packages needed on all platforms
- Also serves as the **rendering backend** for Tesseract (renders pages to PIL images for OCR)
- Handles encrypted PDFs, broken streams, and unusual encodings gracefully

### Limitations

- **Text order** on complex layouts can be wrong — MuPDF processes text objects in PDF-stream order, not visual reading order; two-column academic papers often interleave columns
- **No table understanding** — extracts text from table cells but does not identify the table structure
- **Ligature handling** varies — some fonts use ligature glyphs (ff, fi) that map to private-use Unicode
- **No form field extraction** — AcroForm field values require separate handling

### Best-Suited PDF Types

| PDF Type | Suitability |
|---|---|
| True Digital | ⭐⭐⭐⭐⭐ Excellent |
| Searchable Image | ⭐⭐⭐ Good (extracts existing OCR layer) |
| Complex Layout | ⭐⭐⭐ Good text, poor reading order |
| Forms | ⭐⭐ Extracts labels, misses field values |
| Image-Only Scanned | ⭐ Returns empty text |
| Specialized | ⭐⭐⭐ Good baseline |

---

## 2. pdfplumber

**Version in project**: 0.11.9 (`pdfplumber>=0.10.0`)

### What It Is

pdfplumber is built on top of pdfminer.six and adds a much friendlier API for extracting structured content. It was created by Jeremy Singer-Vine (BuzzFeed News Data Team) specifically for data journalism use cases — extracting tables and typed data from government PDFs.

### Architecture

```
Python (pdfplumber) → pdfminer.six → PDF parser (pure Python)
                                    → CMap / font decoding
                                    → Character-level position tracking
         ↓
   Table detection (bbox clustering)
   Word/line reconstruction (char groupings)
```

pdfminer.six does the low-level PDF parsing; pdfplumber adds a geometry layer that groups characters into words and words into cells using configurable snap tolerances.

### How the Pipeline Uses It

The `PDFPlumberParser` opens the PDF and iterates pages. For each page it calls:
- `page.extract_words()` → word-level positions with bounding boxes
- `page.extract_tables()` → 2D list of lists (table cell content)
- `page.chars` → individual character objects for fine-grained analysis

Words are joined to form the page text. Tables are stored as `ParseResult.tables` with row/column structure.

### Strengths

- **Strong table extraction** for text-based tables (without visible borders or with partial borders) — uses spacing-based column detection
- **Excellent reading order** for single-column text; character-level grouping is careful
- **Word and character bounding boxes** — every character has `x0, y0, x1, y1, text, fontname, size`
- **Tolerances are tunable** — `x_tolerance`, `y_tolerance`, `intersection_tolerance` control word grouping
- **Reliable for data journalism** PDFs: government tabular reports, census data, financial filings

### Limitations

- **Slow** on large or complex PDFs — pure Python parsing is CPU-intensive; 48s on a 17-page arXiv paper vs. 400ms for PyMuPDF
- **Multi-column layout confusion** — like PyMuPDF, reading order on 2-column papers can interleave columns
- **Deep pdfminer dependency** means it can be brittle for unusual PDF encodings
- **Table detection is heuristic** — fails on borderless tables with unusual spacing

### Best-Suited PDF Types

| PDF Type | Suitability |
|---|---|
| True Digital | ⭐⭐⭐⭐⭐ Excellent for tabular data |
| Forms | ⭐⭐⭐⭐ Good spatial positioning |
| Complex Layout | ⭐⭐⭐ Good but slow |
| Searchable Image | ⭐⭐ Depends on OCR layer quality |
| Image-Only Scanned | ⭐ No text layer |
| Specialized | ⭐⭐⭐ Good baseline |

---

## 3. pypdf

**Version in project**: 5.9.0 (`pypdf>=4.0.0`)

### What It Is

pypdf (formerly PyPDF2, before that pyPdf) is a pure-Python PDF library that handles reading, writing, merging, splitting, and encrypting PDFs. The text extraction functionality is deliberately minimal — it focuses on PDF manipulation rather than high-quality text mining. It was originally created by Mathieu Fenniak in 2005 and is now maintained by Martin Thoma.

### Architecture

```
Python (pypdf) → Pure-Python PDF parser
              → Cross-reference table reader
              → Content-stream text operator parser (/Tj, /TJ, /T*)
              → Font mapping (best-effort Unicode)
```

pypdf implements just enough of the PDF specification to decode text operators from content streams. It handles most common font encodings but does not implement a full CMap renderer like pdfminer.

### How the Pipeline Uses It

The `PyPDFParser` opens the PDF and calls `page.extract_text()` for each page. This is the simplest possible extraction path. No bounding boxes, no table detection, no word-level data — just a string per page.

```python
reader = PdfReader(pdf_path)
for page in reader.pages:
    text = page.extract_text()
```

### Strengths

- **Zero system dependencies** — pure Python, runs anywhere
- **Fast** — ~900ms for a 17-page arXiv paper (simple content-stream parse)
- **Excellent for simple manipulation** — merge, split, extract pages from PDFs
- **Handles encryption** — decrypts owner/user password PDFs when password provided
- **Lightweight** — minimal dependency footprint; good for serverless or embedded environments

### Limitations

- **Text quality varies widely** — some PDFs produce perfect output; others produce garbled text due to font encoding issues
- **No bounding boxes** — no spatial information in output; no tables
- **No reading order correction** — same stream-order issue as PyMuPDF
- **Older foundation** — the codebase carries legacy design decisions from 2005
- **Not suitable as a primary research parser** — use as a compatibility baseline, not for quality benchmarking

### Best-Suited PDF Types

| PDF Type | Suitability |
|---|---|
| True Digital (simple) | ⭐⭐⭐⭐ Good baseline |
| True Digital (complex fonts) | ⭐⭐ May garble text |
| Image-Only Scanned | ⭐ No text layer |
| All other types | ⭐⭐ Baseline only |

---

## 4. pypdfium2

**Version in project**: 4.30.0 (`pypdfium2>=4.20.0`)

### What It Is

pypdfium2 provides Python bindings directly to **PDFium** — the same PDF rendering engine used in Google Chrome and Chromium. PDFium is written in C++ and maintained by Google. pypdfium2 auto-downloads pre-compiled binaries for each platform (no manual PDFium install needed).

### Architecture

```
Python (pypdfium2) → PDFium C++ engine (Google Chrome's PDF renderer)
                  → FPDF_LoadDocument → per-page text extraction
                  → Text object coordinate queries
```

PDFium handles the full PDF specification including complex font subsetting, ligature handling, and encoding edge cases that trip up pure-Python parsers.

### How the Pipeline Uses It

The `PyPDFium2Parser` loads the document and iterates pages, calling `page.get_textpage()` to get a text page object, then `.get_text_range()` for full page text. The pipeline uses this as the **fastest high-accuracy baseline** for born-digital PDFs.

### Strengths

- **Fastest non-OCR parser** — ~88ms for a 17-page paper (PDFium is highly optimised C++)
- **High text accuracy** — same engine as Chrome; handles encoding edge cases reliably
- **No system package dependencies** — binaries bundled in the wheel
- **Good Unicode handling** — PDFium's full character map support catches ligatures and special characters
- **Reliable API** — stable bindings, well-maintained

### Limitations

- **No bounding boxes in the basic API** — text page extraction gives text without spatial data (different from PyMuPDF's per-word bbox API)
- **No table detection** — pure text stream
- **No form field reading** — interactive elements ignored
- **Wheel size is large** (~50–100 MB depending on platform)

### Best-Suited PDF Types

| PDF Type | Suitability |
|---|---|
| True Digital | ⭐⭐⭐⭐⭐ Excellent (fastest) |
| Searchable Image | ⭐⭐⭐ Good |
| Complex Layout | ⭐⭐⭐ Fast baseline |
| Image-Only Scanned | ⭐ No text layer |

---

## 5. pdftext

**Version in project**: 0.6.3 (`pdftext>=0.5.0`)

### What It Is

pdftext is a newer library (by Vik Paruchuri, author of Marker) that provides a fast, character-level extraction layer on top of PDFium. It was designed as the text extraction backend for Marker and is optimised for speed and character-position accuracy.

### Architecture

```
Python (pdftext) → PDFium (via ctypes/cffi)
               → Character-level extraction with positions
               → Reading-order reconstruction (column detection heuristics)
               → Block and line grouping
```

Unlike pypdfium2's basic `get_text_range()`, pdftext extracts individual characters with bounding boxes and then applies heuristics to reconstruct reading order — making it more reading-order-aware than raw PDFium extraction.

### How the Pipeline Uses It

The `PDFTextParser` calls the high-level extraction function and collects character-level data per page. Output includes full text with attempted reading-order correction.

### Strengths

- **Fast** (~1.3s for 17-page paper) — much faster than pdfplumber
- **Reading-order awareness** — applies span/block heuristics to reorder characters
- **Character bounding boxes** — enables fine-grained position analysis
- **Designed for Marker** — high compatibility with the Marker ML pipeline

### Limitations

- **Newer library** — less battle-tested than PyMuPDF or pdfplumber
- **No table detection** — character-level only
- **Reading-order heuristics not perfect** — complex layouts still confuse it
- **Less community documentation** compared to the major libraries

### Best-Suited PDF Types

| PDF Type | Suitability |
|---|---|
| True Digital | ⭐⭐⭐⭐⭐ Fast + reading order |
| Complex Layout | ⭐⭐⭐ Better reading order than raw PDFium |
| image-only / Forms | ⭐ No OCR / limited form support |

---

## 6. Unstructured

**Version in project**: 0.18.32 (`unstructured[pdf]>=0.12.0`)

### What It Is

Unstructured (by Unstructured.io) is a document ETL library designed specifically for pre-processing documents for LLM / RAG pipelines. It goes beyond text extraction — it classifies content into typed elements: `Title`, `NarrativeText`, `ListItem`, `Table`, `Image`, `Header`, `Footer`, and others. The PDF backend can use either fast (pymupdf-powered), hi_res (layout analysis with a neural model), or ocr_only strategies.

### Architecture

```
Python (unstructured) → Strategy selection
  fast:    → PyMuPDF for text → element type classifier
  hi_res:  → PDF renderer → layout model (YOLOv8 / DiT) → element detection
                          → Tesseract OCR for images within elements
  ocr_only:→ PDF → images → Tesseract OCR
```

In `hi_res` mode, a document image analysis (DIA) model detects regions (text blocks, tables, figures) and assigns semantic types. This is the most accurate mode but also the slowest.

### How the Pipeline Uses It

The `UnstructuredParser` supports three strategies, configured per-run. The default strategy is `fast`. The adapter:
1. Calls `partition_pdf(strategy=strategy)` → list of `Element` objects
2. Groups elements by type into `tables`, `headings`, `narrative_blocks`
3. Assembles `raw_text_full` from all text-bearing elements

Key output: elements have `.text`, `.metadata.page_number`, `.metadata.coordinates`, and `.category` fields.

### Strengths

- **Semantic element types** — outputs go beyond text strings to typed document elements, ideal for RAG chunk creation
- **Table extraction in hi_res mode** — uses layout model to find tables and extract cell content
- **Form field awareness** — can extract field labels and values from forms
- **Best reading-order accuracy** for complex layouts in hi_res mode
- **Pluggable backends** — can swap OCR engines and layout models

### Limitations

- **Slow** — `hi_res` mode is 60s for a 17-page PDF; `fast` mode is faster but loses layout context
- **Large dependency footprint** — requires `unstructured[pdf]` which pulls in many optional packages
- **Inconsistent outputs** across versions — the library evolves quickly and minor version changes can alter element classification
- **Memory hungry in hi_res** — layout models require 2–4 GB RAM
- **Not suitable for bulk processing** at scale without API or distributed setup

### Best-Suited PDF Types

| PDF Type | Suitability |
|---|---|
| Complex Layout | ⭐⭐⭐⭐⭐ Best reading order |
| Forms | ⭐⭐⭐⭐ Element-level form extraction |
| True Digital | ⭐⭐⭐⭐ Good with fast strategy |
| Specialized | ⭐⭐⭐⭐ Element types help RAG |
| Image-Only Scanned | ⭐⭐⭐ via ocr_only strategy |

---

## 7. EasyOCR

**Version in project**: 1.7.2 (`easyocr>=1.7.0`)

### What It Is

EasyOCR is a deep-learning OCR library that uses a two-stage pipeline: CRAFT (Character-Region Awareness For Text detection) for text region detection, and CRNN (Convolutional Recurrent Neural Network) for character recognition. It supports 80+ languages and requires no system-level dependencies beyond PyTorch.

### Architecture

```
Python (easyocr) → CRAFT detector (PyTorch) → text region bounding boxes
               → CRNN recogniser (PyTorch) → character sequences per region
               → Post-processing: sort regions by position → joined text
```

Models are downloaded on first use and cached in `~/.EasyOCR/`. CPU inference works but is slow; GPU (CUDA) reduces recognition time by 5–10×.

### How the Pipeline Uses It

The `EasyOCRParser` creates a `Reader` instance once and caches it across pages (model loading takes ~30s on first call). For each page it:
1. Renders the page to a PIL image using PyMuPDF at 150 dpi
2. Passes the image to `reader.readtext()` → list of `(bbox, text, confidence)` tuples
3. Sorts detections top-to-bottom, left-to-right
4. Respects `max_pages` limit (default 10) to avoid hour-long runs

### Strengths

- **No system OCR dependencies** — pure Python + PyTorch; no Tesseract, no Java
- **Multi-language support** — 80+ languages from a single model
- **Robust to noise, skew, and unusual fonts** — deep learning generalises better than rule-based OCR
- **Confidence scores** per detection — enables quality thresholding
- **Works well on receipts, handwriting, and signs** — beyond just documents

### Limitations

- **Very slow on CPU** — ~379s for 10 pages of an arXiv PDF; 5–10× slower than Tesseract
- **Requires PyTorch** — adds a large dependency (~500 MB) and long import time
- **Model download on first use** — hundreds of MB; can fail in offline environments
- **Reading order is spatial** — detections are sorted geometrically; complex column layouts can fragment sentences
- **Not designed for long-form document extraction** — optimised for shorter text blocks

### Best-Suited PDF Types

| PDF Type | Suitability |
|---|---|
| Image-Only Scanned | ⭐⭐⭐⭐ Good accuracy on clean scans |
| Searchable Image | ⭐⭐⭐ Good for noisy/multilingual docs |
| Forms (Scanned) | ⭐⭐⭐ Field region detection |
| Born-digital PDFs | ⭐ Unnecessary (use text-layer parsers) |

---

## 8. Tesseract / pytesseract

**Version in project**: pytesseract 0.3.13 / Tesseract 5.5.0 (system)

### What It Is

Tesseract is Google's open-source OCR engine — one of the most widely used OCR systems in the world, with 30+ years of development history. Version 4+ uses LSTM neural networks for recognition on top of the legacy Tesseract engine. pytesseract is a Python wrapper that calls the `tesseract` binary via subprocess.

### Architecture

```
Python (pytesseract) → subprocess call → tesseract binary
                                       → LSTM recogniser
                                       → language model (tessdata)
                                       → TSV / hOCR / text output
```

Tesseract requires: (1) the `tesseract` binary installed on the system, (2) tessdata language files (English `eng.traineddata` minimum), (3) input as an image (PIL/NumPy via pytesseract, or a path to a TIFF/PNG).

### How the Pipeline Uses It

The `TesseractParser` renders each page to a PIL image using PyMuPDF (no Poppler/pdftoppm needed), then calls `pytesseract.image_to_string()`. The Tesseract binary path is auto-detected by checking common install locations (including the Windows AppData path `C:\Users\<user>\AppData\Local\Programs\Tesseract-OCR\tesseract.exe`).

Key parameters used:
- `lang="eng"` (from config)
- `config="--psm 1"` (automatic page segmentation, OSD)
- `dpi=300` rendering to ensure adequate resolution for LSTM recognition

`max_pages` cap (default 10) is enforced to bound runtime.

### Strengths

- **Production-grade OCR** — used in industrial document processing pipelines worldwide
- **Fast on CPU** relative to deep-learning alternatives — ~74s for 10 pages vs ~379s for EasyOCR
- **Mature and stable** — very low bug rate for common document types
- **Good layout analysis** — PSM (page segmentation mode) options handle columns, single-blocks, single-lines
- **Configurable language packs** — 100+ languages via tessdata-fast or tessdata-best

### Limitations

- **Requires system-level install** — the `tesseract` binary must be installed separately; can be difficult in container or cloud environments
- **Resolution-sensitive** — below 200 dpi, accuracy drops significantly; PDFs must be rendered at 300 dpi for good results
- **Struggles with complex tables** — the text output from `image_to_string` doesn't preserve table structure; use hOCR output for that
- **Legacy design** — subprocess-based; not thread-safe without care; startup overhead per call if not batched
- **English-centric default models** — multilingual requires explicit tessdata packs

### Best-Suited PDF Types

| PDF Type | Suitability |
|---|---|
| Image-Only Scanned | ⭐⭐⭐⭐⭐ Primary recommendation |
| Searchable Image (noisy) | ⭐⭐⭐⭐ Re-OCR improves quality |
| Forms (Scanned) | ⭐⭐⭐⭐ Good for handwritten forms |
| Born-digital PDFs | ⭐ Unnecessary |
| Complex Layouts | ⭐⭐⭐ Text extraction OK, order may suffer |

---

## 9. OCRmyPDF

**Version in project**: 17.4.1 (`ocrmypdf>=16.0.0`)

### What It Is

OCRmyPDF takes a scanned PDF and produces a **searchable PDF** — it adds a hidden text layer behind the original images while preserving the visual appearance perfectly. It is a command-line tool (and Python API) that orchestrates: Ghostscript for PDF manipulation, Tesseract for OCR, optionally unpaper for image cleanup, and various image pre-processing steps.

### Architecture

```
Python (ocrmypdf) → Ghostscript → page rasterisation
               → unpaper (optional) → image deskew, denoise
               → Tesseract → per-page OCR → hOCR output
               → Ghostscript → PDF reassembly (image + text layer)
               → PyMuPDF (pipeline) → extract text layer
```

The pipeline's adapter runs OCRmyPDF on a copy of the PDF, then extracts text from the OCR'd output using PyMuPDF.

### How the Pipeline Uses It

The `OCRmyPDFParser`:
1. Creates a temporary output PDF (`ocrmypdf.ocr(input, output)`)
2. Applies `max_pages` slicing — only the first N pages are processed
3. Opens the output PDF with PyMuPDF and extracts the new text layer
4. Returns the extracted text in the standard `ParseResult` format

This two-step approach gives OCRmyPDF's superior image processing pipeline (deskew, denoise, optimise) but wraps it in the same output schema as all other parsers.

### Strengths

- **Best pre-processing pipeline** — deskew, denoise, contrast normalisation before OCR significantly improves Tesseract accuracy on challenging scans
- **Permanent output** — produces a standard searchable PDF that any tool can then extract from
- **Handles multi-column layouts** better than raw Tesseract because Ghostscript rendering is more accurate
- **Audit trail** — OCRmyPDF logs which pages were OCR'd and which already had text
- **Handles encrypted PDFs** — can decrypt if password available

### Limitations

- **Slow** — ~50s for 10 pages (Ghostscript → Tesseract → reassembly is expensive)
- **Requires Ghostscript and Tesseract** as system binaries — two system-level deps
- **Subprocess-based** — not thread-safe without careful temp-dir management
- **Output is a whole PDF** — harder to stream or parallelise at page level
- **Disk I/O heavy** — creates a temporary PDF for every parse call

### Best-Suited PDF Types

| PDF Type | Suitability |
|---|---|
| Image-Only Scanned | ⭐⭐⭐⭐⭐ Best for challenging scans |
| Searchable Image (noisy) | ⭐⭐⭐⭐ Re-OCR with cleanup |
| Born-digital PDFs | ⭐⭐ Works but redundant |

---

## 10. Camelot

**Version in project**: 1.0.9 (`camelot-py[cv]>=0.11.0`)

### What It Is

Camelot is a Python library specifically for extracting tables from PDF files. It implements two table detection algorithms: **lattice** (for tables with visible borders/rules) and **stream** (for whitespace-separated tables without borders). It uses OpenCV for line detection in lattice mode and a sophisticated text-flow analysis engine in stream mode.

### Architecture

```
Python (camelot) → Lattice mode:
                    → Ghostscript → page raster image
                    → OpenCV → line detection (Hough transform)
                    → Cell boundary reconstruction
                    → pdfminer for text within cells

                 → Stream mode:
                    → pdfminer → character-level positions
                    → Column/row boundary inference from text spacing
                    → Table region detection
```

### How the Pipeline Uses It

The `CamelotExtractor` tries lattice mode first, then stream mode if no tables are found. For each detected table:
- Pandas DataFrame extracted via `table.df`
- DataFrame converted to `[[cell, cell, ...], ...]` row-list format
- Stored in `ParseResult.tables`

The adapter also exports table text into the main `raw_text_full` so that table content is included in text completeness scoring.

### Strengths

- **Best table quality** for bordered tables (lattice mode) — uses actual line geometry
- **Output as DataFrames** — immediately usable for data analysis
- **Whitespace-based detection** (stream mode) handles tables in reports and filings without borders
- **Accuracy metrics** built-in — reports detection confidence per table
- Widely used in data journalism, financial analysis, government data extraction

### Limitations

- **Requires Ghostscript** — lattice mode will fail without it (`brew install ghostscript` / `apt-get install ghostscript`)
- **Slow on complex PDFs** — 122s for a 17-page arXiv paper (mostly Ghostscript rendering time)
- **Fails on rotated or overlapping tables**
- **Stream mode is unreliable** on tables with unusual column spacing
- **Only extracts text** — no images, no nested tables

### Best-Suited PDF Types

| PDF Type | Suitability |
|---|---|
| True Digital (tables) | ⭐⭐⭐⭐⭐ Primary table extractor |
| Forms | ⭐⭐⭐⭐ Field value extraction |
| Complex Layout (lattice tables) | ⭐⭐⭐⭐ Bordered academic tables |
| Complex Layout (borderless) | ⭐⭐ Stream mode; less reliable |
| Scanned PDFs | ⭐ Image-to-text table detection is limited |

---

## 11. Tabula-py

**Version in project**: Optional (`tabula-py>=2.9.0`) — requires Java JRE

### What It Is

tabula-py is a Python wrapper around **Tabula**, a Java library for extracting tables from PDFs. Tabula was originally a browser-based tool (Tabula App) and is widely used by data journalists. The Java core uses PDFBox for PDF parsing and implements its own heuristic table detection.

### Architecture

```
Python (tabula-py) → subprocess → Java JVM → Tabula.jar
                                           → PDFBox → text positions
                                           → Tabula heuristics → cell extraction
                              → CSV/JSON output → Python DataFrame
```

Because the Java core is a separate process, tabula-py has higher startup overhead than Camelot but can handle some table formats that Camelot misses.

### How the Pipeline Uses It

The `TabulaExtractor` calls `tabula.read_pdf()` with `pages="all"` and `multiple_tables=True`. Each returned DataFrame is converted to the standard list-of-rows format.

**Note**: If Java is not available on the system, tabula-py raises an error on import. The pipeline handles this gracefully by disabling Tabula and logging a `PARSER_SKIPPED` event.

### Strengths

- **Alternative table detection algorithm** — catches tables that Camelot misses (and vice versa)
- **Handles merged cells** better than Camelot in some cases
- **Battle-tested by journalists** — extensively validated on government and financial PDFs
- **No OpenCV dependency** — different dependency stack from Camelot

### Limitations

- **Requires Java JRE** — a significant system dependency; not available in many cloud/container environments
- **Subprocess overhead** — JVM startup adds ~500ms per call even before PDF processing
- **Worse at bordered tables** — lattice-mode Camelot consistently outperforms Tabula on tables with explicit grid lines
- **Output quality inconsistency** — numeric formatting (commas, currency symbols, negative signs) can be garbled

### Best-Suited PDF Types

| PDF Type | Suitability |
|---|---|
| True Digital (borderless tables) | ⭐⭐⭐⭐ Good for financial data |
| Forms | ⭐⭐⭐ Alternative to Camelot |
| Complex Layout | ⭐⭐⭐ Complementary to Camelot |
| Scanned PDFs | ⭐ No OCR capability |

---

## 12. Marker

**Version in project**: Not installed (graceful stub) — `marker-pdf`

### What It Is

Marker is a PDF-to-Markdown conversion library created by Vik Paruchuri (who also created pdftext). It uses a pipeline of ML models: layout detection (a fine-tuned object detection model), reading-order reconstruction, table recognition, and equation handling. Output is clean, structured Markdown including headings, bold, tables, and LaTeX equations.

### Architecture

```
Python (marker) → pdftext → character extraction + positions
              → Layout model (PyTorch) → region classification
              → Reading order model → sequence ordering
              → Table recognition model → Markdown tables
              → Post-processing → final Markdown string
```

It requires PyTorch and downloads model weights on first run.

### How the Pipeline Uses It

The `MarkerParser` is implemented as a graceful stub: if `marker` is not installed, it raises an `ImportError` that the pipeline catches at registration time. The parser is marked as `enabled: false` in `configs/parsers.yaml` and excluded from benchmark runs unless explicitly enabled after install.

### Strengths

- **Best Markdown output quality** of any open-source tool for academic PDFs
- **Reading order is correct** for multi-column layouts — the layout model explicitly detects columns
- **Table as Markdown** — tables extracted and formatted as `| col | col |` Markdown tables
- **Equation preservation** — detects math regions and bypasses OCR for embedded MathML/LaTeX
- **Fast for an ML pipeline** — pdftext for text, models only for layout; ~30–120s per page depending on content
- **Designed for RAG** — output is clean Markdown, ideal for chunking

### Limitations

- **Requires GPU for practical use** — CPU inference is very slow for the layout model
- **Large install** — PyTorch + model weights are several GB
- **Newer and evolving quickly** — API changes across versions
- **Not ideal for tables in scanned PDFs** — layout model trained primarily on born-digital content

### Best-Suited PDF Types

| PDF Type | Suitability |
|---|---|
| Complex Layout | ⭐⭐⭐⭐⭐ Best open-source option |
| Specialized (scientific) | ⭐⭐⭐⭐⭐ Equation + layout handling |
| True Digital | ⭐⭐⭐⭐ Clean Markdown |
| Forms | ⭐⭐ Limited form understanding |
| Scanned PDFs | ⭐⭐ Path: OCR → Marker is better |

---

## 13. Nougat

**Version in project**: Not installed (graceful stub) — `nougat-ocr`

### What It Is

Nougat (Neural Optical Understanding for Academic Documents) is a transformer-based model from Meta AI, published in 2023. It was trained specifically on arXiv papers and produces output in **mmd** (Modified Markdown) format which includes LaTeX equations. Unlike other PDF parsers, Nougat treats the page as an image and decodes text directly from the visual representation — no dependency on the PDF text layer.

### Architecture

```
Python (nougat) → PDF pages → rasterised images → Swin Transformer encoder
                                               → BART decoder → mmd string
```

The model processes each page as a 896×672 pixel image and generates text token-by-token, similar to an image captioning model. Because it is fully image-based, it works equally on born-digital and scanned scientific PDFs.

### How the Pipeline Uses It

The `NougatParser` is implemented as a graceful stub. Like Marker, it requires installation of the `nougat-ocr` package and model download. The pipeline marks it as `enabled: false` and excludes it from all benchmark runs unless explicitly activated.

### Strengths

- **Best equation extraction** — trained on arXiv LaTeX source; outputs `\frac`, `\sum`, etc. correctly
- **No text layer dependency** — works on scanned scientific papers
- **End-to-end ML pipeline** — avoids all heuristics in text extraction
- **mmd output** is structured and parseable for further processing

### Limitations

- **Very slow** — transformer inference on CPU is impractical; requires GPU
- **Hallucinations** — the decoder can "hallucinate" text not present in the image, especially on degraded pages
- **Only trained on scientific papers** — performs poorly on non-academic document types
- **High memory requirements** — the 0.1.0-small model requires ~8 GB VRAM
- **Repetition loops** — can get stuck repeating phrases; requires repetition penalty tuning

### Best-Suited PDF Types

| PDF Type | Suitability |
|---|---|
| Specialized (arXiv papers) | ⭐⭐⭐⭐⭐ Best equation output |
| Complex Layout (scientific) | ⭐⭐⭐⭐ Academic papers |
| Other types | ⭐ Not trained for general docs |
