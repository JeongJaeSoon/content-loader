"""Core data models for Content Loader.

This module defines the common data structures used across all loaders,
including Document, DocumentMetadata, and content-specific models.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class SourceType(Enum):
    """Supported data source types."""

    SLACK = "slack"
    GITHUB = "github"
    CONFLUENCE = "confluence"


class ContentType(Enum):
    """Content type classification for processing strategy."""

    SOURCE_CODE = "source_code"
    DOCUMENTATION = "documentation"
    CONVERSATION = "conversation"
    MIXED_CONTENT = "mixed_content"


class ChunkType(Enum):
    """Type of processed chunk."""

    ORIGINAL = "original"
    SUMMARY = "summary"


@dataclass
class DocumentMetadata:
    """Metadata associated with a document."""

    # Source information
    source_type: SourceType
    source_id: str  # Unique identifier from source system
    source_url: Optional[str] = None

    # Content classification
    content_type: Optional[ContentType] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Source-specific metadata
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary for serialization."""
        result = {
            "source_type": self.source_type.value,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "content_type": (self.content_type.value if self.content_type else None),
            "created_at": (self.created_at.isoformat() if self.created_at else None),
            "updated_at": (self.updated_at.isoformat() if self.updated_at else None),
        }
        result.update(self.extra)
        return result


@dataclass
class Document:
    """Core document structure used across all loaders."""

    id: str  # Unique document identifier
    title: str
    text: str
    metadata: DocumentMetadata

    # Optional fields
    url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Post-initialization processing."""
        # Sync timestamps with metadata if not set
        if not self.created_at and self.metadata.created_at:
            self.created_at = self.metadata.created_at
        if not self.updated_at and self.metadata.updated_at:
            self.updated_at = self.metadata.updated_at

    def generate_hash(self) -> str:
        """Generate content hash for deduplication."""
        content = f"{self.title}|{self.text}|{self.metadata.source_id}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Convert document to dictionary for serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "text": self.text,
            "url": self.url,
            "created_at": (self.created_at.isoformat() if self.created_at else None),
            "updated_at": (self.updated_at.isoformat() if self.updated_at else None),
            "metadata": self.metadata.to_dict(),
            "content_hash": self.generate_hash(),
        }


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


# Source-specific models


@dataclass
class SlackMessage(Document):
    """Slack-specific message document."""

    def __init__(
        self,
        id: str,
        title: str,
        text: str,
        metadata: DocumentMetadata,
        channel_id: str,
        user_id: str,
        thread_ts: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(id, title, text, metadata, **kwargs)

        # Add Slack-specific metadata
        self.metadata.extra.update(
            {
                "channel_id": channel_id,
                "user_id": user_id,
                "thread_ts": thread_ts,
                "is_thread_reply": thread_ts is not None,
            }
        )


@dataclass
class GitHubIssue(Document):
    """GitHub issue document."""

    def __init__(
        self,
        id: str,
        title: str,
        text: str,
        metadata: DocumentMetadata,
        repository: str,
        issue_number: int,
        state: str,
        labels: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(id, title, text, metadata, **kwargs)

        # Add GitHub-specific metadata
        self.metadata.extra.update(
            {
                "repository": repository,
                "issue_number": issue_number,
                "state": state,
                "labels": labels or [],
            }
        )


@dataclass
class GitHubFile(Document):
    """GitHub file document."""

    def __init__(
        self,
        id: str,
        title: str,
        text: str,
        metadata: DocumentMetadata,
        repository: str,
        file_path: str,
        branch: str = "main",
        file_size: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(id, title, text, metadata, **kwargs)

        # Add GitHub file metadata
        self.metadata.extra.update(
            {
                "repository": repository,
                "file_path": file_path,
                "branch": branch,
                "file_size": file_size,
            }
        )


@dataclass
class ConfluencePage(Document):
    """Confluence page document."""

    def __init__(
        self,
        id: str,
        title: str,
        text: str,
        metadata: DocumentMetadata,
        space_key: str,
        page_id: str,
        version: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(id, title, text, metadata, **kwargs)

        # Add Confluence-specific metadata
        self.metadata.extra.update(
            {"space_key": space_key, "page_id": page_id, "version": version}
        )


@dataclass
class LoaderSource:
    """Configuration for a specific data source."""

    source_type: SourceType
    source_key: str  # Unique identifier for this source configuration
    name: str
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_type": self.source_type.value,
            "source_key": self.source_key,
            "name": self.name,
            "enabled": self.enabled,
            "config": self.config,
        }
