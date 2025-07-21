"""Core modules for content loader."""

# Base classes and interfaces
from .base import (
    BaseExecutor,
    DateRange,
    SimpleMemoryManager,
    SimpleRetryHandler,
)

# Configuration
from .config import Settings

# Exceptions
from .exceptions import (
    AuthenticationError,
    AuthorizationError,
    CacheError,
    ChunkingError,
    ConcurrentExecutionError,
    ConfigurationError,
    ConfluenceError,
    ConfluencePageNotFoundError,
    ConfluenceSpaceNotFoundError,
    ContentLoaderError,
    DataSourceError,
    DataSourceNotFoundError,
    DataSourceUnavailableError,
    EmbeddingError,
    ExecutionError,
    GitHubAppAuthError,
    GitHubError,
    GitHubRepositoryNotFoundError,
    LoaderExecutionError,
    ProcessingError,
    RateLimitError,
    SlackChannelNotFoundError,
    SlackError,
    SlackPermissionError,
    SourceConfigurationError,
    StorageError,
    SummarizationError,
    TokenExpiredError,
    ValidationError,
    VectorStoreError,
    create_error_context,
    extract_retry_delay,
    is_retryable_error,
)

# Main executor
from .executor import LoaderExecutor

# Data models
from .models import (
    ChunkType,
    ConfluencePage,
    ContentType,
    Document,
    DocumentMetadata,
    GitHubFile,
    GitHubIssue,
    LoaderSource,
    ProcessedChunk,
    SlackMessage,
    SourceType,
)

__all__ = [
    # Base classes
    "BaseExecutor",
    "DateRange",
    "SimpleRetryHandler",
    "SimpleMemoryManager",
    # Data models
    "Document",
    "DocumentMetadata",
    "ProcessedChunk",
    "LoaderSource",
    "SourceType",
    "ContentType",
    "ChunkType",
    "SlackMessage",
    "GitHubIssue",
    "GitHubFile",
    "ConfluencePage",
    # Exceptions
    "ContentLoaderError",
    "ConfigurationError",
    "ValidationError",
    "SourceConfigurationError",
    "AuthenticationError",
    "AuthorizationError",
    "TokenExpiredError",
    "DataSourceError",
    "DataSourceUnavailableError",
    "DataSourceNotFoundError",
    "RateLimitError",
    "SlackError",
    "SlackChannelNotFoundError",
    "SlackPermissionError",
    "GitHubError",
    "GitHubRepositoryNotFoundError",
    "GitHubAppAuthError",
    "ConfluenceError",
    "ConfluenceSpaceNotFoundError",
    "ConfluencePageNotFoundError",
    "ProcessingError",
    "ChunkingError",
    "EmbeddingError",
    "SummarizationError",
    "StorageError",
    "VectorStoreError",
    "CacheError",
    "ExecutionError",
    "LoaderExecutionError",
    "ConcurrentExecutionError",
    "create_error_context",
    "is_retryable_error",
    "extract_retry_delay",
    # Main executor
    "LoaderExecutor",
    # Configuration
    "Settings",
]
