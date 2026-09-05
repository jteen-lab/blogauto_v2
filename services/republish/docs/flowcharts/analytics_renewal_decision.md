# 유입 데이터 수집 → 재발행 판정

지금 재발행은 **날짜만** 본다. 주기가 오면 잘 되는 글도 갈아엎는다.
유입을 붙여 "무엇을 할지" 를 글마다 다르게 정한다.

## 수집 (하루 1회)

```mermaid
flowchart TD
    A[일 1회 스케줄] --> B{GA4 연결됨?}
    B -->|아니오| C[GSC 만으로 진행]
    B -->|예| D[GA4 runReport<br/>date · landingPage<br/>sessions · engagedSessions]
    C & D --> E[GSC searchAnalytics<br/>date · page · query<br/>clicks · impressions · position]
    E --> F[URL 정규화 후<br/>SearchVisibilityUrl 에 매칭]
    F --> G[(post_metrics_daily<br/>하루 한 행)]
    G --> H[28일 창으로 추세 계산<br/>PostPerformance 캐시]
```

두 API 모두 **3일 지연**을 두고 조회한다. 서치콘솔은 2~3일,
GA4 는 당일치가 확정 전이다. 어제 것을 읽으면 값이 계속 흔들린다.

## 판정 — 무엇을 할 것인가

```mermaid
flowchart TD
    S[재발행 주기 도래] --> T{유입/노출 데이터<br/>28일치 있나}
    T -->|없음| L[legacy: 지금 동작 그대로<br/>날짜 기준 재생성]

    T -->|있음| U{세션 > 0?}
    U -->|예| V{28일 세션이<br/>직전 28일 대비 -20% 이하}
    V -->|아니오| KEEP[건드리지 않는다<br/>주기만 미룸]
    V -->|예| AUG[보강<br/>renewal_prompt=additional]

    U -->|아니오| W{노출 > 0?}
    W -->|예| X{평균 순위 8~20위}
    X -->|예| CTR[제목·도입부 손질<br/>본문 유지]
    X -->|아니오| AUG2[보강<br/>질문 갭 주입]
    W -->|아니오| NEW[새로 작성<br/>renewal_prompt=new]
```

`KEEP` 가 이 작업의 핵심이다. 지금은 존재하지 않는 선택지다.

## 니즈 갭 — 무엇을 채울 것인가

보강·재작성 어느 쪽이든 "무엇을 더 쓸지" 가 있어야 한다.
외부 유료 API(AlsoAsked 등) 없이 **우리 서치콘솔 실측**으로 만든다.

```mermaid
flowchart LR
    A[이 URL 이 노출된 쿼리<br/>GSC page 필터] --> B[본문에 답이 있는가<br/>토큰 포함 검사]
    B -->|없음| C[미응답 쿼리]
    C --> D[intent.py 로 의도 분류<br/>info/howto/compare/price/...]
    D --> E[의도별 대표 질문]
    E --> F[생성 프롬프트에 주입<br/>이 질문들에 답하라]
```

`intent.py`(의도 분류)와 `angles.py`(경쟁 각도)가 이미 있다.
같은 자리에 **실측 쿼리**를 하나 더 꽂는 것이다.
