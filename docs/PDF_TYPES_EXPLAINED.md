# PDF Types Explained

A beginner-friendly guide to the six PDF categories used in this research pipeline — what makes each type different, where you find them in real life, and how the pipeline handles each one.

---

## The Problem: Not All PDFs Are Equal

A PDF file is just a container. What's *inside* that container varies enormously — and the right tool to extract structured text depends entirely on what kind of PDF you have.

Trying to apply the wrong extraction strategy to a PDF is one of the most common sources of bad results:
- Running a text-only parser on a scanned image PDF returns... nothing.
- Running a full OCR stack on a born-digital PDF wastes minutes and may produce worse output than a simple text copy.

Understanding the six PDF types lets you choose the right tool before running anything.

---

## The Six PDF Types

### 1. True Digital PDF

> "The computer made this directly — it was never paper."

**What it is**: A PDF created entirely by software: word processors (Word, Google Docs), spreadsheet tools, report generators, or code. The text is always perfectly machine-readable because it was typed into software and exported directly to PDF. There are no scans, no images of text, no ambiguity.

**Key characteristics:**
- Every character is stored as a Unicode code point
- Fonts are embedded; text-to-string conversion is lossless
- Selectable text in any PDF viewer
- Often has hyperlinks, bookmarks, and a logical reading order
- File size is typically small relative to content volume

**Real-world examples:**
- Government reports exported from Word (`.docx` → `.pdf`)
- Financial statements from accounting software
- Academic syllabi, policy documents
- Invoices from ERP systems
- This pipeline gets them from `data_gov` (US open data portal)

**What the pipeline does with it:**
- Routed to lightweight text parsers: **PyMuPDF**, **pypdf**, **pypdfium2**, **pdftext**
- No OCR needed — you'd be converting perfect text to image and back
- Table detection with **pdfplumber** or **Camelot** where needed

**Best extraction approach:** PyMuPDF or pypdfium2. Fast, lossless, no dependencies.

---

### 2. Image-Only Scanned PDF

> "Someone scanned a physical document and saved the images as a PDF."

**What it is**: A PDF where every page is a raster image — a photograph or scan of paper. There is no text layer at all. Open it in a text editor and you will find zero characters. The "words" are pixel patterns that look like letters to a human eye.

**Key characteristics:**
- Zero text layer: `pdftotext` and all non-OCR parsers return empty strings
- May be black-and-white, grayscale, or colour
- Often comes from document management systems, archives, or old photocopiers
- DPI quality varies wildly (150 dpi archive scans vs. 600 dpi legal scans)
- File sizes are large (each page is a compressed image)

**Real-world examples:**
- Historical newspaper archives (e.g., Internet Archive collections)
- Court documents scanned from paper filings
- Old academic papers digitised from print journals
- Tax forms submitted via fax, then scanned
- This pipeline gets them from `internet_archive`

**What the pipeline does with it:**
- All non-OCR parsers return empty or near-empty text → flagged as `EMPTY_TEXT` in verification (expected and normal)
- Routed to **Tesseract** (primary) and **OCRmyPDF** (creates a searchable-PDF layer, then extracts)
- **EasyOCR** used as an alternative for difficult fonts or multilingual documents
- `ocr_quality` dimension is weighted 4× higher in scoring for this type

**Best extraction approach:** Tesseract 5.x for most cases; OCRmyPDF for a permanent searchable PDF output.

---

### 3. Searchable Image PDF

> "Someone ran OCR on a scanned document and saved the result — but the images are still there."

**What it is**: A hybrid PDF. The pages are still images (like Type 2 above), but a hidden text layer has been overlaid by an OCR program such as Adobe Acrobat, OCRmyPDF, or ABBYY FineReader. You can copy-paste text, and the file is searchable — but the text layer may have errors.

**Key characteristics:**
- Has a text layer, but it may contain OCR errors (mis-recognitions, run-together words)
- Text and image rendering are both present; text is often invisible unless selected
- Common in digitised library archives and enterprise document management
- Quality depends heavily on original scan quality and OCR engine used

**Real-world examples:**
- Digitised library books processed with ABBYY
- Legal discovery documents put through enterprise OCR
- Old scientific journal articles on JSTOR / Internet Archive
- Scanned government documents available on official portals

**What the pipeline does with it:**
- Text-layer parsers (PyMuPDF, pypdf) can extract text, but it may contain OCR errors
- Re-running fresh OCR (Tesseract, EasyOCR) often gives better results than the embedded layer
- The pipeline benchmarks both approaches and scores them comparatively
- Verification checks confidence scores where available

**Best extraction approach:** Depends on embedded OCR quality. If confidence is high, extract the existing text layer with PyMuPDF. If quality is poor, re-OCR with Tesseract.

---

### 4. Complex Layout PDF

> "The page has columns, diagrams, tables, sidebars — content that isn't in a simple top-to-bottom flow."

**What it is**: A born-digital or high-quality scanned PDF with a rich visual structure. The information is densely packed: multi-column text, embedded figures with captions, numbered equations, data tables, footnotes, headers with page numbers, and cross-references. Extracting this structure correctly is one of the hardest problems in PDF processing.

**Key characteristics:**
- Multi-column layouts (academic papers are typically 2-column)
- Embedded images, charts, and diagrams with associated captions
- Tables of varying complexity (bordered, borderless, nested)
- Mathematical equations (often encoded as images or MathML)
- Footnotes and endnotes that break normal reading order
- Rich internal structure (sections, subsections, figure numbering)

**Real-world examples:**
- arXiv research papers (cs, physics, math) — the primary test case in this pipeline
- Scientific journal articles (Nature, Science, IEEE)
- Technical documentation and textbooks
- Annual reports with infographics
- This pipeline downloads from `arxiv` and `arxiv_specialized`

**What the pipeline does with it:**
- Layout-aware parsers preferred: **Unstructured** (uses document AI), **Marker** (ML layout model)
- Column-order text: PyMuPDF and pdfplumber can extract but reading order gets confused
- Table extraction: **Camelot** for bordered tables, **pdfplumber** for text-based tables
- `coordinate_richness` and `structural_fidelity` scoring dimensions weighted higher

**Best extraction approach:** Unstructured (hi_res mode) or Marker for layout-aware extraction. PyMuPDF as a fast baseline.

---

### 5. Forms / Interactive PDF

> "This PDF has text fields, checkboxes, dropdown menus — it was designed to be filled in."

**What it is**: A PDF that contains interactive form elements (AcroForms or XFA forms). These are commonly used for government applications, tax returns, legal documents, and HR onboarding. The challenge is that *content* lives in form fields, not in the static text layer — a naive parser that reads only the static text will miss everything the user typed.

**Key characteristics:**
- AcroForm or XFA structure with named fields
- Field values may be text boxes, checkboxes, radio buttons, or signatures
- Static labels (field names) are in the text layer; user-entered values are in the form data
- Some forms are locked/protected and resist modification
- Multi-page forms with complex field dependencies

**Real-world examples:**
- IRS 1040 tax forms
- FUNSD (Form Understanding in Noisy Scanned Documents) — the primary test dataset in this pipeline
- Job applications, medical intake forms
- Insurance claim forms
- Visa application PDFs

**What the pipeline does with it:**
- **Unstructured** is the primary parser — it understands form element types
- **pdfplumber** extracts text labels and approximate field positions
- **Camelot** or **Tabula** for tabular regions within forms
- `forms_interactive_pdf` routing uses Unstructured as primary, pdfplumber as fallback

**Best extraction approach:** Unstructured for field-level extraction. For pure text, pdfplumber preserves spatial positioning well.

---

### 6. Specialized PDF

> "This PDF follows a domain-specific standard that requires special handling."

**What it is**: PDFs that conform to specialized sub-formats or domain conventions. This includes scientific papers with embedded datasets, PDFs with 3D models, multilingual documents, CAD drawings exported to PDF, and medical imaging reports. Normal text extraction approaches work partially but miss domain-specific structure.

**Key characteristics:**
- May embed non-text objects: 3D models, audio, spreadsheet data
- Scientific PDFs often have LaTeX-generated mathematical content
- Domain conventions for structure (e.g., JATS XML for journal publishing, DICOM metadata for medical)
- May require domain-specific models trained on that document class
- Often has multilingual content, specialized symbols (Greek letters, chemical formulas)

**Real-world examples:**
- arXiv papers with LaTeX math (this pipeline's `arxiv_specialized` source)
- Medical radiology reports (HL7 FHIR PDF)
- CAD/engineering drawings exported from AutoCAD
- Pharmaceutical clinical trial documents (ICH CTD format)
- Legal contracts in LegalXML format

**What the pipeline does with it:**
- **Nougat** is the gold-standard parser (ML model trained specifically on scientific PDFs from arXiv)
- **Marker** handles layout + equations reasonably well
- Standard parsers work as baselines but miss math and domain structure
- `specialized_pdf` routing uses Nougat as primary, Marker as fallback

**Best extraction approach:** Nougat for scientific papers (preserves LaTeX math as Markdown). Marker as practical alternative. Fall back to PyMuPDF for plain text.

---

## Quick Reference Table

| PDF Type | Has Text Layer | Needs OCR | Layout Complexity | Best Parser(s) |
|---|---|---|---|---|
| True Digital | ✅ Perfect | ❌ | Low | PyMuPDF, pypdfium2, pypdf |
| Image-Only Scanned | ❌ None | ✅ Required | Low–Medium | Tesseract, OCRmyPDF, EasyOCR |
| Searchable Image | ⚠️ May have errors | Optional | Low–Medium | PyMuPDF (if clean), Tesseract (if noisy) |
| Complex Layout | ✅ Good | ❌ | High | Unstructured, Marker, PyMuPDF |
| Forms / Interactive | ⚠️ Labels only | ❌ | Medium | Unstructured, pdfplumber |
| Specialized | ✅ + domain content | ❌ | High + domain | Nougat, Marker |

---

## How the Pipeline Detects PDF Type

PDF type is determined by directory placement. When you download a source, its output goes to a specific subfolder:

```
data/raw/
  complex_layout_pdf/arxiv/           ← arxiv source → complex_layout_pdf
  image_only_scanned_pdf/internet_archive/   ← internet_archive → image_only_scanned_pdf
  forms_interactive_pdf/funsd/         ← funsd → forms_interactive_pdf
  true_digital_pdf/                   ← data_gov → true_digital_pdf
  specialized_pdf/                    ← arxiv_specialized → specialized_pdf
  searchable_image_pdf/               ← (manually placed or future source)
```

The `pdf-pipeline catalog` command reads the path and sets `pdf_type` in the catalog entry accordingly. This type label then governs which scoring weights and which parser routing hints are applied.
