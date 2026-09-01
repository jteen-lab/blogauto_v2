# 키워드 모듈 순서도

> 계획서: `docs/plans/keyword_module_redesign_plan.md`
> 검토서: `docs/plans/keyword_management_review.md`

## 1. 실행 진입 경로 (3경로 동일 실행기)

```mermaid
flowchart TD
    A1[모듈 관리<br/>테스트 실행] --> R
    A2[플로우 단일 모듈 실행<br/>flows_execute.execute_module] --> R
    A3[플로우 전체 실행<br/>_execute_flow_background] --> R
    A4[오토런 스케줄러<br/>flow_scheduler] --> R
    R[KeywordModuleRunner.run_for_blogs]
    R --> B{대상 블로그}
    B -->|플로우 연결 블로그 전체| C[블로그별 1회차]
    C --> D[결과 집계 · AutorunLog]
```

**규칙**: 어느 경로로 들어와도 `KeywordModuleRunner` 하나만 탄다.
다른 코드를 타면 한쪽에서만 나는 버그가 생긴다.

## 2. 한 회차 (블로그 1개)

```mermaid
flowchart TD
    S[시작] --> EN{모듈 enabled?}
    EN -->|off & not force| SKIP1[건너뜀]
    EN -->|on| INV[재고 확인<br/>목표재고 = 일일발행 × 리드타임 × 안전계수]
    INV --> INVQ{재고 >= 목표?}
    INVQ -->|예 & not force| SKIP2[건너뜀 - API 낭비 방지]
    INVQ -->|아니오| SEED

    SEED[1 시드 결정<br/>직접입력 → 채택 재귀 → 블로그 카테고리] --> EXP
    EXP[2 확장<br/>head × 수식어 축] --> COL
    COL[3 수집<br/>엔진별 소스에서 연관키워드 + 검색량] --> COLQ
    COLQ{수집 성공?}
    COLQ -->|실패| ERR[실패 반환 - 사유 노출]
    COLQ -->|성공| MEA
    MEA[4 측정<br/>공급 지표 - 월간 발행량] --> JUD
    JUD[5 판정<br/>하한·상한·포화·위험유형] --> TIT
    TIT{make_titles?}
    TIT -->|off| DONE
    TIT -->|on| GEN[6 제목 생성<br/>채택 키워드 → 제목 N편]
    GEN --> GATE[7 품질 관문]
    GATE --> DONE[결과 반환]
```

## 3. 품질 관문 (제목 → 재고)

```mermaid
flowchart LR
    T[생성된 제목] --> F{금지어 필터<br/>ContentFilter}
    F -->|차단| X1[폐기 · 사유 기록]
    F -->|통과| C{카테고리 분류<br/>CategoryMatcher}
    C -->|실패| Q[미분류 큐<br/>재고로 세지 않음]
    C -->|성공| D{중복·유사도}
    D -->|중복| X2[폐기]
    D -->|신규| M[main_titles<br/>status=available<br/>source=keyword_module]
```

**핵심**: 기존 수집(`temp_titles → main_titles`)이 거치는 관문을 그대로 통과시킨다.
현행은 이 관문을 전부 우회해 금지어·중복·미분류 제목이 재고에 직행했다.

## 4. 플래그 의미 (겸용 금지)

| 컬럼 | 뜻 | 세팅 시점 |
|---|---|---|
| `promoted` | **시드로 이미 썼다** | `pick_seeds()` 가 다음 회차 시드로 뽑을 때 |
| `titled` | **제목을 이미 만들었다** | `TitleMaker` 가 제목을 만든 뒤 |

두 값을 한 칸에 겸용하면 *검색량 상위 채택 키워드가 시드로 소비되면서
제목 대상에서 빠진다*(회귀 이력: 검토서 D-4).

## 5. 블로그별 후보 격리

`keyword_candidates` 유일성은 **(user_id, blog_id, keyword)** 다.
사용자 전역으로 걸면 1번 블로그가 먼저 잡은 키워드를 2~12번 블로그가
영원히 재수집하지 못한다(검토서 D-6).
