# 대량 수집(bulk_collect) 모듈 로직 재설계 작업계획서 (확정본)

> 작성일: 2026-06-04 | 대상 모듈: bulk_collect | 상태: **결정 확정 — 구현 대기**

---

## 0. 이 문서의 목적

대량 수집 모듈의 동작이 사용자 기대와 달랐던 원인을 코드로 규명하고, 옵션이 워크플로우
어느 단계에서 어떤 축을 통제하는지(충돌/중복 없이) 정리한 뒤, 확정된 설계로 구현 단계를
정의한다. **모든 결정(D-1~D-5)은 사용자 승인 완료.**

---

## 1. 현황 진단 (코드 대조 결과)

### 1-1. 결정적 결함 — 사이트맵을 안 크롤링하고 "블로그 홈페이지 제목"만 추출

- **URL탭 = `collected_urls` 테이블** (`/data/urls` API).
- 현재 URL탭 데이터는 **블로그 루트 URL**이다. (실제 DB 샘플: `https://modu.tistory.com/` 등)
- 현재 사이클(`from_collect_module` 모드)은 이 블로그 루트 URL을 **개별 포스트 URL로 착각**하고
  홈페이지 `<title>`(=블로그 이름)만 뽑아 `done` 처리한다. **사이트맵 추출이 통째로 빠져 있음.**
- 그래서 몇 초 만에 끝나고 산출물(블로그 이름)이 무의미했다.

### 1-2. 사이트맵 추출 코드는 존재하나 `direct_input` 모드 전용

- `url_ingester.maybe_ingest_input_urls()` 가 사이트맵 크롤링(Phase 1)을 하지만
  `url_source_mode == "direct_input"` 일 때만 동작. `from_collect_module` 에선 미실행.

### 1-3. `from_collect.max_urls` 등 일부 옵션 미사용 / 직접 입력 모드 잔존

- `from_collect.max_urls`(최대 가져올 URL수)는 코드 어디서도 안 읽힘(unwired).
- `direct_input`(직접 입력)은 자동화 모듈 개념과 안 맞아 **제거 대상**.

### 1-4. 이미 수정 완료된 별건 버그 (참고, 본 재설계와 독립)

- 이벤트 루프 충돌 크래시 → `celery_db_session`(NullPool)로 교체, 수정·검증 완료.
- 동작 로그 결과 표시 / worker_kind 라벨("대량 수집") 수정 완료.

---

## 2. 확정된 데이터 모델 (D-1: 안 A — 꼬리표 방식)

한 테이블(`collected_urls`)이 "블로그 URL(소스)"과 "포스트 URL(크롤 결과)"을 혼용해 1-1 버그가 났다.
**기존 `source_module_id` 컬럼을 꼬리표로 써서 역할을 분리한다 (스키마 변경 없음).**

| 역할 | 식별 | 누가 적재 | 용도 |
|------|------|----------|------|
| 블로그 URL(소스) | `source_module_id IS NULL` | 수집 모듈(URL탭) | Phase 1 사이트맵 크롤 대상 |
| 포스트 URL(결과) | `source_module_id = 모듈ID` | 대량수집 모듈 | Phase 2 제목 추출 대상 |

- 블로그별 크롤 진행 상태는 `BulkCollectProgress`(module_id, blog_domain, last_seen_lastmod,
  last_cycle_at)로 추적 → 증분/재크롤 판단(D-2).

---

## 3. 확정 워크플로우 (옵션 적용 단계 명시)

```
[사이클 시작] ⏱ 타이머 = "사이클 최대 시간(초)" 시작
│
├ Phase 1 — 사이트맵에서 글 주소 모으기 (HTTP 가벼움: 블로그당 sitemap 1~몇 개)
│   ① URL탭(source_module_id IS NULL)에서 크롤할 블로그를 N개 선택
│        ◀ [사이클당 블로그 수]
│        · 선택 우선순위: BulkCollectProgress 기준 미크롤/재크롤 주기 도래 도메인
│   ② 각 블로그의 sitemap.xml → 글 주소 목록(+lastmod) 수신
│   ③ '신규 글'만 골라 블로그당 최대 M개까지 자른다
│        ◀ [블로그당 가져올 글 수] + 증분(D-2: lastmod > last_seen_lastmod & DB 미존재)
│   ④ 자른 글 주소를 collected_urls(source_module_id=모듈ID, status=pending) 적재(중복 스킵)
│   ⑤ BulkCollectProgress.last_seen_lastmod / last_cycle_at 갱신
│   ※ ⏱ 만료 시 즉시 중단(여기까지 적재분 보존)
│
├ Phase 2 — 글에서 제목 뽑기 (HTTP 무거움: 글 1개당 1요청)
│   ⑥ collected_urls(source_module_id=모듈ID, status=pending) 를 열어 제목 추출
│        · 같은 도메인 동시 ≤ [같은 블로그 동시 요청 수]
│        · 전체 동시 ≤ (사이클당 블로그 수 × 같은 블로그 동시 요청 수)  ← 자동 계산(D-5)
│   ⑦ 성공 → 제목을 TempTitle(임시제목탭)에 저장(D-3) + status=done
│      실패 → status=failed
│   ※ ⏱ 만료 시 중단 → 남은 pending 은 다음 사이클이 이어서 처리(재개)
│
└ [사이클 종료] 결과 로그: "블로그 N / 글주소 적재 A / 제목 K (소요 S초)"
```

### 3-1. 옵션 ↔ 단계 ↔ 통제 축 (충돌·중복 없음 검증표)

| 옵션 | 적용 단계 | 통제 축 | 단위 | 다른 옵션과 관계 |
|------|----------|---------|------|------------------|
| 사이클당 블로그 수 | ① | **범위** | 블로그 개수 | 독립 |
| 블로그당 가져올 글 수 | ③ | **깊이**(목록 자르기, 요청 아님) | 글 주소 개수 | 독립 |
| 같은 블로그 동시 요청 수 | ⑥ | **속도**(도메인 예의) | 동시 요청 | 전체동시 자동계산 입력 |
| 사이클 최대 시간(초) | 전체 | **시간**(끊고 이어가기) | 초 | 독립 |
| ~~전체 동시 요청 수~~ | ⑥ | (제거) | — | **자동 = 블로그수 × 동시수** |

- 각 옵션이 서로 다른 축(범위/깊이/속도/시간)을 통제 → 정의상 충돌 없음.
- "전체 동시"는 한 모듈 한 사이클에선 (블로그수 × 도메인동시)로 자동 결정되므로 **옵션에서 제거**(D-5).

### 3-2. 핵심 개념 (혼동 방지)

- **"블로그당 가져올 글 수"는 100번 요청이 아니라 사이트맵 '목록'을 100개로 자르는 것**(Phase 1, 가벼움).
  실제 100요청은 Phase 2(제목 추출)에서 발생하고, 거기서 동시성 옵션이 속도를 제한.
- **"블로그당"은 per-blog** → 사이클당 블로그 3 × 블로그당 100 = 한 사이클 최대 300개(D-4).

### 3-3. 타당성(기본값 기준 300초 내 처리 가능 검토)

- 가정: 글 1개 열기 ~1~2초.
- 글 300개(3블로그×100), 전체 동시 = 3×2 = 6 → 300 ÷ 6 = 50라운드 × 1~2초 ≈ **50~150초.**
- 300초 안에 처리 가능. 못 끝내면 pending 잔여분이 다음 사이클로 자동 이월(재개) → **마감이 아니라 안전장치.**

---

## 4. 확정 옵션 (UI)

| 옵션 라벨 | 키 | 기본값 | 의미 |
|-----------|-----|--------|------|
| 사이클당 블로그 수 | `blogs_per_cycle` | 3 | URL탭에서 한 사이클에 크롤할 블로그 수 |
| 블로그당 가져올 글 수 | `posts_per_blog` | 100 | 각 블로그 사이트맵에서 가져올 신규 글 상한(per-blog) |
| 같은 블로그 동시 요청 수 | `domain_concurrency` | 2 | 동일 도메인 동시 요청 상한 |
| 사이클 최대 시간(초) | `cycle_max_duration_sec` | 300 | 사이클 시간 상한(Timebox) |

- 내부 전역 동시 = `blogs_per_cycle × domain_concurrency` (자동, 옵션 노출 안 함).
- `direct_input`/`input_urls` 관련 옵션은 폼·코드에서 제거.
- (키 이름은 구현 시 기존 settings 호환 고려해 최종 확정; 위는 권장값.)

---

## 5. 확정 결정사항 (D-1 ~ D-5)

- **D-1 데이터 모델**: 안 (A) `source_module_id` 꼬리표(스키마 변경 없음). ✅
- **D-2 재크롤 정책**: 주기적 재크롤 + **신규 글만 증분 수집**(lastmod 비교). ✅
- **D-3 제목 저장 위치**: **임시제목탭(`TempTitle`)** 에 저장. ✅
- **D-4 "블로그당 가져올 글 수"**: 각 블로그 사이트맵에서 가져올 **신규 글 상한(per-blog)**, Phase 1 적용. ✅
- **D-5 "전체 동시 요청 수"**: 옵션 제거, **자동 계산**(블로그수 × 같은블로그동시수). ✅

---

## 6. 구현 단계 (승인 시 진행)

- **P1. Phase 1 신규 구현 (from_collect_module 사이트맵 적재)**
  - URL탭(NULL 풀)에서 `blogs_per_cycle` 블로그 선택(미크롤/재크롤 우선).
  - 각 블로그 sitemap 크롤 → 신규 글만 `posts_per_blog`개까지 → `source_module_id=모듈ID` pending 적재.
  - 기존 `url_ingester`/`sitemap_parser`/`lastmod_tracker` 재사용, 소스를 input_urls → URL탭으로 교체.
- **P2. Phase 2 정합**
  - 제목 추출 대상을 `source_module_id=모듈ID` pending 으로 변경(현재 NULL 풀 오독 수정).
  - 추출 제목을 **TempTitle 저장**(D-3) + status 갱신.
- **P3. 증분 재크롤(D-2)**
  - BulkCollectProgress.last_seen_lastmod 기준 신규 글만 적재. 블로그 재선택 주기 정책.
- **P4. 동시성 정리(D-5)**
  - DomainLimiter global = blogs_per_cycle × domain_concurrency 자동 설정.
- **P5. 옵션/폼 정리**
  - direct_input 제거, 라벨/키/기본값 4종 반영, 설명 문구 추가.
- **P6. 결과 로그·통계 확장**
  - "블로그 N / 글주소 적재 A / 제목 K (소요 S초)" 3단 통계.
- **P7. 테스트**
  - 단일 블로그(소량)·다중 블로그·Timebox 중단/재개·증분 재크롤 시나리오 통합 테스트.

---

## 7. 부록 — 관련 파일

| 파일 | 역할 |
|---|---|
| `app/services/bulk_collect/cycle_runner.py` | 사이클 본체 |
| `app/services/bulk_collect/url_ingester.py` | 사이트맵 적재(Phase 1) — 소스 교체 대상 |
| `app/services/bulk_collect/sitemap_parser.py` | 사이트맵 파싱 + 제목 추출 |
| `app/services/bulk_collect/chunk_processor.py` | pending 글 제목 추출(Phase 2) |
| `app/services/bulk_collect/domain_limiter.py` | 전체/도메인 동시성 |
| `app/services/bulk_collect/lastmod_tracker.py` | BulkCollectProgress 진행/증분 |
| `app/models/collected_url.py` | URL탭 모델 |
| `app/models/bulk_collect_progress.py` | 모듈·도메인별 진행 상태 |
| `app/models/title.py` (TempTitle) | 임시제목탭(제목 저장처, D-3) |
| `app/routers/flows_execute.py::_execute_bulk_collect_module` | 디스패치 |
| 모듈 폼(JS/템플릿) | 옵션 UI(direct_input 제거, 라벨 정리) |
