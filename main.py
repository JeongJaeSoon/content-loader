#!/usr/bin/env python3
"""
Simple main entry point for content-loader system.
"""

import click

from content_loader.core.config import Settings


@click.command()
@click.option("--config", "-c", help="Configuration file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def main(config: str | None = None, verbose: bool = False) -> int:
    """Content Loader main entry point."""
    click.echo("🚀 Content Loader starting...")

    # Initialize settings
    try:
        settings = Settings()
        click.echo("✅ Configuration loaded successfully")
        if verbose:
            click.echo(f"   Redis URL: {settings.redis_url}")
            click.echo(f"   Database URL: {settings.database_url}")
    except Exception as e:
        click.echo(f"❌ Configuration error: {e}")
        return 1

    click.echo("✨ Content Loader ready!")
    return 0


if __name__ == "__main__":
    main()
