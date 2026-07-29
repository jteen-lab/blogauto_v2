# 유사도 핵심어(차별 키워드) 발산 가드

> 목적: 지명 사전에 없는 destination 등 **핵심 키워드가 다른데도** generic 단어 공유로 오그룹되는 문제 차단.

## 배경(오그룹 원인)
- `extract_location`은 JSON 사전 기반 → 해외/관광지 지명 미검출 → `_check_location_compatibility` Case 4(둘 다 지역없음)로 무조건 호환.
- `calculate_text_similarity` = token_sort_ratio + keyword_bonus(공통 가점만, 차이 무감점).
- 결과: "○○ 여행 기초정보…추천 숙소" 템플릿을 공유하는 서로 다른 destination(베로나 vs 마카오)이 임계값 초과 → 자동 그룹.

## 처리 순서

```mermaid
flowchart TD
    A[calculate_similarity_v3] --> B{Stage 0: 지역 호환?}
    B -- 불일치 --> Z[score=0 차단]
    B -- 호환/미검출 --> C[Stage 1: 캐노니컬 키]
    C -->|매칭+텍스트>=75| R1[high score 반환]
    C -->|미매칭| D[Stage 2: 키워드 유사도]
    D --> E[keyword_score * (1-penalty)]
    E --> F{핵심어 발산 가드<br/>_core_divergence}
    F -- 발산(양쪽 고유 차별토큰·공유 0) --> G[score = min(score, CAP=55)<br/>분리]
    F -- 정상 --> H[score 유지]
    G --> I[반환]
    H --> I[반환]
```

## 차별 토큰(distinctive tokens) 정의
- 제목 정규화 → 토큰 분리 → **각 토큰: 구두점 제거 + 조사/접미(과,와,을,를,의,에,로,도,만,별,들…) 경량 제거**.
- `len>1` && `KOREAN_STOPWORDS 제외` && `GENERIC_KEYWORDS 제외` 만 남김.
- GENERIC_KEYWORDS: 여행/숙소/명소/날씨/대중교통/코스/일정/지역/특징/준비/음식/맛집… (여행가이드 골격어).

## 발산 판정(_core_divergence)
- D1, D2 = 두 제목의 차별 토큰. 둘 중 하나라도 비면 False(판정 불가).
- 공유(부분문자열 허용, len>=2) 차별 토큰이 **하나도 없으면** → 양쪽이 서로 다른 고유 핵심어만 가짐 → **발산=True**.

## 캡 동작
- 발산 시 `score = min(score, CORE_DIVERGENCE_CAP=55.0)` → 회색지대 하한(기본 68) 미만으로 눌러 **자동 그룹 및 AI 병합 모두 차단**(핵심어가 명확히 다른 경우이므로 하드 분리).
- 캡은 Stage 2에만 적용(캐노니컬 정확일치 Stage 1은 지역+장소 키 기반이라 영향 없음).

## 영향 범위/안전성
- GENERIC_KEYWORDS는 **가드 판정에만** 사용(점수 계산·보너스엔 미사용) → 점수를 올리지 않음, 캡만 가능.
- 공유 차별 토큰이 하나라도 있으면 미발동 → 같은 핵심어(당뇨↔당뇨 등) 쌍은 그대로 그룹.
- 검증: tests/unit에 실제 오그룹쌍(베로나↔마카오, 호치민↔마드리드) 및 정상쌍(당뇨 음식↔당뇨 식단) 추가.
