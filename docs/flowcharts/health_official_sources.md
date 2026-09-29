# 건강형 주제 공식 출처 우선 (수정 4번, 2026-09-29)

대상: 주제/하위주제 이름에 `HEALTH_TOPIC_KEYWORDS`(건강·의학·다이어트·비만·효능·출산·임신·육아·영양)가
있는 글. 분류가 없으면 제목으로 판정. 코드: `services/republish/app/services/reference/health_sources.py`

```mermaid
flowchart TD
    A[collect_evidence 네이버 웹문서 검색] --> B{건강형 주제?<br/>is_health_topic}
    B -- 아니오 --> D
    B -- 예 --> C[추가 질의: 키워드 + 질병관리청/국가건강정보포털/식약처<br/>공식 도메인 결과만 최대 10건, URL 중복 제거]
    C --> D[관문1 → 최신순 정렬 → boost_official<br/>TRUSTED_HEALTH_DOMAINS 앞으로]
    D --> E[크롤링 → 관문2]
    E --> F[boost_official 후 상위 N건 요약/통합정리]
    F --> G[official_refs: 공식 도메인 문서만 기관명·제목·URL·is_official]
    G --> H{citation_block}
    H -- 공식 출처 있음 --> I[글 끝 '참고 자료' = 실제 사용한 공식 출처만<br/>블로그·카페·지식iN 금지]
    H -- 건강형 & 공식 없음 --> J['참고 자료' 만들지 않음]
    H -- 비건강형 & 공식 없음 --> K[지시 없음 = 기존 동작]
    I --> L{건강형?}
    J --> L
    L -- 예 --> M[수치·용량·효과는 공식 출처에 있는 것만, 없으면 정성적<br/>마지막 줄 의료 면책 1줄]
```

미구현: e약은요(DrbEasyDrugInfoService) 어댑터 — data.go.kr 키는 등록돼 있으나 해당 서비스 활용신청 여부 미확인.
