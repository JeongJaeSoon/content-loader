# Confluence Loader 설계

**Confluence Cloud에서 문서와 댓글을 수집하는 로더입니다.**

## 🎯 주요 특징

- **CQL 기반 검색**: Confluence Query Language로 정교한 검색
- **계층 구조 처리**: 페이지 부모-자식 관계 유지
- **증분 업데이트**: 수정 날짜 기반 효율적 업데이트
- **댓글 수집**: 페이지별 댓글 포함/제외 옵션

## 데이터 모델

```python
@dataclass
class ConfluencePage:
    id: str
    title: str
    content: str
    space_key: str
    created_date: datetime
    modified_date: datetime
    author: str
    url: str
    ancestors: List[str] = field(default_factory=list)
    comments: List['ConfluenceComment'] = field(default_factory=list)

@dataclass
class ConfluenceSource:
    key: str
    space: str
    type: Literal["space", "page"]
    options: ConfluenceOptions = field(default_factory=ConfluenceOptions)

@dataclass
class ConfluenceOptions:
    include_comments: bool = True
    include_attachments: bool = False
    modified_since: Optional[datetime] = None
    incremental: bool = True  # 증분 업데이트 사용
```

## API 연동 (Cloud 기준)

- **Confluence Cloud REST API** 사용
- 인증: Email + API Token
- `GET /wiki/rest/api/content` - 페이지 조회
- `GET /wiki/rest/api/content/{id}/child/comment` - 댓글 조회
- CQL을 통한 고급 검색

## 🔧 핵심 구현

### API 연동 (Cloud)

- **Confluence Cloud REST API** 사용
- **인증**: Email + API Token (Basic Auth)
- `GET /wiki/rest/api/content` - 페이지 조회
- `GET /wiki/rest/api/content/{id}/child/comment` - 댓글 조회

### 메인 로더 클래스

```python
# loaders/confluence/loader.py
from core.base import BaseLoader

class ConfluenceLoader(BaseLoader):
    def __init__(self):
        config_manager = LoaderConfigManager()
        self.config = config_manager.load_loader_config("confluence")
        self.spaces = config_manager.load_loader_sources("confluence")
        self.client = ConfluenceClient(self.config)

    async def load_source(self, source: ConfluenceSource) -> AsyncGenerator[Document, None]:
        # CQL 쿼리 구성
        cql = self._build_cql_query(source)
        pages = await self.client.search_content(cql)

        latest_modified = None
        for page_data in pages:
            page = await self._fetch_page_details(page_data['id'])

            # 최신 수정 시간 추적
            if not latest_modified or page.modified_date > latest_modified:
                latest_modified = page.modified_date

            yield self._page_to_document(page, source)

        # 마지막 수집 시간 업데이트
        if latest_modified:
            await self._update_last_modified_time(source.key, latest_modified)

    def _build_cql_query(self, source: ConfluenceSource) -> str:
        """CQL 쿼리 생성"""
        cql_parts = [f"space = {source.space} AND type = page"]

        # 증분 업데이트 처리
        if source.options.incremental:
            last_modified = self._get_last_modified_time(source.key)
            if last_modified:
                cql_parts.append(f"lastModified > '{last_modified.strftime('%Y-%m-%d')}'")

        return " AND ".join(cql_parts)
```

## 테스트 방법

### 개별 테스트

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

### 설정 예시

```yaml
# loaders/confluence/config/config.yaml
loader:
  name: "confluence"
  enabled: true
  default_options:
    include_comments: true
    include_attachments: false
    incremental: true
  api_settings:
    timeout_seconds: 30
    retry_attempts: 2
    page_size: 25

# loaders/confluence/config/spaces.yaml
spaces:
  - key: "engineering-docs"
    space: "ENG"
    type: "space"
    description: "Engineering documentation space"
    options:
      include_comments: true
      include_attachments: false
      modified_since: "2024-01-01"
    cql_templates:
      recent_pages: "space = ENG AND type = page AND lastModified > '{date}'"
      api_docs: "space = ENG AND label = 'api-doc'"
  - key: "product-specs"
    space: "PROD"
    type: "space"
    description: "Product specifications"
    options:
      include_comments: false
      include_attachments: true
```

## CQL 쿼리 예시

```python
# 최근 수정된 페이지 검색
cql = "space = ENG AND type = page AND lastModified > '2024-01-01'"

# 특정 라벨이 있는 페이지
cql = "space = ENG AND label = 'api-doc'"

# 제목에 특정 키워드가 포함된 페이지
cql = "space = ENG AND title ~ 'authentication'"

# 특정 작성자의 페이지
cql = "space = ENG AND creator = 'john.doe@company.com'"
```

## ⚙️ 설정 및 실행

### 실행 빈도

| 환경 | 스케줄 | 이유 |
|------|--------|------|
| **프로덕션** | 하루 1회 (10시) | 문서는 상대적으로 낮은 업데이트 빈도 |
| **개발환경** | 주 1회 (일요일 12시) | 개발 효율성 |

### 스케줄링 설정

```yaml
# config/schedule.yaml
sources:
  confluence:
    schedule: "0 10 * * *"        # 하루 1회
    timeout_minutes: 45           # API 응답 시간 고려
    priority: medium
```

### 성능 고려사항

- **API 성능**: Confluence Cloud API는 상대적으로 느림
- **배치 크기**: 25개 페이지씩 처리
- **타임아웃**: 45분 (대용량 스페이스 고려)

## 🔄 핵심 기능

### 1. CQL 기반 검색

Confluence Query Language로 정교한 검색 조건 설정

```python
def _build_advanced_cql(self, source: ConfluenceSource) -> str:
    """고급 CQL 쿼리 생성"""
    # 기본 조건
    cql_parts = [f"space = {source.space}", "type = page"]

    # 증분 업데이트
    if source.options.incremental:
        last_modified = self._get_last_modified_time(source.key)
        if last_modified:
            cql_parts.append(f"lastModified > '{last_modified.strftime('%Y-%m-%d')}'")

    # 템플릿 사용 (설정 파일에서)
    if hasattr(source, 'cql_templates'):
        template = source.cql_templates.get('recent_pages')
        if template:
            return template.format(space=source.space, date=last_modified)

    return " AND ".join(cql_parts)

# CQL 쿼리 예시들
COMMON_CQL_QUERIES = {
    "recent_pages": "space = {space} AND type = page AND lastModified > '{date}'",
    "api_docs": "space = {space} AND label = 'api-doc'",
    "user_pages": "space = {space} AND creator = '{email}'"
}
```

### 2. 계층 구조 처리

페이지 부모-자식 관계 유지 및 처리

```python
async def _fetch_page_with_hierarchy(self, page_id: str) -> ConfluencePage:
    """페이지와 계층 정보 함께 조회"""
    page_data = await self.client.get_page(page_id, expand="ancestors,space,version")

    # 부모 페이지 경로 구성
    ancestors = []
    for ancestor in page_data.get('ancestors', []):
        ancestors.append(ancestor['title'])

    return ConfluencePage(
        id=page_data['id'],
        title=page_data['title'],
        content=page_data['body']['storage']['value'],
        space_key=page_data['space']['key'],
        ancestors=ancestors,  # 계층 구조 정보
        url=f"{self.base_url}/wiki{page_data['_links']['webui']}"
    )
```

### 3. 댓글 통합 처리

페이지별 댓글 수집 및 Document 통합

```python
async def _process_page_with_comments(self, page: ConfluencePage, source: ConfluenceSource):
    """페이지와 댓글을 하나의 Document로 통합"""
    content_parts = [page.content]

    if source.options.include_comments:
        comments = await self.client.get_page_comments(page.id)
        comment_texts = [f"댓글: {comment.body}" for comment in comments]
        content_parts.extend(comment_texts)

    return Document(
        id=f"confluence_{page.space_key}_{page.id}",
        title=page.title,
        text="\n---COMMENT---\n".join(content_parts),
        metadata={
            "source_type": "confluence",
            "space_key": page.space_key,
            "page_id": page.id,
            "ancestors": " > ".join(page.ancestors),  # 계층 경로
            "comment_count": len(content_parts) - 1,
            "url": page.url
        }
    )
```

## 🚀 사용 방법

### 1. 개별 실행

```bash
# Confluence 로더만 실행
python main.py --loader confluence

# 특정 스페이스만 실행
python main.py --loader confluence --source engineering-docs
```

### 2. CQL 쿼리 테스트

```bash
# CQL 쿼리 검증
python -c "
from loaders.confluence.client import ConfluenceClient
client = ConfluenceClient(config)
results = client.search_content('space = ENG AND type = page')
print(f'Found {len(results)} pages')
"
```
