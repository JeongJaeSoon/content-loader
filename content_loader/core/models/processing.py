"""Processing-related models for Content Loader.

This module defines models used in document processing, chunking,
and embedding preparation stages.
"""

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .base import ChunkType, DocumentMetadata


@dataclass
class ProcessedChunk:
    """Processed document chunk ready for embedding."""

    id: str  # Unique chunk identifier
    text: str
    chunk_type: ChunkType
    chunk_index: int  # Index within the original document

    # References
    document_id: str
    source_metadata: DocumentMetadata

    # Processing metadata
    start_line: Optional[int] = None  # For code chunks
    end_line: Optional[int] = None  # For code chunks
    node_type: Optional[str] = None  # AST node type for code
    content_hash: Optional[str] = None

    def __post_init__(self) -> None:
        """Post-initialization processing."""
        if not self.content_hash:
            self.content_hash = self._generate_content_hash()

    def _generate_content_hash(self) -> str:
        """Generate hash for this chunk."""
        content = f"{self.text}|{self.document_id}|{self.chunk_index}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_vector_payload(self) -> Dict[str, Any]:
        """Convert to payload format for vector database."""
        payload = {
            "chunk_id": self.id,
            "text": self.text,
            "chunk_type": self.chunk_type.value,
            "chunk_index": self.chunk_index,
            "document_id": self.document_id,
            "content_hash": self.content_hash,
        }

        # Add source metadata
        payload.update(self.source_metadata.to_dict())

        # Add code-specific metadata if available
        if self.start_line is not None:
            payload["start_line"] = self.start_line
        if self.end_line is not None:
            payload["end_line"] = self.end_line
        if self.node_type:
            payload["node_type"] = self.node_type

        return payload
