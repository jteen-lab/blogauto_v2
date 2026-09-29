# 블로거 발행 시 카테고리 라벨 붙이기 (2026-09-29)

## 문제
`_get_labels` 가 `post.matched_main_title.topic/subtopic` 을 읽을 때, 비동기 세션에서
관계가 미리 로드되지 않아 예외(MissingGreenlet)가 났고 `except` 에서 debug 로그로만 삼켜졌다.
→ 모든 블로거 글이 라벨 0개로 발행됨(수작남 실측: 전 글 category=[]).

## 고침
발행 직전에 글이 속한 비동기 세션으로 관계를 **명시적으로 불러온 뒤** 라벨을 만든다.
실패하면 조용히 넘기지 않고 warning 로그를 남긴다(발행 자체는 계속).

```mermaid
flowchart TD
    A[BloggerPublisher.publish] --> B[_load_category_relations post]
    B --> C{post 가 비동기 세션에 붙어 있나?}
    C -->|예| D[refresh post: matched_main_title]
    D --> E{main_title 있음?}
    E -->|예| F[refresh main_title: topic, subtopic]
    E -->|아니오| G[카테고리 라벨 없음]
    C -->|아니오| G
    F --> H[_get_labels: 정적 라벨 + 대주제명 + 소주제명]
    G --> H
    B -. 예외 .-> W[warning 로그 후 계속]
    W --> H
    H --> I{라벨 있음?}
    I -->|예| J[payload.labels 에 넣어 발행]
    I -->|아니오| K[라벨 없이 발행]
```
