"""Plain text / Markdown connector — ingests raw text and markdown files."""

from backend.connectors.base import BaseConnector, IngestedChunk

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200


class TextConnector(BaseConnector):
    """Ingest plain text or markdown files into chunks."""

    @property
    def source_type(self) -> str:
        return "text"

    async def ingest(
        self,
        file_bytes: bytes | None = None,
        file_path: str | None = None,
        text: str | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> list[IngestedChunk]:
        """Extract text and split into overlapping chunks.

        Accepts raw text, file bytes, or a file path.
        """
        if text:
            full_text = text
        elif file_bytes:
            full_text = file_bytes.decode("utf-8", errors="replace")
        elif file_path:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                full_text = f.read()
        else:
            raise ValueError("Provide text, file_bytes, or file_path")

        full_text = full_text.strip()
        if not full_text:
            return []

        # Split into overlapping chunks
        chunks: list[IngestedChunk] = []
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


class MarkdownConnector(TextConnector):
    """Ingest markdown files (same as text, different source_type tag)."""

    @property
    def source_type(self) -> str:
        return "markdown"
