# 내부링크 — 관련성 판정 순서도 (무관 링크 차단)

> 작성: 2026-09-29 | 대상: `app/services/generation/internal_linker.py`, `app/services/generation/link_relevance.py`
> 이전 문서: `internal_link_intro_matching.md` (서론 키워드 1개 매칭 — 이 문서로 대체)

## 배경

블로그 '수작남' 실측에서 무관한 내부링크가 붙었다.

| 현재 글 | 붙은 링크 |
|---|---|
| 여드름 글 | 하나카드 분실신고 |
| 지방흡입 글 | AIA생명보험 지점 |
| 화목난로 글 | 외동딸 육아 |
| 안경사 글 | 우창윤다이어트 |

원인
1. 후보 = 블로그 전체 글(카테고리 무시)
2. 서론 버튼·결론 목록이 **공통 토큰 1개**만 있어도 통과
3. 토큰에 조사·어미가 붙은 채 남아(`방법과`, `무엇인가요`, `알아야`) 일반어끼리 매칭
4. 결론 목록은 통과한 글을 **무작위 셔플**

## 순서도

```mermaid
flowchart TD
    A[insert_links 시작] --> B["후보 로드<br/>CrawledPost ⟕ MainTitle<br/>(topic_id, subtopic_id 함께 조회 — lazy load 없음)"]
    B --> C["현재 글 카테고리 조회<br/>MainTitle.title == current_title"]
    C --> D{현재 글 topic 있음<br/>AND 같은 topic 후보 ≥ 1?}
    D -- 예 --> E["후보 = 같은 topic 글만<br/>(같은 subtopic은 정렬 가산)"]
    D -- 아니오 --> F[후보 = 전체 글<br/>카테고리 정보 없음 폴백]
    E --> G
    F --> G["토큰화 tokenize()<br/>NFKC·소문자 → 특수문자 제거 → 공백분리<br/>→ 조사·어미 제거(남는 길이 ≥2일 때만)<br/>→ 불용어·1글자·숫자 제거"]
    G --> H{공통 의미토큰 ≥ 2?<br/>MIN_SHARED_TOKENS}
    H -- 아니오 --> X[제외 — 채우지 않음]
    H -- 예 --> I["점수 정렬<br/>(같은 subtopic, 공통토큰 수) 내림차순<br/>무작위 셔플 없음"]
    I --> J[서론 버튼: 상위 intro_count]
    I --> K["결론 목록: 서론에 쓴 URL 제외 후<br/>prioritize_by_index(안정정렬)<br/>→ 상위 conclusion_count"]
    G --> L["본문 섹션 링크<br/>섹션제목·글제목을 같은 토큰화 후<br/>유사도 ≥ threshold(75) AND 공통토큰 ≥ 1"]
    J --> M[링크 0개여도 정상 — 무관 글로 패딩 금지]
    K --> M
    L --> M
```

## 기준 (전 블로그 공통 기본값)

- `MIN_SHARED_TOKENS = 2` — 서론·결론 공통
- 현재 글 토큰이 2개 미만이면 서론·결론 링크 0개 (판단 근거 없음 → 넣지 않음)
- 본문 섹션: 기존 75% 유사도 유지, 토큰화 결과로 비교 + 공통 토큰 1개 이상
- 카테고리: 같은 topic 우선, 같은 subtopic 가산. 카테고리 정보가 없으면 전체 글.

## 영향 범위

- 신규: `link_relevance.py` (순수 함수: 토큰화·점수·카테고리 필터)
- 수정: `internal_linker.py` (후보 로드·서론·결론·본문 매칭이 위 모듈 사용)
- 무변경: `insert_links` 시그니처, 호출부(generator·renewal·pipeline_tester), 삽입 위치·마크업, DB 스키마

## 주제 찾기 고침 (2026-10-08, 취업인포마스터 재정비 3단계 10)

```mermaid
flowchart TD
    A[insert_links 호출] --> T{현재 글 주제}
    T -- 리뉴얼: category 넘겨받음 --> C[(topic, subtopic)]
    T -- 생성: source_title_id --> C2[원래 정식제목 번호의 topic/subtopic]
    T -- 둘 다 없음 --> C3[같은 제목 MainTitle — 예전 방식]
    C & C2 & C3 --> P[후보 = 같은 블로그 URL 있는 글<br/>정리로 초안·비공개된 글 status=unpublished 제외]
    P --> R{현재 topic 을 아나?}
    R -- 예 --> S[같은 topic 글만 — 없으면 0개<br/>서론·본문·결론 모두]
    R -- 아니오 --> S2[전체 후보 — 관련성 토큰 기준만]
    S & S2 --> L[공통 의미토큰 2개↑ 서론·결론 / 본문은 섹션 제목 유사도]
    L --> E[삽입. 어느 단계든 예외면 링크 0개로 글은 그대로 진행]
```

- 예전: 재조합된 제목으로 MainTitle 을 찾다 못 찾아 (None, None) → 블로그 전체가 후보. 같은 topic 글이 없을 때도 전체로 넓혔다.
- 불용어 추가: 채용·공고·채용공고·모집·모집공고·절차·일정(무관 기관 글끼리 이어지던 원인).
- 배포 전 모의(블로그별 최근 50편): 링크 0개 글 증가 최대 +20%p(머니조아) — 멈춤 기준 50%p 미만.
