# 블로거 첫 문단 = 검색 설명 (2026-10-23)

블로거는 글마다 '검색 설명'을 API로 넣을 수 없다(10/19 시험 — customMetaData 무시).
글 페이지의 og:description 은 블로그 설명으로 채워지고 name=description 은 없다(수작남·슈마즈 실제 HTML 확인).
형 손으로 테마 head 에 '글 페이지면 본문 앞 150자를 meta description 으로' 한 줄을 넣고,
블로그오토는 첫 문단을 처음부터 그 요약으로 쓰게 한다.

코드: `app/services/generation/lead_summary.py` · 호출: `content_generator_helper.py` (AEO 지시 다음, 분량 지시 앞)

```mermaid
flowchart TD
    A[프롬프트 조립: 모듈 지시 → 참조 → 정보이득 → AEO] --> B{블로그 플랫폼 = BLOGGER?}
    B -- 아니오 --> L[분량 지시 → 경험 규칙(맨 끝)]
    B -- 예 --> C{이미 '첫 문단 = 검색 설명' 있음?}
    C -- 예 --> L
    C -- 아니오 --> D[지시 붙임: H1 다음 첫 문단 2문장 100~150자 즉답<br/>인사·배경·'알아보겠습니다' 금지, 문장으로만<br/>app.log LEAD_SUMMARY]
    D --> L
    L --> G[글 생성 → 발행]
    G --> T[테마 head(형 손): 글 페이지면<br/>본문 앞 150자 → meta name=description]
```

- 워드프레스는 Yoast 가 설명을 내보내므로 대상 아님.
- 새 글부터. 이미 발행한 글은 바꾸지 않는다.
