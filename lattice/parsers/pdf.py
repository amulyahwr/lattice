"""PDF text extraction and segmentation for Lattice.

Uses pypdf (pure Python, no system deps). Install via:
    uv sync --group pdf

Image-only PDFs produce no text — logged as a warning, not an error.
Page boundaries are preserved using \f (form feed) so downstream parsers
can split by page without ambiguity with paragraph breaks.
"""
from __future__ import annotations

import logging

from lattice.parsers import Segment, _parse_plain

log = logging.getLogger("lattice.parsers.pdf")


def extract_pdf_text(path: str) -> str:
    """Extract plain text from a PDF file. Pages separated by \\f (form feed).

    Returns empty string on image-only PDFs.
    """
    try:
        import pypdf
    except ImportError:
        raise ImportError(
            "pypdf is required for PDF ingest. Install it with: uv sync --group pdf"
        )

    pages: list[str] = []
    with open(path, "rb") as f:
        reader = pypdf.PdfReader(f)
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text.strip())

    return "\f".join(p for p in pages if p)


def parse_pdf_text(text: str, max_chars: int) -> list[Segment]:
    """Segment already-extracted PDF text (pages separated by \\f) into Segments.

    Each page becomes one segment with context='page N'. Pages exceeding
    max_chars are split further via _parse_plain.
    """
    pages = [p.strip() for p in text.split("\f") if p.strip()]
    if not pages:
        return []

    segments: list[Segment] = []
    char_pos = 0
    for i, page_text in enumerate(pages):
        context = f"page {i + 1}"
        if len(page_text) > max_chars:
            for part in _parse_plain(page_text, "pdf", max_chars):
                segments.append(Segment(
                    f"s{len(segments)}", part.text, "pdf",
                    char_pos + part.start, char_pos + part.end, context=context,
                ))
        else:
            segments.append(Segment(
                f"s{len(segments)}", page_text, "pdf",
                char_pos, char_pos + len(page_text), context=context,
            ))
        char_pos += len(page_text) + 1  # +1 for \f
    return segments


def parse_pdf(path: str, max_chars: int) -> list[Segment]:
    """Parse a PDF file into Segments. Page breaks become segment boundaries.

    Returns an empty list (with a warning) for image-only PDFs.
    """
    text = extract_pdf_text(path)
    if not text.strip():
        log.warning("pdf: no text extracted from %s — may be image-only, skipping", path)
        return []
    return parse_pdf_text(text, max_chars)
