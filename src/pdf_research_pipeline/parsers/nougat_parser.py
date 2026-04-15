"""
src/pdf_research_pipeline/parsers/nougat_parser.py

Nougat scientific PDF parser adapter.

Decision: Nougat (Neural Optical Understanding for Academic Documents) is
a transformer-based parser designed for scientific PDFs with equations,
figures, and complex formatting. It is the best option for arXiv-style
papers when practical.

Per prompt.md section 13: For difficult layout-heavy scientific documents,
test learning-based approaches such as Nougat.

Installation: pip install nougat-ocr  (not in default requirements.txt)

TODO: This adapter requires `nougat-ocr` to be installed separately.
      It also requires significant VRAM for GPU inference.
"""

from __future__ import annotations

from pathlib import Path

from pdf_research_pipeline.parsers.base import BaseParser, PageResult, ParseResult


class NougatParser(BaseParser):
    """
    Scientific PDF extraction using Nougat.

    Best for:
      - arXiv papers with equations
      - Patents with mixed math/text
      - Academic PDFs with complex figure/table layout

    Requires: pip install nougat-ocr
    """

    parser_name = "nougat"
    library_name = "nougat-ocr"

    def _parse_impl(self, path: Path) -> ParseResult:
        try:
            from nougat import NougatModel  # type: ignore[import]
            from nougat.utils.checkpoint import get_checkpoint  # type: ignore[import]
            from nougat.utils.dataset import LazyDataset  # type: ignore[import]
        except ImportError:
            raise RuntimeError(
                "nougat-ocr is not installed. "
                "Install it with: pip install nougat-ocr\n"
                "Then re-enable it in configs/parsers.yaml"
            )

        import torch  # type: ignore[import]
        import fitz  # type: ignore[import]
        import numpy as np  # type: ignore[import]
        from PIL import Image  # type: ignore[import]
        import tempfile

        # Load Nougat checkpoint (downloads on first run)
        checkpoint = get_checkpoint(model_tag="0.1.0-small")
        model = NougatModel.from_pretrained(checkpoint)
        model = model.to(torch.bfloat16)
        if torch.cuda.is_available():
            model = model.to("cuda")
        model.eval()

        # Render PDF pages with PyMuPDF → pass through Nougat
        pdf_doc = fitz.open(str(path))
        dpi = self.config.get("dpi", 96)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        all_pages: list[PageResult] = []
        all_text_parts: list[str] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            for page_num in range(len(pdf_doc)):
                fitz_page = pdf_doc[page_num]
                pix = fitz_page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
                img_path = tmp_path / f"page_{page_num:04d}.png"
                pix.save(str(img_path))

                img = Image.open(img_path).convert("RGB")
                model_input = model.encoder.prepare_input(img, random_padding=False)
                model_input = model_input.unsqueeze(0)
                if torch.cuda.is_available():
                    model_input = model_input.to("cuda")

                with torch.no_grad():
                    output = model.inference(
                        image_tensors=model_input,
                        early_stopping=True,
                    )

                page_text: str = ""
                if output and output.get("predictions"):
                    page_text = output["predictions"][0] or ""

                all_text_parts.append(page_text)
                all_pages.append(
                    PageResult(
                        page_number=page_num + 1,
                        raw_text=page_text,
                        markdown=page_text,
                        width=float(fitz_page.rect.width),
                        height=float(fitz_page.rect.height),
                        is_empty=not bool(page_text.strip()),
                    )
                )

        pdf_doc.close()
        full_text = "\n\n".join(all_text_parts)
        return ParseResult(
            pdf_id="",
            pdf_type="",
            parser_name=self.parser_name,
            pages=all_pages,
            page_count_detected=len(all_pages),
            raw_text_full=full_text,
            status="completed",
        )
