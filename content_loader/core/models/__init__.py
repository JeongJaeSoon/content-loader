"""Content Loader models package.

This package contains all data models used throughout the content loader
system, organized by functionality:

- base: Core models, enums, and base classes
- source: Source-specific document models
- processing: Document processing and chunking models
"""

# Import all models for convenient access
from .base import (
    ChunkType,
    ContentType,
    Document,
    DocumentMetadata,
    LoaderSource,
    SourceType,
)
from .processing import ProcessedChunk
from .source import ConfluencePage, GitHubFile, GitHubIssue, SlackMessage

# Re-export all models
__all__ = [
    # Base models and enums
    "SourceType",
    "ContentType",
    "ChunkType",
    "DocumentMetadata",
    "Document",
    "LoaderSource",
    # Processing models
    "ProcessedChunk",
    # Source-specific models
    "SlackMessage",
    "GitHubIssue",
    "GitHubFile",
    "ConfluencePage",
]
