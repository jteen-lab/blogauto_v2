# 통합 식별자(discriminator) 발산 게이트

> 목적: 지역명/주어 오매칭을 **하나의 로직**으로 처리. "동일 골격어 + 핵심 식별자만
> 다름 → 유사도 과대"를 지명·주어 구분 없이 차단.

## 식별자 = 지명(사전) ∪ 희소 핵심어(DF)
- **지명 소스**: `extract_location`(사전). 공통 지명(서울/부산/포항)은 DF가 높아 희소
  게이트가 못 잡으므로 사전이 필요.
- **주어 소스**: 코퍼스 토큰 DF 하위(희소) 토큰. 해외지명(베로나)·제품(레노버)·
  기관(기업은행) 등 사전에 없는 핵심어를 자동 포착. 기존 GENERIC 수작업 사전 대체.

## 판정 순서

```mermaid
flowchart TD
    A[calculate_similarity_v3] --> B{Stage 0: 지명 호환?<br/>_check_location_compatibility}
    B -- 지명 다름 --> Z[score=0 분리]
    B -- 호환/미검출 --> C[주어 발산 게이트<br/>_subject_divergence]
    C -->|DF 있음| D{두 제목의 희소 주어<br/>겹침 0?}
    C -->|DF 없음| E[폴백: _core_divergence]
    D -- 겹침0 --> F[diverged=True]
    D -- 겹침 --> G[diverged=False]
    E --> H[diverged]
    F & G & H --> I[Stage 1 캐노니컬<br/>diverged면 고득점 차단]
    I --> J[Stage 2 키워드 점수]
    J --> K{diverged & score>CAP?}
    K -- 예 --> L[score=CAP(55) 분리]
    K -- 아니오 --> M[score 유지]
```

## 주어 토큰 / 발산 판정
- `_content_tokens(title)`: 정규화 → 구두점/공백 분리 → 조사·구두점 제거 →
  len>1 & 불용어 제외. (DF 계산·주어 추출 공통 토큰화)
- `_subject_tokens(title)`: `_content_tokens` 중 **df ≤ 임계** 토큰.
  임계 = max(floor, n_docs × RARE_DF_RATIO). 기본 RARE_DF_RATIO=0.003(≈0.3%).
- `_subject_divergence(t1,t2)`:
  - DF 미주입 → None(폴백 `_core_divergence` 사용)
  - 한쪽이라도 주어 없음 → None(보류=그룹)
  - 양쪽 주어 있고 **부분문자열 허용 겹침이 0** → True(발산)

## DF 주입 경로
- `TokenDFService`(app): MainTitle 전체를 `_content_tokens`로 토큰화해 DF/n_docs
  계산, 인메모리 TTL 캐시(기본 10분). shared는 모델 의존 없이 **주입만** 받음.
- `TitleTransferService.move_to_main` 시작 시 DF 로드 → `SimilarityService`에 주입.
- 미주입 시(auto_match/internal_linker) 기존 동작 유지(폴백).

## 검증(POC 결과)
- 통합 게이트: 지역4 + 주어4 + 정상4 = **12/12** 정확.
- 주어 df≤10(≈0.34%) 라벨 9쌍 9/9. IDF-Jaccard 단독은 정상 과분리 → 주어 겹침 방식 채택.

## 리스크/보완
- 동의어 주어(당뇨/혈당) → 분리 위험 → 회색지대 AI 최종판정.
- DF 신선도: TTL 캐시 + 재분류/야간 갱신. 임계는 percentile 튜닝(감사 101쌍 라벨링).
- 지명 정규화(포항/포항시)는 기존 `is_same_location` 재사용.
