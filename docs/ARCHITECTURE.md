# Content Loader 아키텍처 설계

## 🏗️ 전체 아키텍처

Content Loader는 **계층 분리 아키텍처**를 기반으로 설계되었습니다.

```
content-loader/
├── main.py                    # CLI 진입점
├── executor.py               # 통합 실행기
├── settings.py               # 전역 설정 관리
├── core/                     # 공통 기능 (기반 레이어)
└── loaders/                  # 구현 레이어
    ├── slack/
    ├── confluence/
    └── github/
```

## 🎯 핵심 설계 원칙

### 1. 계층 분리 + 스트리밍 (Layered + Streaming)

- **core/**: 공통 기반 기능 (BaseExecutor, Models, Utils)
- **loaders/**: 구체적인 데이터 소스별 구현체
- **의존성 방향**: `loaders/` → `core/` (단방향)
- **스트리밍**: AsyncGenerator로 메모리 효율적 처리

### 2. 독립성 + 견고성 (Independence + Resilience)

- 각 loader는 완전히 독립적으로 개발/배포 가능
- 새로운 loader 추가 시 기존 코드 수정 불필요
- 설정과 코드가 동일한 디렉토리에 위치
- **통합 재시도 로직**으로 네트워크 오류 대응

### 3. 확장성 + 심플함 (Extensibility + Simplicity)

- 동일한 인터페이스(`BaseExecutor`) 구현으로 일관성 유지
- 플러그인 방식으로 새 loader 추가 가능
- **복잡한 패턴 배제**, 핵심 기능만 구현

## 🔧 핵심 컴포넌트

### **1. Core Layer (공통 기능)**

```python
# core/base.py - 통합 실행기 패턴
@dataclass
class DateRange:
    start: Optional[datetime] = None
    end: Optional[datetime] = None

    def includes(self, target_date: datetime) -> bool:
        if self.start and target_date < self.start:
            return False
        if self.end and target_date > self.end:
            return False
        return True

class BaseExecutor(ABC):
    """통합 실행기 - 스트리밍 + 견고성"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.retry_handler = SimpleRetryHandler()

    @abstractmethod
    async def fetch(self, date_range: DateRange) -> AsyncGenerator[Document, None]:
        """스트리밍으로 문서 로드"""
        pass

    async def execute(self, date_range: Optional[DateRange] = None) -> AsyncGenerator[Document, None]:
        """실행 + 기본 에러 처리"""
        if not date_range:
            date_range = DateRange()

        async for document in self.retry_handler.execute_with_retry(
            lambda: self.fetch(date_range)
        ):
            yield document

# core/models.py - 공통 데이터 모델
@dataclass
class Document:
    id: str
    title: str
    text: str
    metadata: Dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# core/utils.py - 심플한 유틸리티
class SimpleRetryHandler:
    """지수 백오프 재시도 로직"""

    async def execute_with_retry(self, func_generator):
        for attempt in range(3):
            try:
                async for item in func_generator():
                    yield item
                break
            except (ConnectionError, TimeoutError) as e:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise

class SimpleMemoryManager:
    """배치 단위 메모리 관리"""

    async def process_batch(self, documents_stream, batch_size=20):
        batch = []
        async for doc in documents_stream:
            batch.append(doc)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch
```

### **2. Execution Layer (실행 계층) - 스트리밍 기반**

```python
# executor.py - 통합 실행기 (스트리밍)
class LoaderExecutor:
    def __init__(self, settings: GlobalSettings):
        self.executors = {
            "slack": SlackExecutor(settings.slack),
            "github": GitHubExecutor(settings.github),
            "confluence": ConfluenceExecutor(settings.confluence)
        }
        self.memory_manager = SimpleMemoryManager()

    async def run_single_loader(self, loader_type: str, date_range: DateRange = None):
        """특정 loader 스트리밍 실행"""
        executor = self.executors[loader_type]

        # 스트리밍 + 배치 처리
        async for batch in self.memory_manager.process_batch(
            executor.execute(date_range)
        ):
            # 배치 단위로 벡터DB 저장
            # 문서 처리 + 임베딩 + 벡터 저장
            await self._process_and_store_batch(batch)

    async def run_all_loaders(self, date_range: DateRange = None):
        """모든 loader 병렬 실행 (스트리밍)"""
        tasks = []
        for loader_type in self.executors.keys():
            tasks.append(self.run_single_loader(loader_type, date_range))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_and_store_batch(self, documents: List[Document]):
        """문서 배치 처리 + 벡터 저장"""
        document_processor = DocumentProcessor()
        embedding_service = EmbeddingService()

        for document in documents:
            # 1. 스마트 청킹 + 콘텐츠별 요약
            processed_chunks = await document_processor.process_document(document)

            # 2. 임베딩 + Qdrant 저장
            await embedding_service.embed_and_store(processed_chunks, "content_vectors")
```

### **3. Configuration Layer (설정 계층)**

```python
# settings.py - 설정 관리
class LoaderConfigManager:
    def load_loader_config(self, loader_name: str) -> dict:
        """loader별 설정 로드"""
        config_dir = Path(f"loaders/{loader_name}/config")
        return self._load_with_env_override(config_dir)

    def load_loader_sources(self, loader_name: str) -> dict:
        """loader별 소스 설정 로드"""
        # Slack: channels.yaml, GitHub: repositories.yaml, etc.
        pass
```

## 🔄 데이터 플로우

```mermaid
graph TD
    A[main.py] --> B[LoaderExecutor]
    B --> C[SlackLoader]
    B --> D[GitHubLoader]
    B --> E[ConfluenceLoader]

    C --> F[SlackClient]
    D --> G[GitHubClient]
    E --> H[ConfluenceClient]

    F --> I[Document Processing]
    G --> I
    H --> I

    I --> J[DocumentProcessor]
    J --> K[Smart Chunking]
    K --> L[Content-aware Summarization]
    L --> M[EmbeddingService]
    M --> N[Qdrant Vector DB]
```

## 🛡️ 에러 처리 및 복구

### 1. 심플한 재시도 로직

```python
class SimpleRetryHandler:
    """지수 백오프 재시도 로직"""

    async def execute_with_retry(self, func_generator, max_retries=3):
        for attempt in range(max_retries):
            try:
                async for item in func_generator():
                    yield item
                break
            except (ConnectionError, TimeoutError, aiohttp.ClientError) as e:
                if attempt < max_retries - 1:
                    backoff_time = 2 ** attempt  # 지수 백오프
                    await asyncio.sleep(backoff_time)
                else:
                    raise
```

### 2. 체크포인트 기반 복구 (증분 업데이트)

```python
class CheckpointManager:
    """DateRange 기반 체크포인트 관리"""

    async def save_progress(self, source_key: str, last_modified: datetime):
        """마지막 처리 시간 저장"""
        await self.cache_client.set(
            f"checkpoint:{source_key}",
            last_modified.isoformat(),
            expire=86400*30  # 30일 보관
        )

    async def get_last_checkpoint(self, source_key: str) -> Optional[datetime]:
        """마지막 체크포인트로 DateRange 구성"""
        checkpoint = await self.cache_client.get(f"checkpoint:{source_key}")
        return datetime.fromisoformat(checkpoint) if checkpoint else None
```

## 🚀 성능 최적화

### 1. 스트리밍 메모리 관리

```python
class SimpleMemoryManager:
    """스트리밍 기반 배치 처리"""

    async def process_batch(self, documents_stream, batch_size=20):
        """스트리밍 + 배치 처리로 메모리 효율성"""
        batch = []
        async for doc in documents_stream:
            batch.append(doc)

            if len(batch) >= batch_size:
                yield batch
                batch = []
                # 메모리 정리
                import gc; gc.collect()

        if batch:  # 마지막 배치
            yield batch
```

### 2. 페이지네이션 처리

```python
class BaseExecutor:
    """커서 기반 페이지네이션"""

    async def _paginate_fetch(self, initial_params: dict):
        """커서 기반으로 페이지별 데이터 가져오기"""
        cursor = None

        while True:
            params = {**initial_params}
            if cursor:
                params['cursor'] = cursor

            response = await self._make_request(params)

            for item in response.get('items', []):
                yield item

            # 다음 페이지 확인
            if not response.get('has_next_page'):
                break
            cursor = response.get('next_cursor')
```

### 3. 연결 풀 관리

```python
class SimpleClient:
    """재시도 로직 + 연결 관리"""

    def __init__(self, settings):
        self.semaphore = asyncio.Semaphore(settings.max_concurrent)
        self.retry_handler = SimpleRetryHandler()

    async def make_request(self, url: str, **kwargs):
        async with self.semaphore:
            # 재시도 로직 적용
            async for response in self.retry_handler.execute_with_retry(
                lambda: self._single_request(url, **kwargs)
            ):
                return response
```

## 🧠 문서 처리 및 벡터 저장

### 1. Content-Aware Processing

```python
class DocumentProcessor:
    """콘텐츠 타입별 최적화된 문서 처리"""

    def __init__(self):
        self.content_detector = ContentTypeDetector()
        self.summarization_strategies = {
            "source_code": {"should_summarize": False, "chunk_strategy": "function_based"},
            "documentation": {"should_summarize": True, "chunk_strategy": "semantic"},
            "conversation": {"should_summarize": True, "chunk_strategy": "thread_based"},
            "mixed_content": {"should_summarize": True, "chunk_strategy": "adaptive"}
        }

    async def process_document(self, document: Document) -> List[ProcessedChunk]:
        """문서 타입에 따른 차별화된 처리"""

        # 1. 콘텐츠 타입 자동 감지
        content_type = self.content_detector.detect_content_type(document)
        strategy = self.summarization_strategies[content_type]

        # 2. 타입별 스마트 청킹
        chunks = await self._smart_chunk(document, strategy["chunk_strategy"])

        processed_chunks = []
        for chunk in chunks:
            # 3. 원본 청크 항상 생성 (라인 정보 포함)
            processed_chunks.append(self._create_chunk(chunk, "original", content_type))

            # 4. 요약 청크 생성 (필요시만)
            if strategy["should_summarize"] and len(chunk.text) > 500:
                summary = await self._summarize_chunk(chunk, content_type)
                processed_chunks.append(self._create_chunk(summary, "summary", content_type))

        return processed_chunks

class ContentTypeDetector:
    """메타데이터 + 내용 분석으로 콘텐츠 타입 감지"""

    def detect_content_type(self, document: Document) -> str:
        # GitHub 소스코드 파일 체크
        if document.metadata.get('source_type') == 'github':
            file_path = document.metadata.get('file_path', '')
            if file_path.endswith(('.py', '.js', '.ts', '.java', '.cpp', '.go')):
                return "source_code"
            elif file_path.endswith(('.md', '.rst', '.txt')):
                return "documentation"

        # Slack은 대화형
        elif document.metadata.get('source_type') == 'slack':
            return "conversation"

        # Confluence는 문서
        elif document.metadata.get('source_type') == 'confluence':
            return "documentation"

        # 내용 분석으로 분류
        return self._analyze_content(document.text)

class SmartCodeParser:
    """Tree-sitter 기반 AST 코드 청킹"""

    def __init__(self):
        self.MAX_BLOCK_CHARS = 1024
        self.MIN_BLOCK_CHARS = 200
        self.TOLERANCE_FACTOR = 1.5

    async def chunk_code_file(self, document: Document) -> List[CodeChunk]:
        """AST 기반 계층적 코드 청킹"""
        file_path = document.metadata.get('file_path', '')
        language = self._detect_language(file_path)

        # 1. Tree-sitter로 AST 생성
        tree = self._parse_with_tree_sitter(document.text, language)

        # 2. 계층적 노드 추출
        code_blocks = self._extract_code_blocks(tree.root_node, document.text)

        # 3. 크기 기반 자동 청킹
        chunks = []
        for block in code_blocks:
            if len(block.text) > self.MAX_BLOCK_CHARS * self.TOLERANCE_FACTOR:
                # 큰 블록은 더 작은 단위로 분할
                sub_chunks = await self._chunk_large_block(block)
                chunks.extend(sub_chunks)
            else:
                chunks.append(block)

        return chunks

    async def _chunk_large_block(self, block: CodeBlock) -> List[CodeChunk]:
        """큰 코드 블록을 의미 단위로 분할"""

        # 1. 자식 노드가 있으면 자식 단위로 분할
        if block.children:
            chunks = []
            for child in block.children:
                if len(child.text) >= self.MIN_BLOCK_CHARS:
                    chunks.append(CodeChunk(
                        text=child.text,
                        start_line=child.start_line,
                        end_line=child.end_line,
                        node_type=child.node_type,
                        hash=self._generate_hash(child.text)
                    ))
            return chunks

        # 2. 리프 노드는 라인 기반 분할
        return self._chunk_by_lines(block)

    def _chunk_by_lines(self, block: CodeBlock) -> List[CodeChunk]:
        """라인 단위 청킹 (의미 보존)"""
        lines = block.text.split('\n')
        chunks = []
        current_chunk = []
        current_size = 0
        start_line = block.start_line

        for i, line in enumerate(lines):
            current_chunk.append(line)
            current_size += len(line)

            # 청크 크기 체크
            if (current_size >= self.MIN_BLOCK_CHARS and
                current_size <= self.MAX_BLOCK_CHARS):

                # 의미있는 끝점에서 분할 (함수 끝, 클래스 끝 등)
                if self._is_good_break_point(line):
                    chunks.append(CodeChunk(
                        text='\n'.join(current_chunk),
                        start_line=start_line,
                        end_line=start_line + len(current_chunk) - 1,
                        node_type=block.node_type,
                        hash=self._generate_hash('\n'.join(current_chunk))
                    ))
                    current_chunk = []
                    current_size = 0
                    start_line = start_line + i + 1

        # 마지막 청크 처리
        if current_chunk and current_size >= self.MIN_BLOCK_CHARS:
            chunks.append(CodeChunk(
                text='\n'.join(current_chunk),
                start_line=start_line,
                end_line=start_line + len(current_chunk) - 1,
                node_type=block.node_type,
                hash=self._generate_hash('\n'.join(current_chunk))
            ))

        return chunks
```

### 2. 임베딩 및 벡터 저장

```python
class EmbeddingService:
    """배치 기반 임베딩 + Qdrant 저장"""

    def __init__(self):
        self.model_name = "text-embedding-3-small"
        self.qdrant_client = QdrantClient()

    async def embed_and_store(self, chunks: List[ProcessedChunk], collection: str):
        """배치 단위로 임베딩 + 저장"""
        batch_size = 50

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]

            # 1. 임베딩 생성
            texts = [chunk.text for chunk in batch]
            embeddings = await self._generate_embeddings(texts)

            # 2. Qdrant 포인트 구성
            points = [
                PointStruct(
                    id=chunk.id,
                    vector=embedding,
                    payload={
                        "text": chunk.text,
                        "content_type": chunk.metadata.get("content_type"),
                        "chunk_type": chunk.metadata.get("chunk_type"),  # original/summary
                        "source_type": chunk.metadata.get("source_type"),
                        "start_line": chunk.metadata.get("start_line"),  # 코드 라인 정보
                        "end_line": chunk.metadata.get("end_line"),
                        "node_type": chunk.metadata.get("node_type"),    # function, class 등
                        "code_hash": chunk.metadata.get("hash"),         # 중복 방지
                        **chunk.metadata
                    }
                )
                for chunk, embedding in zip(batch, embeddings)
            ]

            # 3. 벡터 저장
            await self.qdrant_client.upsert(collection_name=collection, points=points)
```

### 3. 스마트 요약 기준

```python
class SmartSummarizationRules:
    """실용적인 요약 기준"""

    @staticmethod
    def should_summarize(chunk: Chunk, content_type: str) -> bool:
        """청크별 요약 필요 여부 판단"""

        # 1. 소스코드도 길면 요약 (단, 신중하게)
        if content_type == "source_code":
            # 매우 긴 코드만 요약 (주석/docstring 위주)
            return text_length >= 2000

        # 2. 크기 기준 (핵심!)
        text_length = len(chunk.text)
        if text_length < 300:  # 너무 짧으면 요약 불필요
            return False
        if text_length < 800:  # 적당한 크기면 선택적
            return content_type in ["conversation"]  # 대화만 요약
        if text_length >= 1500:  # 긴 텍스트는 무조건 요약
            return True

        # 3. 콘텐츠 타입별 중간 크기 처리
        return {
            "documentation": text_length >= 600,  # 문서는 조금 더 관대
            "conversation": text_length >= 400,   # 대화는 빨리 요약
            "mixed_content": text_length >= 500   # Mixed는 중간
        }.get(content_type, False)

# 실제 요약 기준 테이블
SUMMARIZATION_THRESHOLDS = {
    "source_code": {"enabled": True, "min_length": 2000, "prompt": "코드의 기능과 목적을 간단히 설명:"},
    "documentation": {"enabled": True, "min_length": 600},
    "conversation": {"enabled": True, "min_length": 400},
    "mixed_content": {"enabled": True, "min_length": 500}
}
```

### 4. 요약 기준 요약

| 콘텐츠 타입 | 기본 정책 | 최소 길이 | 무조건 요약 | 요약 방식 |
|------------|----------|----------|------------|----------|
| **소스코드** | 🌳 AST 기반 청킹 | 200-1024자 단위 | 2000자 이상 | Tree-sitter로 의미 단위 분할 |
| **문서** | 📏 크기 기준 | 600자 이상 | 1500자 이상 | 핵심 내용 요약 |
| **대화** | 📏 크기 기준 | 400자 이상 | 1500자 이상 | 결론/액션 아이템 |
| **Mixed** | 📏 크기 기준 | 500자 이상 | 1500자 이상 | 선택적 요약 |

**💡 스마트 코드 청킹 아이디어**:
- **AST 기반 분할**: Tree-sitter로 함수/클래스 단위 의미 보존
- **계층적 청킹**: 큰 블록 → 자식 노드 → 라인 단위 순차 분할
- **라인 정보 보존**: start_line, end_line으로 정확한 위치 추적
- **중복 방지**: 코드 해시로 동일 코드 블록 감지
- **의미적 끝점**: 함수/클래스 끝에서 자연스럽게 분할

## 📊 모니터링 및 메트릭

### 1. 헬스 체크

```python
@app.get("/health")
async def health_check():
    """기본 헬스 체크"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/health/detailed")
async def detailed_health_check():
    """상세 헬스 체크"""
    checks = {
        "redis": await check_redis_connection(),
        "embedding_service": await check_embedding_service(),
        "llm_service": await check_llm_service()
    }
    return {"status": "healthy" if all(checks.values()) else "unhealthy", "checks": checks}
```

### 2. 메트릭 수집

```python
@dataclass
class SimpleMetrics:
    source_type: str
    source_key: str
    start_time: float
    documents_processed: int = 0
    errors_count: int = 0

    def success_rate(self) -> float:
        total = self.documents_processed + self.errors_count
        return self.documents_processed / total if total > 0 else 0.0

class MetricsCollector:
    def get_summary(self) -> dict:
        return {
            "total_sources": len(self.metrics),
            "sources": {k: {
                "duration": v.duration(),
                "documents": v.documents_processed,
                "success_rate": v.success_rate()
            } for k, v in self.metrics.items()}
        }
```

## 🔐 보안 고려사항

### 1. 인증 정보 관리

- 모든 API 키/토큰은 **환경변수**로 관리
- `.env` 파일 및 민감 정보는 **git에서 제외**
- 로그에 인증 정보 **노출 방지**

### 2. API 연결 검증

```python
class ConnectionValidator:
    async def validate_all_connections(self) -> dict:
        """시작 시 모든 외부 서비스 연결 검증"""
        results = {}

        if self.settings.slack_token:
            results["slack"] = await self._validate_slack()
        if self.settings.github_app_id:
            results["github"] = await self._validate_github()

        return results

    async def _validate_slack(self) -> dict:
        """Slack 연결 검증 (auth.test 호출)"""
        try:
            client = AsyncWebClient(token=self.settings.slack_token)
            response = await client.auth_test()
            return {"status": "success", "user_id": response["user_id"]}
        except Exception as e:
            return {"status": "failed", "error": str(e)}
```

## 🔄 확장 방법

### 새로운 Executor 추가

1. **디렉토리 구조 생성**

```
loaders/new_source/
├── config/
│   ├── config.yaml
│   └── sources.yaml
├── executor.py     # 실행기
├── client.py
└── entities.py     # 데이터 모델
```

2. **BaseExecutor 구현**

```python
from core.base import BaseExecutor, DateRange, Document

class NewSourceExecutor(BaseExecutor):
    def __init__(self, config: dict):
        super().__init__(config)
        self.client = NewSourceClient(config)

    async def fetch(self, date_range: DateRange) -> AsyncGenerator[Document, None]:
        """스트리밍으로 문서 로드"""

        # 증분 업데이트
        params = self._build_query_params(date_range)

        # 페이지네이션 처리
        async for item in self._paginate_fetch(params):
            document = self._item_to_document(item)
            yield document

    def _build_query_params(self, date_range: DateRange) -> dict:
        """DateRange를 API 파라미터로 변환"""
        params = {}
        if date_range.start:
            params['modified_since'] = date_range.start.isoformat()
        if date_range.end:
            params['modified_until'] = date_range.end.isoformat()
        return params
```

3. **LoaderExecutor에 등록**

```python
# executor.py
self.executors = {
    "slack": SlackExecutor(settings.slack),
    "github": GitHubExecutor(settings.github),
    "confluence": ConfluenceExecutor(settings.confluence),
    "new_source": NewSourceExecutor(settings.new_source)  # 추가
}
```

## 🎯 개선 요약

### ✅ 적용된 핵심 패턴들

1. **BaseExecutor 패턴**: 일관된 `fetch()` 인터페이스
2. **스트리밍 처리**: `AsyncGenerator[Document, None]` 반환
3. **견고한 재시도**: 지수 백오프 + HTTP 상태코드별 처리
4. **DateRange 기반**: 증분 업데이트 최적화
5. **페이지네이션**: 메모리 효율적 대용량 처리
6. **배치 처리**: 스트리밍과 결합한 메모리 관리

### 🎯 심플함 유지

- **복잡한 Circuit Breaker 제거** → 심플한 재시도만
- **요약 기능은 옵션** → 기본 기능에 집중
- **최소한의 인터페이스** → BaseExecutor 하나로 통일
- **설정 기반 확장** → 코드 변경 최소화

이 아키텍처는 **견고함과 심플함**을 결합한 구조로, 확장성과 유지보수성을 모두 확보했습니다.
