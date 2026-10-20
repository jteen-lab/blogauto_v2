# 사실 관문(F1·F2·F3)과 공식 출처 보류 개선(O1·O2·O3)

> 2026-10-20 마케팅 지시(형 승인 '전부 추천대로') — 슈마즈(블로그 15·모듈 177)만.
> 근거: 슈마즈 클로드 시험(sonnet 신협 오류, haiku 가짜 주소·틀린 절세 조언·'~다' 말투, 6개 중 4개 공식 출처 0건 보류).
> 모든 기능은 모듈 설정 최상위 키 `fact_gate` 가 있을 때만 동작한다. 없으면 지금과 같다.

```mermaid
flowchart TD
    A[제목 선택] --> B[제목 재조합]
    B --> S{fact_gate.official_seeds<br/>제목 낱말 일치?}
    S -- 예 --> S1[O2 공식 시작 주소 직접 읽기<br/>차단 목록 무시·빽빽한 본문만]
    S -- 아니오 --> C
    S1 --> C[네이버 검색·크롤링·관문 1·2]
    C --> D[시작 주소 문서를 맨 앞에 + 나머지 summary_count 개 통합 요약]
    D --> H{공식 출처 0건?<br/>O1: official_api_counts 면 금감원 API 적중도 1건}
    H -- 예 --> HOLD[보류: hold_count+1]
    H -- 아니오 --> W[글쓰기<br/>F3: system_prompt 에 존댓말 한 줄]
    W --> Q[품질 게이트·이어쓰기]
    Q --> F1[F1 주소 거르기<br/>참고 자료 주소 + 허용 도메인만, 열리는지 확인<br/>밖이면 주소만 지우고 기관 이름 남김]
    F1 --> F3{F3 '다.' 평서문 비율 > 20%?}
    F3 -- 예 --> F3R[같은 모델로 말투만 고쳐 쓰기 1회]
    F3R --> F3C{아직 > 20%?}
    F3C -- 예 --> HOLD
    F3C -- 아니오 --> F2
    F3 -- 아니오 --> F2[F2 haiku 사실 검사<br/>문장·이유·확실도 JSON]
    F2 --> F2H{확실도 높음 있음?}
    F2H -- 아니오 --> SAVE[내부링크·치환·이미지·저장]
    F2H -- 예 --> F2F[그 문장만 글쓰기 모델로 고침<br/>답 없으면 문장 삭제]
    F2F --> F2C{재검사에 높음 남음?}
    F2C -- 예 --> HOLD
    F2C -- 아니오 --> SAVE
    HOLD --> O3{O3 next_title_on_hold?<br/>이번 실행 시도 < 3}
    O3 -- 예 --> N[오늘 보류 안 된 다음 제목] --> B
    O3 -- 아니오 --> END[그날은 실패로 기록]
```

## 설정 (모듈 177 `settings.fact_gate`)

| 키 | 뜻 |
|---|---|
| `url_allowlist.enabled/domains/check_alive` | F1. 도메인은 하위 도메인 포함 |
| `polite_tone.enabled/max_ratio` | F3. 기본 0.2 |
| `fact_check.enabled/provider/model` | F2. 기본 anthropic / claude-haiku-4-5. 검사 호출 실패면 검사 없이 계속(기록) |
| `official_api_counts` | O1 |
| `official_seeds` `[{keywords, urls}]`, `max_seeds` | O2. 기본 최대 3개 |
| `next_title_on_hold.enabled/max_attempts` | O3. 기본 3 |

- 파일: `app/services/generation/fact_gate/`(F1·F2·F3), `official_hold.py`(O1), `app/services/reference/official_seeds.py`(O2), `generation/hold_retry.py`(O3).
- 기록: 로그 `[FACT_GATE]`(지운 주소·뽑힌 문장·고친 결과 JSON), `[OFFICIAL_SEED]`, `[HOLD_RETRY]`. 생성 결과 warnings 에 "F1 주소 n개 삭제·F2 틀린 문장 n개 고침".
