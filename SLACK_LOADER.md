# Slack Loader 상세 설계

## 주요 기능
- Slack 채널의 메시지와 스레드 수집
- 봇 메시지 필터링
- 날짜 범위 기반 수집
- Rate limiting 및 재시도 처리

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

## API 연동
- **Slack Web API** 사용
- `conversations.history` - 채널 메시지 조회
- `conversations.replies` - 스레드 응답 조회
- `users.info` - 사용자 정보 조회

## 구현 예시
```python
class SlackLoader(BaseLoader):
    def __init__(self, client: SlackClient):
        self.client = client

    async def load_source(self, source: SlackSource) -> AsyncGenerator[Document, None]:
        messages = await self.client.get_channel_messages(
            channel=source.channel,
            options=source.options
        )

        for message in messages:
            if self._should_include_message(message):
                yield self._message_to_document(message, source)
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
# config/loader.yaml
sources:
  slack:
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
```

## 실행 빈도 권장사항

Slack은 실시간 커뮤니케이션 도구 특성상 높은 실행 빈도가 필요합니다:

### 권장 스케줄
- **프로덕션**: 하루 3회 (오전 9시, 오후 2시, 오후 6시)
- **개발환경**: 하루 1회 (오전 10시)

### 스케줄링 고려사항
- **업무시간 집중**: 대부분의 Slack 활동이 업무시간에 발생
- **Rate Limiting**: Slack API 제한 (Tier 3: 50+ calls/minute)
- **데이터 볼륨**: 채널 수와 메시지 수에 따라 실행 시간 변동

```yaml
# 권장 설정 예시
slack:
  schedule: "0 9,14,18 * * *"    # 하루 3회
  timeout: 30                   # 30분 타임아웃
  retry_attempts: 3
  rate_limit_buffer: 10         # API 호출 여유분
```

## 주요 특징
- **Rate Limiting**: Slack API 제한 준수
- **Thread 처리**: 스레드 메시지 포함/제외 옵션
- **Bot 필터링**: 봇 메시지 자동 제외
- **날짜 범위**: 특정 기간 메시지만 수집
- **에러 처리**: 지수 백오프로 3회 재시도
- **실시간성**: 최신 대화 내용 신속 반영
- **증분 업데이트**: 마지막 수집 시간 이후 메시지만 처리

## 증분 업데이트 전략
```python
class SlackLoader(BaseLoader):
    async def load_source(self, source: SlackSource) -> AsyncGenerator[Document, None]:
        # 마지막 수집 시간 조회
        last_fetch_time = await self._get_last_fetch_time(source.key)

        # 증분 업데이트 옵션이 활성화된 경우
        if source.options.incremental and last_fetch_time:
            # 마지막 수집 이후 메시지만 처리
            messages = await self.client.get_channel_messages(
                channel=source.channel,
                oldest=last_fetch_time.timestamp()
            )
        else:
            # 전체 메시지 처리
            messages = await self.client.get_channel_messages(
                channel=source.channel,
                options=source.options
            )

        for message in messages:
            if self._should_include_message(message):
                yield self._message_to_document(message, source)

        # 수집 시간 업데이트
        await self._update_last_fetch_time(source.key, datetime.now())

    async def _get_last_fetch_time(self, source_key: str) -> Optional[datetime]:
        """마지막 수집 시간 조회"""
        timestamp = await self.cache_client.get(f"last_fetch:{source_key}")
        return datetime.fromtimestamp(float(timestamp)) if timestamp else None

    async def _update_last_fetch_time(self, source_key: str, fetch_time: datetime):
        """마지막 수집 시간 업데이트"""
        await self.cache_client.set(
            f"last_fetch:{source_key}",
            str(fetch_time.timestamp()),
            expire=86400*30  # 30일 보관
        )
```

## 에러 처리 전략
```python
class SlackLoader(BaseLoader):
    async def load_source(self, source: SlackSource) -> AsyncGenerator[Document, None]:
        retry_count = 0
        max_retries = 3

        while retry_count <= max_retries:
            try:
                messages = await self.client.get_channel_messages(
                    channel=source.channel,
                    options=source.options
                )

                for message in messages:
                    if self._should_include_message(message):
                        yield self._message_to_document(message, source)
                break

            except SlackAPIError as e:
                if e.response['error'] == 'rate_limited':
                    retry_after = int(e.response.headers.get('Retry-After', 60))
                    await asyncio.sleep(retry_after)
                    continue
                elif retry_count < max_retries:
                    retry_count += 1
                    await asyncio.sleep(2 ** retry_count)
                    continue
                else:
                    raise
            except Exception as e:
                if retry_count < max_retries:
                    retry_count += 1
                    await asyncio.sleep(2 ** retry_count)
                    continue
                else:
                    raise
```
