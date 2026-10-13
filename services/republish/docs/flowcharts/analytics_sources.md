# 유입 경로 · 옛 글 수집 (2026-10-14, 마케팅 B1·B2)

기존 `post_metrics_daily`(블로그오토 발행 글 × 날짜)는 그대로 두고, **블로그의 모든
방문 페이지**를 유입 경로(네이버/구글/직접/기타)별로 따로 적는다. 블로그오토가 쓰지
않은 옛 글(인생꿀팁 수작업 글 등)과 첫 화면까지 빠짐없이 잡힌다.

옛 글을 `search_visibility_urls` 에 넣지 않는 이유: 그 표는 색인 되먹임(발행 상한)·
재발행·문체 선택이 함께 본다. 옛 글이 섞이면 발행 상한과 재발행 판정이 흔들린다.

```mermaid
flowchart TD
    A[하루 한 번 유입 수집 / 지금 수집] --> B[GA4 runReport<br/>날짜·방문페이지·sessionSource·sessionMedium<br/>1만 행씩 끝까지]
    B --> C{행마다 경로 맞추기}
    C -->|블로그오토 발행 글| D[post_metrics_daily<br/>세션 합·평균시간은 세션 가중평균]
    C -->|어떤 경로든| E[경로·날짜별 합산<br/>네이버/구글/직접/기타 나눔]
    E --> F{crawled_posts 주소와 같은가}
    F -->|예| G[crawled_post_id 붙임<br/>옛 글도 제목으로 보임]
    F -->|아니오| H[첫 화면·목록 등 그대로]
    G --> I[page_metrics_daily<br/>그 블로그·그 기간 지우고 다시 넣음]
    H --> I
    I --> J[GET /analytics/sources<br/>블로그별 경로 합계 + 상위 글]
    J --> K[대시보드 유입 분석 패널<br/>경로 칸 + 상위 글 표 · 옛 글 표시]
```

경로 판정(`channels.classify_channel`)
- `(direct)` → 직접
- source 에 `naver` → 네이버
- source 에 `google` → 구글
- 나머지(다음·빙·추천 사이트·AI 등) → 기타
