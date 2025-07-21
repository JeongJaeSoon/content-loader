"""Core base classes and interfaces for Content Loader.

This module provides the fundamental abstractions and base classes
that all loaders must implement.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from .models import Document


@dataclass
class DateRange:
    """Date range filter for incremental updates."""

    start: Optional[datetime] = None
    end: Optional[datetime] = None

    def includes(self, target_date: datetime) -> bool:
        """Check if target date falls within this range."""
        if self.start and target_date < self.start:
            return False
        if self.end and target_date > self.end:
            return False
        return True


class BaseExecutor(ABC):
    """Base executor interface for all content loaders.

    Provides streaming data loading with built-in retry logic
    and consistent error handling across all loaders.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize executor with configuration.

        Args:
            config: Configuration dictionary for this executor
        """
        self.config = config
        self.retry_handler = SimpleRetryHandler()

    @abstractmethod
    async def fetch(self, date_range: DateRange) -> AsyncGenerator[Document, None]:
        """Fetch documents from the data source.

        This method must be implemented by all concrete executors.
        Should yield documents one by one for memory efficiency.

        Args:
            date_range: Date range filter for incremental updates

        Yields:
            Document: Individual documents from the data source
        """
        # This is an abstract method that must be implemented by subclasses
        # The following unreachable code helps mypy understand the return type
        if False:  # pragma: no cover
            yield Document(id="", title="", text="", metadata=None)  # type: ignore

    async def execute(
        self, date_range: Optional[DateRange] = None
    ) -> AsyncGenerator[Document, None]:
        """Execute the loader with error handling and retry logic.

        Args:
            date_range: Optional date range filter

        Yields:
            Document: Documents from the data source
        """
        if not date_range:
            date_range = DateRange()

        async def fetch_generator() -> AsyncGenerator[Document, None]:
            async for doc in self.fetch(date_range):
                yield doc

        async for document in self.retry_handler.execute_with_retry(fetch_generator):
            yield document

    def _should_process_document(
        self, document: Document, date_range: DateRange
    ) -> bool:
        """Check if document should be processed based on date range."""
        if not document.updated_at:
            return True  # Process documents without timestamp
        return date_range.includes(document.updated_at)


class SimpleRetryHandler:
    """Simple exponential backoff retry handler for network operations."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        """Initialize retry handler.

        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for exponential backoff
        """
        self.max_retries = max_retries
        self.base_delay = base_delay

    async def execute_with_retry(
        self, func_generator: Callable[[], AsyncGenerator[Any, None]]
    ) -> AsyncGenerator[Any, None]:
        """Execute async generator function with retry logic.

        Args:
            func_generator: Function that returns an async generator

        Yields:
            Any: Items from the generator

        Raises:
            Exception: Last exception if all retries failed
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                async for item in func_generator():
                    yield item
                return  # Success, exit retry loop

            except (ConnectionError, TimeoutError, OSError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2**attempt)
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise

            except Exception:
                # Don't retry on non-network errors
                raise

        # This should not be reached, but just in case
        if last_exception:
            raise last_exception


class SimpleMemoryManager:
    """Memory-efficient batch processing for document streams."""

    def __init__(self, batch_size: int = 20, enable_gc: bool = True):
        """Initialize memory manager.

        Args:
            batch_size: Number of documents per batch
            enable_gc: Whether to trigger garbage collection after each batch
        """
        self.batch_size = batch_size
        self.enable_gc = enable_gc

    async def process_batch(
        self,
        documents_stream: AsyncGenerator[Document, None],
        batch_size: Optional[int] = None,
    ) -> AsyncGenerator[List[Document], None]:
        """Process document stream in batches.

        Args:
            documents_stream: Stream of documents
            batch_size: Optional override for batch size

        Yields:
            List[Document]: Batches of documents
        """
        effective_batch_size = batch_size or self.batch_size
        batch = []

        async for document in documents_stream:
            batch.append(document)

            if len(batch) >= effective_batch_size:
                yield batch
                batch = []

                # Optional garbage collection
                if self.enable_gc:
                    import gc

                    gc.collect()

        # Yield remaining documents
        if batch:
            yield batch
