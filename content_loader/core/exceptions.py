"""Custom exceptions for Content Loader.

This module defines all custom exceptions used throughout the application,
organized by category and with clear error messages for debugging.
"""

from typing import Any, Dict, List, Optional


class ContentLoaderError(Exception):
    """Base exception for all Content Loader errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize exception with message and optional details.

        Args:
            message: Error message
            details: Optional dictionary with additional error context
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        """String representation of the error."""
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


# Configuration and validation errors


class ConfigurationError(ContentLoaderError):
    """Raised when there's an issue with configuration."""

    pass


class ValidationError(ContentLoaderError):
    """Raised when data validation fails."""

    pass


class SourceConfigurationError(ConfigurationError):
    """Raised when source-specific configuration is invalid."""

    def __init__(
        self, source_type: str, source_key: str, message: str, **kwargs: Any
    ) -> None:
        details = {"source_type": source_type, "source_key": source_key}
        details.update(kwargs)
        super().__init__(
            f"Configuration error for {source_type}:{source_key} - {message}",
            details,
        )


# Authentication and authorization errors


class AuthenticationError(ContentLoaderError):
    """Raised when authentication fails."""

    pass


class AuthorizationError(ContentLoaderError):
    """Raised when authorization fails (insufficient permissions)."""

    pass


class TokenExpiredError(AuthenticationError):
    """Raised when an authentication token has expired."""

    pass


# Data source errors


class DataSourceError(ContentLoaderError):
    """Base class for data source related errors."""

    def __init__(self, source_type: str, message: str, **kwargs: Any) -> None:
        details = {"source_type": source_type}
        details.update(kwargs)
        super().__init__(f"{source_type} error: {message}", details)


class DataSourceUnavailableError(DataSourceError):
    """Raised when a data source is temporarily unavailable."""

    pass


class DataSourceNotFoundError(DataSourceError):
    """Raised when a requested resource is not found."""

    pass


class RateLimitError(DataSourceError):
    """Raised when API rate limit is exceeded."""

    def __init__(
        self,
        source_type: str,
        retry_after: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        details = {"retry_after": retry_after}
        details.update(kwargs)
        message = "Rate limit exceeded"
        if retry_after:
            message += f", retry after {retry_after} seconds"
        super().__init__(source_type, message, **details)


# Slack-specific errors


class SlackError(DataSourceError):
    """Base class for Slack-specific errors."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__("slack", message, **kwargs)


class SlackChannelNotFoundError(SlackError):
    """Raised when a Slack channel is not found or not accessible."""

    def __init__(self, channel_id: str, **kwargs: Any) -> None:
        super().__init__(
            f"Channel not found or not accessible: {channel_id}",
            channel_id=channel_id,
            **kwargs,
        )


class SlackPermissionError(SlackError):
    """Raised when bot lacks necessary permissions."""

    def __init__(self, required_scope: str, **kwargs: Any) -> None:
        super().__init__(
            f"Missing required scope: {required_scope}",
            required_scope=required_scope,
            **kwargs,
        )


# GitHub-specific errors


class GitHubError(DataSourceError):
    """Base class for GitHub-specific errors."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__("github", message, **kwargs)


class GitHubRepositoryNotFoundError(GitHubError):
    """Raised when a GitHub repository is not found or not accessible."""

    def __init__(self, repository: str, **kwargs: Any) -> None:
        super().__init__(
            f"Repository not found or not accessible: {repository}",
            repository=repository,
            **kwargs,
        )


class GitHubAppAuthError(GitHubError):
    """Raised when GitHub App authentication fails."""

    def __init__(
        self,
        app_id: Optional[str] = None,
        installation_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        details = {}
        if app_id:
            details["app_id"] = app_id
        if installation_id:
            details["installation_id"] = installation_id
        super().__init__("GitHub App authentication failed", **details, **kwargs)


# Confluence-specific errors


class ConfluenceError(DataSourceError):
    """Base class for Confluence-specific errors."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__("confluence", message, **kwargs)


class ConfluenceSpaceNotFoundError(ConfluenceError):
    """Raised when a Confluence space is not found or not accessible."""

    def __init__(self, space_key: str, **kwargs: Any) -> None:
        super().__init__(
            f"Space not found or not accessible: {space_key}",
            space_key=space_key,
            **kwargs,
        )


class ConfluencePageNotFoundError(ConfluenceError):
    """Raised when a Confluence page is not found."""

    def __init__(self, page_id: str, **kwargs: Any) -> None:
        super().__init__(f"Page not found: {page_id}", page_id=page_id, **kwargs)


# Processing errors


class ProcessingError(ContentLoaderError):
    """Base class for document processing errors."""

    pass


class ChunkingError(ProcessingError):
    """Raised when document chunking fails."""

    def __init__(self, document_id: str, message: str, **kwargs: Any) -> None:
        details = {"document_id": document_id}
        details.update(kwargs)
        super().__init__(
            f"Chunking failed for document {document_id}: {message}", details
        )


class EmbeddingError(ProcessingError):
    """Raised when embedding generation fails."""

    def __init__(self, chunk_id: str, message: str, **kwargs: Any) -> None:
        details = {"chunk_id": chunk_id}
        details.update(kwargs)
        super().__init__(f"Embedding failed for chunk {chunk_id}: {message}", details)


class SummarizationError(ProcessingError):
    """Raised when summarization fails."""

    def __init__(self, document_id: str, message: str, **kwargs: Any) -> None:
        details = {"document_id": document_id}
        details.update(kwargs)
        super().__init__(
            f"Summarization failed for document {document_id}: {message}", details
        )


# Storage errors


class StorageError(ContentLoaderError):
    """Base class for storage-related errors."""

    pass


class VectorStoreError(StorageError):
    """Raised when vector database operations fail."""

    def __init__(self, operation: str, message: str, **kwargs: Any) -> None:
        details = {"operation": operation}
        details.update(kwargs)
        super().__init__(f"Vector store {operation} failed: {message}", details)


class CacheError(StorageError):
    """Raised when cache operations fail."""

    def __init__(self, operation: str, key: str, message: str, **kwargs: Any) -> None:
        details = {"operation": operation, "key": key}
        details.update(kwargs)
        super().__init__(
            f"Cache {operation} failed for key '{key}': {message}", details
        )


# Execution errors


class ExecutionError(ContentLoaderError):
    """Base class for execution-related errors."""

    pass


class LoaderExecutionError(ExecutionError):
    """Raised when loader execution fails."""

    def __init__(
        self,
        loader_type: str,
        source_key: str,
        message: str,
        **kwargs: Any,
    ) -> None:
        details = {"loader_type": loader_type, "source_key": source_key}
        details.update(kwargs)
        super().__init__(
            f"Loader execution failed for {loader_type}:{source_key} - " f"{message}",
            details,
        )


class ConcurrentExecutionError(ExecutionError):
    """Raised when concurrent execution fails."""

    def __init__(self, failed_loaders: List[str], **kwargs: Any) -> None:
        message = f"Multiple loaders failed: {failed_loaders}"
        details = {"failed_loaders": failed_loaders}
        details.update(kwargs)
        super().__init__(message, details)


# Utility functions for error handling


def create_error_context(
    operation: str,
    source_type: Optional[str] = None,
    source_key: Optional[str] = None,
    document_id: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Create standardized error context dictionary.

    Args:
        operation: The operation that failed
        source_type: Optional source type
        source_key: Optional source key
        document_id: Optional document ID
        **extra: Additional context

    Returns:
        Dict with error context
    """
    context = {"operation": operation}

    if source_type:
        context["source_type"] = source_type
    if source_key:
        context["source_key"] = source_key
    if document_id:
        context["document_id"] = document_id

    context.update(extra)
    return context


def is_retryable_error(error: Exception) -> bool:
    """Check if an error is retryable.

    Args:
        error: Exception to check

    Returns:
        True if the error is retryable
    """
    # Network-related errors are retryable
    retryable_types = (
        ConnectionError,
        TimeoutError,
        OSError,
        DataSourceUnavailableError,
        RateLimitError,
    )

    return isinstance(error, retryable_types)


def extract_retry_delay(error: Exception) -> Optional[int]:
    """Extract retry delay from error if available.

    Args:
        error: Exception to check

    Returns:
        Retry delay in seconds, or None
    """
    if isinstance(error, RateLimitError):
        return error.details.get("retry_after")
    return None
