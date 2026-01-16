# PDF Splitting for Large Document Processing

**Date:** 2026-01-16
**Status:** Approved

## Problem

MinerU crashes when processing large image-heavy PDFs (60-75MB, 200+ pages). The crash occurs in `load_images_from_pdf` which tries to parallelize image extraction across all pages simultaneously, exhausting system resources.

## Solution

Automatically split large PDFs into 50-page chunks before MinerU processing, then merge results transparently.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| When to split | Processing time | Keep original file intact, split temporarily |
| Split trigger | Page count (50 pages) | MinerU crashes on page processing, not file size |
| Result handling | Merge into single content list | Downstream code shouldn't know about splitting |
| Error handling | Fail whole document | Partial processing leaves knowledge gaps |

## Architecture

```
Upload PDF → Save to raw/ → RAGAnything.initialize() called
                                    ↓
                           Check page count > 50?
                                    ↓
                    No: Process normally with MinerU
                    Yes: Split → Process each chunk → Merge results
                                    ↓
                           Clean up temp chunk files
                                    ↓
                           Return merged content list
```

The splitting is invisible to upstream (upload API) and downstream (knowledge graph indexing) code. Only the RAGAnything pipeline knows about it.

## New File: `src/utils/pdf_splitter.py`

```python
from pathlib import Path
from typing import List

class PDFSplitter:
    DEFAULT_CHUNK_SIZE = 50  # pages per chunk

    @staticmethod
    def needs_splitting(pdf_path: Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> bool:
        """Check if PDF exceeds page threshold."""

    @staticmethod
    def split(
        pdf_path: Path,
        output_dir: Path,
        chunk_size: int = DEFAULT_CHUNK_SIZE
    ) -> List[Path]:
        """Split PDF into chunks, return list of chunk file paths.

        Output files named: {original_stem}_chunk001.pdf, _chunk002.pdf, etc.
        Raises PDFSplitError if splitting fails.
        """

    @staticmethod
    def get_page_count(pdf_path: Path) -> int:
        """Return total page count of PDF."""
```

**Dependencies:** `pypdf` (already available)

**Temp file location:** `{kb_path}/.tmp_chunks/{document_name}/`

## Pipeline Integration

**Modified file:** `src/services/rag/pipelines/raganything.py`

```python
from src.utils.pdf_splitter import PDFSplitter

async def initialize(self, kb_name: str, file_paths: List[str], **kwargs):
    # ... existing setup code ...

    for file_path in file_paths:
        path = Path(file_path)

        if path.suffix.lower() == '.pdf' and PDFSplitter.needs_splitting(path):
            tmp_dir = kb_dir / ".tmp_chunks" / path.stem
            tmp_dir.mkdir(parents=True, exist_ok=True)

            try:
                chunk_paths = PDFSplitter.split(path, tmp_dir)

                all_content = []
                for chunk_path in chunk_paths:
                    content = await rag.process_document_complete(chunk_path)
                    all_content.extend(content)

                self._save_merged_content(kb_name, path.name, all_content)

            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
        else:
            await rag.process_document_complete(file_path)
```

## Content Merging

Each chunk produces content with page numbers relative to that chunk. Merging adjusts page references to reflect the original PDF.

```python
def _merge_chunk_content(
    chunk_contents: List[List[Dict]],
    chunk_size: int = 50
) -> List[Dict]:
    """Merge content from multiple chunks, adjusting page numbers."""
    merged = []

    for chunk_idx, content_list in enumerate(chunk_contents):
        page_offset = chunk_idx * chunk_size

        for item in content_list:
            adjusted_item = item.copy()

            if 'page' in adjusted_item:
                adjusted_item['page'] += page_offset
            if 'page_number' in adjusted_item:
                adjusted_item['page_number'] += page_offset

            merged.append(adjusted_item)

    return merged
```

## Logging

```python
logger.info(f"PDF '{pdf_path.name}' has {page_count} pages, splitting into {num_chunks} chunks")
logger.debug(f"Processing chunk {i+1}/{num_chunks}: {chunk_path.name}")
logger.info(f"Successfully merged {len(all_content)} content items from {num_chunks} chunks")
```

Progress tracker updated to show: `"Processing large PDF: chunk 2/6 (pages 51-100)"`

## Files Changed

| File | Change |
|------|--------|
| `src/utils/pdf_splitter.py` | New file - splitting utility |
| `src/services/rag/pipelines/raganything.py` | Integrate splitter before MinerU calls |

## No Changes To

- Upload API
- Document validator (size limits stay at 100MB)
- Knowledge graph indexing
- Frontend
