"""PDF text extraction for Lattice inbox.

Uses pypdf (pure Python, no system deps). Install via:
    uv sync --group pdf

Image-only PDFs produce no text — logged as a warning, not an error.
"""
from __future__ import annotations

import logging

from lattice.parsers import Segment, _parse_plain

log = logging.getLogger("lattice.parsers.pdf")


def extract_pdf_text(path: str) -> str:
    """Extract plain text from a PDF file. Returns empty string on image-only PDFs."""
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

    return "\n\n".join(p for p in pages if p)


def parse_pdf(path: str, max_chars: int) -> list[Segment]:
    """Parse a PDF file into Segment list. Page breaks become segment boundaries.

    Returns an empty list (with a warning) for image-only PDFs.
    """
    text = extract_pdf_text(path)

    if not text.strip():
        log.warning("pdf: no text extracted from %s — may be image-only, skipping", path)
        return []

    # Split on double-newlines (page breaks) and treat each page as a context chunk
    import re
    pages = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    if not pages:
        return []

    segments: list[Segment] = []
    char_pos = 0
    for i, page_text in enumerate(pages):
        context = f"page {i + 1}"
        if len(page_text) > max_chars:
            for part in _parse_plain(page_text, "plain", max_chars):
                segments.append(Segment(
                    f"s{len(segments)}", part.text, "plain",
                    char_pos + part.start, char_pos + part.end, context=context,
                ))
        else:
            segments.append(Segment(
                f"s{len(segments)}", page_text, "plain",
                char_pos, char_pos + len(page_text), context=context,
            ))
        char_pos += len(page_text) + 2  # +2 for the \n\n separator

    return segments
