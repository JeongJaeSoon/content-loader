# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Content Loader is a unified content collection system that fetches data from multiple sources (Slack, Confluence, GitHub) and sends it to an embedding service. It uses Python 3.11+ with uv for dependency management and implements a streaming-based architecture with layered design principles.

## Development Commands

### Environment Setup

```bash
# Install dependencies and create virtual environment
uv pip install -e ".[dev]"

# Install pre-commit hooks
uv run pre-commit install
```

### Code Quality & Testing

```bash
# Format code
uv run black .
uv run isort .

# Type checking
uv run mypy .

# Linting
uv run flake8

# Run all pre-commit checks
uv run pre-commit run --all-files

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=content_loader

# Run specific test file
uv run pytest tests/test_slack_loader.py
```

### Running the Application

```bash
# Run demo with core functionality
uv run python main.py --demo

# Run with verbose logging
uv run python main.py --demo --verbose

# Run specific loader (when implemented)
uv run python main.py --loader slack
```

## Architecture Overview

### Core Design Principles

- **Layered + Streaming Architecture**: `core/` provides base functionality, `loaders/` contains source-specific implementations
- **BaseExecutor Pattern**: All loaders implement the same `BaseExecutor` interface with `async fetch()` method
- **Streaming Processing**: Uses `AsyncGenerator[Document, None]` for memory-efficient processing
- **Independence**: Each loader is completely independent and can be developed/deployed separately

### Key Components

#### Core Layer (`content_loader/core/`)

- `base.py`: BaseExecutor interface, DateRange, retry logic, memory management
- `models.py`: Common data models (Document, DocumentMetadata, enums)
- `config.py`: Global settings and configuration management
- `exceptions.py`: Common exception types
- `executor.py`: LoaderExecutor for unified execution

#### Project Structure

```
content-loader/
├── main.py                    # CLI entry point
├── content_loader/
│   ├── core/                  # Core functionality layer
│   │   ├── base.py           # BaseExecutor interface & utilities
│   │   ├── models.py         # Common data models
│   │   ├── config.py         # Settings management
│   │   ├── exceptions.py     # Exception types
│   │   └── executor.py       # LoaderExecutor
│   └── loaders/              # Loader implementations (to be added)
│       ├── slack/
│       ├── confluence/
│       └── github/
├── docs/                     # Architecture documentation
└── tests/                    # Test files
```

### Data Flow

1. `main.py` → `LoaderExecutor` → Individual loaders
2. Each loader implements `BaseExecutor.fetch()` → yields `Document` objects
3. Documents processed in batches via `SimpleMemoryManager`
4. Built-in retry logic handles network failures with exponential backoff

### Key Classes and Interfaces

#### BaseExecutor (content_loader/core/base.py:32)

- Abstract base class all loaders must implement
- Provides `fetch(date_range)` method that yields Document objects
- Built-in retry logic and error handling via `SimpleRetryHandler`

#### DateRange (content_loader/core/base.py:16)

- Handles incremental updates with start/end datetime filtering
- Used by all loaders for efficient data fetching

#### Document (content_loader/core/models.py)

- Standard document format across all data sources
- Contains id, title, text, metadata, timestamps, and URL

#### LoaderExecutor (content_loader/core/executor.py)

- Orchestrates multiple loaders
- Handles batch processing and health monitoring
- Provides execution statistics and health checks

## Adding New Loaders

When implementing a new loader:

1. Create directory structure: `content_loader/loaders/new_source/`
2. Implement `BaseExecutor` interface:

   ```python
   from content_loader.core.base import BaseExecutor, DateRange
   from content_loader.core.models import Document

   class NewSourceExecutor(BaseExecutor):
       async def fetch(self, date_range: DateRange) -> AsyncGenerator[Document, None]:
           # Implementation here
           yield document
   ```

3. Register in `LoaderExecutor.executors` dictionary
4. Add configuration in loader's `config/` directory

## Environment Variables

Set these for external service connections:

- `SLACK_BOT_TOKEN`: Slack API token
- `CONFLUENCE_EMAIL` / `CONFLUENCE_API_TOKEN`: Confluence authentication
- `GITHUB_APP_ID` / `GITHUB_PRIVATE_KEY_PATH`: GitHub App credentials
- `EMBEDDING_SERVICE_URL`: External embedding service endpoint
- `REDIS_HOST` / `REDIS_PORT`: Redis cache configuration

## Important Implementation Notes

- All async operations use proper error handling with retry logic
- Memory management through streaming and batch processing (default batch_size=20)
- Use `uv` for all Python operations, not pip
- Korean documentation exists but code/comments should be in English
- Configuration supports environment variable overrides
- Health checks available at runtime via `LoaderExecutor.health_check()`

## Debugging and Monitoring

- Use `--verbose` flag for detailed logging
- Health check method available: `executor.health_check()`
- Execution statistics: `executor.get_execution_stats()`
- Built-in retry logic logs connection issues automatically
