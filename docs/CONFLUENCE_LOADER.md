# Confluence Loader 상세 설계

## 주요 기능

- Confluence Cloud API를 통한 페이지 및 댓글 수집
- CQL(Confluence Query Language) 기반 검색
- 페이지 계층 구조 처리
- 첨부파일 메타데이터 수집

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

## 주요 개선점

```python
class ConfluenceCloudClient:
    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url  # https://company.atlassian.net
        self.auth = aiohttp.BasicAuth(email, api_token)

    async def search_content(self, cql: str) -> List[Dict]:
        # CQL 예시: "space = ENG AND type = page AND lastModified > '2024-01-01'"
        url = f"{self.base_url}/wiki/rest/api/content/search"
        params = {"cql": cql, "expand": "body.storage,space,version"}

        async with self.session.get(url, params=params, auth=self.auth) as response:
            data = await response.json()
            return data.get("results", [])
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
# config/loader.yaml
sources:
  confluence:
    - key: "engineering-docs"
      space: "ENG"
      type: "space"
      options:
        include_comments: true
        include_attachments: false
        modified_since: "2024-01-01"
    - key: "product-specs"
      space: "PROD"
      type: "space"
      options:
        include_comments: false
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

## 실행 빈도 권장사항

Confluence는 문서 관리 시스템 특성상 상대적으로 낮은 실행 빈도가 적절합니다:

### 권장 스케줄

- **프로덕션**: 하루 1회 (오전 10시)
- **개발환경**: 주 1회 (일요일 오후 12시)

### 스케줄링 고려사항

- **문서 업데이트 패턴**: 일반적으로 일괄 업데이트 또는 주기적 업데이트
- **API 성능**: Confluence Cloud API는 상대적으로 느림
- **증분 업데이트**: `modified_since` 옵션으로 효율적 처리 가능

```yaml
# 권장 설정 예시
confluence:
  schedule: "0 10 * * *"        # 하루 1회
  timeout: 45                   # 45분 타임아웃 (API 응답 고려)
  retry_attempts: 2
  options:
    modified_since: "1 day ago" # 증분 업데이트
```

## 주요 특징

- **CQL 지원**: 복잡한 검색 조건 설정 가능
- **계층 구조**: 페이지 부모-자식 관계 유지
- **댓글 처리**: 페이지 댓글 포함/제외 옵션
- **첨부파일**: 메타데이터만 수집 (실제 파일은 별도 처리)
- **증분 업데이트**: 수정 날짜 기반 업데이트 지원
- **에러 처리**: API 타임아웃 및 인증 오류 대응
- **Cloud 최적화**: Confluence Cloud API 특성에 맞춘 설계

## 증분 업데이트 전략

```python
class ConfluenceLoader(BaseLoader):
    async def load_source(self, source: ConfluenceSource) -> AsyncGenerator[Document, None]:
        # CQL 쿼리 구성
        cql_parts = [f"space = {source.space} AND type = page"]

        # 증분 업데이트 처리
        if source.options.incremental:
            last_modified = await self._get_last_modified_time(source.key)
            if last_modified:
                # 마지막 수집 이후 수정된 페이지만 처리
                cql_parts.append(f"lastModified > '{last_modified.strftime('%Y-%m-%d')}'")
        elif source.options.modified_since:
            # 수동 설정된 날짜 이후
            cql_parts.append(f"lastModified > '{source.options.modified_since.strftime('%Y-%m-%d')}'")

        cql = " AND ".join(cql_parts)
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

    async def _get_last_modified_time(self, source_key: str) -> Optional[datetime]:
        """마지막 수집된 페이지의 수정 시간 조회"""
        timestamp = await self.cache_client.get(f"last_modified:{source_key}")
        return datetime.fromisoformat(timestamp) if timestamp else None

    async def _update_last_modified_time(self, source_key: str, modified_time: datetime):
        """마지막 수집 시간 업데이트"""
        await self.cache_client.set(
            f"last_modified:{source_key}",
            modified_time.isoformat(),
            expire=86400*30  # 30일 보관
        )
```

## 에러 처리 전략

```python
class ConfluenceLoader(BaseLoader):
    async def load_source(self, source: ConfluenceSource) -> AsyncGenerator[Document, None]:
        retry_count = 0
        max_retries = 2  # Confluence API는 느리므로 적은 재시도

        while retry_count <= max_retries:
            try:
                pages = await self.client.search_content(
                    cql=self._build_cql_query(source)
                )

                for page_data in pages:
                    page = await self._fetch_page_details(page_data['id'])
                    yield self._page_to_document(page, source)
                break

            except ConfluenceAPITimeoutError:
                if retry_count < max_retries:
                    retry_count += 1
                    wait_time = min(30, 10 * retry_count)  # 최대 30초
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise
            except ConfluenceAuthError:
                # 인증 오류는 재시도하지 않음
                raise
            except Exception as e:
                if retry_count < max_retries:
                    retry_count += 1
                    await asyncio.sleep(5 * retry_count)
                    continue
                else:
                    raise
```
