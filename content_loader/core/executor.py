"""Main executor for coordinating all content loaders.

This module provides the LoaderExecutor class that manages multiple loaders,
handles concurrent execution, and coordinates the document processing pipeline.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Set

from .base import BaseExecutor, DateRange, SimpleMemoryManager
from .exceptions import (
    ConcurrentExecutionError,
    ConfigurationError,
    LoaderExecutionError,
    create_error_context,
)
from .models import Document, LoaderSource, SourceType

logger = logging.getLogger(__name__)


class LoaderExecutor:
    """Main executor that coordinates all content loaders."""

    def __init__(self, settings: Any, sources: Optional[List[LoaderSource]] = None):
        """Initialize executor with settings and sources.

        Args:
            settings: Application settings
            sources: List of configured data sources
        """
        self.settings = settings
        self.sources = sources or []
        self.executors: Dict[str, BaseExecutor] = {}
        self.memory_manager = SimpleMemoryManager()

        # Statistics tracking
        self.execution_stats: Dict[str, Dict[str, Any]] = {}

        # Initialize executors for configured sources
        self._initialize_executors()

    def _initialize_executors(self) -> None:
        """Initialize executors for all configured sources."""
        for source in self.sources:
            if not source.enabled:
                continue

            executor_key = f"{source.source_type.value}:{source.source_key}"

            try:
                executor = self._create_executor(source)
                self.executors[executor_key] = executor
                logger.info(f"Initialized executor for {executor_key}")

            except Exception as e:
                logger.error(f"Failed to initialize executor for {executor_key}: {e}")
                raise ConfigurationError(
                    f"Failed to initialize {executor_key}",
                    create_error_context(
                        "executor_init",
                        source.source_type.value,
                        source.source_key,
                        error=str(e),
                    ),
                )

    def _create_executor(self, source: LoaderSource) -> BaseExecutor:
        """Create executor instance for a source.

        This is a placeholder that will be implemented once we have
        concrete loader implementations.

        Args:
            source: Source configuration

        Returns:
            BaseExecutor instance

        Raises:
            ConfigurationError: If source type is not supported
        """
        # TODO: Import and create actual executor implementations
        # For now, return a mock executor

        if source.source_type == SourceType.SLACK:
            # from ..loaders.slack.executor import SlackExecutor
            # return SlackExecutor(source.config)
            pass
        elif source.source_type == SourceType.GITHUB:
            # from ..loaders.github.executor import GitHubExecutor
            # return GitHubExecutor(source.config)
            pass
        elif source.source_type == SourceType.CONFLUENCE:
            # from ..loaders.confluence.executor import ConfluenceExecutor
            # return ConfluenceExecutor(source.config)
            pass

        raise ConfigurationError(f"Unsupported source type: {source.source_type}")

    async def run_single_loader(
        self,
        loader_type: str,
        source_key: str,
        date_range: Optional[DateRange] = None,
    ) -> AsyncGenerator[Document, None]:
        """Execute a single loader and yield documents.

        Args:
            loader_type: Type of loader (slack, github, confluence)
            source_key: Specific source key to run
            date_range: Optional date range filter

        Yields:
            Document: Documents from the loader

        Raises:
            LoaderExecutionError: If loader execution fails
        """
        executor_key = f"{loader_type}:{source_key}"

        if executor_key not in self.executors:
            raise LoaderExecutionError(
                loader_type,
                source_key,
                "Executor not found or not initialized",
            )

        executor = self.executors[executor_key]
        start_time = datetime.now()
        documents_processed = 0
        errors_count = 0

        try:
            logger.info(f"Starting execution for {executor_key}")

            async for document in executor.execute(date_range):
                documents_processed += 1
                yield document

                # Log progress periodically
                if documents_processed % 100 == 0:
                    logger.info(
                        f"Processed {documents_processed} documents "
                        f"from {executor_key}"
                    )

        except Exception as e:
            errors_count += 1
            logger.error(f"Error in {executor_key}: {e}")
            raise LoaderExecutionError(
                loader_type,
                source_key,
                f"Execution failed: {str(e)}",
                error_type=type(e).__name__,
                documents_processed=documents_processed,
            )

        finally:
            # Record execution statistics
            execution_time = (datetime.now() - start_time).total_seconds()
            self.execution_stats[executor_key] = {
                "start_time": start_time.isoformat(),
                "execution_time_seconds": execution_time,
                "documents_processed": documents_processed,
                "errors_count": errors_count,
                "success_rate": (
                    documents_processed / (documents_processed + errors_count)
                    if (documents_processed + errors_count) > 0
                    else 0.0
                ),
            }

            logger.info(
                f"Completed {executor_key}: {documents_processed} documents "
                f"in {execution_time:.2f}s"
            )

    async def run_all_loaders(
        self, date_range: Optional[DateRange] = None, max_concurrent: int = 3
    ) -> Dict[str, List[Document]]:
        """Execute all configured loaders concurrently.

        Args:
            date_range: Optional date range filter
            max_concurrent: Maximum number of concurrent loaders

        Returns:
            Dict mapping executor keys to lists of documents

        Raises:
            ConcurrentExecutionError: If multiple loaders fail
        """
        if not self.executors:
            logger.warning("No executors configured")
            return {}

        semaphore = asyncio.Semaphore(max_concurrent)
        results: Dict[str, List[Document]] = {}
        failed_loaders: List[str] = []

        async def run_loader_with_semaphore(executor_key: str) -> None:
            """Run a single loader with concurrency control."""
            async with semaphore:
                loader_type, source_key = executor_key.split(":", 1)
                documents = []

                try:
                    async for document in self.run_single_loader(
                        loader_type, source_key, date_range
                    ):
                        documents.append(document)

                    results[executor_key] = documents

                except Exception as e:
                    logger.error(f"Loader {executor_key} failed: {e}")
                    failed_loaders.append(executor_key)
                    results[executor_key] = []  # Empty result for failure

        # Create tasks for all executors
        tasks = [
            run_loader_with_semaphore(executor_key)
            for executor_key in self.executors.keys()
        ]

        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        if failed_loaders:
            logger.warning(f"Some loaders failed: {failed_loaders}")

            # Only raise if ALL loaders failed
            if len(failed_loaders) == len(self.executors):
                raise ConcurrentExecutionError(failed_loaders)

        total_documents = sum(len(docs) for docs in results.values())
        logger.info(
            f"All loaders completed: {total_documents} total documents "
            f"from {len(results)} sources"
        )

        return results

    async def run_loaders_by_type(
        self, source_type: SourceType, date_range: Optional[DateRange] = None
    ) -> Dict[str, List[Document]]:
        """Execute all loaders of a specific type.

        Args:
            source_type: Type of loaders to run
            date_range: Optional date range filter

        Returns:
            Dict mapping executor keys to lists of documents
        """
        matching_executors = {
            key: executor
            for key, executor in self.executors.items()
            if key.startswith(f"{source_type.value}:")
        }

        if not matching_executors:
            logger.warning(f"No executors found for type {source_type.value}")
            return {}

        results: Dict[str, List[Document]] = {}

        for executor_key in matching_executors.keys():
            loader_type, source_key = executor_key.split(":", 1)
            documents = []

            try:
                async for document in self.run_single_loader(
                    loader_type, source_key, date_range
                ):
                    documents.append(document)

                results[executor_key] = documents

            except Exception as e:
                logger.error(f"Loader {executor_key} failed: {e}")
                results[executor_key] = []

        return results

    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics for all loaders.

        Returns:
            Dict with execution statistics
        """
        if not self.execution_stats:
            return {"message": "No execution statistics available"}

        total_documents = sum(
            stats["documents_processed"] for stats in self.execution_stats.values()
        )
        total_errors = sum(
            stats["errors_count"] for stats in self.execution_stats.values()
        )
        avg_success_rate = sum(
            stats["success_rate"] for stats in self.execution_stats.values()
        ) / len(self.execution_stats)

        return {
            "summary": {
                "total_loaders": len(self.execution_stats),
                "total_documents": total_documents,
                "total_errors": total_errors,
                "average_success_rate": avg_success_rate,
            },
            "by_loader": self.execution_stats,
        }

    def list_configured_sources(self) -> List[Dict[str, Any]]:
        """List all configured sources.

        Returns:
            List of source configurations
        """
        return [source.to_dict() for source in self.sources]

    def get_enabled_executors(self) -> Set[str]:
        """Get set of enabled executor keys.

        Returns:
            Set of executor keys that are enabled
        """
        return set(self.executors.keys())

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all executors.

        Returns:
            Dict with health check results
        """
        health_results: Dict[str, Any] = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "executors": {},
            "summary": {
                "total": len(self.executors),
                "healthy": 0,
                "unhealthy": 0,
            },
        }

        # Type-safe references for nested dictionaries
        executors_dict = health_results["executors"]
        summary_dict = health_results["summary"]

        for executor_key, executor in self.executors.items():
            try:
                # Basic health check - try to initialize a DateRange
                # More sophisticated health checks would test connections
                DateRange()  # Simple test to check class availability
                executors_dict[executor_key] = {
                    "status": "healthy",
                    "message": "Executor initialized successfully",
                }
                summary_dict["healthy"] += 1

            except Exception as e:
                executors_dict[executor_key] = {
                    "status": "unhealthy",
                    "message": f"Health check failed: {str(e)}",
                }
                summary_dict["unhealthy"] += 1

        # Overall status
        if summary_dict["unhealthy"] > 0:
            health_results["status"] = (
                "degraded" if summary_dict["healthy"] > 0 else "unhealthy"
            )

        return health_results
