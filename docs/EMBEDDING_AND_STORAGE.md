# 임베딩 및 벡터 저장 설계

> **📋 메인 설계 문서**: [ARCHITECTURE.md](./ARCHITECTURE.md#-문서-처리-및-벡터-저장)
>
> 이 문서는 임베딩/벡터저장의 **상세 구현 내용**을 담고 있습니다. 전체 아키텍처는 메인 문서를 참고하세요.

## 🎯 핵심 요약 전략

## 🎯 실용적 요약 기준

| 텍스트 길이 | 소스코드 | 문서 | 대화 | Mixed |
|------------|----------|------|------|-------|
| **< 300자** | ❌ | ❌ | ❌ | ❌ |
| **300-600자** | ❌ | ❌ | ✅ | ❌ |
| **600-1500자** | ❌ | ✅ | ✅ | ✅ |
| **> 1500자** | ❌ | ✅ | ✅ | ✅ |

**💡 핵심 원칙**:
1. **짧은 텍스트(300자 미만)**: 요약하면 오히려 손실
2. **긴 텍스트(1500자 이상)**: 무조건 요약해서 검색성 향상
3. **중간 텍스트**: 콘텐츠 타입별 차별화
4. **소스코드**: 길이 관계없이 절대 요약 안함

## 🔧 구현 세부사항

> **💡 간소화된 핵심 로직은 [ARCHITECTURE.md](./ARCHITECTURE.md#-문서-처리-및-벡터-저장)에서 확인**

### 1. 콘텐츠 타입 감지 로직

```python
# 메타데이터 기반 1차 분류
if source_type == 'github':
    if file_path.endswith(('.py', '.js', '.ts')):
        return "source_code"  # 요약 안함
    elif file_path.endswith(('.md', '.rst')):
        return "documentation"  # 요약 진행

elif source_type == 'slack':
    return "conversation"  # 스레드별 요약

elif source_type == 'confluence':
    return "documentation"  # 의미 단위 요약
```

### 2. 청킹 전략별 구현

**함수 기반 청킹 (코드)**:
- Python: AST 파싱으로 함수/클래스 추출
- JavaScript: 정규식 기반 함수 분리
- 기타: 고정 크기 백업

**스레드 기반 청킹 (Slack)**:
- `---THREAD---` 구분자로 스레드 단위 분리
- 대화 흐름 유지

**적응형 청킹 (Mixed)**:
- 코드 블록과 텍스트 섹션 구분
- 각각 다른 전략 적용

## 🗄️ Qdrant Schema Design

### Collection 구조

```python
# 컬렉션 생성
collection_config = {
    "vectors": {
        "size": 1536,  # text-embedding-3-small 차원
        "distance": "Cosine"
    }
}

# 페이로드 인덱스 설정 (빠른 필터링용)
payload_indexes = {
    "content_type": "keyword",     # source_code, documentation, conversation
    "chunk_type": "keyword",       # original, summary
    "source_type": "keyword",      # github, slack, confluence
    "created_at": "datetime"
}
```

### 데이터 예시

```json
{
  "id": "12345",
  "vector": [0.1, 0.2, ...],
  "payload": {
    "chunk_id": "github_owner_repo_file.py_chunk_0",
    "text": "def process_data(data):\n    ...",
    "content_type": "source_code",
    "chunk_type": "original",
    "source_type": "github",
    "source_id": "https://github.com/owner/repo/blob/main/file.py",
    "file_path": "src/utils/file.py",
    "repository": "owner/repo",
    "chunk_index": 0,
    "created_at": "2024-01-15T10:30:00Z"
  }
}
```

## ⚙️ 설정

```yaml
# config/embedding.yaml
embedding:
  service: "openai"  # openai, azure, local
  model: "text-embedding-3-small"
  batch_size: 50
  max_retries: 3

summarization:
  enabled: true
  service: "openai"  # openai, azure, local
  model: "gpt-4o-mini"
  max_tokens: 200

  # 콘텐츠별 요약 설정
  strategies:
    documentation:
      enabled: true
      min_chunk_size: 500  # 500자 이상만 요약
      prompt: "다음 문서의 핵심 내용을 3-5문장으로 요약:"

    conversation:
      enabled: true
      min_chunk_size: 300
      prompt: "다음 대화를 요약하되 주요 결정사항과 액션 아이템 포함:"

    source_code:
      enabled: false  # 코드는 요약하지 않음

    mixed_content:
      enabled: true
      min_chunk_size: 400
      prompt: "다음 내용을 요약 (코드는 제외하고 설명 부분만):"

# config/qdrant.yaml
qdrant:
  url: "http://localhost:6333"
  collection_name: "content_vectors"
  vector_size: 1536
  distance_metric: "Cosine"

  # 컬렉션별 설정
  collections:
    main:
      name: "content_vectors"
      description: "모든 콘텐츠 통합 벡터"

    code_only:
      name: "code_vectors"
      description: "소스코드만 따로 저장"
      filter: "content_type=source_code"
```

## 🚀 사용 예시

```python
# 문서 처리 파이프라인 실행
processor = DocumentProcessor()
embedding_service = EmbeddingService()

async def process_document_stream(documents: AsyncGenerator[Document, None]):
    async for document in documents:
        # 1. 문서 처리 (청킹 + 요약)
        processed_chunks = await processor.process_document(document)

        # 2. 임베딩 + 벡터 저장
        await embedding_service.embed_and_store(
            processed_chunks,
            collection_name="content_vectors"
        )

        print(f"처리 완료: {document.id} -> {len(processed_chunks)} chunks")
```

이 설계로 **콘텐츠 타입별 최적화된 처리**와 **효율적인 벡터 저장**이 가능합니다!
