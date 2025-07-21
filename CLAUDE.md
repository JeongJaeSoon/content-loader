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

## Docker Services

The project includes Docker Compose setup for required services:

### Starting Services

```bash
# Start Qdrant (vector database) and Redis
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs qdrant
docker-compose logs redis

# Stop services
docker-compose down
```

### Service Configuration

- **Qdrant**: Port 6333 (HTTP), 6334 (gRPC), data persisted in `./qdrant_storage`
- **Redis**: Port 6379, data persisted in named volume `redis_data`
- **Health checks**: Built-in health monitoring for both services

### Running the Application

```bash
# Start required services first
docker-compose up -d

# Run demo loader (✅ Fully functional)
# This will: generate documents → chunk → embed → store → search
uv run python main.py --demo

# Run with verbose logging
uv run python main.py --demo --verbose

# Default help and status
uv run python main.py

# Available loaders: demo (working), slack/confluence/github (not yet implemented)
uv run python main.py --loader demo
```

## Architecture Overview

### Core Design Principles

- **Layered + Streaming Architecture**: `core/` provides base functionality, `loaders/` contains source-specific implementations
- **BaseExecutor Pattern**: All loaders implement the same `BaseExecutor` interface with `async fetch()` method
- **Streaming Processing**: Uses `AsyncGenerator[Document, None]` for memory-efficient processing
- **Independence**: Each loader is completely independent and can be developed/deployed separately

### Key Components

#### Core Layer (`content_loader/core/`)

- `base.py`: BaseExecutor interface, DateRange, SimpleRetryHandler, SimpleMemoryManager
- `models/`: Common data models split by functionality (organized for maintainability):
  - `base.py`: Core models (Document, DocumentMetadata, LoaderSource, enums)
  - `source.py`: Source-specific models (SlackMessage, GitHubIssue, GitHubFile, ConfluencePage)
  - `processing.py`: Document processing models (ProcessedChunk for vector storage)
- `config.py`: Pydantic-based settings with environment variable support (.env loading)
- `exceptions.py`: Comprehensive exception hierarchy (production-ready with 20+ exception types)
- `executor.py`: LoaderExecutor with advanced features (statistics, health checks, concurrent execution)

#### Services Layer (`content_loader/services/`)

**EmbeddingService** (`embedding_service.py`):
- SentenceTransformers integration with `all-MiniLM-L6-v2` model
- Batch text embedding with `embed_texts()` method
- Lazy model loading for memory efficiency
- Embedding dimension: 384

**VectorStore** (`vector_store.py`):
- Qdrant vector database client with async operations
- Collection management with `ensure_collection()`
- Vector storage with `store_embeddings()` for batch operations
- Similarity search with `search_similar()` supporting custom thresholds
- Collection statistics via `get_collection_info()` for monitoring

**DocumentProcessor** (`document_processor.py`):
- Complete document processing pipeline orchestration
- Document chunking with configurable chunk size (default: 512 characters)
- End-to-end processing: Document → Chunks → Embeddings → Vector Storage
- Search functionality with `search_documents()` including relevance scoring

#### Project Structure

```
content-loader/
├── main.py                           # CLI entry point (✅ Working)
├── content_loader/
│   ├── core/                         # Core functionality layer
│   │   ├── base.py                   # BaseExecutor interface & utilities
│   │   ├── config.py                 # Pydantic Settings (✅ Implemented)
│   │   ├── exceptions.py             # Exception hierarchy
│   │   ├── executor.py               # LoaderExecutor
│   │   └── models/                   # ✅ Organized into modules
│   │       ├── base.py               # Document, DocumentMetadata, enums
│   │       ├── source.py             # Source-specific models
│   │       └── processing.py         # ProcessedChunk for vector storage
│   ├── loaders/                      # Loader implementations
│   │   ├── demo/                     # ✅ Fully implemented demo loader
│   │   │   ├── executor.py           # Complete embedding pipeline
│   │   │   └── __init__.py
│   │   └── github/                   # Empty (planned)
│   └── services/                     # ✅ Complete service layer
│       ├── document_processor.py     # Document chunking & processing
│       ├── embedding_service.py      # SentenceTransformers integration
│       └── vector_store.py           # Qdrant vector database client
├── docker-compose.yml                # ✅ Qdrant + Redis services
├── setup.cfg                         # flake8 configuration
├── docs/                             # Architecture documentation
└── tests/                            # Test files (to be added)
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
- Memory management through `SimpleMemoryManager` with configurable batch processing

#### DateRange (content_loader/core/base.py:16)

- Handles incremental updates with start/end datetime filtering
- `includes()` method for efficient date range checking
- Used by all loaders for efficient data fetching

#### Document (content_loader/core/models/base.py)

- Standard document format across all data sources
- Contains id, title, text, metadata, timestamps, and URL
- Methods: `generate_hash()`, `to_dict()`, JSON serialization support

#### LoaderExecutor (content_loader/core/executor.py)

- Orchestrates multiple loaders with concurrent execution
- Advanced features: execution statistics, health monitoring, source type filtering
- Handles batch processing and error aggregation
- Production-ready with comprehensive logging and metrics

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

3. Register in `LoaderExecutor._create_executor()` method (currently a placeholder)
4. Add configuration in loader's `config/` directory

## Demo Loader

The project includes a fully functional demo loader for testing the complete pipeline:

### What it does

1. **Generates 10 sample documents** with realistic content (team meetings, code reviews, etc.)
2. **Processes through embedding pipeline**: Document → Chunks → Embeddings → Vector Storage
3. **Demonstrates search functionality** with example queries
4. **Provides collection statistics** and performance metrics

### Usage

```bash
# Run complete demo pipeline
uv run python main.py --demo

# Expected output:
# - Document generation logs
# - Embedding processing logs
# - Vector storage confirmation
# - Search results for "team meeting", "code review", "bug investigation"
# - Collection statistics
```

### Implementation

- Located in `content_loader/loaders/demo/executor.py`
- Extends `BaseExecutor` interface
- Includes realistic content templates
- Demonstrates all core functionality

## Environment Variables

Based on the `Settings` class in `content_loader/core/config.py`:

### Required Settings

```bash
# Vector database (required for demo)
export QDRANT_URL="http://localhost:6333"  # Default

# Redis (required for demo)
export REDIS_URL="redis://localhost:6379/0"  # Default

# Optional API tokens (for future loaders)
export GITHUB_TOKEN="your-github-token"
export SLACK_BOT_TOKEN="xoxb-your-slack-token"

# Logging
export LOG_LEVEL="INFO"  # Default
```

### Configuration Loading

The project uses `pydantic-settings` for automatic environment variable loading:

- Supports `.env` file loading
- Type validation and conversion
- Default values for development

## Current Implementation Status

- ✅ **Complete Core Framework**: BaseExecutor, models, exceptions, configuration
- ✅ **Fully Functional Demo Loader**: Generates documents and processes through embedding pipeline
- ✅ **Complete Services Layer**: EmbeddingService, VectorStore, DocumentProcessor
- ✅ **Vector Database Integration**: Qdrant with collection management and search
- ✅ **Docker Infrastructure**: Qdrant and Redis services
- ✅ **Working CLI**: Main application with demo mode
- ❌ **Concrete Loaders**: Slack, Confluence, GitHub loaders not yet implemented
- ❌ **Tests**: No test files present
- ❌ **Production Dockerfile**: Only docker-compose for dependencies

## Important Implementation Notes

- **Production-Ready Core**: The current implementation exceeds MVP requirements with comprehensive error handling, statistics, and operational features
- **Model Organization**: Models are split into 3 modules (`base.py`, `source.py`, `processing.py`) for better maintainability
- **Advanced Error Handling**: 20+ exception types with hierarchical structure and retry utilities
- **Memory management** through streaming and batch processing (default batch_size=20)
- **Concurrent Execution**: LoaderExecutor supports parallel loader execution with proper error aggregation
- **Configuration**: Pydantic-based settings with automatic environment variable loading and validation
- Use `uv` for all Python operations, not pip
- Health checks and execution statistics available at runtime via `LoaderExecutor`

## Debugging and Monitoring

- Use `--verbose` flag for detailed logging
- Health check method available: `executor.health_check()`
- Execution statistics: `executor.get_execution_stats()`
- Built-in retry logic logs connection issues automatically
