# Slack Loader 설계

**실시간 커뮤니케이션 도구인 Slack에서 메시지와 스레드를 수집하는 로더입니다.**

## 🎯 주요 특징

- **메시지 및 스레드 수집**: 채널 메시지와 스레드 답글 모두 처리
- **봇 메시지 필터링**: 봇 메시지 자동 제외로 노이즈 감소
- **증분 업데이트**: 마지막 수집 시간 이후 메시지만 처리
- **Rate Limiting**: Slack API 제한 준수 (50+ calls/minute)

## 데이터 모델

```python
@dataclass
class SlackMessage:
    id: str
    channel_id: str
    user_id: str
    text: str
    timestamp: datetime
    thread_ts: Optional[str] = None
    replies: List['SlackMessage'] = field(default_factory=list)

@dataclass
class SlackSource:
    key: str
    workspace: str
    channel: str
    name: str
    options: SlackOptions = field(default_factory=SlackOptions)

@dataclass
class SlackOptions:
    include_replies: bool = True
    exclude_bots: bool = True
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    incremental: bool = True  # 증분 업데이트 사용
```

## 🔧 핵심 구현

### API 연동

- **Slack Web API** 사용
- `conversations.history` - 채널 메시지 조회
- `conversations.replies` - 스레드 응답 조회
- `users.info` - 사용자 정보 조회

### 메인 로더 클래스

```python
# loaders/slack/loader.py
from core.base import BaseLoader

class SlackLoader(BaseLoader):
    def __init__(self):
        config_manager = LoaderConfigManager()
        self.config = config_manager.load_loader_config("slack")
        self.channels = config_manager.load_loader_sources("slack")
        self.client = SlackClient(self.config)

    async def load_source(self, source: SlackSource) -> AsyncGenerator[Document, None]:
        # 증분 업데이트 처리
        last_fetch_time = await self._get_last_fetch_time(source.key)

        messages = await self.client.get_channel_messages(
            channel=source.channel,
            oldest=last_fetch_time.timestamp() if last_fetch_time else None
        )

        for message in messages:
            if self._should_include_message(message):
                yield self._message_to_document(message, source)

        # 수집 시간 업데이트
        await self._update_last_fetch_time(source.key, datetime.now())
```

## 테스트 방법

### 개별 테스트

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

### 설정 예시

```yaml
# loaders/slack/config/config.yaml
loader:
  name: "slack"
  enabled: true
  default_options:
    include_replies: true
    exclude_bots: true
    incremental: true
  rate_limit:
    requests_per_minute: 50
    retry_attempts: 3
    backoff_factor: 2

# loaders/slack/config/channels.yaml
channels:
  - key: "general-channel"
    workspace: "T029G2MBUF6"
    channel: "C052ADQ5B3N"
    name: "#general"
    options:
      include_replies: true
      exclude_bots: true
      date_from: "2024-01-01"
  - key: "dev-channel"
    workspace: "T029G2MBUF6"
    channel: "C052ADQ5B3X"
    name: "#dev"
    options:
      include_replies: false  # 개발 채널은 스레드 제외
      exclude_bots: true
```

## ⚙️ 설정 및 실행

### 실행 빈도

| 환경 | 스케줄 | 이유 |
|------|--------|------|
| **프로덕션** | 하루 3회 (9시, 14시, 18시) | 업무시간 집중 활동 |
| **개발환경** | 하루 1회 (10시) | 개발 편의성 |

### 스케줄링 설정

```yaml
# config/schedule.yaml
sources:
  slack:
    schedule: "0 9,14,18 * * *"    # 하루 3회
    timeout_minutes: 30
    priority: high
```

### 성능 고려사항

- **Rate Limiting**: Slack API 제한 (50+ calls/minute) 준수
- **배치 처리**: 100개 메시지마다 체크포인트 저장
- **에러 처리**: 지수 백오프로 3회 재시도

## 🔄 핵심 기능

### 1. 증분 업데이트

마지막 수집 시간 이후 메시지만 처리하여 효율성 향상

```python
async def _get_last_fetch_time(self, source_key: str) -> Optional[datetime]:
    """Redis에서 마지막 수집 시간 조회"""
    timestamp = await self.cache_client.get(f"last_fetch:{source_key}")
    return datetime.fromtimestamp(float(timestamp)) if timestamp else None

async def _update_last_fetch_time(self, source_key: str, fetch_time: datetime):
    """수집 완료 후 시간 업데이트 (30일 보관)"""
    await self.cache_client.set(
        f"last_fetch:{source_key}",
        str(fetch_time.timestamp()),
        expire=86400*30
    )
```

### 2. 에러 처리 및 재시도

Rate Limiting과 네트워크 오류에 대한 견고한 처리

```python
async def load_source_with_retry(self, source: SlackSource):
    for attempt in range(3):  # 최대 3회 재시도
        try:
            async for message in self._fetch_messages(source):
                yield message
            break
        except SlackAPIError as e:
            if e.response['error'] == 'rate_limited':
                retry_after = int(e.response.headers.get('Retry-After', 60))
                await asyncio.sleep(retry_after)
            else:
                await asyncio.sleep(2 ** attempt)  # 지수 백오프
        except Exception:
            if attempt == 2:  # 마지막 시도
                raise
            await asyncio.sleep(2 ** attempt)
```

### 3. 스레드 처리

메시지별 스레드 답글 수집 및 연결

```python
async def _process_message_with_thread(self, message: SlackMessage, source: SlackSource):
    """메시지와 스레드를 하나의 Document로 통합"""
    content = [message.text]

    if source.options.include_replies and message.thread_ts:
        replies = await self.client.get_thread_replies(
            channel=message.channel_id,
            thread_ts=message.thread_ts
        )
        content.extend([reply.text for reply in replies])

    return Document(
        id=f"slack_{message.channel_id}_{message.timestamp}",
        title=f"#{source.name} - {message.user_id}",
        text="\n---THREAD---\n".join(content),
        metadata={
            "source_type": "slack",
            "channel": source.name,
            "user": message.user_id,
            "has_thread": bool(message.thread_ts),
            "reply_count": len(content) - 1
        }
    )
```

## 🚀 사용 방법

### 1. 개별 실행

```bash
# Slack 로더만 실행
python main.py --loader slack

# 특정 채널만 실행
python main.py --loader slack --source general-channel
```

### 2. 테스트 실행

```bash
# 개별 테스트 스크립트
python scripts/test_slack.py

# 연결 검증만
python -c "from loaders.slack.client import SlackClient; print(SlackClient.test_connection())"
```
