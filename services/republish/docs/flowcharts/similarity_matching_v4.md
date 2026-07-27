# 유사도 매칭 개편 V4 — 순서도

> 관련 설계서: `docs/plans/similarity_matching_v4_plan.md`
> 작성일: 2026-07-25 | 상태: 설계(미구현)

임베딩 없이 기존 구조를 확장한다. 핵심 4축: **(A) 설정 통일, (B) 회색지대 AI,
(C) 키워드 블로킹, (E) 수동 재매칭 + 멱등성**.

---

## 1. 그룹핑 파이프라인 (승격/데이터모듈/재매칭 공통)

```mermaid
flowchart TD
    START([대상 제목 1건 T]) --> KW["C. 키워드 블로킹<br/>T의 의미토큰 추출<br/>→ 같은 토큰 가진 후보만 조회"]
    KW --> HASC{후보 존재?}
    HASC -- 아니오 --> NEWG[새 그룹 생성<br/>T=대표]
    HASC -- 예 --> SCORE["유사도 점수 계산<br/>calculate_similarity_v3<br/>(후보 전부와, 대표만 아님)"]
    SCORE --> BEST[최고점 후보 C*, 점수 S]
    BEST --> BAND{"B. 밴드 판정<br/>(상한=임계값 T, 하한 L)"}
    BAND -- "S >= T(임계값)" --> GROUP[C*의 그룹에 합류]
    BAND -- "S <= L(하한)" --> NEWG
    BAND -- "L < S < T (회색지대)" --> CACHE{AI 판정 캐시<br/>(T,C*) 존재?}
    CACHE -- 예 --> USECACHE[캐시 결과 사용]
    CACHE -- 아니오 --> AI["저렴 AI 질의<br/>'같은 주제인가?'"]
    AI --> STOREC[판정 캐시에 저장]
    STOREC --> DECI{같은 주제?}
    USECACHE --> DECI
    DECI -- 예 --> GROUP
    DECI -- 아니오 --> NEWG
    GROUP --> STAMP["A/E. 처리 도장<br/>similarity_version=현재버전<br/>similarity_matched_at=now<br/>similarity_score=S"]
    NEWG --> STAMP
    STAMP --> END([완료])
```

---

## 2. 수동 재매칭 흐름 (정식제목 탭) — 멱등성

```mermaid
flowchart TD
    U([사용자: 정식제목 탭<br/>'유사도 재매칭' 클릭]) --> SCOPE[범위 선택<br/>전체 / 카테고리 / 선택]
    SCOPE --> MODE{모드}
    MODE -- "미처리만(기본)" --> Q1["대상 조회:<br/>similarity_version != 현재버전<br/>(또는 NULL)"]
    MODE -- "전체 강제" --> Q2[대상 조회: 범위 내 전부]
    Q1 --> DISPATCH[celery 백그라운드 작업 시작]
    Q2 --> DISPATCH
    DISPATCH --> LOOP["배치 반복:<br/>각 제목 → 1번 파이프라인 적용<br/>(그룹 재배정 계산만, 미확정)"]
    LOOP --> PREVIEW[미리보기 산출<br/>어떤 그룹으로 병합/이동/신설되는지]
    PREVIEW --> CONFIRM{사용자 확정?}
    CONFIRM -- 아니오 --> DISCARD[변경 폐기]
    CONFIRM -- 예 --> APPLY["반영:<br/>group_id 재배정·그룹 병합·대표 재선정<br/>+ 처리 도장 찍기"]
    APPLY --> SNAP[되돌리기 스냅샷 저장<br/>run_id 단위]
    SNAP --> DONE([완료 + 진행률/결과 보고])
    DONE --> RERUN([다시 실행 시])
    RERUN --> Q1
    note1["이미 현재버전 도장 → 미처리 조회에서 제외<br/>= 재매칭해도 새 매칭 없음"]
    Q1 -.-> note1
```

---

## 3. 멱등성 상태 전이 (버전 도장)

```mermaid
stateDiagram-v2
    [*] --> 미처리: 옛 로직으로 이동됨<br/>(version=NULL/old)
    미처리 --> 처리됨: 재매칭 실행<br/>version=현재버전 도장
    처리됨 --> 처리됨: 재매칭 재실행<br/>(스킵 — 새 매칭 없음)
    처리됨 --> 재대상: 로직/설정 변경<br/>현재버전 상향 → 옛 도장이 됨
    재대상 --> 처리됨: 재매칭 실행<br/>새 버전 도장
```
