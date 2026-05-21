# -*- coding: utf-8 -*-
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from src.schema import DocumentChunk


SUPPORTED_SUFFIXES = {".txt", ".md", ".py", ".json", ".csv", ".log", ".pdf"}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="gbk", errors="ignore")


def _read_pdf_pages(path: Path) -> list[tuple[str, dict[str, Any]]]:
    try:
        import fitz
    except ImportError as exc:
        raise ImportError(
            "PDF parsing requires PyMuPDF. Install it with: pip install pymupdf"
        ) from exc

    pages: list[tuple[str, dict[str, Any]]] = []
    with fitz.open(str(path)) as pdf:
        for page_index, page in enumerate(pdf, start=1):
            text = page.get_text().strip()
            if not text:
                continue
            pages.append((text, {"page": page_index}))
    return pages


def _iter_file_sections(path: Path, root: Path) -> Iterator[tuple[str, str, dict[str, Any]]]:
    relative_path = str(path.relative_to(root))
    if path.suffix.lower() == ".pdf":
        for text, metadata in _read_pdf_pages(path):
            yield relative_path, text, metadata
        return

    yield relative_path, _read_text(path), {}


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[tuple[str, int, int]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be greater than or equal to 0.")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size.")

    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []

    chunks: list[tuple[str, int, int]] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        window = normalized[start:end]
        if end < len(normalized):
            split_at = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind("。"))
            if split_at >= chunk_size // 2:
                end = start + split_at + 1
                window = normalized[start:end]
        chunks.append((window.strip(), start, end))
        if end >= len(normalized):
            break
        start = max(0, end - chunk_overlap)
    return chunks


def load_knowledge_base(
    data_dir: str,
    chunk_size: int = 700,
    chunk_overlap: int = 100,
) -> list[DocumentChunk]:
    """Load local knowledge files and split them into metadata-rich chunks."""
    root = Path(data_dir)
    if not root.exists():
        raise FileNotFoundError(f"Knowledge directory not found: {data_dir}")

    chunks: list[DocumentChunk] = []
    paths = [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    ]

    for path in paths:
        for relative_path, text, section_metadata in _iter_file_sections(path, root):
            page = section_metadata.get("page")
            for chunk_index, (content, start, end) in enumerate(
                _split_text(text, chunk_size, chunk_overlap)
            ):
                chunk_id = (
                    f"{relative_path}:p{page}:c{chunk_index}"
                    if page is not None
                    else f"{relative_path}:c{chunk_index}"
                )
                metadata = {
                    "source": relative_path,
                    "chunk_id": chunk_id,
                    "chunk_index": len(chunks),
                    "chunk_in_file": chunk_index,
                    "char_start": start,
                    "char_end": end,
                    "length": len(content),
                    **section_metadata,
                }
                chunks.append(DocumentChunk(content=content, metadata=metadata))

    if not chunks:
        raise ValueError(f"No supported knowledge files found in {data_dir}.")
    return chunks
