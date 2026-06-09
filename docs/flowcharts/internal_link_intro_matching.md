# 내부링크 — 서론 링크 매칭 순서도

> 작성: 2026-06-09 | 대상: `app/services/generation/internal_linker.py`

## 배경

서론 링크가 운영 블로그(수백 포스트)에서도 거의 달리지 않는 문제.
원인: 서론은 **현재 글 제목 전체 ↔ 발행 포스트 제목 전체**를 `calculate_text_similarity`
로 비교해 임계값(75%) 이상만 추출하는데, SEO상 긴 제목끼리는 `token_sort_ratio`가
75%를 넘는 일이 거의 없음(같은 주제 변형글도 ~52%). 본론은 짧은 섹션 제목이라
"포함 관계 보너스(85~95)"로 매칭되고, 결론은 랜덤이라 항상 달림.

## 해결 방향

서론은 **공통 핵심 키워드 기반 매칭** + **부족 시 최신순/랜덤 fallback** 으로 변경.
본론·결론 로직은 불변. UI/스키마/DB 변경 없음.

## 순서도

```mermaid
flowchart TD
    A[서론 링크 단계 시작] --> B["현재 글 제목 키워드 추출<br/>normalize_text → 토큰화<br/>→ 불용어·1글자 제거"]
    B --> C{키워드 집합 비었나?}
    C -- 예 --> F[키워드 매칭 결과 = 0]
    C -- 아니오 --> D[각 발행 포스트 제목 키워드 추출]
    D --> E["공통 키워드 개수 계산<br/>target_kw ∩ post_kw"]
    E --> G{공통 키워드 ≥ 1?}
    G -- 예 --> H[후보에 추가<br/>겹침 수 기록]
    G -- 아니오 --> I[제외]
    H --> J[공통 키워드 많은 순 정렬<br/>상위 intro_count 선택]
    F --> J
    J --> K{선택 수 < intro_count?}
    K -- 아니오 --> P[서론 링크 확정]
    K -- 예 --> L["fallback 보충<br/>남은 포스트 중<br/>used_urls·이미선택 제외"]
    L --> M["발행일 있는 것: published_at 내림차순<br/>발행일 없는 것: 뒤에 배치"]
    M --> N[부족분 채워 intro_count 도달]
    N --> P
    P --> Q["_insert_intro_links<br/>버튼/일반 타입으로 두 번째 ## 앞 삽입<br/>used_urls 갱신"]
    Q --> R[본론 단계로]
```

## 매칭 기준 (기본값)

- 서론 매칭: **공통 핵심 키워드 1개 이상** (본론 75% 임계값과 독립)
- fallback 순서: 최신 발행순(`published_at` desc) → 발행일 없음/랜덤
- 채울 개수: 기존 `intro_count` 설정 그대로 (최대 `MAX_INTRO_LINKS=5`)

## 영향 범위

- 수정: `internal_linker.py` (서론 단계 + 헬퍼 추가), `requirements.txt` (rapidfuzz)
- 무변경: 본론/결론 삽입, SimilarityService, substitution_processor, UI, 스키마, DB
