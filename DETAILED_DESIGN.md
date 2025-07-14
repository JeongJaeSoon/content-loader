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
        return bool(doc.text and doc.text.strip())
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
        loader = self.loaders[source_type]
        async for document in loader.load_source(source):
            if loader._should_process_document(document):
                await self._process_document(document)
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

#### CacheClient (S3 + Redis 하이브리드)
```python
class CacheClient:
    def __init__(self, s3_client: S3Client, redis_client: RedisClient):
        self.s3_client = s3_client
        self.redis_client = redis_client

    async def get(self, key: str) -> Optional[str]:
        # 1. Redis에서 먼저 확인 (빠른 접근)
        cached_value = await self.redis_client.get(key)
        if cached_value:
            return cached_value

        # 2. S3에서 확인 (영구 저장소)
        try:
            s3_value = await self.s3_client.get_object(key)
            if s3_value:
                # S3에서 가져온 값을 Redis에 캐시
                await self.redis_client.set(key, s3_value, expire=3600)
                return s3_value
        except NoSuchKeyError:
            pass

        return None

    async def set(self, key: str, value: str, expire: int = 86400) -> None:
        # 1. Redis에 단기 캐시 저장
        await self.redis_client.set(key, value, expire=min(expire, 3600))

        # 2. S3에 장기 캐시 저장 (비동기)
        await self.s3_client.put_object(key, value)

    def _generate_cache_key(self, text: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(text.encode("utf-8"))
        digest = hasher.hexdigest()
        return f"summary/{digest[:4]}/{digest}"
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
      # AWS 캐싱 설정
      - S3_ENDPOINT=http://minio:9000
      - AWS_ACCESS_KEY_ID=minio
      - AWS_SECRET_ACCESS_KEY=miniominio
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - SUMMARY_CACHE_BUCKET=content-loader-summary-cache
      - METADATA_CACHE_BUCKET=content-loader-metadata-cache
    volumes:
      - ./config:/app/config
      - ./secrets:/app/secrets
    depends_on:
      - redis
      - minio

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

  # MinIO (S3 호환 객체 스토리지)
  minio:
    image: minio/minio:RELEASE.2023-05-04T21-44-30Z
    ports:
      - "9000:9000"    # API 포트
      - "9001:9001"    # 웹 콘솔 포트
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD: miniominio
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data

  # MinIO 초기 설정 (버킷 생성)
  minio-init:
    image: minio/mc:RELEASE.2023-05-04T18-10-16Z
    depends_on:
      - minio
    entrypoint: >
      /bin/sh -c "
      /usr/bin/mc config host add minio http://minio:9000 minio miniominio;
      /usr/bin/mc mb minio/content-loader-summary-cache;
      /usr/bin/mc mb minio/content-loader-metadata-cache;
      /usr/bin/mc policy set public minio/content-loader-summary-cache;
      /usr/bin/mc policy set public minio/content-loader-metadata-cache;
      exit 0;
      "

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
  minio_data:
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

#### 로컬 AWS 서비스 접근 정보

| 서비스 | 접속 URL | 로그인 정보 |
|--------|----------|-------------|
| MinIO 웹 콘솔 | http://localhost:9001 | minio / miniominio |
| Redis Commander | http://localhost:8081 | 로그인 불필요 |
| Qdrant 대시보드 | http://localhost:6333/dashboard | 로그인 불필요 |

#### 캐싱 동작 확인 방법

##### 1. S3 캐시 확인 (MinIO)
```bash
# MinIO 웹 콘솔에서 확인
# 1. http://localhost:9001 접속
# 2. minio/miniominio 로그인
# 3. content-loader-summary-cache 버킷에서 캐시 파일 확인

# 명령줄에서 확인
docker-compose exec minio-init mc ls minio/content-loader-summary-cache
```

##### 2. Redis 캐시 확인
```bash
# Redis Commander 웹 인터페이스에서 확인
# http://localhost:8081 접속

# 명령줄에서 확인
docker-compose exec redis redis-cli
> KEYS summary:*
> GET summary:abcd:1234567890abcdef...
```

##### 3. 캐시 히트율 모니터링
```bash
# Redis 통계 확인
docker-compose exec redis redis-cli INFO stats

# 캐시 히트율 계산
# keyspace_hits / (keyspace_hits + keyspace_misses)
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

# 로컬 개발 설정 (Docker Compose에서 자동 설정)
# S3_ENDPOINT=http://minio:9000
# AWS_ACCESS_KEY_ID=minio
# AWS_SECRET_ACCESS_KEY=miniominio
# REDIS_HOST=redis
# REDIS_PORT=6379
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

# 두 번째 요약 실행 (캐시 히트)
# 동일한 코드를 다시 실행하면 캐시에서 빠르게 반환됨
```

##### 3. 캐시 무효화 테스트
```bash
# Redis 캐시 초기화
docker-compose exec redis redis-cli FLUSHDB

# 특정 키 삭제
docker-compose exec redis redis-cli DEL "summary:abcd:1234567890abcdef..."

# MinIO 캐시 삭제
docker-compose exec minio-init mc rm --recursive minio/content-loader-summary-cache
```

##### 4. 성능 모니터링
```bash
# 실시간 Redis 모니터링
docker-compose exec redis redis-cli MONITOR

# 메모리 사용량 확인
docker-compose exec redis redis-cli MEMORY USAGE summary:abcd:1234567890abcdef...

# MinIO 스토리지 사용량 확인
docker-compose exec minio-init mc du minio/content-loader-summary-cache
```

#### 개발 환경 리셋
```bash
# 전체 환경 재시작
docker-compose down -v
docker-compose up -d

# 캐시만 초기화
docker-compose exec redis redis-cli FLUSHALL
docker-compose exec minio-init mc rm --recursive --force minio/content-loader-summary-cache
docker-compose exec minio-init mc rm --recursive --force minio/content-loader-metadata-cache
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

### 4.2 스케줄링 전략 옵션

#### Option 1: 차등 스케줄링 (권장)
```yaml
# 데이터 특성별 차등 적용
slack:
  schedule: "0 9,14,18 * * *"    # 하루 3회 (9시, 14시, 18시)
  priority: high

github:
  schedule: "0 8,20 * * *"       # 하루 2회 (8시, 20시)
  priority: high

confluence:
  schedule: "0 10 * * *"         # 하루 1회 (10시)
  priority: medium
```

#### Option 2: 통합 실행
```yaml
# 모든 소스 동시 실행 (리소스 집약적)
content-loader:
  schedule: "0 9,18 * * *"       # 하루 2회
  sources: ["slack", "github", "confluence"]
```

#### Option 3: 증분 업데이트 기반
```yaml
# 변경 감지 후 실행 (고급)
content-loader:
  schedule: "*/30 * * * *"       # 30분마다 변경 체크
  mode: incremental              # 변경된 데이터만 처리
  change_detection: true
```

### 4.3 단계별 도입 계획

#### Phase 1: 기본 차등 스케줄링
```yaml
# 초기 배포 시 안전한 설정
scheduler:
  strategy: "differential"
  sources:
    slack:
      schedule: "0 9,18 * * *"   # 하루 2회로 시작
    github:
      schedule: "0 8,20 * * *"   # 하루 2회
    confluence:
      schedule: "0 10 * * *"     # 하루 1회
```

#### Phase 2: 최적화 (모니터링 후 조정)
```yaml
# 사용 패턴 분석 후 최적화
scheduler:
  strategy: "optimized"
  sources:
    slack:
      schedule: "0 9,14,18 * * *"  # 3회로 증가
      incremental: true            # 증분 업데이트 활성화
    github:
      schedule: "0 8,20 * * *"     # 유지
      batch_size: 100              # 배치 크기 최적화
    confluence:
      schedule: "0 10 * * *"       # 유지
```

#### Phase 3: 지능형 스케줄링
```yaml
# AI 기반 최적화 (향후)
scheduler:
  strategy: "intelligent"
  auto_adjust: true
  metrics_based: true
  peak_hours: ["9-11", "14-16", "18-20"]
```

### 4.4 스케줄링 고려사항

#### 리소스 최적화
- **CPU/메모리**: 대용량 소스코드 인덱싱 시간대 분산
- **네트워크**: API Rate Limit 준수 (GitHub: 5000/hour)
- **저장소**: 벡터 DB 쓰기 성능 고려

#### 비즈니스 요구사항
- **업무 시간**: 오전 9시-오후 6시 집중 업데이트
- **사용자 패턴**: 검색 빈도가 높은 시간대 고려
- **장애 대응**: 실패 시 재시도 전략

#### 모니터링 지표
```python
# 스케줄링 성능 메트릭
class SchedulingMetrics:
    execution_duration: Dict[str, float]    # 소스별 실행 시간
    success_rate: Dict[str, float]          # 소스별 성공률
    data_freshness: Dict[str, datetime]     # 데이터 신선도
    resource_usage: Dict[str, ResourceUsage] # 리소스 사용량
```

### 4.5 환경별 스케줄링

#### 개발 환경
```yaml
# 개발/테스트용 - 리소스 절약
dev:
  slack:
    schedule: "0 10 * * *"       # 하루 1회
  github:
    schedule: "0 11 * * *"       # 하루 1회
  confluence:
    schedule: "0 12 * * 0"       # 주 1회
```

#### 프로덕션 환경
```yaml
# 프로덕션 - 최적 성능
prod:
  slack:
    schedule: "0 9,14,18 * * *"  # 하루 3회
  github:
    schedule: "0 8,20 * * *"     # 하루 2회
  confluence:
    schedule: "0 10 * * *"       # 하루 1회
```

이 설계를 통해 기존의 분산된 loader들을 통합하면서도 각각의 특성을 유지하고, 데이터 신선도와 시스템 성능을 균형있게 최적화하는 확장 가능한 아키텍처를 구현할 수 있습니다.
