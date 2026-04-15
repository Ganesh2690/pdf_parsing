import os
import sys

sys.path.insert(0, "src")
os.chdir("d:/Projects/pdf/pdf_research_pipeline")

from pdf_research_pipeline.parsers.easyocr_parser import EasyOCRParser
from pathlib import Path

pdfs = list(Path("data/raw").rglob("*.pdf"))
if not pdfs:
    print("No PDFs found")
    sys.exit(1)

p = pdfs[0]
print(f"Testing with: {p}")
parser = EasyOCRParser(
    parsed_root="data/parsed", config={"lang": ["en"], "gpu": False, "dpi": 150}
)
result = parser.run(path=p, pdf_id="test", pdf_type="complex_layout_pdf")
print(f"Status: {result.status}")
print(f"Pages: {result.page_count_detected}")
chars = len(result.raw_text_full or "")
print(f"Chars: {chars}")
if result.errors:
    print(f"Errors: {result.errors[:2]}")
else:
    preview = (result.raw_text_full or "")[:200]
    print(f"Text preview: {preview}")
