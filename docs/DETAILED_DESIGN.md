# Content Loader 상세 설계

## 1. 각 Loader 상세 설계

각 Loader의 상세 설계는 별도 문서로 분리되어 있습니다:

- **[Slack Loader](./SLACK_LOADER.md)** - Slack 채널 메시지 및 스레드 수집
- **[Confluence Loader](./CONFLUENCE_LOADER.md)** - Confluence 페이지 및 댓글 수집
- **[GitHub Loader](./GITHUB_LOADER.md)** - GitHub Issues, Files, Source Code 수집

## 2. 공통 아키텍처 패턴

### 2.1 Base Loader Interface

```python
class BaseLoader(ABC):
    def __init__(self, llm_settings: LLMSettings):
        self.llm_settings = llm_settings
        self.llm_client = LLMClient(llm_settings)

    @abstractmethod
    async def load_source(self, source: Any) -> AsyncGenerator[Document, None]:
        """특정 소스에서 문서를 로드합니다."""
        pass

    @abstractmethod
    def validate_source(self, source: Any) -> bool:
        """소스 설정의 유효성을 검증합니다."""
        pass

    def _should_process_document(self, doc: Document) -> bool:
        """문서를 처리할지 결정합니다."""
        if not (doc.text and doc.text.strip()):
            return False

        # 증분 업데이트 검사
        return self._is_document_updated(doc)

    def _is_document_updated(self, doc: Document) -> bool:
        """문서가 업데이트되었는지 확인 (SHA/수정시간 기반)"""
        # 저장된 해시/수정시간과 비교
        stored_hash = self._get_stored_document_hash(doc.id)
        current_hash = self._calculate_document_hash(doc)

        return stored_hash != current_hash

    def _calculate_document_hash(self, doc: Document) -> str:
        """문서 해시 계산"""
        content = f"{doc.text}{doc.metadata.get('modified_time', '')}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _get_stored_document_hash(self, doc_id: str) -> str:
        """저장된 문서 해시 조회"""
        # Redis에서 조회
        return self.cache_client.get(f"doc_hash:{doc_id}") or ""

    async def _update_document_hash(self, doc_id: str, hash_value: str):
        """문서 해시 업데이트"""
        await self.cache_client.set(f"doc_hash:{doc_id}", hash_value, expire=86400*7)  # 7일
```

### 2.2 Executor Pattern

```python
class LoaderExecutor:
    def __init__(self, config: LoaderConfig, llm_settings: LLMSettings):
        self.config = config
        self.llm_settings = llm_settings
        self.loaders = {
            "slack": SlackLoader(SlackClient(config.slack_token), llm_settings),
            "confluence": ConfluenceLoader(ConfluenceClient(config.confluence_config), llm_settings),
            "github": GitHubLoader(GitHubClient(config.github_config), llm_settings)
        }

    async def execute_all(self) -> None:
        """모든 구성된 소스를 실행합니다."""
        tasks = []
        for source_type, sources in self.config.sources.items():
            for source in sources:
                task = self._execute_source(source_type, source)
                tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_source(self, source_type: str, source: Any) -> None:
        """소스 실행 시 에러 처리 및 재시도 로직 포함"""
        loader = self.loaders[source_type]
        retry_count = 0
        max_retries = 3

        while retry_count <= max_retries:
            try:
                async for document in loader.load_source(source):
                    if loader._should_process_document(document):
                        await self._process_document(document)
                break  # 성공시 루프 종료
            except Exception as e:
                retry_count += 1
                if retry_count > max_retries:
                    logger.error(f"Failed to process {source_type} after {max_retries} retries: {e}")
                    raise
                else:
                    wait_time = 2 ** retry_count  # 지수 백오프
                    logger.warning(f"Retry {retry_count}/{max_retries} for {source_type} in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
```

### 2.3 Service Layer 설계

#### EmbeddingService

```python
class EmbeddingService:
    def __init__(self, service_url: str):
        self.service_url = service_url
        self.session = aiohttp.ClientSession()

    async def upsert_documents(self, documents: List[Document]) -> List[str]:
        operations = [self._document_to_upsert_operation(doc) for doc in documents]

        async with self.session.post(
            f"{self.service_url}/upsert",
            json=[op.dict() for op in operations]
        ) as response:
            return await response.json()

    async def delete_documents(self, filters: List[DocumentFilter]) -> List[str]:
        operations = [DeleteOperation(filter=filter) for filter in filters]

        async with self.session.post(
            f"{self.service_url}/delete",
            json=[op.dict() for op in operations]
        ) as response:
            return await response.json()
```

#### SummarizerService

```python
class SummarizerService:
    def __init__(self, llm_settings: LLMSettings, cache_client: CacheClient):
        self.llm_client = LLMClient(llm_settings)
        self.cache_client = cache_client

    async def summarize(self, text: str, max_tokens: int = 500) -> str:
        # 캐시 확인
        cache_key = self._generate_cache_key(text)
        cached_summary = await self.cache_client.get(cache_key)
        if cached_summary:
            return cached_summary

        # LLM으로 요약 생성
        summary = await self.llm_client.summarize(text, max_tokens)

        # 캐시에 저장
        await self.cache_client.set(cache_key, summary, expire=86400)
        return summary
```

#### CacheClient (Redis 기반)

```python
class CacheClient:
    def __init__(self, redis_client: RedisClient):
        self.redis_client = redis_client

    async def get(self, key: str) -> Optional[str]:
        """Redis에서 캐시 조회"""
        return await self.redis_client.get(key)

    async def set(self, key: str, value: str, expire: int = 3600) -> None:
        """Redis에 캐시 저장 (기본 1시간)"""
        await self.redis_client.set(key, value, expire=expire)

    def _generate_cache_key(self, text: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(text.encode("utf-8"))
        digest = hasher.hexdigest()
        return f"summary:{digest[:16]}"
```

#### LLMClient (사내 Proxy 및 OpenAI 지원)

```python
class LLMSettings:
    """LLM 서비스 설정"""
    def __init__(self):
        # 프로바이더 선택: "internal" 또는 "openai"
        self.provider = os.getenv("LLM_PROVIDER", "internal")

        # 사내 LLM 프록시 설정
        self.internal_base_url = os.getenv("INTERNAL_LLM_URL", "https://your-internal-llm-proxy.com")
        self.internal_api_key = os.getenv("INTERNAL_API_KEY", "")
        self.internal_model = os.getenv("INTERNAL_MODEL", "gpt-3.5-turbo")
        self.internal_embedding_model = os.getenv("INTERNAL_EMBEDDING_MODEL", "text-embedding-ada-002")

        # OpenAI 직접 연결 설정
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        self.openai_embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
        self.openai_organization = os.getenv("OPENAI_ORGANIZATION", None)

class LLMClient:
    def __init__(self, settings: LLMSettings):
        self.settings = settings
        self.client = self._create_client()

    def _create_client(self) -> AsyncOpenAI:
        """설정에 따라 적절한 OpenAI 클라이언트 생성"""
        if self.settings.provider == "openai":
            return AsyncOpenAI(
                base_url=self.settings.openai_base_url,
                api_key=self.settings.openai_api_key,
                organization=self.settings.openai_organization,
                timeout=30.0
            )
        else:  # internal
            return AsyncOpenAI(
                base_url=self.settings.internal_base_url,
                api_key=self.settings.internal_api_key,
                timeout=30.0
            )

    def _get_model(self, model_type: str = "chat") -> str:
        """프로바이더에 따른 모델명 반환"""
        if self.settings.provider == "openai":
            return self.settings.openai_model if model_type == "chat" else self.settings.openai_embedding_model
        else:
            return self.settings.internal_model if model_type == "chat" else self.settings.internal_embedding_model

    async def summarize(self, text: str, max_tokens: int = 500) -> str:
        model = self._get_model("chat")
        response = await self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "다음 텍스트를 간결하게 요약해주세요."},
                {"role": "user", "content": text}
            ],
            max_tokens=max_tokens,
            temperature=0.3
        )

        return response.choices[0].message.content

## 로깅 및 모니터링

### 구조화된 로깅
```python
import structlog

# 로깅 설정
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

class LoaderExecutor:
    def __init__(self, config: LoaderConfig, llm_settings: LLMSettings):
        self.logger = structlog.get_logger()
        # ... 기존 코드

    async def _execute_source(self, source_type: str, source: Any) -> None:
        start_time = time.time()
        self.logger.info(
            "loader_execution_started",
            source_type=source_type,
            source_key=getattr(source, 'key', 'unknown')
        )

        try:
            # ... 기존 실행 로직

            execution_time = time.time() - start_time
            self.logger.info(
                "loader_execution_completed",
                source_type=source_type,
                source_key=getattr(source, 'key', 'unknown'),
                execution_time=execution_time,
                documents_processed=processed_count
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(
                "loader_execution_failed",
                source_type=source_type,
                source_key=getattr(source, 'key', 'unknown'),
                execution_time=execution_time,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
```

### 메트릭 수집

```python
from dataclasses import dataclass
from typing import Dict, Optional
import time

@dataclass
class LoaderMetrics:
    source_type: str
    source_key: str
    start_time: float
    end_time: Optional[float] = None
    documents_processed: int = 0
    documents_failed: int = 0
    api_calls_made: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    error_count: int = 0
    last_error: Optional[str] = None

    @property
    def execution_time(self) -> Optional[float]:
        if self.end_time:
            return self.end_time - self.start_time
        return None

    @property
    def success_rate(self) -> float:
        total = self.documents_processed + self.documents_failed
        return self.documents_processed / total if total > 0 else 0.0

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

class MetricsCollector:
    def __init__(self):
        self.metrics: Dict[str, LoaderMetrics] = {}

    def start_execution(self, source_type: str, source_key: str):
        key = f"{source_type}:{source_key}"
        self.metrics[key] = LoaderMetrics(
            source_type=source_type,
            source_key=source_key,
            start_time=time.time()
        )

    def end_execution(self, source_type: str, source_key: str):
        key = f"{source_type}:{source_key}"
        if key in self.metrics:
            self.metrics[key].end_time = time.time()

    def record_document_processed(self, source_type: str, source_key: str):
        key = f"{source_type}:{source_key}"
        if key in self.metrics:
            self.metrics[key].documents_processed += 1

    def record_api_call(self, source_type: str, source_key: str):
        key = f"{source_type}:{source_key}"
        if key in self.metrics:
            self.metrics[key].api_calls_made += 1

    def record_cache_hit(self, source_type: str, source_key: str):
        key = f"{source_type}:{source_key}"
        if key in self.metrics:
            self.metrics[key].cache_hits += 1

    def record_cache_miss(self, source_type: str, source_key: str):
        key = f"{source_type}:{source_key}"
        if key in self.metrics:
            self.metrics[key].cache_misses += 1

    def get_summary(self) -> Dict[str, any]:
        """전체 실행 요약 반환"""
        total_execution_time = sum(
            m.execution_time for m in self.metrics.values()
            if m.execution_time is not None
        )
        total_documents = sum(m.documents_processed for m in self.metrics.values())
        total_api_calls = sum(m.api_calls_made for m in self.metrics.values())

        return {
            "total_sources": len(self.metrics),
            "total_execution_time": total_execution_time,
            "total_documents_processed": total_documents,
            "total_api_calls": total_api_calls,
            "average_success_rate": sum(m.success_rate for m in self.metrics.values()) / len(self.metrics),
            "average_cache_hit_rate": sum(m.cache_hit_rate for m in self.metrics.values()) / len(self.metrics),
            "sources": {k: v for k, v in self.metrics.items()}
        }
```

### 헬스 체크 및 상태 모니터링

```python
from fastapi import FastAPI, HTTPException
from datetime import datetime, timedelta

app = FastAPI()

@app.get("/health")
async def health_check():
    """기본 헬스 체크"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.get("/health/detailed")
async def detailed_health_check():
    """상세 헬스 체크"""
    checks = {
        "redis": await check_redis_connection(),
        "embedding_service": await check_embedding_service(),
        "llm_service": await check_llm_service()
    }

    all_healthy = all(checks.values())

    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "timestamp": datetime.now().isoformat(),
        "checks": checks
    }

@app.get("/metrics")
async def get_metrics():
    """메트릭 엔드포인트"""
    return metrics_collector.get_summary()

@app.get("/metrics/sources/{source_type}")
async def get_source_metrics(source_type: str):
    """소스별 메트릭"""
    source_metrics = {
        k: v for k, v in metrics_collector.metrics.items()
        if v.source_type == source_type
    }

    if not source_metrics:
        raise HTTPException(status_code=404, detail=f"No metrics found for {source_type}")

    return source_metrics

async def check_redis_connection() -> bool:
    """Redis 연결 확인"""
    try:
        await redis_client.ping()
        return True
    except Exception:
        return False

async def check_embedding_service() -> bool:
    """임베딩 서비스 연결 확인"""
    try:
        # 간단한 테스트 요청
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{EMBEDDING_SERVICE_URL}/health", timeout=5) as response:
                return response.status == 200
    except Exception:
        return False

async def check_llm_service() -> bool:
    """LLM 서비스 연결 확인"""
    try:
        # 간단한 테스트 요약 요청
        test_response = await llm_client.summarize("test", max_tokens=10)
        return bool(test_response)
    except Exception:
        return False
```

## 설정 검증 및 오류 처리

### YAML 스키마 검증

```python
from pydantic import BaseModel, ValidationError, validator
from typing import List, Optional, Literal
from datetime import datetime

class SourceConfigSchema(BaseModel):
    """Base 소스 설정 스키마"""
    key: str
    type: str

    @validator('key')
    def key_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('key cannot be empty')
        return v.strip()

class SlackSourceSchema(SourceConfigSchema):
    workspace: str
    channel: str
    name: str
    type: Literal["slack"] = "slack"

    @validator('channel')
    def channel_must_be_valid(cls, v):
        if not v.startswith('C') or len(v) != 11:
            raise ValueError('channel must be a valid Slack channel ID (C + 10 chars)')
        return v

class GitHubSourceSchema(SourceConfigSchema):
    owner: str
    name: str
    type: Literal["github"] = "github"
    source_type: Literal["issues", "files", "source_code"]

    @validator('owner', 'name')
    def github_names_must_be_valid(cls, v):
        if not v or '/' in v or ' ' in v:
            raise ValueError('GitHub owner/name must not contain spaces or slashes')
        return v

class ConfluenceSourceSchema(SourceConfigSchema):
    space: str
    type: Literal["confluence"] = "confluence"

    @validator('space')
    def space_must_be_valid(cls, v):
        if not v or len(v) > 10:
            raise ValueError('Confluence space key must be 1-10 characters')
        return v.upper()

class ConfigValidator:
    def __init__(self):
        self.schemas = {
            "slack": SlackSourceSchema,
            "github": GitHubSourceSchema,
            "confluence": ConfluenceSourceSchema
        }

    def validate_source_config(self, source_data: dict) -> BaseModel:
        """소스 설정 검증"""
        source_type = source_data.get('type')
        if not source_type:
            raise ValidationError('source type is required')

        schema_class = self.schemas.get(source_type)
        if not schema_class:
            raise ValidationError(f'unsupported source type: {source_type}')

        try:
            return schema_class(**source_data)
        except ValidationError as e:
            raise ValidationError(f'validation failed for {source_type}: {e}')

    def validate_environment_variables(self) -> List[str]:
        """필수 환경변수 검증"""
        missing_vars = []
        required_vars = {
            'EMBEDDING_SERVICE_URL': 'Embedding service URL',
            'LLM_PROVIDER': 'LLM provider (internal/openai)',
            'REDIS_HOST': 'Redis host',
            'REDIS_PORT': 'Redis port'
        }

        for var, description in required_vars.items():
            if not os.getenv(var):
                missing_vars.append(f'{var} ({description})')

        # LLM 프로바이더별 추가 검증
        llm_provider = os.getenv('LLM_PROVIDER', '').lower()
        if llm_provider == 'internal':
            if not os.getenv('INTERNAL_LLM_URL'):
                missing_vars.append('INTERNAL_LLM_URL (for internal LLM provider)')
            if not os.getenv('INTERNAL_API_KEY'):
                missing_vars.append('INTERNAL_API_KEY (for internal LLM provider)')
        elif llm_provider == 'openai':
            if not os.getenv('OPENAI_API_KEY'):
                missing_vars.append('OPENAI_API_KEY (for OpenAI provider)')

        return missing_vars

    def validate_api_credentials(self) -> Dict[str, bool]:
        """각 API 자격 증명 검증"""
        results = {}

        # Slack 토큰 검증
        slack_token = os.getenv('SLACK_BOT_TOKEN')
        if slack_token:
            results['slack'] = slack_token.startswith('xoxb-') and len(slack_token) > 50
        else:
            results['slack'] = False

        # GitHub 설정 검증
        github_app_id = os.getenv('GITHUB_APP_ID')
        github_key_path = os.getenv('GITHUB_PRIVATE_KEY_PATH')
        if github_app_id and github_key_path:
            results['github'] = github_app_id.isdigit() and os.path.exists(github_key_path)
        else:
            results['github'] = False

        # Confluence 설정 검증
        confluence_email = os.getenv('CONFLUENCE_EMAIL')
        confluence_token = os.getenv('CONFLUENCE_API_TOKEN')
        if confluence_email and confluence_token:
            results['confluence'] = '@' in confluence_email and len(confluence_token) > 10
        else:
            results['confluence'] = False

        return results

# 시작 시 검증 실행
async def validate_startup_configuration():
    """시작 시 전체 설정 검증"""
    validator = ConfigValidator()

    # 1. 환경변수 검증
    missing_vars = validator.validate_environment_variables()
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    # 2. API 자격증명 검증
    credential_results = validator.validate_api_credentials()
    invalid_credentials = [k for k, v in credential_results.items() if not v]
    if invalid_credentials:
        logger.warning(f"Invalid credentials for: {', '.join(invalid_credentials)}")

    # 3. 외부 서비스 연결 검증
    service_health = {
        "redis": await check_redis_connection(),
        "embedding_service": await check_embedding_service(),
        "llm_service": await check_llm_service()
    }

    unhealthy_services = [k for k, v in service_health.items() if not v]
    if unhealthy_services:
        raise ConnectionError(f"Cannot connect to services: {', '.join(unhealthy_services)}")

    logger.info("Startup configuration validation completed successfully")
```

### 런타임 오류 처리

```python
class ContentLoaderError(Exception):
    """Base 예외 클래스"""
    pass

class ConfigurationError(ContentLoaderError):
    """설정 오류"""
    pass

class APIConnectionError(ContentLoaderError):
    """외부 API 연결 오류"""
    pass

class DataProcessingError(ContentLoaderError):
    """데이터 처리 오류"""
    pass

# 전역 예외 핸들러
@app.exception_handler(ContentLoaderError)
async def content_loader_exception_handler(request, exc):
    logger.error(
        "content_loader_error",
        error_type=type(exc).__name__,
        error_message=str(exc),
        request_path=str(request.url)
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "message": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )

@app.exception_handler(ValidationError)
async def validation_exception_handler(request, exc):
    logger.warning(
        "validation_error",
        error_details=exc.errors(),
        request_path=str(request.url)
    )

    return JSONResponse(
        status_code=400,
        content={
            "error": "ValidationError",
            "details": exc.errors(),
            "timestamp": datetime.now().isoformat()
        }
    )
```

## 성능 최적화 및 메모리 관리

### 비동기 처리 최적화

```python
import asyncio
from asyncio import Semaphore, Queue
from typing import AsyncGenerator

class PerformanceOptimizedExecutor:
    def __init__(self, config: LoaderConfig, llm_settings: LLMSettings):
        self.config = config
        self.llm_settings = llm_settings

        # 동시 실행 제한
        self.max_concurrent_sources = 3
        self.max_concurrent_documents = 10

        # 세마포어 설정
        self.source_semaphore = Semaphore(self.max_concurrent_sources)
        self.document_semaphore = Semaphore(self.max_concurrent_documents)

        # 배치 처리를 위한 큐
        self.document_queue = Queue(maxsize=100)

    async def execute_all_optimized(self) -> None:
        """성능 최적화된 모든 소스 실행"""
        # 배치 처리기 시작
        batch_processor_task = asyncio.create_task(self._batch_processor())

        # 소스별 태스크 생성
        tasks = []
        for source_type, sources in self.config.sources.items():
            for source in sources:
                task = asyncio.create_task(
                    self._execute_source_with_semaphore(source_type, source)
                )
                tasks.append(task)

        # 모든 소스 실행 대기
        await asyncio.gather(*tasks, return_exceptions=True)

        # 큐 종료 신호 및 배치 처리기 종료 대기
        await self.document_queue.put(None)  # 종료 신호
        await batch_processor_task

    async def _execute_source_with_semaphore(self, source_type: str, source: Any):
        """세마포어를 사용한 소스 실행"""
        async with self.source_semaphore:
            loader = self.loaders[source_type]

            async for document in loader.load_source(source):
                if loader._should_process_document(document):
                    # 문서를 배치 처리 큐에 추가
                    await self.document_queue.put(document)

    async def _batch_processor(self):
        """배치 단위 문서 처리"""
        batch = []
        batch_size = 10

        while True:
            try:
                # 1초 타임아웃으로 문서 수집
                document = await asyncio.wait_for(
                    self.document_queue.get(),
                    timeout=1.0
                )

                if document is None:  # 종료 신호
                    if batch:
                        await self._process_document_batch(batch)
                    break

                batch.append(document)

                # 배치 크기에 도달하면 처리
                if len(batch) >= batch_size:
                    await self._process_document_batch(batch)
                    batch = []

            except asyncio.TimeoutError:
                # 타임아웃 시 현재 배치 처리
                if batch:
                    await self._process_document_batch(batch)
                    batch = []

    async def _process_document_batch(self, documents: List[Document]):
        """문서 배치 처리"""
        if not documents:
            return

        # 청킹
        chunked_docs = []
        for doc in documents:
            chunks = await self._chunk_document(doc)
            chunked_docs.extend(chunks)

        # 요약 (배치 처리)
        if self.config.summarization_enabled:
            summarized_docs = await self._batch_summarize(chunked_docs)
        else:
            summarized_docs = chunked_docs

        # 임베딩 서비스에 전송
        await self._send_to_embedding_service(summarized_docs)
```

### 메모리 관리 전략

```python
import gc
import psutil
from typing import Optional
from dataclasses import dataclass

@dataclass
class MemoryConfig:
    max_memory_mb: int = 2048  # 2GB
    gc_threshold_mb: int = 1536  # 1.5GB
    chunk_size_limit: int = 1024  # 1KB per chunk
    max_chunks_in_memory: int = 1000

class MemoryManager:
    def __init__(self, config: MemoryConfig):
        self.config = config
        self.chunks_in_memory = 0
        self.process = psutil.Process()

    def get_memory_usage_mb(self) -> float:
        """현재 메모리 사용량 (MB)"""
        memory_info = self.process.memory_info()
        return memory_info.rss / 1024 / 1024

    def should_trigger_gc(self) -> bool:
        """가비지 컴렉션 실행 여부 판단"""
        current_memory = self.get_memory_usage_mb()
        return current_memory > self.config.gc_threshold_mb

    def should_pause_processing(self) -> bool:
        """처리 일시 중지 여부 판단"""
        current_memory = self.get_memory_usage_mb()
        return current_memory > self.config.max_memory_mb

    async def manage_memory_pressure(self):
        """메모리 압박 관리"""
        if self.should_trigger_gc():
            logger.warning(f"Memory usage high: {self.get_memory_usage_mb():.1f}MB, triggering GC")
            gc.collect()

        if self.should_pause_processing():
            logger.error(f"Memory usage critical: {self.get_memory_usage_mb():.1f}MB, pausing processing")
            # 진행 중인 처리 일시 중지
            await asyncio.sleep(5)  # 5초 대기
            gc.collect()

    def track_chunk_creation(self, chunk_size: int):
        """청크 생성 추적"""
        if chunk_size > self.config.chunk_size_limit:
            logger.warning(f"Large chunk created: {chunk_size} bytes")

        self.chunks_in_memory += 1
        if self.chunks_in_memory > self.config.max_chunks_in_memory:
            logger.warning(f"Too many chunks in memory: {self.chunks_in_memory}")

    def track_chunk_deletion(self):
        """청크 삭제 추적"""
        self.chunks_in_memory = max(0, self.chunks_in_memory - 1)

# 메모리 관리를 포함한 버전
class MemoryAwareLoader(BaseLoader):
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager

    async def load_source(self, source: Any) -> AsyncGenerator[Document, None]:
        document_count = 0

        async for document in self._load_source_impl(source):
            # 메모리 압박 검사
            await self.memory_manager.manage_memory_pressure()

            yield document
            document_count += 1

            # 100개 문서마다 메모리 상태 확인
            if document_count % 100 == 0:
                memory_usage = self.memory_manager.get_memory_usage_mb()
                logger.info(f"Processed {document_count} documents, memory: {memory_usage:.1f}MB")

    async def _chunk_document_with_memory_management(self, document: Document) -> List[Document]:
        """메모리 관리를 포함한 문서 청킹"""
        chunks = []

        # 기본 청킹 로직
        text_chunks = self._split_text(document.text)

        for i, chunk_text in enumerate(text_chunks):
            chunk_doc = Document(
                id=f"{document.id}_chunk_{i}",
                text=chunk_text,
                metadata={**document.metadata, "chunk_index": i}
            )

            # 청크 크기 추적
            chunk_size = len(chunk_text.encode('utf-8'))
            self.memory_manager.track_chunk_creation(chunk_size)

            chunks.append(chunk_doc)

            # 메모리 압박 검사
            if self.memory_manager.should_pause_processing():
                logger.warning("Memory pressure detected during chunking, yielding control")
                await asyncio.sleep(0.1)  # 시스템에 제어권 양보

        return chunks
```

### 대용량 데이터 처리 전략

```python
class LargeDataProcessor:
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager
        self.temp_storage_path = "/tmp/content-loader"
        os.makedirs(self.temp_storage_path, exist_ok=True)

    async def process_large_repository(self, repo_source: GitHubSource) -> AsyncGenerator[Document, None]:
        """대용량 리포지토리 스트리밍 처리"""
        files = await self._get_repository_files(repo_source)

        # 파일 크기별 정렬 (작은 파일부터)
        files.sort(key=lambda f: f.size)

        batch_size = 10
        current_batch = []

        for file in files:
            # 대용량 파일은 바로 처리
            if file.size > 1024 * 1024:  # 1MB 이상
                async for doc in self._process_large_file(file, repo_source):
                    yield doc
            else:
                current_batch.append(file)

                # 배치 처리
                if len(current_batch) >= batch_size:
                    async for doc in self._process_file_batch(current_batch, repo_source):
                        yield doc
                    current_batch = []

                    # 메모리 압박 검사
                    await self.memory_manager.manage_memory_pressure()

        # 남은 배치 처리
        if current_batch:
            async for doc in self._process_file_batch(current_batch, repo_source):
                yield doc

    async def _process_large_file(self, file: GitHubFile, source: GitHubSource) -> AsyncGenerator[Document, None]:
        """대용량 파일 스트리밍 처리"""
        # 파일을 임시 디스크에 저장
        temp_file_path = os.path.join(self.temp_storage_path, f"{file.sha}.tmp")

        try:
            # 파일 다운로드
            await self._download_file_to_disk(file, temp_file_path)

            # 스트리밍 방식으로 청킹
            async for chunk_doc in self._stream_chunk_file(temp_file_path, file, source):
                yield chunk_doc

        finally:
            # 임시 파일 삭제
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    async def _stream_chunk_file(self, file_path: str, file: GitHubFile, source: GitHubSource) -> AsyncGenerator[Document, None]:
        """파일 스트리밍 청킹"""
        chunk_size = 2048  # 2KB 청크
        chunk_index = 0

        with open(file_path, 'r', encoding='utf-8') as f:
            while True:
                chunk_text = f.read(chunk_size)
                if not chunk_text:
                    break

                # 청크 문서 생성
                chunk_doc = Document(
                    id=f"{file.path}_chunk_{chunk_index}",
                    text=chunk_text,
                    metadata={
                        "source_type": "github",
                        "file_path": file.path,
                        "chunk_index": chunk_index,
                        "file_sha": file.sha
                    }
                )

                yield chunk_doc
                chunk_index += 1

                # 메모리 압박 검사
                if chunk_index % 50 == 0:  # 50개 청크마다
                    await self.memory_manager.manage_memory_pressure()

    async def generate_embedding(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model("embedding")
        response = await self.client.embeddings.create(
            model=model,
            input=texts
        )

        return [embedding.embedding for embedding in response.data]
```

## 3. 실행 및 테스트 방법

### 3.1 개발 환경 설정

#### uv 기반 개발

```bash
# 프로젝트 초기화
uv init content-loader
cd content-loader

# 의존성 설치
uv add fastapi uvicorn aiohttp pydantic python-dotenv
uv add --dev pytest pytest-asyncio pytest-mock

# 개발 서버 실행
uv run python -m content_loader.main
```

#### Tiltfile 설정

```python
# Tiltfile
docker_build('content-loader', '.')

k8s_yaml('k8s/deployment.yaml')

local_resource(
    'content-loader-dev',
    serve_cmd='uv run python -m content_loader.main',
    deps=['src/', 'config/'],
    readiness_probe=probe(
        http_get=http_get_action(port=8000, path='/health')
    )
)
```

### 3.2 개별 Loader 테스트

#### Slack Loader 테스트

```python
# scripts/test_slack.py
import asyncio
from content_loader.loaders.slack import SlackLoader, SlackClient
from content_loader.settings import Settings

async def test_slack_loader():
    settings = Settings()
    client = SlackClient(settings.slack_token)
    loader = SlackLoader(client)

    # 테스트 소스 정의
    source = SlackSource(
        key="test-channel",
        workspace="T029G2MBUF6",
        channel="C052ADQ5B3N",
        name="#test-channel"
    )

    # 문서 로드 테스트
    documents = []
    async for doc in loader.load_source(source):
        documents.append(doc)
        if len(documents) >= 10:  # 처음 10개만 테스트
            break

    print(f"로드된 문서 수: {len(documents)}")
    for doc in documents[:3]:  # 처음 3개 출력
        print(f"ID: {doc.id}")
        print(f"제목: {doc.title}")
        print(f"내용: {doc.text[:100]}...")
        print("---")

if __name__ == "__main__":
    asyncio.run(test_slack_loader())
```

#### Confluence Loader 테스트

```python
# scripts/test_confluence.py
import asyncio
from content_loader.loaders.confluence import ConfluenceLoader, ConfluenceClient
from content_loader.settings import Settings

async def test_confluence_loader():
    settings = Settings()
    client = ConfluenceClient(
        base_url=settings.confluence_url,
        email=settings.confluence_email,
        api_token=settings.confluence_token
    )
    loader = ConfluenceLoader(client)

    source = ConfluenceSource(
        key="engineering-space",
        space="ENG",
        type="space"
    )

    documents = []
    async for doc in loader.load_source(source):
        documents.append(doc)
        if len(documents) >= 5:
            break

    print(f"로드된 문서 수: {len(documents)}")
    for doc in documents:
        print(f"제목: {doc.title}")
        print(f"스페이스: {doc.metadata.get('space_key')}")
        print(f"URL: {doc.metadata.get('url')}")
        print("---")

if __name__ == "__main__":
    asyncio.run(test_confluence_loader())
```

#### GitHub Loader 테스트

```python
# scripts/test_github.py
import asyncio
from content_loader.loaders.github import GitHubLoader, GitHubClient
from content_loader.settings import Settings

async def test_github_loader():
    settings = Settings()
    client = GitHubClient(
        app_id=settings.github_app_id,
        private_key_path=settings.github_private_key_path,
        installation_id=settings.github_installation_id
    )
    loader = GitHubLoader(client)

    # Issues 테스트
    issue_source = GitHubSource(
        key="backend-issues",
        owner="company",
        name="backend-service",
        type="issues"
    )

    print("=== GitHub Issues 테스트 ===")
    async for doc in loader.load_source(issue_source):
        print(f"이슈: {doc.title}")
        print(f"상태: {doc.metadata.get('state')}")
        print(f"작성자: {doc.metadata.get('author')}")
        print("---")
        break  # 첫 번째만 테스트

    # Files 테스트
    file_source = GitHubSource(
        key="docs-files",
        owner="company",
        name="documentation",
        type="files",
        options=GitHubOptions(extensions=[".md"])
    )

    print("=== GitHub Files 테스트 ===")
    async for doc in loader.load_source(file_source):
        print(f"파일: {doc.title}")
        print(f"경로: {doc.metadata.get('path')}")
        print(f"크기: {doc.metadata.get('size')} bytes")
        print("---")
        break

if __name__ == "__main__":
    asyncio.run(test_github_loader())
```

### 3.3 통합 테스트

#### Full Pipeline 테스트

```python
# scripts/test_full_pipeline.py
import asyncio
from content_loader.main import ContentLoaderApp
from content_loader.settings import Settings

async def test_full_pipeline():
    settings = Settings()
    llm_settings = LLMSettings()
    app = ContentLoaderApp(settings, llm_settings)

    # 단일 소스 로드 테스트
    result = await app.load_single_source(
        source_type="slack",
        source_key="test-channel"
    )

    print(f"처리 결과: {result}")
    print(f"성공: {result.success}")
    print(f"처리된 문서 수: {result.processed_count}")
    print(f"사용된 LLM 프로바이더: {llm_settings.provider}")
    if result.errors:
        print(f"오류: {result.errors}")

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
```

### 3.4 Docker 기반 실행

#### docker-compose.yml

```yaml
version: '3.8'

services:
  content-loader:
    build: .
    ports:
      - "8000:8000"
    environment:
      - EMBEDDING_SERVICE_URL=http://embedding-retrieval:8000
      # LLM 서비스 설정
      - LLM_PROVIDER=${LLM_PROVIDER:-internal}
      - INTERNAL_LLM_URL=${INTERNAL_LLM_URL}
      - INTERNAL_API_KEY=${INTERNAL_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - OPENAI_BASE_URL=${OPENAI_BASE_URL:-https://api.openai.com/v1}
      - SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
      - CONFLUENCE_EMAIL=${CONFLUENCE_EMAIL}
      - CONFLUENCE_API_TOKEN=${CONFLUENCE_API_TOKEN}
      # Redis 캐싱 설정
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    volumes:
      - ./config:/app/config
      - ./secrets:/app/secrets
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --maxmemory-policy allkeys-lru --maxmemory 256mb

  # Redis 모니터링 도구
  redis-commander:
    image: rediscommander/redis-commander:latest
    ports:
      - "8081:8081"
    environment:
      - REDIS_HOSTS=local:redis:6379
    depends_on:
      - redis

  embedding-retrieval:
    image: embedding-retrieval:latest
    ports:
      - "8001:8000"
    environment:
      - QDRANT_HOST=qdrant
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - qdrant

  qdrant:
    image: qdrant/qdrant:v1.7.0
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  qdrant_data:
```

#### 실행 명령어

```bash
# 개발 환경 시작
docker-compose up -d

# 로그 확인
docker-compose logs -f content-loader

# 특정 소스 테스트
docker-compose exec content-loader python scripts/test_slack.py

# 전체 파이프라인 실행
docker-compose exec content-loader python -m content_loader.main --run-once
```

### 3.5 로컬 개발 환경 설정 및 모니터링

#### 로컬 개발 서비스 접근 정보

| 서비스 | 접속 URL | 로그인 정보 |
|--------|----------|-------------|
| Redis Commander | http://localhost:8081 | 로그인 불필요 |
| Qdrant 대시보드 | http://localhost:6333/dashboard | 로그인 불필요 |

#### Redis 캐시 확인 방법

```bash
# Redis Commander 웹 인터페이스에서 확인
# http://localhost:8081 접속

# 명령줄에서 확인
docker-compose exec redis redis-cli
> KEYS summary:*
> GET summary:1234567890abcdef

# 캐시 통계 확인
docker-compose exec redis redis-cli INFO stats
```

#### 환경 변수 설정 (.env 파일)

```bash
# .env 파일 생성
# LLM 서비스 설정
LLM_PROVIDER=internal                    # "internal" 또는 "openai"

# 사내 LLM 프록시 설정 (LLM_PROVIDER=internal 시 사용)
INTERNAL_LLM_URL=https://your-internal-llm-proxy.com
INTERNAL_API_KEY=your-internal-api-key
INTERNAL_MODEL=gpt-3.5-turbo
INTERNAL_EMBEDDING_MODEL=text-embedding-ada-002

# OpenAI 직접 연결 설정 (LLM_PROVIDER=openai 시 사용)
OPENAI_API_KEY=your-openai-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo
OPENAI_EMBEDDING_MODEL=text-embedding-ada-002
OPENAI_ORGANIZATION=your-org-id

# 데이터 소스 설정
SLACK_BOT_TOKEN=xoxb-your-slack-token
CONFLUENCE_EMAIL=your-email@company.com
CONFLUENCE_API_TOKEN=your-confluence-token
GITHUB_APP_ID=your-github-app-id
GITHUB_PRIVATE_KEY_PATH=/app/secrets/github-private-key.pem

# Redis 캐싱 설정
REDIS_HOST=redis
REDIS_PORT=6379
```

#### 개발 워크플로우

##### 1. 초기 설정

```bash
# 1. 저장소 클론
git clone <repository-url>
cd content-loader

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일 수정

# 3. 개발 환경 시작
docker-compose up -d

# 4. 로그 확인
docker-compose logs -f content-loader
```

##### 2. 개발 중 캐시 동작 확인

```bash
# 첫 번째 요약 실행 (캐시 미스)
docker-compose exec content-loader python -c "
from content_loader.services.summarizer import SummarizerService
from content_loader.settings import LLMSettings
import asyncio

async def test():
    llm_settings = LLMSettings()
    service = SummarizerService(llm_settings, cache_client)
    result = await service.summarize('테스트 텍스트')
    print(f'첫 번째 실행: {result}')
    print(f'사용된 프로바이더: {llm_settings.provider}')

asyncio.run(test())
"
```

##### 3. 캐시 무효화 테스트

```bash
# Redis 캐시 초기화
docker-compose exec redis redis-cli FLUSHDB

# 특정 키 삭제
docker-compose exec redis redis-cli DEL "summary:1234567890abcdef"
```

#### 개발 환경 리셋

```bash
# 전체 환경 재시작
docker-compose down -v
docker-compose up -d

# Redis 캐시만 초기화
docker-compose exec redis redis-cli FLUSHALL
```

## 4. 종류별 독립 실행 방법

### 4.1 개별 Loader 실행 옵션

각 content-loader를 종류별로 독립적으로 실행하는 다양한 방법을 제공합니다:

#### Option A: 개별 테스트 스크립트

```bash
# Slack 단독 실행
uv run python scripts/test_slack.py

# Confluence 단독 실행
uv run python scripts/test_confluence.py

# GitHub 단독 실행
uv run python scripts/test_github.py
```

#### Option B: 단일 소스 로드 API

```python
# 특정 소스만 실행
from content_loader.main import ContentLoaderApp

await app.load_single_source(
    source_type="slack",
    source_key="engineering-general"
)
```

#### Option C: 커맨드라인 인자

```bash
# 특정 loader 타입만 실행
uv run python -m content_loader.main --source-type slack
uv run python -m content_loader.main --source-type github
uv run python -m content_loader.main --source-type confluence
```

#### Option D: Docker 컨테이너 분리

```yaml
# docker-compose.yml
services:
  slack-loader:
    build: .
    command: python -m content_loader.main --source-type slack
    environment:
      - SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}

  github-loader:
    build: .
    command: python -m content_loader.main --source-type github
    environment:
      - GITHUB_APP_ID=${GITHUB_APP_ID}
      - GITHUB_PRIVATE_KEY_PATH=${GITHUB_PRIVATE_KEY_PATH}

  confluence-loader:
    build: .
    command: python -m content_loader.main --source-type confluence
    environment:
      - CONFLUENCE_EMAIL=${CONFLUENCE_EMAIL}
      - CONFLUENCE_API_TOKEN=${CONFLUENCE_API_TOKEN}
```

### 4.2 스케줄링 분리 전략

#### 전략 1: 차등 스케줄링 (권장)

```yaml
# config/scheduler.yaml
scheduler:
  strategy: "differential"

  sources:
    slack:
      schedule: "0 9,14,18 * * *"    # 하루 3회 (9시, 14시, 18시)
      priority: high
      timeout: 30m

    github:
      schedule: "0 8,20 * * *"       # 하루 2회 (8시, 20시)
      priority: high
      timeout: 60m                   # 소스코드 인덱싱 고려

    confluence:
      schedule: "0 10 * * *"         # 하루 1회 (10시)
      priority: medium
      timeout: 20m
```

#### 전략 2: Kubernetes CronJob 분리

```yaml
# k8s/slack-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: slack-loader
spec:
  schedule: "0 9,14,18 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: slack-loader
            image: content-loader:latest
            command: ["python", "-m", "content_loader.main", "--source-type", "slack"]
            env:
            - name: SLACK_BOT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: slack-secret
                  key: token
```

#### 전략 3: 환경별 분리 설정

```yaml
# config/environments/dev.yaml
scheduler:
  sources:
    slack:
      schedule: "0 10 * * *"         # 개발: 하루 1회
    github:
      schedule: "0 11 * * *"         # 개발: 하루 1회
    confluence:
      schedule: "0 12 * * 0"         # 개발: 주 1회

# config/environments/prod.yaml
scheduler:
  sources:
    slack:
      schedule: "0 9,14,18 * * *"    # 프로덕션: 하루 3회
    github:
      schedule: "0 8,20 * * *"       # 프로덕션: 하루 2회
    confluence:
      schedule: "0 10 * * *"         # 프로덕션: 하루 1회
```

### 4.3 실행 빈도 및 스케줄링 전략

#### 데이터 소스별 특성 분석

각 데이터 소스는 서로 다른 업데이트 패턴과 비즈니스 임팩트를 가지므로 차등 스케줄링이 필요합니다:

| 데이터 소스 | 업데이트 빈도 | 비즈니스 임팩트 | 데이터 볼륨 | 권장 실행 빈도 |
|------------|-------------|--------------|------------|-------------|
| Slack      | 매우 높음 (실시간) | 높음 (최신 논의) | 중간 | 하루 3회 |
| GitHub     | 높음 (개발 활동) | 높음 (코드/이슈) | 높음 | 하루 2회 |
| Confluence | 낮음-중간 (문서) | 중간 (정책/문서) | 중간 | 하루 1회 |

### 4.2 간단한 cron 기반 스케줄링

```yaml
# config/scheduler.yaml - 단순한 cron 기반 설정
scheduler:
  slack:
    schedule: "0 9,14,18 * * *"    # 하루 3회
    timeout: 30m

  github:
    schedule: "0 8,20 * * *"       # 하루 2회
    timeout: 60m

  confluence:
    schedule: "0 10 * * *"         # 하루 1회
    timeout: 20m
```

### 4.3 스케줄링 고려사항

- **API Rate Limit**: GitHub (5000/hour), Slack (50+ calls/min) 준수
- **실행 시간**: 소스코드 인덱싱 등 긴 처리 시간 고려
- **업무 시간**: 오전 9시-오후 6시 집중 업데이트
- **모니터링**: 각 실행의 성공률과 성능 지표 추적

이 설계를 통해 기존의 분산된 loader들을 통합하면서도 각각의 특성을 유지하고, 데이터 신선도와 시스템 성능을 균형있게 최적화하는 확장 가능한 아키텍처를 구현할 수 있습니다.
