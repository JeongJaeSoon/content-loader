# Content Loader 구현 체크리스트

## 🚀 프로젝트 준비 단계

### 📋 환경 설정 및 키 발급

#### Slack 설정
- [ ] **Slack App 생성**
  - [ ] https://api.slack.com/apps 에서 새 앱 생성
  - [ ] OAuth & Permissions에서 Bot Token Scopes 설정
    - [ ] `channels:history` - 채널 메시지 읽기
    - [ ] `channels:read` - 채널 정보 읽기
    - [ ] `users:read` - 사용자 정보 읽기
    - [ ] `groups:history` - 비공개 채널 메시지 읽기 (필요시)
  - [ ] Bot User OAuth Token (`xoxb-...`) 발급
  - [ ] Bot Member ID 확인
- [ ] **워크스페이스 설정**
  - [ ] 봇을 대상 채널에 초대
  - [ ] 채널 ID 수집 (C로 시작하는 ID)
  - [ ] 워크스페이스 ID 수집 (T로 시작하는 ID)

#### Confluence 설정 (Cloud)
- [ ] **API Token 발급**
  - [ ] https://id.atlassian.com/manage-profile/security/api-tokens 접속
  - [ ] 새 API Token 생성
  - [ ] 토큰과 이메일 주소 저장
- [ ] **Space 정보 수집**
  - [ ] 대상 Space Key 확인 (예: ENG, PROD)
  - [ ] Space 접근 권한 확인
  - [ ] Confluence URL 확인 (예: https://company.atlassian.net)

#### GitHub 설정
- [ ] **GitHub App 생성**
  - [ ] Organization Settings > Developer settings > GitHub Apps
  - [ ] 새 GitHub App 생성
  - [ ] Repository permissions 설정:
    - [ ] Contents: Read
    - [ ] Issues: Read
    - [ ] Metadata: Read
    - [ ] Pull requests: Read (필요시)
  - [ ] Private key 생성 및 다운로드
  - [ ] App ID 확인
- [ ] **Installation 설정**
  - [ ] 대상 Organization/Repository에 앱 설치
  - [ ] Installation ID 확인
  - [ ] 접근 권한 확인

#### 사내 LLM Proxy 설정
- [ ] **사내 프록시 정보 수집**
  - [ ] Base URL 확인
  - [ ] API Key 형식 확인
  - [ ] 지원 모델 목록 확인
  - [ ] Rate Limit 정책 확인

#### 임베딩 서비스 설정
- [ ] **Embedding Service 정보**
  - [ ] Service URL 확인
  - [ ] API 스키마 확인
  - [ ] 인증 방식 확인

#### Redis 설정 (캐싱용)
- [ ] **Redis 인스턴스**
  - [ ] Redis 인스턴스 설정 (로컬 개발용)
  - [ ] 연결 정보 확인 (host, port, password)
  - [ ] 메모리 정책 설정 (`allkeys-lru`)
- [ ] **캐시 키 전략**
  - [ ] 요약 캐시 키 형식: `summary:{hash[:16]}`
  - [ ] 메타데이터 캐시 키 형식: `metadata:{source_type}:{source_key}`
  - [ ] TTL 설정 (Redis: 1시간 기본)

### 🏗️ 개발 환경 설정

#### 기본 도구 설치
- [ ] **Python 환경**
  - [ ] Python 3.11+ 설치
  - [ ] uv 설치: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - [ ] Git 설정 확인
- [ ] **개발 도구**
  - [ ] Docker Desktop 설치
  - [ ] VS Code 또는 선호하는 IDE 설정
  - [ ] Tilt 설치 (선택사항): `curl -fsSL https://raw.githubusercontent.com/tilt-dev/tilt/master/scripts/install.sh | bash`

#### 환경 변수 설정
- [ ] **환경 변수 파일 생성**
  - [ ] `.env` 파일 생성
  - [ ] 모든 필수 환경 변수 설정
  - [ ] `.env.example` 파일 작성

---

## 🔧 구현 단계

### 1️⃣ **High Priority - 핵심 구현**

#### [ ] 프로젝트 기본 구조 설정
- [ ] `uv init content-loader` 실행
- [ ] `pyproject.toml` 설정
  - [ ] Python 버전 지정 (>=3.11)
  - [ ] 의존성 추가 (fastapi, uvicorn, aiohttp, pydantic, etc.)
  - [ ] 개발 의존성 추가 (pytest, black, ruff, etc.)
- [ ] 디렉터리 구조 생성
  - [ ] `src/content_loader/` 생성
  - [ ] `config/` 생성
  - [ ] `tests/` 생성
  - [ ] `scripts/` 생성
- [ ] `.gitignore` 파일 생성
- [ ] `README.md` 초기 작성

#### [ ] Core Layer 구현
- [ ] **BaseLoader 인터페이스**
  - [ ] `src/content_loader/core/base.py` 생성
  - [ ] `load_source()` 추상 메서드 정의
  - [ ] `validate_source()` 메서드 정의
  - [ ] `_should_process_document()` 공통 메서드 구현
- [ ] **Models 정의**
  - [ ] `src/content_loader/core/models.py` 생성
  - [ ] `Document` 데이터 클래스 정의
  - [ ] `DocumentMetadata` 클래스 정의
  - [ ] 각 소스별 모델 정의 (SlackMessage, ConfluencePage, etc.)
- [ ] **Executor 구현**
  - [ ] `src/content_loader/core/executor.py` 생성
  - [ ] `LoaderExecutor` 클래스 구현
  - [ ] `execute_all()` 메서드 구현
  - [ ] `execute_single_source()` 메서드 구현
- [ ] **Storage 인터페이스**
  - [ ] `src/content_loader/core/storage.py` 생성
  - [ ] 벡터 DB 연동 인터페이스 정의
- [ ] **Exception 정의**
  - [ ] `src/content_loader/core/exceptions.py` 생성
  - [ ] 커스텀 예외 클래스 정의

#### [ ] Settings 및 Configuration 시스템
- [ ] **Settings 클래스**
  - [ ] `src/content_loader/settings.py` 생성
  - [ ] Pydantic Settings 사용
  - [ ] 환경변수 로딩 구현
  - [ ] YAML 설정 로딩 구현
- [ ] **Configuration 로더**
  - [ ] 계층적 설정 로딩 (환경변수 > YAML > 기본값)
  - [ ] 설정 검증 로직 구현
  - [ ] 환경별 설정 분리 (dev, staging, prod)

#### [ ] Service Layer 구현
- [ ] **EmbeddingService**
  - [ ] `src/content_loader/services/embedding.py` 생성
  - [ ] `upsert_documents()` 메서드 구현
  - [ ] `delete_documents()` 메서드 구현
  - [ ] 배치 처리 로직 구현
- [ ] **SummarizerService**
  - [ ] `src/content_loader/services/summarizer.py` 생성
  - [ ] `summarize()` 메서드 구현
  - [ ] Redis 캐싱 로직 구현
  - [ ] 요약 품질 검증 로직
- [ ] **CacheClient (Redis 기반)**
  - [ ] `src/content_loader/services/cache_client.py` 생성
  - [ ] Redis 캐싱 구현 (1시간 기본 TTL)
  - [ ] 캐시 키 생성 전략 구현
  - [ ] 에러 처리 로직 구현
- [ ] **LLMClient (사내 proxy 지원)**
  - [ ] `src/content_loader/services/llm_client.py` 생성
  - [ ] OpenAI 호환 인터페이스 구현
  - [ ] 사내 프록시 연동 로직
  - [ ] Rate limiting 처리

#### [ ] Slack Loader 구현
- [ ] **SlackClient**
  - [ ] `src/content_loader/loaders/slack/client.py` 생성
  - [ ] Slack Web API 연동
  - [ ] `get_channel_messages()` 메서드 구현
  - [ ] `get_thread_replies()` 메서드 구현
  - [ ] Rate limiting 처리
- [ ] **SlackLoader**
  - [ ] `src/content_loader/loaders/slack/loader.py` 생성
  - [ ] `load_source()` 메서드 구현
  - [ ] 메시지 필터링 로직 (봇 제외, 날짜 범위)
  - [ ] 스레드 처리 로직
- [ ] **Slack Models**
  - [ ] `src/content_loader/loaders/slack/models.py` 생성
  - [ ] `SlackMessage`, `SlackSource`, `SlackOptions` 정의

#### [ ] Confluence Loader 구현
- [ ] **ConfluenceClient (Cloud)**
  - [ ] `src/content_loader/loaders/confluence/client.py` 생성
  - [ ] Confluence Cloud REST API 연동
  - [ ] Email + API Token 인증 구현
  - [ ] `search_content()` 메서드 구현 (CQL 지원)
  - [ ] `get_page_content()` 메서드 구현
  - [ ] `get_page_comments()` 메서드 구현
- [ ] **ConfluenceLoader**
  - [ ] `src/content_loader/loaders/confluence/loader.py` 생성
  - [ ] `load_source()` 메서드 구현
  - [ ] CQL 쿼리 생성 로직
  - [ ] 페이지 계층 구조 처리
- [ ] **Confluence Models**
  - [ ] `src/content_loader/loaders/confluence/models.py` 생성
  - [ ] `ConfluencePage`, `ConfluenceSource`, `ConfluenceOptions` 정의

#### [ ] GitHub Loader 구현
- [ ] **GitHubClient (App 인증)**
  - [ ] `src/content_loader/loaders/github/client.py` 생성
  - [ ] GitHub App 인증 구현
  - [ ] JWT 토큰 생성 로직
  - [ ] Installation Token 획득 로직
  - [ ] `get_issues()` 메서드 구현
  - [ ] `get_files()` 메서드 구현
  - [ ] `get_source_files()` 메서드 구현
- [ ] **GitHubLoader**
  - [ ] `src/content_loader/loaders/github/loader.py` 생성
  - [ ] `load_source()` 메서드 구현
  - [ ] Issues/Files/Source Code 타입별 처리
  - [ ] GraphQL 쿼리 구현
- [ ] **GitHub Models**
  - [ ] `src/content_loader/loaders/github/models.py` 생성
  - [ ] `GitHubIssue`, `GitHubFile`, `GitHubSource`, `GitHubOptions` 정의

### 2️⃣ **Medium Priority - 확장 기능**

#### [ ] GitHub 소스코드 인덱싱 프리셋 시스템
- [ ] **프리셋 정의**
  - [ ] Python 프리셋 (*.py, 함수 기반 청킹)
  - [ ] JavaScript 프리셋 (*.js, *.ts, 의미 기반 청킹)
  - [ ] Full Stack 프리셋 (다중 언어 지원)
- [ ] **프리셋 로더**
  - [ ] `config/presets.yaml` 파일 구조 설계
  - [ ] 프리셋 로딩 로직 구현
  - [ ] 커스텀 설정 오버라이드 지원

#### [ ] 소스코드 청킹 전략 구현 (GitHub 전용)
- [ ] **Function-based 청킹**
  - [ ] AST 파싱을 통한 함수/클래스 추출
  - [ ] 언어별 파서 구현
  - [ ] docstrings 및 comments 포함
- [ ] **기본 청킹 전략**
  - [ ] 고정 크기 분할 (1024 bytes)
  - [ ] 오버랩 처리 (200 bytes)
  - [ ] 문맥 보존 로직

#### [ ] 보안 필터링 시스템
- [ ] **민감 파일 검사**
  - [ ] 환경 변수 파일 (*.env*) 제외
  - [ ] 시크릿 파일 패턴 검사
  - [ ] 키 파일 패턴 검사
- [ ] **보안 패턴 검사**
  - [ ] 정규식 기반 민감 정보 검사
  - [ ] API 키 패턴 검사
  - [ ] 비밀번호 패턴 검사
- [ ] **화이트리스트 시스템**
  - [ ] 안전한 파일 패턴 정의
  - [ ] 예외 처리 로직

#### [ ] Utils 모듈 구현
- [ ] **Retry 유틸리티**
  - [ ] `src/content_loader/utils/retry.py` 생성
  - [ ] 지수 백오프 구현
  - [ ] 재시도 조건 설정
- [ ] **Chunking 유틸리티**
  - [ ] `src/content_loader/utils/chunking.py` 생성
  - [ ] 텍스트 분할 로직
  - [ ] 오버랩 처리
- [ ] **Logging 유틸리티**
  - [ ] `src/content_loader/utils/logging.py` 생성
  - [ ] 구조화된 로깅 (JSON)
  - [ ] 로그 레벨 설정
  - [ ] 로그 회전 설정

#### [ ] 설정 파일 구조 구현
- [ ] **slack.yaml**
  - [ ] 채널별 설정
  - [ ] 옵션 설정 (replies, bots, date_range)
- [ ] **confluence.yaml**
  - [ ] 스페이스별 설정
  - [ ] CQL 쿼리 템플릿
- [ ] **github.yaml**
  - [ ] 저장소별 설정
  - [ ] 타입별 설정 (issues, files, source_code)
- [ ] **presets.yaml**
  - [ ] 언어별 프리셋 정의
  - [ ] 청킹 전략 설정
- [ ] **settings.yaml**
  - [ ] 공통 설정 (chunking, embedding, retry)

#### [ ] Main 애플리케이션 구현
- [ ] **ContentLoaderApp**
  - [ ] `src/content_loader/main.py` 생성
  - [ ] 메인 애플리케이션 클래스
  - [ ] `run()` 메서드 구현
  - [ ] `load_single_source()` 메서드 구현
- [ ] **CLI 인터페이스**
  - [ ] 명령행 인자 파싱
  - [ ] `--source-type` 옵션 구현
  - [ ] `--source-key` 옵션 구현
  - [ ] `--run-once` 옵션 구현
- [ ] **종류별 독립 실행**
  - [ ] 소스 타입별 필터링
  - [ ] 선택적 로더 초기화
  - [ ] 독립 실행 모드

#### [ ] 개별 Loader 테스트 스크립트
- [ ] **test_slack.py**
  - [ ] `scripts/test_slack.py` 생성
  - [ ] Slack 로더 단독 테스트
  - [ ] 메시지 로드 검증
- [ ] **test_confluence.py**
  - [ ] `scripts/test_confluence.py` 생성
  - [ ] Confluence 로더 단독 테스트
  - [ ] 페이지 로드 검증
- [ ] **test_github.py**
  - [ ] `scripts/test_github.py` 생성
  - [ ] GitHub 로더 단독 테스트
  - [ ] Issues/Files/Source Code 검증
- [ ] **load_single_source.py**
  - [ ] 단일 소스 로드 스크립트
  - [ ] 디버깅 및 검증 용도

#### [ ] 통합 테스트 구현
- [ ] **단위 테스트**
  - [ ] `tests/unit/` 디렉터리 생성
  - [ ] 각 클래스별 단위 테스트
  - [ ] Mock 객체 활용
- [ ] **통합 테스트**
  - [ ] `tests/integration/` 디렉터리 생성
  - [ ] 전체 파이프라인 테스트
  - [ ] 임베딩 서비스 연동 테스트
- [ ] **Test Configuration**
  - [ ] `tests/conftest.py` 생성
  - [ ] 테스트 픽스처 정의
  - [ ] 테스트 설정 분리

#### [ ] Docker 설정 구현
- [ ] **Dockerfile**
  - [ ] 멀티스테이지 빌드
  - [ ] uv 기반 의존성 설치
  - [ ] 런타임 최적화
- [ ] **docker-compose.yml**
  - [ ] 서비스 정의 (content-loader, redis, qdrant)
  - [ ] 환경 변수 설정
  - [ ] 볼륨 마운트 설정
- [ ] **환경별 설정**
  - [ ] `docker-compose.dev.yml`
  - [ ] `docker-compose.prod.yml`
  - [ ] 환경별 오버라이드

### 3️⃣ **Low Priority - 운영 최적화**

#### [ ] 누락된 기능 추가 (설계 재검토 반영)
- [ ] **로깅 및 모니터링 시스템**
  - [ ] 구조화된 로깅 (structlog, JSON)
  - [ ] 성능 메트릭 수집기 구현
  - [ ] 헬스 체크 엔드포인트 (/health, /health/detailed)
  - [ ] 메트릭 엔드포인트 (/metrics, /metrics/sources/{type})
- [ ] **설정 검증 및 오류 처리**
  - [ ] Pydantic 기반 YAML 스키마 검증
  - [ ] 필수 환경변수 검증
  - [ ] API 자격증명 검증
  - [ ] 시작 시 전체 설정 검증
  - [ ] 커스텀 예외 처리 클래스
- [ ] **성능 최적화 및 메모리 관리**
  - [ ] 비동기 처리 최적화 (Semaphore, Queue)
  - [ ] 메모리 관리자 구현 (GC, 압박 감지)
  - [ ] 대용량 데이터 스트리밍 처리
  - [ ] 배치 처리 및 동시성 제어
- [ ] **증분 업데이트 로직 상세화**
  - [ ] Slack: 마지막 수집 시간 기반
  - [ ] Confluence: CQL 베이스 lastModified 필터
  - [ ] GitHub: SHA 기반 파일 변경 감지
  - [ ] Redis 기반 상태 관리
- [ ] **에러 처리 및 복구 로직**
  - [ ] 지수 백오프 재시도
  - [ ] 소스별 에러 처리 전략
  - [ ] Rate Limit 예외 처리
  - [ ] 인증 오류 처리

#### [ ] Tiltfile 구현
- [ ] **개발 환경 자동화**
  - [ ] 로컬 개발 서버 자동 시작
  - [ ] 파일 변경 감지 및 재시작
  - [ ] 로그 스트리밍
- [ ] **의존성 서비스 연동**
  - [ ] Redis, Qdrant 자동 시작
  - [ ] 헬스 체크 구현

#### [ ] 간단한 cron 기반 스케줄링 구현
- [ ] **기본 스케줄링**
  - [ ] Slack: 하루 3회 (9,14,18시)
  - [ ] GitHub: 하루 2회 (8,20시)
  - [ ] Confluence: 하루 1회 (10시)
- [ ] **환경변수 기반 설정**
  - [ ] ENV 변수로 환경 구분
  - [ ] 각 소스별 SCHEDULE 변수 설정

#### [ ] 모니터링 및 메트릭 시스템
- [ ] **성능 메트릭**
  - [ ] 실행 시간 추적
  - [ ] 메모리 사용량 모니터링
  - [ ] API 호출 횟수 추적
- [ ] **비즈니스 메트릭**
  - [ ] 성공률 추적
  - [ ] 데이터 신선도 측정
  - [ ] 처리된 문서 수 추적
- [ ] **알림 시스템**
  - [ ] 실패 시 알림
  - [ ] 성능 임계값 알림
  - [ ] 일일 보고서 생성

#### [ ] 문서화
- [ ] **API 문서**
  - [ ] OpenAPI 스키마 생성
  - [ ] API 엔드포인트 문서화
- [ ] **사용 가이드**
  - [ ] 설치 가이드
  - [ ] 설정 가이드
  - [ ] 트러블슈팅 가이드
- [ ] **배포 가이드**
  - [ ] Docker 배포 가이드
  - [ ] Kubernetes 배포 가이드
  - [ ] 운영 가이드

---

## 🎯 완료 기준

### 기능 완료 기준
- [ ] 모든 3개 loader(Slack, Confluence, GitHub)가 정상 동작
- [ ] 개별 테스트 스크립트로 각 loader 검증 완료
- [ ] 전체 파이프라인 테스트 통과
- [ ] Docker 컨테이너로 실행 가능
- [ ] 환경변수 기반 설정 완료
- [ ] 에러 처리 및 재시도 로직 동작 확인
- [ ] 증분 업데이트 기능 동작 확인
- [ ] Redis 캐싱 동작 확인

### 성능 완료 기준
- [ ] Slack: 1000개 메시지 처리 시간 < 5분
- [ ] Confluence: 100개 페이지 처리 시간 < 10분
- [ ] GitHub: 50개 이슈 + 파일 처리 시간 < 15분
- [ ] 소스코드 인덱싱: 1MB 코드 처리 시간 < 30분

### 보안 완료 기준
- [ ] 민감 파일 자동 제외 동작 확인
- [ ] 환경 변수 및 시크릿 보호 확인
- [ ] API 키 노출 방지 확인
- [ ] 보안 패턴 검사 동작 확인

### 운영 완료 기준
- [ ] 구조화된 로깅 및 메트릭 수집 동작
- [ ] 에러 처리 및 재시도 로직 검증
- [ ] 간단한 cron 기반 스케줄링 동작 확인
- [ ] 성능 최적화 및 메모리 관리 기능 동작
- [ ] 증분 업데이트 기능 안정성 검증
