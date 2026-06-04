# 대량 수집(bulk_collect) 재설계 순서도

> 계획서: `docs/plans/bulk_collect_redesign_plan.md` | 작성일 2026-06-04

## 1 사이클 전체 흐름

```mermaid
flowchart TD
    Start([사이클 시작]) --> TB[Timebox 시작<br/>cycle_max_duration_sec=300]
    TB --> Params[옵션 파싱<br/>blogs_per_cycle/posts_per_blog/domain_concurrency<br/>global = blogs × domain 자동]

    Params --> P1{{Phase 1: 사이트맵 적재}}
    P1 --> SelBlog[URL탭에서 블로그 선택<br/>source_module_id IS NULL, is_active<br/>BulkCollectProgress 미크롤/오래된 순 우선<br/>최대 blogs_per_cycle 개]
    SelBlog --> LoopB[블로그 each]
    LoopB --> Sitemap[sitemap.xml 크롤<br/>포스트 URL 목록 수신]
    Sitemap --> Dedup[이미 DB에 있는 URL 제외<br/>= 신규 글만]
    Dedup --> Cap[신규 글 최대 posts_per_blog 개까지]
    Cap --> Ingest[collected_urls 적재<br/>source_module_id=모듈ID, status=pending]
    Ingest --> Prog[BulkCollectProgress 갱신<br/>last_seen_lastmod/last_cycle_at]
    Prog --> TBchk1{Timebox 만료?}
    TBchk1 -- 예 --> P2
    TBchk1 -- 아니오 --> LoopB

    P1 -.남은 시간.-> P2{{Phase 2: 제목 수집}}
    P2 --> LoadPend[pending 포스트 로드<br/>source_module_id=모듈ID]
    LoadPend --> Fetch[각 글 페이지 열어 title 추출<br/>같은도메인 ≤ domain_concurrency<br/>전체 ≤ global]
    Fetch --> Ok{제목 추출 성공?}
    Ok -- 예 --> SaveT[TempTitle 저장 + status=done]
    Ok -- 아니오 --> Fail[status=failed]
    SaveT --> TBchk2{Timebox 만료?}
    Fail --> TBchk2
    TBchk2 -- 아니오 --> Fetch
    TBchk2 -- 예 --> Done

    Fetch -.모두 처리.-> Done([사이클 종료<br/>결과 로그: 블로그 N/적재 A/제목 K])
```

## 재개(이어하기) 메커니즘

```mermaid
flowchart LR
    C1[사이클 1] -->|Timebox 만료| Save1[pending 잔여 보존]
    Save1 --> C2[사이클 2]
    C2 -->|load pending| Cont[남은 pending 이어서 제목 추출]
    Cont --> Recrawl[Phase1 재크롤 시<br/>dedup 으로 신규 글만 추가]
```

## 데이터 역할 분리 (D-1 꼬리표)

| collected_urls 행 | source_module_id | 역할 |
|---|---|---|
| 블로그 루트 URL | NULL (수집 모듈 적재) | Phase 1 크롤 대상 |
| 포스트 URL | 모듈 ID (대량수집 적재) | Phase 2 제목 추출 대상 |
