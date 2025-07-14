# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Content Loader is a unified system for collecting and processing content from various external data sources (Slack, Confluence, GitHub). It consolidates previously distributed loaders into a single architecture to improve maintainability and scalability.

## Core Architecture

### Layered Architecture Design
- **Core Layer**: BaseLoader interface, Executor, Models, Storage abstractions
- **Loader Layer**: SlackLoader, ConfluenceLoader, GitHubLoader implementations
- **Service Layer**: EmbeddingService, SummarizerService, LLMClient, CacheClient

### Key Design Patterns
- **Base Loader Interface**: All loaders inherit from BaseLoader with standardized methods
- **Executor Pattern**: LoaderExecutor orchestrates loading operations across multiple sources
- **Service Layer**: Separate services for embedding, summarization, caching, and LLM operations

## Development Commands

### Environment Setup
```bash
# Initialize with uv (Python package manager)
uv sync
uv run python -m content_loader.main

# Development with Tiltfile (if available)
tilt up
```

### Testing Individual Loaders
```bash
# Test Slack loader independently
uv run python scripts/test_slack.py

# Test Confluence loader independently  
uv run python scripts/test_confluence.py

# Test GitHub loader independently
uv run python scripts/test_github.py
```

### Running Specific Source Types
```bash
# Run only Slack sources
uv run python -m content_loader.main --source-type slack

# Run only GitHub sources
uv run python -m content_loader.main --source-type github

# Run only Confluence sources
uv run python -m content_loader.main --source-type confluence
```

### Docker Operations
```bash
# Start development environment
docker-compose up -d

# View logs
docker-compose logs -f content-loader

# Run individual loader in container
docker-compose exec content-loader python scripts/test_slack.py
```

## Configuration System

### Hierarchical Configuration Structure
- **Environment Variables**: Highest priority for sensitive data (API keys, URLs)
- **YAML Files**: Source-specific configurations in `config/` directory
- **Default Values**: Fallback configurations in code

### Configuration Files
- `config/slack.yaml`: Slack channel configurations and options
- `config/confluence.yaml`: Confluence space configurations  
- `config/github.yaml`: GitHub repository configurations including source code indexing
- `config/presets.yaml`: Reusable configuration presets for different programming languages
- `config/settings.yaml`: Common settings (chunking, embedding, retry policies)

## Key Environment Variables

### Required Variables
```bash
# Embedding Service
EMBEDDING_SERVICE_URL=http://embedding-retrieval:8000

# LLM Provider Selection
LLM_PROVIDER=internal|openai

# Internal LLM Proxy (if LLM_PROVIDER=internal)
INTERNAL_LLM_URL=https://internal-llm-proxy.company.com
INTERNAL_API_KEY=your-internal-api-key

# OpenAI Direct (if LLM_PROVIDER=openai)  
OPENAI_API_KEY=your-openai-key

# Data Source APIs
SLACK_BOT_TOKEN=xoxb-your-slack-token
CONFLUENCE_EMAIL=your-email@company.com
CONFLUENCE_API_TOKEN=your-confluence-token
GITHUB_APP_ID=123456
GITHUB_PRIVATE_KEY_PATH=/secrets/github-app-private-key.pem

# Redis Caching
REDIS_HOST=redis
REDIS_PORT=6379
```

## Core Components

### BaseLoader Interface
- `load_source()`: Abstract method for loading documents from a source
- `validate_source()`: Validates source configuration
- `_should_process_document()`: Determines if document should be processed (includes incremental update logic)
- `_is_document_updated()`: SHA/timestamp-based document change detection

### LoaderExecutor
- Orchestrates execution across multiple loaders
- Implements retry logic with exponential backoff
- Handles concurrent processing with proper error handling
- Supports both full execution and single-source execution

### Service Components
- **EmbeddingService**: Interfaces with vector database for document storage
- **SummarizerService**: AI-based summarization with Redis caching
- **CacheClient**: Redis-based caching with configurable TTL
- **LLMClient**: Supports both internal proxy and OpenAI direct connections

## GitHub Source Code Indexing

### Preset System
- **Python Preset**: Function-based chunking, includes docstrings
- **JavaScript Preset**: Semantic chunking, preserves context  
- **Full Stack Preset**: Multi-language support with security filtering

### Security Features
- Automatic exclusion of sensitive files (`.env*`, `*_secret*`, `*_key*`)
- Pattern-based security scanning
- Configurable whitelist system

## Data Processing Pipeline

```
Data Source → Loader → Chunking → Summarization → Embedding → Vector DB
```

1. **Collection**: Each loader fetches data from external sources
2. **Chunking**: Long texts split into appropriate sizes (configurable)
3. **Summarization**: Optional AI-based summary generation (cached)
4. **Embedding**: Text converted to vectors
5. **Storage**: Vectors stored in database

## Monitoring and Observability

### Structured Logging
- JSON-formatted logs with structured fields
- Performance metrics (execution time, document counts)
- Error tracking with contextual information

### Health Checks
- `/health`: Basic health check endpoint
- `/health/detailed`: Comprehensive service dependency checks
- `/metrics`: Performance metrics endpoint

### Cache Monitoring
- Redis cache hit/miss rates
- Cache key patterns: `summary:{hash[:16]}`, `metadata:{source_type}:{source_key}`
- TTL management (1 hour default, 7 days for document hashes)

## Development Patterns

### Testing Strategy
- **Unit Tests**: Individual component testing with mocks
- **Integration Tests**: Full pipeline testing
- **Individual Loader Tests**: Isolated testing scripts for each data source

### Memory Management
- Automatic garbage collection triggers
- Memory pressure detection and handling
- Large file streaming processing
- Batch processing for performance optimization

### Error Handling
- Custom exception hierarchy (`ContentLoaderError`, `ConfigurationError`, etc.)
- Retry logic with exponential backoff
- API rate limiting handling
- Configuration validation at startup

## Incremental Updates

### Change Detection Strategy
- **Slack**: Last collection timestamp-based filtering
- **Confluence**: CQL-based `lastModified` filters  
- **GitHub**: SHA-based file change detection
- **State Management**: Redis-based tracking of processed documents

## Multi-Provider LLM Support

The system supports both internal company LLM proxies and direct OpenAI connections:
- Set `LLM_PROVIDER=internal` for company proxy
- Set `LLM_PROVIDER=openai` for direct OpenAI API
- Unified interface handles provider-specific authentication and endpoints

## Implementation Progress Tracking

**IMPORTANT**: When working on this project, always update the implementation checklist:

### Updating Progress
```bash
# After completing any task, update the checklist
# Mark completed items with [x] in IMPLEMENTATION_CHECKLIST.md
```

### Key Checklist Sections to Track
- **프로젝트 준비 단계**: Environment setup and API key configuration
- **핵심 구현 (High Priority)**: Core components (BaseLoader, Models, Services)
- **확장 기능 (Medium Priority)**: Advanced features (GitHub indexing, security filtering)
- **운영 최적화 (Low Priority)**: Monitoring, performance optimization

### Progress Tracking Guidelines
1. **Before starting work**: Review IMPLEMENTATION_CHECKLIST.md to understand dependencies
2. **During implementation**: Check off completed sub-items as you finish them
3. **After major milestones**: Update completion status and verify functionality
4. **Document blockers**: Note any issues preventing progress in checklist comments

### Quick Progress Commands
```bash
# Check current implementation status
grep -c "\[x\]" IMPLEMENTATION_CHECKLIST.md   # Count completed items
grep -c "\[ \]" IMPLEMENTATION_CHECKLIST.md   # Count remaining items

# View high-priority pending items
grep -A 5 -B 1 "High Priority" IMPLEMENTATION_CHECKLIST.md
```

This ensures all team members can track progress and understand current implementation status.