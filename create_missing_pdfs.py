"""
create_missing_pdfs.py — Generate synthetic PDFs for missing categories.

Creates:
  data/raw/true_digital_pdf/        — 3 clean machine-generated PDFs (fpdf2)
  data/raw/searchable_image_pdf/synthetic/  — 3 scanned-look PDFs with OCR text layer (PyMuPDF)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

# ── true_digital_pdf ────────────────────────────────────────────────────────

TRUE_DIGITAL_DIR = ROOT / "data" / "raw" / "true_digital_pdf"
TRUE_DIGITAL_DIR.mkdir(parents=True, exist_ok=True)

TRUE_DIGITAL_DOCS = [
    {
        "filename": "annual_report_2024.pdf",
        "title": "Annual Performance Report 2024",
        "sections": [
            (
                "Executive Summary",
                (
                    "This report presents the annual performance metrics for fiscal year 2024. "
                    "Key milestones were achieved across all departments. Revenue increased by "
                    "12.4% year-over-year, driven primarily by digital transformation initiatives. "
                    "Operating costs were reduced by 8.2% through process automation."
                ),
            ),
            (
                "Financial Overview",
                (
                    "Total revenue for 2024 reached $4.7 billion, compared to $4.2 billion in "
                    "fiscal year 2023. Gross profit margin improved from 34.1% to 36.8%. "
                    "Net income attributable to shareholders was $812 million, a 15.3% increase. "
                    "Earnings per diluted share were $2.47, compared to $2.14 in the prior year. "
                    "The board of directors approved a dividend of $0.45 per share for Q4 2024."
                ),
            ),
            (
                "Operational Highlights",
                (
                    "The company successfully launched three major product lines in Q2 2024. "
                    "Customer satisfaction scores improved to 87% from 81% in the previous year. "
                    "Employee headcount grew from 12,400 to 14,200, an increase of 14.5%. "
                    "Expansion into two new international markets was completed ahead of schedule. "
                    "The research and development budget was increased to $340 million."
                ),
            ),
            (
                "Strategic Outlook",
                (
                    "Looking ahead to 2025, management expects continued growth across all segments. "
                    "Investment in artificial intelligence and machine learning will be prioritised. "
                    "The company plans to acquire two strategic targets in the data analytics space. "
                    "Capital expenditure guidance for 2025 is set at $580 million. "
                    "Long-term debt refinancing at lower rates is expected to reduce interest costs."
                ),
            ),
        ],
    },
    {
        "filename": "technical_specification_v3.pdf",
        "title": "System Architecture Technical Specification v3.0",
        "sections": [
            (
                "Introduction",
                (
                    "This document describes the technical architecture for the distributed data "
                    "processing platform. Version 3.0 introduces significant improvements in "
                    "scalability and fault tolerance. The platform is designed to handle up to "
                    "10 million events per second with sub-millisecond latency requirements."
                ),
            ),
            (
                "Architecture Overview",
                (
                    "The platform uses a microservices architecture deployed on Kubernetes. "
                    "Service communication is handled via gRPC with Protocol Buffers. "
                    "Data persistence is provided by a combination of PostgreSQL and Apache Kafka. "
                    "The API gateway handles authentication using OAuth 2.0 and JWT tokens. "
                    "All services expose Prometheus metrics for observability."
                ),
            ),
            (
                "Data Pipeline",
                (
                    "Ingestion is handled by a fleet of stateless collector services. "
                    "Data is partitioned by tenant ID and event type for parallel processing. "
                    "The stream processing layer uses Apache Flink for stateful computations. "
                    "Windowing operations support tumbling, sliding, and session windows. "
                    "Results are materialised to both a data warehouse and real-time dashboards."
                ),
            ),
            (
                "Security Requirements",
                (
                    "All data at rest is encrypted using AES-256-GCM. "
                    "Data in transit uses TLS 1.3 with mutual certificate authentication. "
                    "Role-based access control is enforced at the API and storage layers. "
                    "Audit logs are immutable and retained for a minimum of seven years. "
                    "Penetration testing is conducted quarterly by an independent security firm."
                ),
            ),
            (
                "Performance Benchmarks",
                (
                    "End-to-end latency at the 99th percentile is under 8 milliseconds. "
                    "Throughput tests confirmed 12.4 million events per second peak capacity. "
                    "Storage efficiency gains of 41% were achieved through columnar compression. "
                    "Cold-start time for worker containers is under 400 milliseconds. "
                    "Mean time to recovery from node failure is under 30 seconds."
                ),
            ),
        ],
    },
    {
        "filename": "policy_guidelines_2025.pdf",
        "title": "Data Governance Policy Guidelines 2025",
        "sections": [
            (
                "Purpose and Scope",
                (
                    "These guidelines establish the framework for data governance within the "
                    "organisation. They apply to all employees, contractors, and third-party "
                    "service providers who access, process, or store organisational data. "
                    "Compliance with these guidelines is mandatory and subject to audit."
                ),
            ),
            (
                "Data Classification",
                (
                    "Data is classified into four tiers: Public, Internal, Confidential, and "
                    "Restricted. Public data may be freely shared outside the organisation. "
                    "Internal data is for use within the organisation only. Confidential data "
                    "requires business justification for access. Restricted data requires "
                    "executive approval and is subject to enhanced monitoring."
                ),
            ),
            (
                "Retention Policy",
                (
                    "Operational data is retained for a minimum of three years from creation. "
                    "Financial records must be retained for seven years in accordance with "
                    "regulatory requirements. Customer personal data is retained only for the "
                    "duration necessary to fulfil contractual obligations. Records related to "
                    "legal proceedings are retained until final resolution plus seven years."
                ),
            ),
            (
                "Incident Response",
                (
                    "Any suspected data breach must be reported to the Information Security team "
                    "within one hour of discovery. The incident response team will conduct an "
                    "initial triage within four hours. Affected parties will be notified in "
                    "accordance with applicable data protection regulations. A post-incident "
                    "review will be completed within fourteen days of resolution."
                ),
            ),
        ],
    },
]


def generate_true_digital_pdfs() -> list[Path]:
    import fitz  # PyMuPDF — reliable cross-platform

    W, H = 595, 842  # A4 points
    L, R = 60, 535  # left / right x positions

    def _wrap_text(page, text, x, y, fontname, fontsize, max_w):
        words = text.split()
        line: list[str] = []
        for word in words:
            test = " ".join(line + [word])
            if (
                fitz.get_text_length(test, fontname=fontname, fontsize=fontsize) > max_w
                and line
            ):
                page.insert_text(
                    (x, y), " ".join(line), fontname=fontname, fontsize=fontsize
                )
                y += fontsize + 4
                line = [word]
            else:
                line.append(word)
        if line:
            page.insert_text(
                (x, y), " ".join(line), fontname=fontname, fontsize=fontsize
            )
            y += fontsize + 4
        return y

    generated: list[Path] = []
    for doc in TRUE_DIGITAL_DOCS:
        dest = TRUE_DIGITAL_DIR / doc["filename"]
        if dest.exists():
            print(f"  [skip] {dest.name} (already exists)")
            generated.append(dest)
            continue

        pdf = fitz.open()

        # Cover page
        page = pdf.new_page(width=W, height=H)
        page.draw_rect(fitz.Rect(0, 0, W, H), color=None, fill=(1, 1, 1))
        t_len = fitz.get_text_length(doc["title"], fontname="hebo", fontsize=18)
        page.insert_text(
            ((W - t_len) / 2, 280), doc["title"], fontname="hebo", fontsize=18
        )
        sub = "Prepared by: Research & Development Division"
        s_len = fitz.get_text_length(sub, fontname="helv", fontsize=11)
        page.insert_text(((W - s_len) / 2, 315), sub, fontname="helv", fontsize=11)
        d_txt = "Date: April 2025"
        d_len = fitz.get_text_length(d_txt, fontname="helv", fontsize=11)
        page.insert_text(((W - d_len) / 2, 334), d_txt, fontname="helv", fontsize=11)

        # Content pages
        for section_title, body_text in doc["sections"]:
            page = pdf.new_page(width=W, height=H)
            page.draw_rect(fitz.Rect(0, 0, W, H), color=None, fill=(1, 1, 1))
            y = 60
            page.insert_text((L, y), section_title, fontname="hebo", fontsize=13)
            y += 24
            y = _wrap_text(page, body_text, L, y, "helv", 10, R - L)
            y += 10
            # Simple table header
            col_w = (R - L) / 3
            page.draw_rect(
                fitz.Rect(L, y, R, y + 16), color=None, fill=(0.85, 0.85, 0.85)
            )
            for ci, col in enumerate(["Metric", "Value", "Status"]):
                page.insert_text(
                    (L + ci * col_w + 4, y + 11), col, fontname="hebo", fontsize=9
                )
            y += 16
            for i, (m, v, s) in enumerate(
                [
                    ("Key Indicator 1", "85.0%", "On Track"),
                    ("Key Indicator 2", "88.2%", "On Track"),
                    ("Key Indicator 3", "91.4%", "Exceeded"),
                ]
            ):
                page.draw_rect(fitz.Rect(L, y, R, y + 14), color=(0.5, 0.5, 0.5))
                for ci, cell in enumerate([m, v, s]):
                    page.insert_text(
                        (L + ci * col_w + 4, y + 10), cell, fontname="helv", fontsize=9
                    )
                y += 14

        pdf.save(str(dest))
        pdf.close()
        size_kb = dest.stat().st_size // 1024
        print(f"  [OK] {dest.name}  ({size_kb} KB, {1 + len(doc['sections'])} pages)")
        generated.append(dest)

    return generated


# ── searchable_image_pdf ─────────────────────────────────────────────────────

SEARCHABLE_DIR = ROOT / "data" / "raw" / "searchable_image_pdf" / "synthetic"
SEARCHABLE_DIR.mkdir(parents=True, exist_ok=True)

SEARCHABLE_TEXTS = [
    {
        "filename": "scanned_memo_001.pdf",
        "pages": [
            "MEMORANDUM\n\nTO: All Staff\nFROM: Director of Operations\nDATE: March 12 2024\nSUBJECT: Policy Update\n\n"
            "This memo outlines the updated travel reimbursement policy effective April 1 2024. "
            "All travel requests must be submitted at least five business days in advance. "
            "Economy class is required for domestic flights under four hours. "
            "Hotel accommodation is capped at $180 per night in standard markets. "
            "Receipts are required for all expenses exceeding $25.",
            "TRAVEL REIMBURSEMENT RATES\n\n"
            "Domestic Economy Airfare: Actual cost up to $450 per leg.\n"
            "International Economy Airfare: Actual cost up to $900 per leg.\n"
            "Ground Transportation: Actual cost, with taxi receipt required.\n"
            "Meals: $65 per diem for full travel days.\n"
            "Lodging: Actual cost up to $180 per night.\n\n"
            "Expenses must be submitted within 30 days of return. "
            "Late submissions may be denied at the discretion of the Finance department. "
            "Contact finance@company.org for questions regarding this policy.",
        ],
    },
    {
        "filename": "scanned_form_contract_002.pdf",
        "pages": [
            "SERVICE AGREEMENT\n\nThis Agreement is entered into as of January 15 2024\n"
            "between Acme Solutions LLC (Provider) and\nNorthstar Technologies Inc (Client).\n\n"
            "1. SERVICES\nProvider agrees to deliver software development services\n"
            "as described in Schedule A attached hereto.\n\n"
            "2. TERM\nThis Agreement commences January 15 2024 and continues\n"
            "for twelve months unless earlier terminated.\n\n"
            "3. PAYMENT\nClient shall pay Provider $12500 per month\n"
            "within fifteen days of invoice receipt.",
            "4. CONFIDENTIALITY\nEach party agrees to keep confidential all proprietary\n"
            "information of the other party disclosed during the term.\n\n"
            "5. INTELLECTUAL PROPERTY\nAll work product produced under this Agreement\n"
            "shall be the sole property of Client upon full payment.\n\n"
            "6. TERMINATION\nEither party may terminate with 30 days written notice.\n\n"
            "SIGNATURES\n\nProvider: _________________________  Date: ________\n"
            "Client:   _________________________  Date: ________",
        ],
    },
    {
        "filename": "scanned_report_003.pdf",
        "pages": [
            "QUARTERLY INSPECTION REPORT\n\nFacility: Building A - Main Campus\n"
            "Inspection Date: February 28 2024\nInspector: J. Rodriguez\nReport ID: INS-2024-0228-A\n\n"
            "SUMMARY OF FINDINGS\n\n"
            "The quarterly safety inspection was conducted on February 28 2024. "
            "Overall facility condition is satisfactory. Three minor deficiencies were identified. "
            "All deficiencies are classified as low severity and have been assigned for remediation.",
            "DEFICIENCY LOG\n\n"
            "Item 1: Fire extinguisher in Room 214 is past annual inspection date.\n"
            "Recommendation: Schedule inspection within 15 days.\n\n"
            "Item 2: Exit sign in north corridor has a failed lamp.\n"
            "Recommendation: Replace lamp immediately.\n\n"
            "Item 3: Handrail on stairwell B shows minor corrosion.\n"
            "Recommendation: Apply protective coating within 30 days.\n\n"
            "All other systems including HVAC electrical and plumbing were found to be\n"
            "in satisfactory condition. Next inspection is scheduled for May 31 2024.",
        ],
    },
]


def generate_searchable_image_pdfs() -> list[Path]:
    """
    Create PDFs that look like scanned documents: a white background image page
    with invisible (OCR-style) text overlaid via PyMuPDF's text insertion.
    Each page is first rendered as an image, then embedded back with the text
    layer preserved — mimicking a searchable scanned PDF.
    """
    import fitz  # PyMuPDF

    generated: list[Path] = []
    for doc_data in SEARCHABLE_TEXTS:
        dest = SEARCHABLE_DIR / doc_data["filename"]
        if dest.exists():
            print(f"  [skip] {dest.name} (already exists)")
            generated.append(dest)
            continue

        pdf = fitz.open()
        for page_text in doc_data["pages"]:
            page = pdf.new_page(width=595, height=842)  # A4

            # Step 1: Draw a slightly off-white background (simulates aged paper scan)
            page.draw_rect(
                fitz.Rect(0, 0, 595, 842), color=None, fill=(0.97, 0.96, 0.94)
            )

            # Step 2: Insert the visible text (dark grey simulating scanned ink)
            tw = fitz.TextWriter(page.rect)
            font = fitz.Font("helv")
            lines = page_text.split("\n")
            y = 60
            for line in lines:
                if not line.strip():
                    y += 12
                    continue
                font_size = 14 if line.isupper() and len(line) < 40 else 10
                tw.append((50, y), line, font=font, fontsize=font_size)
                y += font_size + 5
                if y > 800:
                    break
            tw.write_text(page)

            # Step 3: Render page to pixmap and embed as image (making it look scanned)
            mat = fitz.Matrix(1.5, 1.5)  # slight upscale for scan quality feel
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)

            # Step 4: Build new page with the image + re-overlaid invisible text
            img_page = pdf.new_page(width=595, height=842)
            img_rect = fitz.Rect(0, 0, 595, 842)
            img_page.insert_image(img_rect, pixmap=pix)

            # Re-insert invisible OCR-style text layer (in white, 0 opacity = searchable)
            # Using "render mode 3" means invisible text — standard searchable PDF technique
            for span_idx, line in enumerate(lines):
                if not line.strip():
                    continue
                font_size = 14 if line.isupper() and len(line) < 40 else 10
                y_pos = 60 + span_idx * (font_size + 5)
                if y_pos > 800:
                    break
                # Insert text at render mode 3 (invisible) — this is the OCR text layer
                img_page.insert_text(
                    (50, y_pos),
                    line,
                    fontname="helv",
                    fontsize=font_size,
                    color=(1, 1, 1),  # white = invisible over white bg
                    render_mode=3,  # 3 = invisible (clip path only), standard OCR layer trick
                )

            # Remove the intermediate draft page
            pdf.delete_page(-2)  # delete the draft page, keep the final image+text page

        pdf.save(str(dest))
        pdf.close()
        size_kb = dest.stat().st_size // 1024
        print(f"  [OK] {dest.name}  ({size_kb} KB, {len(doc_data['pages'])} pages)")
        generated.append(dest)

    return generated


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== Generating true_digital_pdf ===")
    td = generate_true_digital_pdfs()
    print(f"  → {len(td)} files in {TRUE_DIGITAL_DIR}")

    print("\n=== Generating searchable_image_pdf ===")
    si = generate_searchable_image_pdfs()
    print(f"  → {len(si)} files in {SEARCHABLE_DIR}")

    total = len(td) + len(si)
    print(f"\nDone. {total} PDF files ready.")
