# Content Loader Architecture Design

## 개요

Content Loader는 다양한 외부 데이터 소스(Slack, Confluence, GitHub)에서 콘텐츠를 수집하고 처리하는 통합 시스템입니다. 기존의 분산된 loader들을 하나의 아키텍처로 통합하여 유지보수성과 확장성을 개선합니다.

## 프로젝트 구조

```
content-loader/
├── README.md
├── pyproject.toml
├── uv.lock
├── docker-compose.yml
├── Dockerfile
├── Tiltfile
├── .env.example
├── config/
│   ├── slack.yaml
│   ├── confluence.yaml
│   ├── github.yaml
│   ├── presets.yaml
│   └── settings.yaml
├── src/
│   └── content_loader/
│       ├── __init__.py
│       ├── main.py
│       ├── settings.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── executor.py
│       │   ├── models.py
│       │   ├── exceptions.py
│       │   └── storage.py
│       ├── loaders/
│       │   ├── __init__.py
│       │   ├── slack/
│       │   │   ├── __init__.py
│       │   │   ├── client.py
│       │   │   ├── loader.py
│       │   │   └── models.py
│       │   ├── confluence/
│       │   │   ├── __init__.py
│       │   │   ├── client.py
│       │   │   ├── loader.py
│       │   │   └── models.py
│       │   └── github/
│       │       ├── __init__.py
│       │       ├── client.py
│       │       ├── loader.py
│       │       └── models.py
│       ├── services/
│       │   ├── __init__.py
│       │   ├── embedding.py
│       │   ├── summarizer.py
│       │   └── llm_client.py
│       └── utils/
│           ├── __init__.py
│           ├── retry.py
│           ├── chunking.py
│           └── logging.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_slack_loader.py
│   │   ├── test_confluence_loader.py
│   │   └── test_github_loader.py
│   └── integration/
│       ├── test_full_pipeline.py
│       └── test_embedding_service.py
└── scripts/
    ├── test_slack.py
    ├── test_confluence.py
    ├── test_github.py
    └── load_single_source.py
```

## 아키텍처 설계

### 1. 핵심 설계 원칙

- **단일 책임 원칙**: 각 모듈은 명확한 단일 책임을 가집니다
- **확장성**: 새로운 데이터 소스를 쉽게 추가할 수 있는 구조
- **테스트 가능성**: 각 컴포넌트를 독립적으로 테스트 가능
- **설정 기반**: 코드 변경 없이 설정으로 동작 조정
- **비동기 처리**: 성능 최적화를 위한 비동기 아키텍처

### 2. 주요 컴포넌트

#### Core Layer
- **BaseLoader**: 모든 loader의 기본 인터페이스
- **Executor**: 로딩 작업을 조율하는 실행 엔진
- **Models**: 공통 데이터 모델 정의
- **Storage**: 결과 저장 인터페이스

#### Loader Layer
- **SlackLoader**: Slack 채널/메시지 처리
- **ConfluenceLoader**: Confluence 페이지/댓글 처리
- **GitHubLoader**: GitHub 이슈/파일 처리

#### Service Layer
- **EmbeddingService**: 벡터 데이터베이스 연동
- **SummarizerService**: AI 기반 요약 기능
- **LLMClient**: LLM 서비스 연동 (사내 proxy 지원)

### 3. 데이터 플로우

```
Data Source → Loader → Chunking → Summarization → Embedding → Vector DB
```

1. **수집**: 각 loader가 외부 소스에서 데이터 수집
2. **청킹**: 긴 텍스트를 적절한 크기로 분할
3. **요약**: 선택적으로 AI 기반 요약 생성
4. **임베딩**: 텍스트를 벡터로 변환
5. **저장**: 벡터 데이터베이스에 저장

## 환경 변수

### 필수 환경 변수

```bash
# 임베딩 서비스
EMBEDDING_SERVICE_URL=http://embedding-retrieval:8000

# LLM 서비스 (사내 proxy)
LLM_SERVICE_URL=https://internal-llm-proxy.company.com
LLM_API_KEY=your-internal-api-key

# Slack
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_BOT_MEMBER_ID=U1234567890

# Confluence (Cloud)
CONFLUENCE_URL=https://your-company.atlassian.net
CONFLUENCE_EMAIL=your-email@company.com
CONFLUENCE_API_TOKEN=your-confluence-api-token

# GitHub
GITHUB_APP_ID=123456
GITHUB_PRIVATE_KEY_PATH=/secrets/github-app-private-key.pem
GITHUB_INSTALLATION_ID=87654321

# AWS (요약 캐싱용)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-west-2
SUMMARY_CACHE_BUCKET=content-loader-cache
```

### 선택적 환경 변수

```bash
# 로깅
LOG_LEVEL=INFO
LOG_FORMAT=json

# 성능 튜닝
CHUNK_SIZE=512
EMBEDDING_BATCH_SIZE=32
SUMMARY_ENABLED=true
MAX_WORKERS=4

# 재시도 설정
MAX_RETRIES=3
RETRY_DELAY=1.0
```

## 기존 설계에서 개선된 점

### 1. 통합 아키텍처
- **기존**: 각 loader가 독립적인 서비스
- **개선**: 단일 서비스 내에서 모든 loader 통합 관리

### 2. 공통 기능 추상화
- **기존**: 각 loader가 중복된 기능 구현
- **개선**: 공통 기능을 core layer에서 재사용

### 3. 설정 관리 개선
- **기존**: 환경변수와 YAML 설정이 분산
- **개선**: 계층적 설정 구조와 명확한 우선순위

### 4. 테스트 향상
- **기존**: 통합 테스트 위주
- **개선**: 단위 테스트 + 통합 테스트 + 개별 loader 테스트

### 5. 개발 환경 개선
- **기존**: Docker 기반 개발
- **개선**: uv + Tiltfile을 통한 빠른 개발 환경

## Confluence Cloud 지원

### 주요 변경사항
- **인증**: Username/Password → Email/API Token
- **API URL**: Self-hosted → Cloud URL (atlassian.net)
- **권한**: 기본 권한으로 모든 페이지 접근 가능

### 설정 예시
```yaml
confluence:
  url: "https://your-company.atlassian.net"
  email: "user@company.com"
  api_token: "${CONFLUENCE_API_TOKEN}"
  spaces:
    - name: "Engineering"
      key: "ENG"
    - name: "Product"
      key: "PROD"
```

## 사내 LLM Proxy 연동

### 특징
- OpenAI 호환 인터페이스
- 사내 보안 정책 준수
- 다른 API Key 형식

### 설정
```python
class LLMClient:
    def __init__(self, base_url: str, api_key: str):
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=30.0
        )
```

## 개발 및 실행 방법

### 개발 환경 설정

```bash
# uv를 사용한 개발 환경
uv sync
uv run python -m content_loader.main

# Tiltfile을 사용한 통합 개발 환경
tilt up
```

### 개별 Loader 테스트

```bash
# Slack 테스트
uv run python scripts/test_slack.py

# Confluence 테스트
uv run python scripts/test_confluence.py

# GitHub 테스트
uv run python scripts/test_github.py
```

### 종류별 독립 실행

각 content-loader를 종류별로 독립적으로 실행하는 방법:

#### 1. 커맨드라인 인자 사용
```bash
# 특정 loader 타입만 실행
uv run python -m content_loader.main --source-type slack
uv run python -m content_loader.main --source-type github
uv run python -m content_loader.main --source-type confluence
```

#### 2. 단일 소스 로드 API
```python
from content_loader.main import ContentLoaderApp

# 특정 소스만 실행
await app.load_single_source(
    source_type="slack",
    source_key="engineering-general"
)
```

#### 3. Docker 컨테이너 분리
```bash
# 각 loader별 독립 실행
docker-compose up slack-loader
docker-compose up github-loader
docker-compose up confluence-loader
```

### Docker를 사용한 배포

```bash
# 개발용
docker-compose up -d

# 프로덕션용
docker build -t content-loader .
docker run -d --env-file .env content-loader
```

## 설정 파일 구조

각 loader별로 설정 파일을 분리하여 관리합니다.

### config/slack.yaml
```yaml
sources:
  - key: "engineering-general"
    workspace: "T029G2MBUF6"
    channel: "C052ADQ5B3N"
    name: "#engineering-general"
    options:
      include_replies: true
      exclude_bots: true
      date_from: "2024-01-01"

  - key: "product-discuss"
    workspace: "T029G2MBUF6"
    channel: "C052ADQ5B4O"
    name: "#product-discuss"
    options:
      include_replies: false
```

### config/confluence.yaml
```yaml
sources:
  - key: "engineering-space"
    space: "ENG"
    type: "space"
    options:
      include_comments: true
      modified_since: "2024-01-01"

  - key: "product-space"
    space: "PROD"
    type: "space"
    options:
      include_comments: false
```

### config/github.yaml
```yaml
sources:
  # 기존 이슈/파일 소스
  - key: "backend-issues"
    owner: "company"
    name: "backend-service"
    type: "issues"
    options:
      state: "all"

  - key: "docs-files"
    owner: "company"
    name: "documentation"
    type: "files"
    options:
      extensions: [".md", ".rst"]

  # 새로운 소스코드 인덱싱
  - key: "backend-source-python"
    owner: "company"
    name: "backend-service"
    type: "source_code"
    options:
      preset: "python"
      branch: "main"
      max_file_size_kb: 500

  - key: "frontend-source-js"
    owner: "company"
    name: "frontend-app"
    type: "source_code"
    options:
      preset: "javascript"
      include_patterns:
        - "src/**/*.ts"
        - "src/**/*.tsx"
      exclude_patterns:
        - "src/**/*.test.ts"
        - "src/**/*.spec.ts"
      chunking_strategy: "semantic"

  - key: "fullstack-monorepo"
    owner: "company"
    name: "main-app"
    type: "source_code"
    options:
      preset: "full_stack"
      include_patterns:
        - "backend/**/*.py"
        - "frontend/src/**/*.ts"
        - "frontend/src/**/*.tsx"
        - "docs/**/*.md"
      exclude_patterns:
        - "**/__pycache__/**"
        - "**/node_modules/**"
        - "**/dist/**"
        - "**/*.test.*"
      max_file_size_kb: 300
      preserve_context: true
```

### config/presets.yaml
```yaml
# 소스코드 인덱싱 프리셋 정의
github_code_presets:
  python:
    include_patterns:
      - "**/*.py"
    exclude_patterns:
      - "**/__pycache__/**"
      - "**/venv/**"
      - "**/.pytest_cache/**"
      - "**/migrations/**"
    chunking_strategy: "function_based"
    include_docstrings: true
    include_comments: false
    security_exclude_patterns:
      - "**/.env*"
      - "**/secrets.py"
      - "**/*_secret*"
      - "**/*_key*"

  javascript:
    include_patterns:
      - "**/*.js"
      - "**/*.jsx"
      - "**/*.ts"
      - "**/*.tsx"
    exclude_patterns:
      - "**/node_modules/**"
      - "**/dist/**"
      - "**/build/**"
      - "**/*.min.js"
    chunking_strategy: "semantic"
    preserve_context: true
    security_exclude_patterns:
      - "**/.env*"
      - "**/secrets/**"
      - "**/*.min.js"

  full_stack:
    include_patterns:
      - "**/*.py"
      - "**/*.js"
      - "**/*.jsx"
      - "**/*.ts"
      - "**/*.tsx"
      - "**/*.md"
      - "**/*.yml"
      - "**/*.yaml"
    exclude_patterns:
      - "**/node_modules/**"
      - "**/__pycache__/**"
      - "**/venv/**"
      - "**/dist/**"
      - "**/build/**"
      - "**/.pytest_cache/**"
    chunking_strategy: "semantic"
    max_file_size_kb: 200
    security_exclude_patterns:
      - "**/.env*"
      - "**/secrets/**"
      - "**/*_secret*"
      - "**/*_key*"
      - "**/credentials/**"
```

### settings.yaml
```yaml
chunking:
  default_size: 512
  overlap: 50

summarization:
  enabled: true
  model: "gpt-3.5-turbo"
  max_tokens: 500

embedding:
  batch_size: 32
  service_url: "${EMBEDDING_SERVICE_URL}"

retry:
  max_attempts: 3
  backoff_factor: 2.0
```

## 설정 파일 분리의 장점

### 1. 관리 편의성
- **모듈별 관리**: 각 loader별로 독립적인 설정 관리
- **팀별 책임 분담**: Slack은 운영팀, GitHub는 개발팀이 관리
- **설정 충돌 방지**: 다른 loader 설정에 영향 없이 수정 가능

### 2. 확장성
- **새로운 소스 추가**: 새로운 YAML 파일만 추가하면 됨
- **프리셋 재사용**: 공통 설정을 presets.yaml에서 재사용
- **환경별 설정**: 개발/스테이징/프로덕션별 분리 가능

### 3. 보안
- **접근 권한 제어**: 파일별로 다른 접근 권한 설정 가능
- **민감정보 분리**: 각 서비스별 credential 분리 관리
- **감사 추적**: 변경 이력을 파일별로 추적 가능

## 실행 빈도 및 스케줄링

### 권장 스케줄링 설정

각 데이터 소스의 특성에 맞는 차등 스케줄링을 권장합니다:

```yaml
# config/scheduler.yaml
scheduler:
  strategy: "differential"

  # 프로덕션 환경
  production:
    slack:
      schedule: "0 9,14,18 * * *"  # 하루 3회 (오전9시, 오후2시, 오후6시)
      priority: high
      timeout: 30m

    github:
      schedule: "0 8,20 * * *"     # 하루 2회 (오전8시, 오후8시)
      priority: high
      timeout: 60m                 # 소스코드 인덱싱 고려

    confluence:
      schedule: "0 10 * * *"       # 하루 1회 (오전10시)
      priority: medium
      timeout: 20m

  # 개발 환경 (리소스 절약)
  development:
    slack:
      schedule: "0 10 * * *"       # 하루 1회
    github:
      schedule: "0 11 * * *"       # 하루 1회
    confluence:
      schedule: "0 12 * * 0"       # 주 1회 (일요일)
```

### 단계별 도입 계획

1. **Phase 1**: 기본 차등 스케줄링 (하루 1-2회)
2. **Phase 2**: 사용 패턴 분석 후 최적화
3. **Phase 3**: 증분 업데이트 및 지능형 스케줄링

### 모니터링 지표

- 실행 시간 및 성공률
- 데이터 신선도
- API Rate Limit 사용량
- 시스템 리소스 사용률

## 향후 확장 계획

1. **새로운 데이터 소스**: Notion, Jira 등을 위한 개별 설정 파일 추가
2. **지능형 스케줄링**: 사용 패턴 기반 자동 최적화
3. **동적 설정 로딩**: 런타임에 설정 파일 변경 감지 및 적용
4. **설정 검증**: YAML 스키마 기반 설정 유효성 검사
5. **템플릿 지원**: 공통 패턴을 위한 설정 템플릿 제공
6. **GUI 설정 도구**: 웹 기반 설정 관리 인터페이스
