# PDF Libraries — Real-World Usage Mapping

Where you actually encounter each PDF extraction library in production systems, data pipelines, and applications. Organised by library, then real-world domain, and then the pipeline's own mapping.

---

## How to Use This Document

This guide answers: *"I have this kind of document — which library do practitioners actually use for this?"*

It maps each library to:
- **Real-world domains** where it is the standard or most common choice
- **Example document types** seen in those domains
- **Why that library** fits those documents
- **Common alternative** for the same use case

---

## Library-to-Domain Mapping Table

| Library | Primary Domain | Secondary Domain | Typical Document | Why It Fits |
|---|---|---|---|---|
| PyMuPDF | Research / RAG pipelines | Document rendering | arXiv papers, technical reports | Fastest; spatial data; PyPI-only |
| pdfplumber | Data journalism | Government data portals | Census tables, financial filings | Word-level positions; reliable tables |
| pypdf | Simple tooling / scripts | PDF manipulation utilities | Bulk PDF metadata extraction | Zero deps; merge/split capability |
| pypdfium2 | Browser / embedded systems | Fast search indexing | Any born-digital PDF | Chrome-engine accuracy; fast |
| pdftext | LLM pre-processing | ML training data prep | Scientific papers, Wikipedia PDFs | Character positions; reading order |
| Unstructured | Enterprise RAG | LangChain / LlamaIndex stacks | Mixed document repositories | Element types → chunks |
| EasyOCR | ID document processing | Multilingual OCR | Receipts, signs, handwritten notes | No C deps; 80+ languages |
| Tesseract | Document archival | Compliance scanning | Historical documents, legal archives | Fast; LSTM quality; mature |
| OCRmyPDF | Office / legal digitisation | Government archive | Paper filings, court documents | Searchable PDF output; deskew |
| Camelot | Investigative journalism | Financial compliance | Annual reports, government filings | Lattice precision; DataFrame output |
| Tabula | Data journalism toolkits | Spreadsheet extraction | Budget tables, statistics releases | Browser GUI; CSV export |
| Marker | Research pre-processing | LLM corpus building | arXiv, scientific books | Markdown output; reading order |
| Nougat | Scientific NLP | Formula extraction | Math-heavy arXiv papers | LaTeX equation output |

---

## Per-Library Real-World Usage Profiles

### PyMuPDF (`fitz`)

**Who uses it**: MLOps teams building document ingestion pipelines; open-source RAG frameworks.

| Domain | Use Case | Example Systems |
|---|---|---|
| Research / RAG | Fast text extraction for embedding | LlamaIndex (`PyMuPDFReader`), Haystack |
| Document rendering | Thumbnail generation, page preview | Document management web apps |
| Data extraction | Bulk extraction of text + positions | Internal data lake pipelines |
| Academic research | PDF corpus analysis | NLP research scripts |
| Security tools | PDF content scanning | Malware analysis tooling |

**Why PyMuPDF**: No system dependencies beyond the Python package. Sub-second per page. Precise bounding boxes for every word. The clean API handles malformed PDFs gracefully.

**Common alternative**: pypdfium2 when you only need text and want even faster extraction.

---

### pdfplumber

**Who uses it**: Data journalists; government data analysts; anyone whose primary goal is extracting tables from PDF-trapped data.

| Domain | Use Case | Example Systems |
|---|---|---|
| Investigative journalism | Extract data tables from government PDFs | OCCRP data team, ProPublica |
| Open data | Parse statistical releases (ONS, BLS, Eurostat) | Government transparency tools |
| Legal | Extract clause tables from contracts | Contract analysis scripts |
| Finance | Parse mutual fund fact sheets, EDGAR filings | Financial data APIs |
| Academia | Extract experiment results from papers | Reproducibility tools |

**Why pdfplumber**: The geometry-first approach (characters → words → lines → cells) is the right model for data extraction. Word-level bounding boxes are accurate enough for column detection even on borderless tables.

**Common alternative**: Camelot for bordered tables; tabula-py as alternative.

---

### pypdf

**Who uses it**: Developers who need basic PDF manipulation without heavy dependencies; utility script authors.

| Domain | Use Case | Example Systems |
|---|---|---|
| File management | PDF merge, split, rotate operations | Office automation scripts |
| Metadata extraction | Title, author, creation date from PDF metadata | Document indexing pipelines |
| Simple text extraction | Quick-and-dirty scraping from simple PDFs | Data science notebooks |
| Testing | Mocking PDF inputs in unit tests | Test harnesses |
| Document assembly | Watermarking, page insertion | Reporting tools |

**Why pypdf**: Zero system dependencies. Excellent for PDF manipulation operations where text quality is not the primary concern.

**Common alternative**: PyMuPDF for any use case where text quality or speed matters.

---

### pypdfium2

**Who uses it**: High-throughput search indexing systems; embedded Python environments where other libraries are impractical.

| Domain | Use Case | Example Systems |
|---|---|---|
| Search indexing | Fast text extraction at scale | Document search backends |
| AI training data | Clean corpus creation from PDF collections | LLM pre-training pipelines |
| Cloud functions | Lightweight serverless PDF processing | AWS Lambda, GCP Cloud Functions |
| Browser-adjacent tooling | PDF processing in Chromium-based contexts | WebAssembly PDF tools |

**Why pypdfium2**: PDFium is the same engine Chrome uses to render PDFs. Maximum compatibility with edge-case encodings. Pre-compiled wheels mean zero build dependencies. The ~88ms for a 17-page paper makes it the fastest non-OCR option.

**Common alternative**: PyMuPDF when bounding boxes are needed.

---

### pdftext

**Who uses it**: Teams building Marker-based document processing pipelines; researchers preparing ML training data.

| Domain | Use Case | Example Systems |
|---|---|---|
| ML training data | High-quality text with positions | arXiv corpus preparation |
| Marker pipeline | Text extraction stage before layout analysis | Marker PDF-to-Markdown |
| Reading order research | Benchmarking reading order reconstruction | Document understanding research |

**Why pdftext**: Designed from scratch for Marker's needs — speed, character positions, reading-order heuristics. Not a Swiss Army knife, but excellent in its target use case.

**Common alternative**: PyMuPDF with manual reading-order reconstruction.

---

### Unstructured

**Who uses it**: Enterprise AI/RAG teams integrating with LangChain, LlamaIndex, or building custom document Q&A systems.

| Domain | Use Case | Example Systems |
|---|---|---|
| Enterprise RAG | Ingest mixed document collections | LangChain document loaders, LlamaIndex readers |
| Legal tech | Parse legal documents into typed elements | Contract analysis platforms |
| Finance | Parse earning reports, SEC filings | Investment research tools |
| Healthcare | Extract clinical notes, discharge summaries | EHR integration pipelines |
| HR / operations | Process invoices, purchase orders | Accounts payable automation |

**Why Unstructured**: The element-type system (Title, NarrativeText, Table, ListItem) maps directly to RAG chunk types. Instead of deciding how to split a document for retrieval, you split it at element boundaries and tag each chunk with its type.

**Common alternative**: PyMuPDF + manual post-processing for simpler use cases; Marker for academic documents.

---

### EasyOCR

**Who uses it**: Mobile/identity verification companies; receipt processing apps; multilingual document services.

| Domain | Use Case | Example Systems |
|---|---|---|
| Identity verification | Passport, ID card text extraction | KYC pipelines, fintech apps |
| Receipt / invoice processing | Text from photos of receipts | Expense management apps |
| Retail | Price tag, label, packaging recognition | Inventory management |
| Multilingual archives | Non-Latin script document digitisation | Southeast Asian archival projects |
| Computer vision research | OCR component benchmarking | Academic research |

**Why EasyOCR**: No C/C++ system install needed — PyTorch wheels are sufficient. 80+ languages from one model. Works naturally on images from cameras, not just scanned PDFs. Great community support.

**Common alternative**: Tesseract for document-type OCR where speed matters; commercial APIs (Google Vision, AWS Textract) for highest accuracy.

---

### Tesseract / pytesseract

**Who uses it**: Document archivists; legal discovery firms; compliance teams; open-source document management systems.

| Domain | Use Case | Example Systems |
|---|---|---|
| Document archival | Mass digitisation of historical records | Internet Archive, HathiTrust |
| Legal discovery | OCR for litigation document production | e-discovery platforms (Relativity has Tesseract components) |
| Healthcare | Digitise paper forms, prescription labels | EMR document upload pipelines |
| Government | Property records, court filings | Open government data portals |
| Banking / insurance | Process mailed paper documents | Document digitisation services |
| Open source CMS | Document search in open-source platforms | Paperless-ngx, SOLR integrations |

**Why Tesseract**: 30 years of development; unmatched language coverage; free; battle-tested at Internet Archive scale. The LSTM engine (v4+) is competitive with commercial OCR for clean document scans.

**Common alternative**: OCRmyPDF (which uses Tesseract internally plus image cleanup) for challenging scans; commercial APIs for highest-stakes accurate extraction.

---

### OCRmyPDF

**Who uses it**: Law firms; compliance teams; document management system integrators; anyone who needs the original PDF appearance preserved with added searchability.

| Domain | Use Case | Example Systems |
|---|---|---|
| Legal / compliance | Make scanned filings searchable | Law firm DMS (iManage, NetDocuments companions) |
| Finance | Searchable bank statements, broker confirms | Back-office document archival |
| Healthcare | Searchable patient records from scanned charts | EHR integrations |
| Government | Modernise legacy paper archives | Open records / FOIA fulfilment |
| Personal productivity | Make scanned books/notes searchable | Personal knowledge management |

**Why OCRmyPDF**: It produces a **standard PDF output** that any tool can then work with. The original image is preserved (important for legal admissibility). Optional deskew and denoise pre-processing dramatically improves accuracy on challenging scans. The `--redo-ocr` flag replaces existing OCR layers.

**Common alternative**: Tesseract directly if you only need text, not the searchable PDF artifact.

---

### Camelot

**Who uses it**: Data journalists; financial analysts; compliance data teams; open data advocates.

| Domain | Use Case | Example Systems |
|---|---|---|
| Investigative journalism | Extract financial/statistical tables from PDFs | ICIJ tools, newsroom data desks |
| Government data portals | Parse statistics from official PDF releases | ONS, Eurostat data extraction |
| Financial compliance | Parse regulatory filings, annual reports | RegTech data pipelines |
| Academic research | Reproducible data extraction from published papers | Reproducibility studies |
| Legal | Extract numeric data from contracts and agreements | Contract analytics |

**Why Camelot**: The lattice mode is uniquely accurate for bordered tables — it uses actual line-detection geometry (OpenCV Hough transform) to identify grid lines, then maps PDF characters to cells. For tables with clear borders, this is the most reliable Python-native approach.

**Common alternative**: Tabula-py (if Java available, catches some Camelot misses); pdfplumber for borderless tables.

---

### Tabula-py

**Who uses it**: Data journalists who started with the Tabula browser app; teams that inherited Tabula-based workflows; analysts who need the browser GUI equivalent in a script.

| Domain | Use Case | Example Systems |
|---|---|---|
| Data journalism | Semi-automated table extraction | Tabula App user base, newsroom scripts |
| Government data | Statistical table extraction | Many open data scripts on GitHub |
| Financial research | Balance sheet / income statement extraction | Independent analyst tools |
| NGO / civil society | Budget monitoring, aid fund tracking | Transparency/accountability NGOs |

**Why Tabula**: The browser app (Tabula.technology) popularised PDF table extraction. Many workflows were built around it, and tabula-py makes those scriptable. For teams already familiar with the app, the behaviour is familiar.

**Common alternative**: Camelot for bordered tables; pdfplumber for borderless.

---

### Marker

**Who uses it**: AI researchers building document-level RAG systems; teams creating ML training datasets from academic papers.

| Domain | Use Case | Example Systems |
|---|---|---|
| LLM training data | Clean Markdown corpora from PDF | arXiv → Markdown for LLM pre-training |
| Academic RAG | High-quality document ingestion | Research paper Q&A systems |
| Knowledge bases | Structured representation of technical books | Internal knowledge management |
| Translation | Source text extraction for MT pipelines | Document translation systems |

**Why Marker**: It produces clean, structured Markdown — the format that LLMs understand best. Column order is correct. Tables are formatted. Math is preserved as LaTeX. This dramatically reduces post-processing compared to raw text output.

**Common alternative**: Nougat for math-heavy papers; Unstructured for enterprise mixed-document scenarios.

---

### Nougat

**Who uses it**: Scientific NLP researchers; math formula extraction systems; LLMs trained specifically on scientific content.

| Domain | Use Case | Example Systems |
|---|---|---|
| Scientific NLP | LaTeX-equivalent text from paper images | arXiv corpus for math LLMs |
| Formula extraction | Math region detection + LaTeX output | Scientific search engines |
| LLM training | Nougat-derived formulas in training data | Minerva, Galactica-style models |
| Document understanding research | PDF understanding benchmark systems | Academic research groups |

**Why Nougat**: No other open-source tool reliably converts PDF equations to LaTeX. The transformer trained on arXiv source distributions "knows" what equations should look like — it generates LaTeX even when the PDF encoding is ambiguous or missing.

**Common alternative**: Marker (handles equations reasonably, less accurately); commercial tools (Mathpix) for highest math accuracy.

---

## Pipeline's Own PDF-Type → Library Routing

This table shows exactly how `configs/parsers.yaml` routes each PDF type through the pipeline:

| PDF Type | Primary Parser | Fallback Parser | Table Extractor |
|---|---|---|---|
| `true_digital_pdf` | pymupdf | pypdf | camelot |
| `image_only_scanned_pdf` | tesseract | ocrmypdf | _(none)_ |
| `searchable_image_pdf` | pymupdf | tesseract | pdfplumber |
| `complex_layout_pdf` | unstructured | pymupdf | camelot |
| `forms_interactive_pdf` | unstructured | pdfplumber | tabula |
| `specialized_pdf` | nougat _(if installed)_ | marker _(if installed)_ | _(none)_ |

When primary fails or returns `EMPTY_TEXT`, the pipeline automatically falls back to the configured fallback. This routing can be overridden globally or per-PDF via CLI flags.
