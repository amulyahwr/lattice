"""Base connector interface — all connectors implement this."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class IngestedChunk:
    """A chunk of content ready for embedding and storage."""

    content: str
    chunk_index: int
    metadata: dict | None = None


class BaseConnector(ABC):
    """Interface that all Lattice connectors must implement."""

    @abstractmethod
    async def ingest(self, **kwargs) -> list[IngestedChunk]:
        """
        Ingest data from the source and return chunks.

        Each connector defines its own kwargs (file path, connection string, etc.)
        """
        ...

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the source type identifier (e.g., 'pdf', 'postgres')."""
        ...
