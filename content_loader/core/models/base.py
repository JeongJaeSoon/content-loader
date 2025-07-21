"""Base data models and enums for Content Loader.

This module defines the core data structures used across all loaders,
including enums, DocumentMetadata, and the base Document class.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


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

    TEXT = "text"
    CODE = "code"
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
