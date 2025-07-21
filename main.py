#!/usr/bin/env python3
"""
Content Loader main entry point.

This script runs specific loaders based on command line arguments.
"""

import asyncio
import logging

import click

from content_loader.core import Settings
from content_loader.loaders.demo import DemoExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_demo_loader(verbose: bool = False) -> None:
    """Run demo loader with embedding pipeline."""
    logger.info("Starting demo loader...")

    # Initialize demo executor
    demo_executor = DemoExecutor({"source_name": "demo-channel", "document_count": 10})

    try:
        # Process documents through embedding pipeline
        await demo_executor.process_and_store_documents()

        # Demonstrate search functionality
        await demo_executor.search_demo("team meeting")
        await demo_executor.search_demo("code review")
        await demo_executor.search_demo("bug investigation")

        logger.info("Demo loader completed successfully!")

    except Exception as e:
        logger.error(f"Demo loader failed: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        raise
    finally:
        # Clean up resources
        await demo_executor.cleanup()


@click.command()
@click.option("--config", "-c", help="Configuration file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option(
    "--loader",
    "-l",
    type=click.Choice(["demo", "slack", "confluence", "github"]),
    help="Loader to run",
)
@click.option("--demo", is_flag=True, help="Run demo loader (alias for --loader demo)")
def main(
    config: str | None = None,  # noqa: ARG001
    verbose: bool = False,
    loader: str | None = None,
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

    # Determine which loader to run
    if demo or loader == "demo":
        try:
            asyncio.run(run_demo_loader(verbose))
            click.echo("✨ Demo loader completed successfully!")
        except Exception as e:
            click.echo(f"❌ Demo loader failed: {e}")
            return 1
    elif loader == "slack":
        click.echo("❌ Slack loader not yet implemented")
        return 1
    elif loader == "confluence":
        click.echo("❌ Confluence loader not yet implemented")
        return 1
    elif loader == "github":
        click.echo("❌ GitHub loader not yet implemented")
        return 1
    else:
        click.echo("✨ Content Loader ready!")
        click.echo("💡 Use --loader demo or --demo to run the demo loader")
        click.echo("💡 Available loaders: demo, slack, confluence, github")

    return 0


if __name__ == "__main__":
    main()
