"""
PDF Splitter Utility
====================

Splits large PDFs into smaller chunks for processing by MinerU,
which can crash on very large image-heavy documents.
"""

import shutil
from pathlib import Path
from typing import List

from pypdf import PdfReader, PdfWriter

from src.logging import get_logger

logger = get_logger("PDFSplitter")


class PDFSplitError(Exception):
    """Raised when PDF splitting fails."""

    pass


class PDFSplitter:
    """Utility for splitting large PDFs into manageable chunks."""

    DEFAULT_CHUNK_SIZE = 50  # pages per chunk

    @staticmethod
    def get_page_count(pdf_path: Path) -> int:
        """Return total page count of PDF."""
        try:
            reader = PdfReader(pdf_path)
            return len(reader.pages)
        except Exception as e:
            raise PDFSplitError(f"Failed to read PDF '{pdf_path.name}': {e}") from e

    @staticmethod
    def needs_splitting(pdf_path: Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> bool:
        """Check if PDF exceeds page threshold."""
        try:
            page_count = PDFSplitter.get_page_count(pdf_path)
            return page_count > chunk_size
        except PDFSplitError:
            return False

    @staticmethod
    def split(
        pdf_path: Path,
        output_dir: Path,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> List[Path]:
        """
        Split PDF into chunks.

        Args:
            pdf_path: Path to the PDF file
            output_dir: Directory to write chunk files
            chunk_size: Maximum pages per chunk

        Returns:
            List of paths to chunk files, ordered by page range

        Raises:
            PDFSplitError: If splitting fails
        """
        try:
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)

            if total_pages <= chunk_size:
                raise PDFSplitError(
                    f"PDF has {total_pages} pages, no splitting needed (threshold: {chunk_size})"
                )

            output_dir.mkdir(parents=True, exist_ok=True)
            chunk_paths: List[Path] = []
            num_chunks = (total_pages + chunk_size - 1) // chunk_size

            logger.info(
                f"PDF '{pdf_path.name}' has {total_pages} pages, splitting into {num_chunks} chunks"
            )

            for chunk_idx in range(num_chunks):
                start_page = chunk_idx * chunk_size
                end_page = min(start_page + chunk_size, total_pages)

                writer = PdfWriter()
                for page_num in range(start_page, end_page):
                    writer.add_page(reader.pages[page_num])

                chunk_filename = f"{pdf_path.stem}_chunk{chunk_idx + 1:03d}.pdf"
                chunk_path = output_dir / chunk_filename

                with open(chunk_path, "wb") as f:
                    writer.write(f)

                chunk_paths.append(chunk_path)
                logger.debug(
                    f"Created chunk {chunk_idx + 1}/{num_chunks}: {chunk_filename} "
                    f"(pages {start_page + 1}-{end_page})"
                )

            return chunk_paths

        except PDFSplitError:
            raise
        except Exception as e:
            raise PDFSplitError(f"Failed to split PDF '{pdf_path.name}': {e}") from e

    @staticmethod
    def cleanup_chunks(output_dir: Path) -> None:
        """Remove chunk directory and all contents."""
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)
            logger.debug(f"Cleaned up chunk directory: {output_dir}")
