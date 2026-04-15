"""
src/pdf_research_pipeline/downloader/funsd.py

FUNSD form dataset downloader.

Source: https://guillaumejaume.github.io/FUNSD/
Download: https://guillaumejaume.github.io/FUNSD/dataset.zip

Decision: FUNSD provides scanned form images (PNG), not PDFs.
We download the ZIP, extract the images, and convert each scanned form image
to a single-page PDF using PIL/Pillow so the rest of the pipeline can
process them uniformly.

This matches the prompt.md guidance: forms_interactive_pdf type.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any, Iterator

import requests

from pdf_research_pipeline.downloader.base import BaseDownloader, DownloadCandidate
from pdf_research_pipeline.logging_utils import get_logger
from pdf_research_pipeline.utils.files import ensure_dir

logger = get_logger(__name__)

_FUNSD_ZIP_URL = "https://guillaumejaume.github.io/FUNSD/dataset.zip"


class FUNSDDownloader(BaseDownloader):
    """
    Downloads the FUNSD form dataset and converts images to single-page PDFs.

    Since FUNSD provides PNG images, each image is wrapped in a PDF so that
    all downstream parsers (and OCR) can process them uniformly.
    """

    source_name = "funsd"

    def list_candidates(self) -> Iterator[DownloadCandidate]:
        """
        FUNSD is a single ZIP download, not individual PDF URLs.
        We download and extract it in run(), then yield candidates from extracted images.
        """
        # Download the ZIP first
        zip_path = self._download_zip()
        if zip_path is None:
            return

        # Extract and convert images to PDFs, yielding empty candidates
        # (actual files are created directly here since they come from a ZIP)
        yield from self._extract_and_convert(zip_path)

    def _download_zip(self) -> Path | None:
        """Download FUNSD dataset ZIP to a temp location."""
        zip_url = self.config.get("download_url", _FUNSD_ZIP_URL)
        dest_dir = ensure_dir(self.raw_root / "forms_interactive_pdf" / "funsd")
        zip_path = dest_dir / "funsd_dataset.zip"

        if zip_path.exists():
            logger.info(
                "funsd_zip_exists",
                event_type="funsd_zip_exists",
                stage="download",
                log_category="download",
                source_name=self.source_name,
                local_path=str(zip_path),
                observation="ZIP already downloaded — skipping",
                decision="skip",
                status="skipped",
            )
            return zip_path

        logger.info(
            "funsd_zip_download",
            event_type="funsd_zip_download",
            stage="download",
            log_category="download",
            source_name=self.source_name,
            source_url=zip_url,
            status="downloading",
        )

        try:
            self._stream_download(zip_url, zip_path)
            logger.info(
                "funsd_zip_downloaded",
                event_type="funsd_zip_downloaded",
                stage="download",
                log_category="download",
                source_name=self.source_name,
                local_path=str(zip_path),
                status="completed",
            )
            return zip_path
        except Exception as exc:
            logger.error(
                "funsd_zip_failed",
                event_type="funsd_zip_failed",
                stage="download",
                log_category="errors",
                source_name=self.source_name,
                error_message=str(exc),
                status="failed",
            )
            return None

    def _extract_and_convert(self, zip_path: Path) -> Iterator[DownloadCandidate]:
        """
        Extract PNG images from FUNSD ZIP and convert to single-page PDFs.
        Yields DownloadCandidate for each converted PDF.
        """
        try:
            from PIL import Image  # type: ignore[import]
        except ImportError:
            logger.error(
                "funsd_pillow_missing",
                event_type="funsd_pillow_missing",
                stage="download",
                log_category="errors",
                source_name=self.source_name,
                error_message="Pillow not installed — cannot convert FUNSD images to PDF",
                status="failed",
            )
            return

        dest_dir = self.raw_root / "forms_interactive_pdf" / "funsd"
        converted = 0

        with zipfile.ZipFile(zip_path, "r") as zf:
            png_files = [
                name for name in zf.namelist() if name.lower().endswith(".png")
            ]

            logger.info(
                "funsd_images_found",
                event_type="funsd_images_found",
                stage="download",
                log_category="download",
                source_name=self.source_name,
                image_count=len(png_files),
                status="processing",
            )

            for img_name in png_files[: self.limit_per_type]:
                pdf_name = Path(img_name).stem + ".pdf"
                pdf_path = dest_dir / pdf_name

                if pdf_path.exists():
                    yield DownloadCandidate(
                        url=_FUNSD_ZIP_URL,
                        filename=pdf_name,
                        pdf_type="forms_interactive_pdf",
                        source_name=self.source_name,
                        subfolder="funsd",
                        extra={"original_image": img_name},
                    )
                    converted += 1
                    continue

                try:
                    img_data = zf.read(img_name)
                    img = Image.open(io.BytesIO(img_data))
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    img.save(str(pdf_path), "PDF", resolution=150)

                    logger.info(
                        "funsd_image_converted",
                        event_type="funsd_image_converted",
                        stage="download",
                        log_category="download",
                        source_name=self.source_name,
                        original_image=img_name,
                        pdf_path=str(pdf_path),
                        status="converted",
                    )

                    yield DownloadCandidate(
                        url=_FUNSD_ZIP_URL,
                        filename=pdf_name,
                        pdf_type="forms_interactive_pdf",
                        source_name=self.source_name,
                        subfolder="funsd",
                        extra={"original_image": img_name},
                    )
                    converted += 1

                except Exception as exc:
                    logger.warning(
                        "funsd_conversion_error",
                        event_type="funsd_conversion_error",
                        stage="download",
                        log_category="errors",
                        source_name=self.source_name,
                        original_image=img_name,
                        error_message=str(exc),
                        status="failed",
                    )

        logger.info(
            "funsd_conversion_complete",
            event_type="funsd_conversion_complete",
            stage="download",
            log_category="download",
            source_name=self.source_name,
            converted_count=converted,
            status="completed",
        )

    def download_one(self, candidate: DownloadCandidate) -> Any:
        """
        Override: FUNSD files are already created during list_candidates().
        Just build and return metadata.
        """
        dest_dir = self.raw_root / candidate.pdf_type / candidate.subfolder
        dest_path = dest_dir / candidate.filename

        if not dest_path.exists():
            return None

        from pdf_research_pipeline.utils.hashing import sha256_file
        from pdf_research_pipeline.utils.metadata import append_to_catalog_jsonl

        checksum = sha256_file(dest_path)
        meta = self._build_metadata(candidate, dest_path, checksum)
        append_to_catalog_jsonl(self.catalog_path, meta)
        return meta
