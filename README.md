# Content Loader

다양한 데이터 소스(Slack, Confluence, GitHub)에서 콘텐츠를 수집하여 임베딩 서비스로 전송하는 통합 로더 시스템입니다.

## 🎯 주요 기능

- **3개 주요 데이터 소스 지원**: Slack 채널, Confluence 스페이스, GitHub 저장소
- **증분 업데이트**: 변경된 데이터만 효율적으로 처리
- **스마트 청킹**: 데이터 소스별 최적화된 청킹 전략
- **에러 복구**: 체크포인트 기반 부분 실패 복구
- **성능 최적화**: 메모리 관리 및 배치 처리

## 📁 프로젝트 구조

```
content-loader/
├── main.py                    # 실행 진입점
├── executor.py               # 통합 실행기
├── settings.py               # 전역 설정 관리
├── core/                     # 공통 기능
│   ├── base.py              # BaseLoader 인터페이스
│   ├── models.py            # 공통 데이터 모델
│   ├── exceptions.py        # 공통 예외
│   └── utils.py             # 공통 유틸리티
├── config/
│   ├── settings.yaml        # 전역 설정
│   └── schedule.yaml        # 스케줄링 설정
└── loaders/                 # 각 로더 구현
    ├── slack/
    ├── confluence/
    └── github/
```

## 🚀 빠른 시작

### 1. 개발 환경 설정

uv를 사용한 Python 환경 설정:

```bash
# uv 설치 (https://docs.astral.sh/uv/getting-started/installation/)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Python 3.11 설치 및 가상환경 생성
uv python install 3.11
uv venv

# 의존성 설치
uv pip install -e ".[dev]"

# 개발도구 설정
uv run pre-commit install
```

### 2. 서비스 의존성 실행

먼저 Qdrant vector database와 Redis를 시작합니다:

```bash
# Docker Compose로 필요한 서비스 실행
docker-compose up -d

# 서비스 상태 확인
docker-compose ps

# 로그 확인
docker-compose logs qdrant
docker-compose logs redis
```

### 3. 환경변수 설정

```bash
# 필수 환경변수 설정
export SLACK_BOT_TOKEN="xoxb-your-token"
export CONFLUENCE_EMAIL="your-email@company.com"
export CONFLUENCE_API_TOKEN="your-confluence-token"
export GITHUB_APP_ID="1605315"
export GITHUB_PRIVATE_KEY_PATH="./secrets/github-private-key.pem"

# 서비스 연동 (docker-compose 사용 시)
export EMBEDDING_SERVICE_URL="http://embedding-service:8000"
export QDRANT_URL="http://localhost:6333"
export REDIS_URL="redis://localhost:6379/0"
```

### 4. 실행

uv 환경에서 다음 명령어로 실행:

```bash
# 전체 로더 실행
uv run python main.py

# 데모 로더 실행 (벡터 데이터베이스 테스트용)
uv run python main.py --demo

# 특정 로더만 실행
uv run python main.py --loader slack
uv run python main.py --loader github
uv run python main.py --loader confluence

# 특정 소스만 실행
uv run python main.py --loader slack --source general-channel
```

### 5. 설정 파일 구성

각 로더의 설정은 해당 디렉토리 내 `config/` 폴더에서 관리됩니다:

- `loaders/slack/config/channels.yaml` - Slack 채널 설정
- `loaders/confluence/config/spaces.yaml` - Confluence 스페이스 설정
- `loaders/github/config/repositories.yaml` - GitHub 저장소 설정

## 📊 데이터 소스별 특징

| 소스 | 실행 빈도 | 특징 | 데이터 타입 |
|------|----------|------|------------|
| **Slack** | 하루 3회 | 실시간 대화, 스레드 포함 | 메시지, 스레드 |
| **Confluence** | 하루 1회 | 문서 중심, CQL 검색 | 페이지, 댓글 |
| **GitHub** | 하루 2회 | 코드/이슈, 프리셋 지원 | Issues, 파일, 소스코드 |

## 🔧 주요 설정

### 환경별 설정

```yaml
# config/settings.yaml
app:
  name: "content-loader"

embedding:
  service_url: ${EMBEDDING_SERVICE_URL}
  batch_size: 50

cache:
  redis_host: ${REDIS_HOST}
  default_ttl: 3600
```

### 스케줄링 설정

```yaml
# config/schedule.yaml
sources:
  slack:
    schedule: "0 9,14,18 * * *"  # 하루 3회
    priority: high
  github:
    schedule: "0 8,20 * * *"     # 하루 2회
    priority: high
  confluence:
    schedule: "0 10 * * *"       # 하루 1회
    priority: medium
```

## 🛡️ 보안 및 안정성

- **민감 정보 보호**: 환경변수 기반 인증 정보 관리
- **에러 복구**: 체크포인트 기반 중단 지점 복구
- **메모리 관리**: 배치 처리로 메모리 사용량 제한
- **Rate Limiting**: 각 API별 호출 제한 준수

## 📚 상세 문서

- [공통 설계 및 아키텍처](docs/ARCHITECTURE.md)
- [Slack Loader 설계](docs/SLACK_LOADER.md)
- [Confluence Loader 설계](docs/CONFLUENCE_LOADER.md)
- [GitHub Loader 설계](docs/GITHUB_LOADER.md)
- [구현 체크리스트](docs/IMPLEMENTATION_CHECKLIST.md)

## 🔍 모니터링

### 헬스 체크

```bash
# 기본 헬스 체크
curl http://localhost:8000/health

# 상세 헬스 체크
curl http://localhost:8000/health/detailed

# 메트릭 조회
curl http://localhost:8000/metrics
```

### 로그 확인

```bash
# 실행 로그
tail -f logs/content-loader.log

# 특정 로더 로그 필터링
grep "slack" logs/content-loader.log
```

## 🚀 배포

### Docker 실행

```bash
# 개발 환경
docker-compose up -d

# 프로덕션 환경
docker-compose -f docker-compose.prod.yml up -d
```

### 환경별 실행

```bash
# 개발 환경
ENVIRONMENT=dev uv run python main.py

# 프로덕션 환경
ENVIRONMENT=prod uv run python main.py
```

## 🧪 개발 워크플로우

### 코드 품질 검사

```bash
# 코드 포맷팅
uv run black .
uv run isort .

# 타입 검사
uv run mypy .

# 린팅
uv run flake8

# 모든 검사 실행
uv run pre-commit run --all-files
```

### 테스트 실행

```bash
# 전체 테스트
uv run pytest

# 커버리지 포함 테스트
uv run pytest --cov=content_loader

# 특정 테스트만 실행
uv run pytest tests/test_slack_loader.py
```

## 🤝 기여하기

1. 새로운 로더 추가 시 `loaders/` 디렉토리 아래에 동일한 구조로 생성
2. `core/base.py`의 `BaseLoader` 인터페이스 구현
3. 해당 로더의 `config/` 디렉토리에 설정 파일 추가
4. 테스트 스크립트 작성 및 검증

## 📄 라이센스

MIT License
