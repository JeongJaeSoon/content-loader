# GitHub Loader 상세 설계

## 주요 기능
- GitHub Issues, Discussions, Files 수집
- GitHub App 인증
- GraphQL과 REST API 병행 사용
- 파일 변경 추적 및 삭제 처리
- 소스코드 인덱싱 및 청킹

## 데이터 모델
```python
@dataclass
class GitHubIssue:
    id: str
    number: int
    title: str
    body: str
    state: str
    created_at: datetime
    updated_at: datetime
    author: str
    url: str
    comments: List['GitHubComment'] = field(default_factory=list)

@dataclass
class GitHubFile:
    id: str
    path: str
    content: str
    sha: str
    size: int
    url: str
    last_modified: datetime

@dataclass
class GitHubSource:
    key: str
    owner: str
    name: str
    type: Literal["issues", "discussions", "files", "source_code"]
    options: GitHubOptions = field(default_factory=GitHubOptions)

@dataclass
class GitHubOptions:
    # 기존 파일/이슈 옵션
    extensions: List[str] = field(default_factory=lambda: [".md"])
    ignore_document_ids: List[str] = field(default_factory=list)
    state: str = "all"  # open, closed, all
    incremental: bool = True  # 증분 업데이트 사용

    # 소스코드 인덱싱 옵션
    preset: Optional[str] = None  # python, javascript, java, full_stack
    include_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    max_file_size_kb: int = 500
    branch: str = "main"

    # 보안 설정
    exclude_secrets: bool = True
    exclude_credentials: bool = True
    security_exclude_patterns: List[str] = field(default_factory=lambda: ["**/.env*", "**/secrets/**"])

    # 청킹 설정 (코드 전용)
    chunking_strategy: str = "function_based"  # function_based, semantic, fixed_size
    chunk_size: int = 1024
    chunk_overlap: int = 200
    include_docstrings: bool = True
    include_comments: bool = True
```

## API 연동
- **GitHub App** 인증 (Installation Token)
- **GraphQL API** - 복잡한 쿼리용
- **REST API** - 단순한 데이터 조회용

## 구현 예시
```python
class GitHubLoader(BaseLoader):
    def __init__(self, client: GitHubClient):
        self.client = client

    async def load_source(self, source: GitHubSource) -> AsyncGenerator[Document, None]:
        if source.type == "issues":
            async for issue in self.client.get_issues(source.owner, source.name):
                yield self._issue_to_document(issue, source)
        elif source.type == "files":
            async for file in self.client.get_files(source.owner, source.name):
                if self._should_include_file(file, source.options):
                    yield self._file_to_document(file, source)
        elif source.type == "source_code":
            async for file in self.client.get_source_files(source.owner, source.name, source.options):
                if self._should_include_source_file(file, source.options):
                    # 소스코드 파일을 청킹하여 여러 Document로 분할
                    async for chunk_doc in self._chunk_source_file(file, source):
                        yield chunk_doc
```

## 소스코드 인덱싱 프리셋
```python
# GitHub 소스코드 프리셋 설정
GITHUB_CODE_PRESETS = {
    "python": {
        "include_patterns": ["**/*.py"],
        "exclude_patterns": ["**/__pycache__/**", "**/venv/**", "**/.pytest_cache/**"],
        "chunking_strategy": "function_based",
        "include_docstrings": True,
        "security_exclude_patterns": ["**/.env*", "**/secrets.py", "**/*_secret*"]
    },
    "javascript": {
        "include_patterns": ["**/*.js", "**/*.jsx", "**/*.ts", "**/*.tsx"],
        "exclude_patterns": ["**/node_modules/**", "**/dist/**", "**/build/**"],
        "chunking_strategy": "function_based",
        "include_docstrings": True,
        "include_comments": True,
        "security_exclude_patterns": ["**/.env*", "**/secrets/**", "**/*.min.js"]
    },
    "full_stack": {
        "include_patterns": ["**/*.py", "**/*.js", "**/*.jsx", "**/*.ts", "**/*.tsx", "**/*.md", "**/*.yml"],
        "exclude_patterns": ["**/node_modules/**", "**/__pycache__/**", "**/venv/**", "**/dist/**", "**/build/**"],
        "chunking_strategy": "function_based",
        "max_file_size_kb": 300,
        "include_docstrings": True,
        "include_comments": True,
        "security_exclude_patterns": ["**/.env*", "**/secrets/**", "**/*_secret*", "**/*_key*"]
    }
}
```

## 소스코드 청킹 전략
```python
class GitHubSourceCodeProcessor:
    def __init__(self, preset_name: str = None, custom_options: GitHubOptions = None):
        self.preset = GITHUB_CODE_PRESETS.get(preset_name, {}) if preset_name else {}
        self.options = custom_options or GitHubOptions()

    def _should_include_source_file(self, file_path: str) -> bool:
        """프리셋과 커스텀 설정을 기반으로 파일 포함 여부 결정"""
        # 보안 패턴 체크
        security_patterns = self.preset.get("security_exclude_patterns", []) + self.options.security_exclude_patterns
        for pattern in security_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return False

        # 포함 패턴 체크
        include_patterns = self.options.include_patterns or self.preset.get("include_patterns", [])
        if include_patterns:
            for pattern in include_patterns:
                if fnmatch.fnmatch(file_path, pattern):
                    break
            else:
                return False

        # 제외 패턴 체크
        exclude_patterns = self.options.exclude_patterns or self.preset.get("exclude_patterns", [])
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return False

        return True

    async def _chunk_source_file(self, file: GitHubFile, source: GitHubSource) -> AsyncGenerator[Document, None]:
        """소스코드 파일을 적절한 단위로 청킹"""
        strategy = self.options.chunking_strategy or self.preset.get("chunking_strategy", "function_based")

        if strategy == "function_based":
            # 함수/클래스 단위로 청킹
            async for chunk in self._chunk_by_functions(file):
                yield chunk
        elif strategy == "semantic":
            # 의미 단위로 청킹
            async for chunk in self._chunk_semantically(file):
                yield chunk
        else:
            # 고정 크기로 청킹
            async for chunk in self._chunk_by_size(file):
                yield chunk
```

## 테스트 방법

### 개별 테스트
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

### 설정 예시
```yaml
# config/loader.yaml
sources:
  github:
    - key: "backend-issues"
      owner: "company"
      name: "backend-service"
      type: "issues"
      options:
        state: "open"
    - key: "docs-files"
      owner: "company"
      name: "documentation"
      type: "files"
      options:
        extensions: [".md", ".rst"]
    - key: "python-source"
      owner: "company"
      name: "api-service"
      type: "source_code"
      options:
        preset: "python"
        branch: "main"
        max_file_size_kb: 200
```

## 실행 빈도 권장사항

GitHub는 개발 활동에 따라 높은 업데이트 빈도를 가지므로 적절한 실행 빈도가 필요합니다:

### 권장 스케줄
- **프로덕션**: 하루 2회 (오전 8시, 오후 8시)
- **개발환경**: 하루 1회 (오전 11시)

### 스케줄링 고려사항
- **소스코드 인덱싱**: 대용량 처리로 인한 긴 실행 시간 (30-60분)
- **API Rate Limit**: GitHub API 제한 (5000 requests/hour)
- **개발 패턴**: 주로 업무시간과 저녁 시간대 활동

### 소스별 차등 스케줄링
```yaml
# 권장 설정 예시
github:
  issues:
    schedule: "0 8,20 * * *"      # 하루 2회
    timeout: 20                   # 20분 타임아웃

  files:
    schedule: "0 8,20 * * *"      # 하루 2회
    timeout: 30                   # 30분 타임아웃

  source_code:
    schedule: "0 20 * * *"        # 하루 1회 (저녁)
    timeout: 90                   # 90분 타임아웃 (대용량 처리)
    priority: low                 # 리소스 우선순위 낮음
```

### 성능 최적화 팁
- **배치 크기 조정**: 대용량 저장소는 작은 배치로 분할
- **병렬 처리**: 여러 저장소 동시 처리
- **캐싱 활용**: SHA 기반 변경 감지로 불필요한 처리 방지

## 주요 특징
- **다양한 소스**: Issues, Files, Source Code 지원
- **프리셋 시스템**: 언어별 최적화된 설정
- **보안 필터링**: 민감한 파일 자동 제외
- **청킹 전략**: 함수 기반 코드 청킹
- **GraphQL 지원**: 복잡한 쿼리 최적화
- **파일 추적**: SHA 기반 변경 감지
- **에러 처리**: Rate Limit 및 네트워크 오류 대응
- **대용량 처리**: 소스코드 인덱싱을 위한 최적화
- **증분 업데이트**: SHA 기반 파일 변경 감지

## 증분 업데이트 전략
```python
class GitHubLoader(BaseLoader):
    async def load_source(self, source: GitHubSource) -> AsyncGenerator[Document, None]:
        if source.type == "issues":
            await self._load_issues_incremental(source)
        elif source.type == "source_code":
            await self._load_source_code_incremental(source)

    async def _load_issues_incremental(self, source: GitHubSource):
        """이슈 증분 로딩"""
        # 마지막 수집 시간 조회
        since = None
        if source.options.incremental:
            since = await self._get_last_fetch_time(f"{source.key}:issues")

        issues = await self.client.get_issues(
            source.owner,
            source.name,
            since=since
        )

        latest_updated = None
        for issue in issues:
            if not latest_updated or issue.updated_at > latest_updated:
                latest_updated = issue.updated_at
            yield self._issue_to_document(issue, source)

        # 마지막 수집 시간 업데이트
        if latest_updated:
            await self._update_last_fetch_time(f"{source.key}:issues", latest_updated)

    async def _load_source_code_incremental(self, source: GitHubSource):
        """소스코드 증분 로딩 (SHA 기반)"""
        files = await self.client.get_source_files(
            source.owner,
            source.name,
            source.options
        )

        for file in files:
            if not self._should_include_source_file(file, source.options):
                continue

            # SHA 기반 변경 감지
            stored_sha = await self._get_stored_file_sha(f"{source.key}:{file.path}")
            if stored_sha == file.sha:
                continue  # 변경되지 않은 파일 스킵

            # 파일 처리 및 SHA 업데이트
            async for chunk_doc in self._chunk_source_file(file, source):
                yield chunk_doc

            await self._update_stored_file_sha(f"{source.key}:{file.path}", file.sha)

    async def _get_stored_file_sha(self, file_key: str) -> Optional[str]:
        """저장된 파일 SHA 조회"""
        return await self.cache_client.get(f"file_sha:{file_key}")

    async def _update_stored_file_sha(self, file_key: str, sha: str):
        """파일 SHA 업데이트"""
        await self.cache_client.set(
            f"file_sha:{file_key}",
            sha,
            expire=86400*30  # 30일 보관
        )
```

## 에러 처리 전략
```python
class GitHubLoader(BaseLoader):
    async def load_source(self, source: GitHubSource) -> AsyncGenerator[Document, None]:
        retry_count = 0
        max_retries = 3

        while retry_count <= max_retries:
            try:
                if source.type == "issues":
                    async for issue in self.client.get_issues(source.owner, source.name):
                        yield self._issue_to_document(issue, source)
                elif source.type == "source_code":
                    async for file in self.client.get_source_files(source.owner, source.name, source.options):
                        if self._should_include_source_file(file, source.options):
                            async for chunk_doc in self._chunk_source_file(file, source):
                                yield chunk_doc
                break

            except GitHubRateLimitError as e:
                # Rate Limit 예외 처리
                reset_time = e.reset_time
                wait_time = min(reset_time - time.time(), 3600)  # 최대 1시간
                logger.warning(f"GitHub rate limit exceeded. Waiting {wait_time}s")
                await asyncio.sleep(wait_time)
                continue

            except GitHubAuthError:
                # 인증 오류는 재시도하지 않음
                raise

            except Exception as e:
                if retry_count < max_retries:
                    retry_count += 1
                    wait_time = min(60, 5 * (2 ** retry_count))  # 최대 60초
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise
```
