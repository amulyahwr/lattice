"""PDF connector — extracts text from PDFs and chunks it."""

import io

from pypdf import PdfReader

from backend.connectors.base import BaseConnector, IngestedChunk

# Default chunk size in characters
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200


class PDFConnector(BaseConnector):
    """Ingest PDF files into chunks."""

    @property
    def source_type(self) -> str:
        return "pdf"

    async def ingest(
        self,
        file_bytes: bytes | None = None,
        file_path: str | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> list[IngestedChunk]:
        """Extract text from a PDF and split into overlapping chunks."""
        if file_bytes:
            reader = PdfReader(io.BytesIO(file_bytes))
        elif file_path:
            reader = PdfReader(file_path)
        else:
            raise ValueError("Provide either file_bytes or file_path")

        # Extract all text
        full_text = ""
        for page_num, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            full_text += f"\n{page_text}"

        # Split into overlapping chunks
        chunks = []
        start = 0
        index = 0
        while start < len(full_text):
            end = start + chunk_size
            chunk_text = full_text[start:end].strip()
            if chunk_text:
                chunks.append(
                    IngestedChunk(
                        content=chunk_text,
                        chunk_index=index,
                        metadata={"char_start": start, "char_end": end},
                    )
                )
                index += 1
            start += chunk_size - chunk_overlap

        return chunks
