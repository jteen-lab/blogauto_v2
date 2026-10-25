# 재발행 리뉴얼 — 성과 순서로 고르기 · 옛 글 포함 · 제목/이미지 함께 (2026-10-25, 마케팅 지시·형 승인)

지시서: cheshirecat-app/data/프로젝트/마케팅/보고/2026-10-25_지시서_블로그오토_승인4곳_공격발행·리뉴얼.md (4장)
기존 리뉴얼(`services/renewal/`)을 살린다. 새 동작은 블로그 `renewal_config.pick == "performance"` 일 때만 —
키가 없으면 지금과 똑같다(6개월 지난 블로그오토 글만).

## 1. 재발행 회차에서 리뉴얼 대상 고르기 (renewal_pick.py)

```mermaid
flowchart TD
    R[재발행 회차] --> E{renewal_config.enabled?}
    E -- 아니오 --> D[날짜만 바꾸기]
    E -- 예 --> P{pick == performance?}
    P -- 아니오 --> O[예전 규칙: 6개월 지난 블로그오토 글] --> X
    P -- 예 --> C{오늘 리뉴얼 수 < max_per_day?<br/>인생꿀팁 2 · 나머지 1}
    C -- 아니오 --> D
    C -- 예 --> G[후보: 이 블로그 글 전체(옛 글 crawled 포함)<br/>정리된 글·exclude_paths·min_gap_days(90) 안에 리뉴얼한 글 뺌<br/>제목 관문 위험주제·대출상품이면 뺌]
    G --> M[GA page_metrics_daily 네이버 유입<br/>창 = min(28일, 수집일수/2)]
    M --> Q1{1. 유입 있었는데 줄어드는 글?}
    Q1 -- 있음 --> A1[augment + 새 이미지<br/>직전 유입 큰 순]
    Q1 -- 없음 --> Q2{2. 노출은 있는데 유입 적은 글?<br/>서치콘솔 이력 있는 글만}
    Q2 -- 있음 --> A2[title + 새 이미지]
    Q2 -- 없음 --> Q3{3. 유입·노출 다 없는 옛 글?<br/>블로그 GA 수집 14일↑일 때만}
    Q3 -- 있음 --> A3[rewrite + 새 이미지<br/>오래된 순]
    Q3 -- 없음 --> Q4{4. 6개월 지난 블로그오토 글?}
    Q4 -- 있음 --> A4[legacy — 예전 동작]
    Q4 -- 없음 --> D
    A1 & A2 & A3 & A4 --> X[RenewalService.renew_post]
```

- **수익 글 보호:** 28일 네이버 유입 상위 10편은 rewrite 금지(→ augment), 제목은 그대로.
- GA 행이 없는 글 = 유입 0 으로 읽는 것은 **그 블로그 GA 수집이 14일 이상일 때만**. 아니면 판정 안 함(legacy).

## 2. 한 글 리뉴얼 (renewal_service.py)

```mermaid
flowchart TD
    S[라이브 글 읽기] --> B[원본 백업 logs/renewal_backup/블로그_글번호_시각.json<br/>제목·HTML·이미지 주소]
    B --> PF[성과 판정: 서치콘솔 이력 → 없으면 GA → 보호 규칙]
    PF --> K{keep?}
    K -- 예 --> Z[건너뜀]
    K -- 아니오 --> T{제목 바꿈? title·rewrite}
    T -- 예 --> N1[N1 맨 앞 검색어 재조합 → N4 지난 연도 빼기<br/>→ 같은 블로그·형제 사이트·다른 블로그 중복이면 원래 제목]
    T -- 아니오 --> KT[원래 제목(N4 지난 연도만 뺌)]
    N1 & KT --> REF[참조 수집 → 건강형인데 공식 출처 0건이면 보류(실패)]
    REF --> GEN[본문 생성(augment=살려 확장 · rewrite=새로) + 내부링크 + 치환]
    GEN --> IMG[이미지: 옛 글·제목 재조합이면 새로(템플릿 카드, alt=새 제목)]
    IMG --> CHK[결과 검사: 본문에 옛 업로드 이미지(wp-content/uploads/2022~2025) 남았나]
    CHK --> U{dry_run?}
    U -- 예 --> PV[미리보기만 — 라이브·DB 안 건드림]
    U -- 아니오 --> UP[같은 글 번호로 갱신(주소 그대로, bump_date 끄면 수정일만)] --> L[logs/renewal.jsonl 한 줄]
```

## 3. 이미지만 바꾸기 (renewal_images.py — 10/14 갱신 4편)

```mermaid
flowchart TD
    I[라이브 글 읽기] --> BK[원본 백업]
    BK --> RM[본문 그림(img·감싼 figure) 빼기]
    RM --> NEW[지금 양식 이미지 새로 — 모듈 이미지 설정, 제목 그대로]
    NEW --> DR{dry_run?}
    DR -- 예 --> PV2[새 이미지 파일·새 HTML 만 저장]
    DR -- 아니오 --> UP2[제목·본문 글자 그대로, 그림만 바뀐 HTML 로 갱신(수정일만)]
```

- 옛 이미지 파일은 지우지 않는다. `renewal_cleanup` 은 **서버에 남은 블로그오토 글 사본**(content_html·서버 이미지)만
  지우고 워드프레스 미디어는 건드리지 않는다. 그래도 리뉴얼 켜는 블로그는 `delete_grace_days` 30 으로.

## 4. 사실 관문 · 합치기 후보 · 하한 (2026-10-25 마케팅 검수 반영, 형 '전부 적용')

```mermaid
flowchart TD
    T[제목 정하기 renewal_title] --> D{새 제목이 같은 사이트 글과 겹쳐 '제목 유지'?}
    D -- 예 --> M[리뉴얼 안 함 → logs/renewal_merge_candidates.jsonl 한 줄<br/>301 합치기는 형 확인 뒤 편마다]
    D -- 아니오 --> G[본문 생성]
    G --> R1[R1 규칙: '저도·제 아이도·필자는' 지어낸 경험,<br/>'많은 사용자들이 …보고' 일반화 문장 지움]
    R1 --> R2[R2 검사 모델(기본 claude-sonnet-5): 틀린 문장 + 틀린 전제]
    R2 --> P{전제가 틀렸나?}
    P -- 예 --> RW[바로잡을 전제 지시를 붙여 본문 한 번 다시 쓰기] --> R1b[R1·R2 다시(전제 재시도 없음)]
    P -- 아니오 --> R3[R3 '높음' 문장 고치기(못 고치면 지움) → 재검사]
    R1b --> R3
    R3 --> L{남은 오류·검사 실패·전제 오류?}
    L -- 엄격 주제(건강 약 용량·간격 / 법령 과태료·기준 / 금액 할인율·한도·지원금·상품권) --> H[갱신 안 함(보류)]
    L -- 그 밖 --> X[남은 문장 지우고 계속]
    L -- 없음 --> K[내부 링크 → 자기 글 링크 빼기('함께 볼 글' 버튼 통째로)]
    X --> K
    K --> IMG[대표 그림 넣기 — 이미지만 바꾸기와 같은 [caption]]
    IMG --> S{augment 인데 90% 아래 / rewrite 인데 1,300자 아래?}
    S -- 예 --> NO[실제 갱신 안 함]
    S -- 아니오 --> OK[갱신(백업 먼저)]
```

- 켜는 조건: renewal_config.pick=performance 일 때 기본 켬. `renewal_config.fact_gate = {"enabled": false}` 로 끔,
  `{"provider", "model"}` 로 검사 모델 바꿈.

## 5. 카드 글자 (card_text.py — 모든 템플릿 카드)

- 연도·괄호 빼기('(2026년 기준)'), 쉼표·빗금·대시 앞 검색어 부분만(앞이 5글자 미만이면 그대로),
  마지막 줄 한 글자면 앞 줄 끝 낱말을 같이 내림, `overlay_config.text_band` 있으면 글자 뒤 반투명 띠.

## 6. 맨 앞 검색어 후보 core (lead_keyword_pick.core_words)

- 마지막 '의·와·과' 붙은 낱말 뒤 두 낱말 이상을 후보·조회어 맨 앞에: '아파트와 공동주택의 완강기 설치 기준' →
  「완강기 설치 기준」(2,250). 첫 낱말이 일반어·숫자·'~는/한/할' 이면 안 만든다.
