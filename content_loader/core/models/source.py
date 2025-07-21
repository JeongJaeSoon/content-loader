"""Source-specific document models for Content Loader.

This module defines specialized document classes for different data sources
like Slack, GitHub, and Confluence.
"""

from dataclasses import dataclass
from typing import Any, List, Optional

from .base import Document, DocumentMetadata


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
