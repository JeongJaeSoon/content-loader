# GitHub Loader 설계

**GitHub 저장소에서 Issues, 파일, 소스코드를 수집하는 로더입니다.**

## 🎯 주요 특징

- **다양한 데이터 타입**: Issues, Files, Source Code 지원
- **GitHub App 인증**: 안전한 앱 기반 인증
- **소스코드 프리셋**: 언어별 최적화된 청킹 전략
- **보안 필터링**: 민감한 파일 자동 제외

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

## 🔧 핵심 구현

### API 연동

- **GitHub App 인증**: Installation Token 기반
- **GraphQL API**: 복잡한 쿼리용
- **REST API**: 단순한 데이터 조회용

### 메인 로더 클래스

```python
# loaders/github/loader.py
from core.base import BaseLoader

class GitHubLoader(BaseLoader):
    def __init__(self):
        config_manager = LoaderConfigManager()
        self.config = config_manager.load_loader_config("github")
        self.repositories = config_manager.load_loader_sources("github")
        self.presets = self._load_presets()
        self.client = GitHubClient(self.config)

    async def load_source(self, source: GitHubSource) -> AsyncGenerator[Document, None]:
        if source.type == "issues":
            await self._load_issues(source)
        elif source.type == "files":
            await self._load_files(source)
        elif source.type == "source_code":
            await self._load_source_code(source)

    async def _load_source_code(self, source: GitHubSource):
        """소스코드 타입 처리 - 프리셋 기반"""
        preset = self.presets.get(source.options.preset, {})

        files = await self.client.get_source_files(
            source.owner,
            source.name,
            include_patterns=preset.get('include_patterns', []),
            exclude_patterns=preset.get('exclude_patterns', [])
        )

        for file in files:
            # 보안 필터링
            if self._is_sensitive_file(file.path, preset):
                continue

            # SHA 기반 변경 감지
            stored_sha = await self._get_stored_file_sha(f"{source.key}:{file.path}")
            if stored_sha == file.sha:
                continue

            # 파일 청킹 처리
            async for chunk_doc in self._chunk_source_file(file, source, preset):
                yield chunk_doc

            await self._update_stored_file_sha(f"{source.key}:{file.path}", file.sha)
```

## 소스코드 인덱싱 프리셋

**YAML 설정 파일 기반으로 언어별 최적화 프리셋을 제공합니다.**

프리셋은 `loaders/github/config/presets.yaml`에서 관리되며, 실행 시 동적으로 로드됩니다.

## 소스코드 청킹 전략

```python
class GitHubSourceCodeProcessor:
    def __init__(self, preset_name: str = None, custom_options: GitHubOptions = None):
        # presets.yaml에서 프리셋 로드
        self.preset = self._load_preset(preset_name) if preset_name else {}
        self.options = custom_options or GitHubOptions()

    def _load_preset(self, preset_name: str) -> dict:
        """loaders/github/config/presets.yaml에서 프리셋 로드"""
        config_path = Path("loaders/github/config/presets.yaml")
        if config_path.exists():
            with open(config_path) as f:
                presets = yaml.safe_load(f)
                return presets.get("presets", {}).get(preset_name, {})
        return {}

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
# loaders/github/config/config.yaml
loader:
  name: "github"
  enabled: true
  default_options:
    incremental: true
    max_file_size_kb: 500
    branch: "main"
  api_settings:
    timeout_seconds: 60
    retry_attempts: 3
    rate_limit_buffer: 100  # API 호출 여유분

# loaders/github/config/repositories.yaml
repositories:
  - key: "backend-issues"
    owner: "company"
    name: "backend-service"
    type: "issues"
    description: "Backend service issues and discussions"
    options:
      state: "open"
      include_closed: false
  - key: "docs-files"
    owner: "company"
    name: "documentation"
    type: "files"
    description: "Documentation files"
    options:
      extensions: [".md", ".rst"]
      exclude_paths: ["archived/", "drafts/"]
  - key: "python-source"
    owner: "company"
    name: "api-service"
    type: "source_code"
    description: "Python API service source code"
    options:
      preset: "python"
      branch: "main"
      max_file_size_kb: 200
      custom_include_patterns: ["**/*.py", "**/*.pyi"]

# loaders/github/config/presets.yaml
presets:
  python:
    include_patterns: ["**/*.py"]
    exclude_patterns: ["**/__pycache__/**", "**/venv/**", "**/.pytest_cache/**"]
    chunking_strategy: "function_based"
    include_docstrings: true
    security_exclude_patterns: ["**/.env*", "**/secrets.py", "**/*_secret*"]
  javascript:
    include_patterns: ["**/*.js", "**/*.jsx", "**/*.ts", "**/*.tsx"]
    exclude_patterns: ["**/node_modules/**", "**/dist/**", "**/build/**"]
    chunking_strategy: "function_based"
    include_docstrings: true
    include_comments: true
    security_exclude_patterns: ["**/.env*", "**/secrets/**", "**/*.min.js"]
```

## ⚙️ 설정 및 실행

### 실행 빈도

| 환경 | 데이터 타입 | 스케줄 | 이유 |
|------|-------------|--------|------|
| **프로덕션** | Issues/Files | 하루 2회 (8시, 20시) | 개발 활동 패턴 |
| **프로덕션** | Source Code | 하루 1회 (20시) | 대용량 처리 고려 |
| **개발환경** | 전체 | 하루 1회 (11시) | 개발 편의성 |

### 스케줄링 설정

```yaml
# config/schedule.yaml
sources:
  github:
    schedule: "0 8,20 * * *"      # 하루 2회
    timeout_minutes: 60           # 소스코드 처리 시간 고려
    priority: high

# 소스별 차등 처리
github_source_code:
  schedule: "0 20 * * *"          # 저녁 1회만
  timeout_minutes: 90
  priority: low
```

### 성능 고려사항

- **API Rate Limit**: GitHub API 제한 (5000 requests/hour) 준수
- **대용량 처리**: 소스코드 인덱싱 시 90분 타임아웃
- **SHA 기반 캐싱**: 변경되지 않은 파일 스킵으로 효율성 향상

## 🔄 핵심 기능

### 1. 소스코드 프리셋 시스템

언어별 최적화된 청킹 및 필터링 전략

프리셋은 `loaders/github/config/presets.yaml`에서 설정되며, 각 저장소는 원하는 프리셋을 선택하거나 커스텀 설정으로 오버라이드할 수 있습니다.

```python
def _apply_preset(self, source: GitHubSource) -> dict:
    """프리셋 설정 적용"""
    preset = self._load_preset(source.options.preset)

    # 커스텀 설정으로 오버라이드
    if source.options.custom_include_patterns:
        preset['include_patterns'] = source.options.custom_include_patterns

    return preset
```

### 2. SHA 기반 증분 업데이트

파일 내용 변경 감지로 효율적 처리

```python
async def _process_file_with_sha_check(self, file: GitHubFile, source: GitHubSource):
    """SHA 기반 파일 변경 감지"""
    file_key = f"{source.key}:{file.path}"
    stored_sha = await self.cache_client.get(f"file_sha:{file_key}")

    if stored_sha == file.sha:
        return  # 변경되지 않은 파일 스킵

    # 파일 처리
    if source.type == "source_code":
        async for chunk_doc in self._chunk_source_file(file, source):
            yield chunk_doc
    else:
        yield self._file_to_document(file, source)

    # SHA 업데이트 (30일 보관)
    await self.cache_client.set(
        f"file_sha:{file_key}",
        file.sha,
        expire=86400*30
    )
```

### 3. 함수 기반 코드 청킹

소스코드를 함수/클래스 단위로 분할

```python
async def _chunk_source_file(self, file: GitHubFile, source: GitHubSource):
    """프리셋 기반 소스코드 청킹"""
    preset = self._load_preset(source.options.preset)
    strategy = preset.get('chunking_strategy', 'fixed_size')

    if strategy == "function_based":
        # AST 파싱으로 함수/클래스 추출
        chunks = self._extract_functions_and_classes(file.content, file.path)
    else:
        # 고정 크기 청킹
        chunks = self._chunk_by_size(file.content, 1024)

    for i, chunk_content in enumerate(chunks):
        yield Document(
            id=f"github_{source.owner}_{source.name}_{file.path}_chunk_{i}",
            title=f"{file.path} - Chunk {i+1}",
            text=chunk_content,
            metadata={
                "source_type": "github",
                "repository": f"{source.owner}/{source.name}",
                "file_path": file.path,
                "chunk_index": i,
                "file_sha": file.sha,
                "preset": source.options.preset
            }
        )

def _extract_functions_and_classes(self, content: str, file_path: str) -> List[str]:
    """AST 파싱으로 함수/클래스 추출"""
    if file_path.endswith('.py'):
        return self._extract_python_functions(content)
    elif file_path.endswith(('.js', '.ts')):
        return self._extract_javascript_functions(content)
    else:
        return self._chunk_by_size(content, 1024)
```

## 🚀 사용 방법

### 1. 개별 실행

```bash
# GitHub 로더만 실행
python main.py --loader github

# 특정 저장소만 실행
python main.py --loader github --source backend-issues

# 소스코드만 실행
python main.py --loader github --source python-source
```

### 2. 프리셋 테스트

```bash
# 프리셋 설정 확인
python -c "
from loaders.github.loader import GitHubLoader
loader = GitHubLoader()
print(loader.presets['python'])
"

# 특정 저장소 파일 목록 확인
python scripts/test_github.py --repository company/backend-service --type source_code
```
