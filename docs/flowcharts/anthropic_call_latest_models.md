# 클로드 호출부 최신화 (2026-10-20, 슈마즈 0단계)

```mermaid
flowchart TD
    A[AIService._try_provider provider=anthropic] --> B{모델 지정?}
    B -- 없음 --> C[기본 claude-haiku-4-5]
    B -- 있음 --> D[지정 모델]
    C --> E[_call_anthropic]
    D --> E
    E --> F{max_tokens >= 4096?}
    F -- 예 --> G[8000 으로 올림 - 글 한 편 잘림 방지]
    F -- 아니오 --> H[그대로]
    G --> I[sampling_kwargs 모델별]
    H --> I
    I --> J{모델 이름}
    J -- haiku-4-5 / sonnet-4-5 --> K[temperature 만]
    J -- sonnet-5 / opus-4-7·4-8 / opus-5* / fable / mythos --> L[샘플링 값 모두 뺌]
    J -- 그 밖의 옛 모델 --> M[temperature·top_p·top_k 그대로]
    K --> N[messages.create]
    L --> N
    M --> N
    N --> O[response_text: type=text 블록만 이어 붙임]
    O --> P{stop_reason=max_tokens?}
    P -- 예 --> Q[로그 '[AI_SERVICE] anthropic 잘림']
    P -- 아니오 --> R[본문 반환 + 토큰 로그]
    Q --> R
```

- gpt·gemini·deepseek 경로는 바뀌지 않는다.
- 참고 요약(reference_summary_service)의 클로드 호출도 같은 response_text 를 쓴다.
