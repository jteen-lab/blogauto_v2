# 대량 수집 모듈 (bulk_collect) — 워크플로우 플로우차트

> **작성일**: 2026-06-02
> **모듈 타입**: `bulk_collect`
> **목적**: 저장된 URL 또는 사용자 입력 URL에서 대량으로 포스트 제목을 추출. 메모리·시간 분산을 위한 청크 기반 처리.

---

## 1. 모듈 전체 흐름 (High-Level)

```mermaid
flowchart TD
    Start([스케줄러 트리거]) --> CheckActive{GP 활성<br/>시간대?}
    CheckActive -- No --> Skip[스킵 + 다음 스케줄]
    CheckActive -- Yes --> CheckCallback{콜백 큐<br/>적체?}
    CheckCallback -- Yes &<br/>pause_on_backlog=true --> Skip
    CheckCallback -- No --> CheckMem{워커 메모리<br/>여유?}
    CheckMem -- No --> Skip
    CheckMem -- Yes --> StartCycle[사이클 시작<br/>타임박스 시작]

    StartCycle --> LoadURLs[URL 소스 결정]
    LoadURLs --> Source{URL 입력<br/>방식?}

    Source -- 직접 입력 --> FromSettings[Module.settings의<br/>URL 목록]
    Source -- 수집 모듈 DB --> FromDB[collected_urls<br/>is_processed=false<br/>순서/랜덤]

    FromSettings --> Classify
    FromDB --> Classify[URL 자동 판별]

    Classify --> Phase[Phase 1: 사이트맵 적재<br/>Phase 2: 제목 추출]
    Phase --> ChunkLoop{청크<br/>남았나?}

    ChunkLoop -- Yes --> ProcessChunk[청크 처리]
    ProcessChunk --> CheckTime{타임박스<br/>초과?}
    CheckTime -- No --> ChunkLoop
    CheckTime -- Yes --> Commit

    ChunkLoop -- No --> Commit[처리분 커밋]
    Commit --> Reschedule[다음 사이클 예약<br/>GP interval + jitter]
    Reschedule --> End([종료])

    Skip --> End
```

---

## 2. URL 자동 판별 로직

```mermaid
flowchart TD
    URL[입력 URL] --> TryPattern{URL 패턴<br/>매칭}

    TryPattern -- /post/, /entry/,<br/>YYYY/MM/DD, ?p=숫자 --> AsPost[포스트 URL 판정]
    TryPattern -- 매칭 안 됨 --> TrySitemap[/sitemap.xml<br/>HEAD 요청/]

    TrySitemap -- 200 OK --> AsBlog[블로그 URL 판정]
    TrySitemap -- 404/실패 --> Fallback[제목 추출 모드<br/>폴백]

    AsBlog --> ExtractUrls[Phase 1: 사이트맵에서<br/>포스트 URL 추출 →<br/>collected_urls 적재]
    AsPost --> ExtractTitle[Phase 2: HTML에서<br/>title 태그 추출]
    Fallback --> ExtractTitle
```

---

## 3. Phase 1 — 사이트맵 URL 적재 (블로그 URL 입력 시)

```mermaid
flowchart TD
    BlogURL[블로그 URL] --> CheckLastmod{lastmod_only_after_first<br/>+ 첫 실행 아님?}

    CheckLastmod -- Yes --> LoadLast[bulk_collect_progress<br/>에서 last_seen_lastmod 로드]
    CheckLastmod -- No --> FullScan[전체 사이트맵 파싱]

    LoadLast --> ParseSitemap[sitemap.xml /<br/>sitemapindex 파싱]
    FullScan --> ParseSitemap

    ParseSitemap --> FilterNew{각 URL의<br/>lastmod > last_seen?}

    FilterNew -- Yes (또는 lastmod 없음) --> Adapter[중복 체크 후<br/>collected_urls 적재<br/>title_fetch_status=pending]
    FilterNew -- No --> Skip[스킵]

    Adapter --> UpdateProgress[last_seen_lastmod<br/>갱신]
    Skip --> NextURL{다음 URL}
    UpdateProgress --> NextURL
    NextURL --> ParseSitemap
```

**핵심 포인트**:
- Phase 1은 빠른 작업 (네트워크 1회 + XML 파싱). 1만 URL이라도 분 단위에 끝남.
- 적재만 하고 제목 추출은 Phase 2에 위임.

---

## 4. Phase 2 — 청크 단위 제목 추출 (메인 부하)

```mermaid
flowchart TD
    Start[Phase 2 시작] --> InitSem[asyncio.Semaphore 초기화<br/>전역: parallel_titles<br/>도메인별: domain_concurrency]

    InitSem --> LoadChunk[collected_urls 에서<br/>title_fetch_status=pending<br/>chunk_size_initial 개 SELECT]

    LoadChunk --> EmptyCheck{청크 비었나?}
    EmptyCheck -- Yes --> Done[Phase 2 완료]
    EmptyCheck -- No --> GroupByDomain[도메인별 그룹화]

    GroupByDomain --> Parallel[asyncio.gather<br/>병렬 제목 추출]

    Parallel --> Fetch{GET +<br/>title 파싱}
    Fetch -- 성공 --> Save[title 컬럼 저장<br/>title_fetch_status=done<br/>title_fetched_at=now]
    Fetch -- 실패 --> Retry{재시도<br/>횟수?}

    Retry -- 3회 미만 --> Backoff[지수 백오프 후<br/>다시 큐에]
    Retry -- 3회 이상 --> MarkFailed[title_fetch_status=failed]

    Save --> CheckTime
    Backoff --> CheckTime
    MarkFailed --> CheckTime

    CheckTime{타임박스<br/>도달?}
    CheckTime -- Yes --> EarlyCommit[처리분 커밋 + 중단]
    CheckTime -- No --> Adapt{adaptive_chunk_enabled?}

    Adapt -- Yes --> ResizeChunk[처리 시간 측정 →<br/>다음 chunk_size 조정<br/>±50% 범위]
    Adapt -- No --> LoadChunk
    ResizeChunk --> LoadChunk
```

---

## 5. 도메인별 Rate Limit (Semaphore)

```mermaid
flowchart LR
    URL1[example.com/a] --> GlobalSem{전역 세마포어<br/>parallel_titles=10}
    URL2[example.com/b] --> GlobalSem
    URL3[other.com/x] --> GlobalSem
    URL4[example.com/c] --> GlobalSem

    GlobalSem -- acquire --> DomainSem1{example.com<br/>세마포어<br/>concurrency=2}
    GlobalSem -- acquire --> DomainSem2{other.com<br/>세마포어<br/>concurrency=2}

    DomainSem1 -- 2개 동시 통과 --> Fetch1[GET]
    DomainSem1 -- 3번째 대기 --> Wait[대기]
    DomainSem2 -- 통과 --> Fetch2[GET]
```

**효과**:
- 단일 도메인 1만개 → 동시 2개씩만 처리 (사이트 차단 회피)
- 도메인 분산되면 전체 10개 병렬 (1만 URL × 0.3초 = 50분 → 약 5분)

---

## 6. 시간 분산 (Time-Sliced Cycles)

```mermaid
gantt
    title 하루 사이클 분포 예시 (30분 간격, 5분 작업)
    dateFormat HH:mm
    axisFormat %H:%M

    section 활성 시간대 (08:00~22:00)
    사이클 1 :08:00, 5m
    사이클 2 :08:30, 5m
    사이클 3 :09:00, 5m
    사이클 4 :09:30, 5m
    사이클 N :11:00, 5m

    section 야간 부스트 (선택)
    부스트 사이클 :02:00, 8m
```

**계산 예시 (1만 URL, 청크 100, 5분 상한)**:
- 사이클당 100~150개 처리
- 활성 14시간 / 30분 간격 = 28사이클
- 일 처리량: 2,800~4,200개
- 1만 URL 완수: **3~4일**
- 이후 lastmod 증분: 신규 글만 → 사이클 1회로 끝

---

## 7. 데이터 흐름 (DB 관점)

```mermaid
flowchart LR
    User[사용자 입력] --> ModuleSettings[Module.settings.<br/>input_urls JSONB]
    CollectModule[기존 수집 모듈] --> CollectedUrls[(collected_urls)]

    ModuleSettings -- Phase 1 --> Classifier[URL 분류기]
    CollectedUrls -- Phase 1 --> Classifier

    Classifier -- 블로그 URL --> Sitemap[사이트맵 파싱]
    Classifier -- 포스트 URL --> DirectTitle[직접 제목 추출]

    Sitemap --> CollectedUrls
    DirectTitle --> CollectedUrls

    CollectedUrls -- Phase 2 chunk --> TitleExtractor[제목 추출기]
    TitleExtractor -- title 저장 --> CollectedUrls

    BulkProgress[(bulk_collect_progress<br/>last_seen_lastmod)] -.증분 비교.- Sitemap
```

---

## 8. 신규 DB 변경 요약

| 테이블 | 변경 | 설명 |
|--------|------|------|
| `module_types` | row 추가 | `code='bulk_collect'`, `name='대량 수집'` |
| `collected_urls` | 컬럼 추가 | `title_fetched_at`, `title_fetch_status`, `title` (이미 있으면 재사용) |
| `bulk_collect_progress` (신규) | 테이블 신설 | `module_id`, `blog_domain`, `last_seen_lastmod`, `last_cycle_at`, `last_cycle_stats` |
| `modules.settings` JSONB | 키 추가 | bulk_collect 전용 8개 파라미터 + `input_urls` 배열 + `url_source_mode` |

---

## 9. 위험·예외 흐름

```mermaid
flowchart TD
    Fetch[GET 요청] --> Error{에러 유형}
    Error -- Timeout --> Retry1[재시도 + 백오프]
    Error -- 429 Rate Limit --> SlowDown[도메인 세마포어 1로 강제]
    Error -- 403/404 --> Mark[failed로 마킹, 재시도 안 함]
    Error -- 5xx --> Retry2[3회까지 재시도]
    Error -- DNS 실패 --> Mark
    Error -- 사이트맵 없음 --> FallbackTitle[제목 추출 모드 전환]
```

---

## 10. 사용자 시나리오

### Scenario A. 처음 등록한 큰 블로그
1. 사용자가 `https://big-blog.com` 입력 (직접 입력)
2. 사이클 1 (Phase 1): 사이트맵 파싱 → 1만개 URL `collected_urls`에 적재 (1분)
3. 사이클 2~: Phase 2 청크 처리 시작, 100개씩 → 28사이클/일 → **3~4일 후 1만 제목 완수**
4. 이후 매 사이클: lastmod 증분 → 신규 5~10개만 처리 (수십 초)

### Scenario B. 수집 모듈에서 쌓인 미처리 URL 처리
1. 수집 모듈이 일주일 누적 500개 미처리 URL
2. 대량 수집 모듈: "DB → 미처리만 → 순서대로" 설정
3. 사이클당 100개 → 5사이클(2.5시간)에 완료

### Scenario C. 운영 중 콜백 적체 발생
1. 발행 워커가 막혀 callback_queue 적체
2. 다음 사이클 시작 시 `pause_on_callback_backlog` 체크 → 스킵
3. 적체 해소되면 자연 재개
