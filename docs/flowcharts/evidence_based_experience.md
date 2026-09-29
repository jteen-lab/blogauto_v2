# 근거 기반 경험담 (경험 서술 규칙)

자동 블로그에는 실제 경험이 없다. 1인칭을 전부 막지 않고, 경험처럼 읽히는
문장을 **수집한 자료의 사실**로만 만들게 한다.

```mermaid
flowchart TD
    A[제목·카테고리] --> B{classify_risk}
    B -->|건강 낱말 + 의료 낱말<br/>또는 육아 외 건강 낱말| H[health]
    B -->|금융·법률 낱말| Y[ymyl]
    B -->|그 외 / 육아 노하우| L[low]
    H --> R[(A) 후기 요약형 + (B) 절차 체험형<br/>1인칭 경험 금지]
    Y --> R
    L --> R2[(A) + (B) + (C) 1인칭 생활 경험<br/>글당 1~2문장·감각/감정만]
    R --> K[공통 금지: 경험 속 사실 지어내기,<br/>의료·금융·법률 1인칭, 효과 체험 주장,<br/>재료 없으면 경험 문단 생략]
    R2 --> K
    K --> S{후기 재료 있음?}
    S -->|예| T[후기 재료 최대 3개 첨부]
    S -->|아니오| U[규칙만]
    T --> Z[프롬프트 맨 끝에 붙임<br/>이 규칙은 위의 경험·페르소나 지시보다 우선한다]
    U --> Z
```

## 붙는 곳

| 경로 | 조립 위치 |
|---|---|
| 자동 생성 · 흐름(flow_generate_executor) · 전체 테스트 · 리뉴얼 | `content_generator_helper.generate_content_with_meta` — 분량 지시문 뒤, AI 호출 직전 |
| 모듈 테스터(단계별) | `pipeline_tester_helpers.call_ai_generate` — 치환 직후 |

모듈 DB 프롬프트(예: 169, 로테이션 변형)의 경험 지시는 DB 를 고치지 않고
이 블록이 마지막에 덮는다. 코드 블록(`blocks.py`·`blocks_voice.py`)의
"저도 같은 경험이 있어서~", "본인 1인칭 시점, 회고체" 등은 자료 기반 표현으로 바꿨다.

## 후기 재료

`build_block(review_snippets=...)` 로 넘길 수 있으나 호출부는 아직 넘기지 않는다.
자동 수집은 체크리스트가 켜진 경우 '실제 겪은 사례·후기' 항목을 kin/cafe 로
검색하지만(evidence_checklist.py), 결과는 통합 요약(digest)에 섞여 프롬프트
조립 시점에 후기만 따로 꺼낼 수 없다. 대신 규칙이 참고 자료 안의 후기를
(A) 형식으로 쓰도록 안내한다.

코드: `services/republish/app/services/prompt_builder/experience_rules.py`
