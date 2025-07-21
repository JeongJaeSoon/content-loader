#!/usr/bin/env python3
"""
Content Loader main entry point.

This script demonstrates the core functionality of the content loader system.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import AsyncGenerator

import click

from content_loader.core import (
    BaseExecutor,
    ContentType,
    DateRange,
    Document,
    DocumentMetadata,
    LoaderExecutor,
    Settings,
    SourceType,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class DemoExecutor(BaseExecutor):
    """Demo executor for testing core functionality."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.source_name = config.get("source_name", "demo")
        self.document_count = config.get("document_count", 5)

    async def fetch(self, date_range: DateRange) -> AsyncGenerator[Document, None]:
        """Generate demo documents."""
        logger.info(
            f"Demo executor ({self.source_name}): "
            f"Generating {self.document_count} documents"
        )

        for i in range(self.document_count):
            await asyncio.sleep(0.1)  # Simulate async work

            metadata = DocumentMetadata(
                source_type=SourceType.SLACK,
                source_id=f"demo_{self.source_name}_{i}",
                source_url=f"https://demo.example.com/{self.source_name}/{i}",
                content_type=ContentType.CONVERSATION,
                created_at=datetime.now() - timedelta(days=i),
                updated_at=datetime.now() - timedelta(hours=i),
            )

            document = Document(
                id=f"demo_{self.source_name}_{i}",
                title=f"Demo Document {i} from {self.source_name}",
                text=(
                    f"This is demo document content {i} from "
                    f"{self.source_name}. " * (i + 1)
                ),
                metadata=metadata,
                url=f"https://demo.example.com/{self.source_name}/{i}",
                created_at=metadata.created_at,
                updated_at=metadata.updated_at,
            )

            logger.info(f"Generated document: {document.id}")
            yield document


async def demo_core_functionality(settings: Settings, verbose: bool = False) -> None:
    """Demonstrate core functionality with mock data."""
    logger.info("Starting Core Layer demonstration...")

    # Create demo executor
    executor = LoaderExecutor(settings, sources=[])

    # Add demo executors manually
    executor.executors["demo:channel1"] = DemoExecutor(
        {"source_name": "general", "document_count": 3}
    )
    executor.executors["demo:channel2"] = DemoExecutor(
        {"source_name": "dev", "document_count": 2}
    )

    # Test health check
    click.echo("\n📊 Health Check:")
    health = await executor.health_check()
    click.echo(f"   Status: {health['status']}")
    click.echo(f"   Healthy executors: {health['summary']['healthy']}")

    # Test single loader execution
    click.echo("\n🔄 Running single loader (demo:channel1)...")
    documents = []
    async for doc in executor.run_single_loader("demo", "channel1"):
        documents.append(doc)
        if verbose:
            click.echo(f"   📄 {doc.id}: {doc.title}")

    click.echo(f"   ✅ Processed {len(documents)} documents")

    # Test date range filtering
    click.echo("\n📅 Testing date range filtering...")
    yesterday = datetime.now() - timedelta(days=1)
    date_range = DateRange(start=yesterday)

    filtered_docs = []
    async for doc in executor.run_single_loader("demo", "channel2", date_range):
        if doc.updated_at and date_range.includes(doc.updated_at):
            filtered_docs.append(doc)
        if verbose:
            click.echo(f"   📄 {doc.id}: {doc.updated_at}")

    click.echo(f"   ✅ Found {len(filtered_docs)} documents within date range")

    # Show execution stats
    click.echo("\n📈 Execution Statistics:")
    stats = executor.get_execution_stats()
    if "by_loader" in stats:
        for loader_key, loader_stats in stats["by_loader"].items():
            click.echo(f"   {loader_key}:")
            click.echo(f"     Documents: {loader_stats['documents_processed']}")
            click.echo(f"     Duration: {loader_stats['execution_time_seconds']:.2f}s")
            click.echo(f"     Success rate: {loader_stats['success_rate']:.2%}")

    # Test document serialization
    if documents:
        click.echo("\n📋 Document Serialization Test:")
        sample_doc = documents[0]
        doc_dict = sample_doc.to_dict()
        click.echo(f"   Sample document serialized: {len(doc_dict)} fields")
        if verbose:
            click.echo(f"   Hash: {sample_doc.generate_hash()}")

    logger.info("Core Layer demonstration completed successfully!")


@click.command()
@click.option("--config", "-c", help="Configuration file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--demo", is_flag=True, help="Run core functionality demo")
def main(
    config: str | None = None,  # noqa: ARG001
    verbose: bool = False,
    demo: bool = False,
) -> int:
    """Content Loader main entry point."""
    click.echo("🚀 Content Loader starting...")

    # Configure verbose logging
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("content_loader").setLevel(logging.DEBUG)

    # Initialize settings
    try:
        settings = Settings()
        click.echo("✅ Configuration loaded successfully")
        if verbose:
            click.echo(f"   Redis URL: {settings.redis_url}")
            click.echo(f"   Qdrant URL: {settings.qdrant_url}")
            click.echo(f"   Log level: {settings.log_level}")
    except Exception as e:
        click.echo(f"❌ Configuration error: {e}")
        return 1

    # Run demo if requested
    if demo:
        try:
            asyncio.run(demo_core_functionality(settings, verbose))
            click.echo("✨ Demo completed successfully!")
        except Exception as e:
            click.echo(f"❌ Demo failed: {e}")
            if verbose:
                import traceback

                traceback.print_exc()
            return 1
    else:
        click.echo("✨ Content Loader ready!")
        click.echo("💡 Use --demo flag to run core functionality demonstration")

    return 0


if __name__ == "__main__":
    main()
