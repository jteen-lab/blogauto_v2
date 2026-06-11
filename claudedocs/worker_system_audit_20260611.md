# 워커 시스템 전수 조사 + 지역 데이터 누락 원인 보고서

> 작성일: 2026-06-11 | 대상 서버: A1.Flex 168.110.98.47 (운영) | 이미지 SHA: a3da1b7 (= 로컬 HEAD = origin/main, 3값 일치)

---

## 0. 결론 요약 (TL;DR)

| # | 문제 | 사실(증거) | 심각도 |
|---|------|-----------|--------|
| A | **서버 전 워커가 17워커 autoscale 설계를 미적용** — 고정 소수 concurrency로 구동 | 서버 실제 실행 command 직접 확인 | 🟡 처리량 병목 |
| B | **callback_queue 소비 워커 없음** (서버) | 서버 4개 워커 모두 `-Q`에 callback_queue 없음 | 🟡 잠재(현재 휴면) |
| C | **지역 데이터(korean_locations.json) 서버 이미지에서 통째로 누락** | `/app/shared/data/` 디렉토리 자체 부재 | 🔴 기능 무력화 |

A/B의 뿌리: **서버 `/opt/blogauto/docker-compose.yml`이 레포의 `docker-compose.yml`과 별개로 손수 작성되어, 설계(autoscale 17)가 반영되지 않은 채 임의 값으로 굳어짐** (A1.Flex 마이그레이션 시점).
C의 뿌리: **`.gitignore`의 `*.json` 무차별 제외** → 파일이 git 미추적 → GitHub Actions 체크아웃에 없음 → 이미지 COPY에서 빠짐. 로컬은 볼륨 마운트로 동작해 차이를 못 느낌.

---

## 1. 워커 시스템 전수 조사

### 1-1. 큐 구조 (`app/core/celery_config.py`) — 5큐 체계

| 큐 | 용도 | 라우팅되는 태스크 |
|----|------|------------------|
| generation_queue | 글 생성 파이프라인 | generate_content, recombine_title |
| publish_queue | 발행/재발행 | publish_post, publish_batch, republish_post |
| image_queue | 이미지 생성/업로드 | generate_image, upload_image |
| utility_queue | 수집/데이터 처리 | collect_keywords, transfer_titles, collect_references, bulk_collect_cycle |
| callback_queue | 완료 후처리 | on_generation_complete, on_publish_complete, handle_dead_letter |

### 1-2. 설계값(레포 `docker-compose.yml`) vs 서버 실제값

| 워커 | 레포 설계 (의도) | 서버 실제 (`/opt/blogauto`) | 일치? |
|------|----------------|------------------------|-------|
| generation | `--autoscale=8,3` (3~8 유동) | `--concurrency=2` (고정) | ❌ |
| publish | `--autoscale=5,2` (2~5 유동) | `--concurrency=3` (고정) | ❌ |
| image | `--concurrency=2` | `--concurrency=1` (고정) | ❌ |
| utility | `--concurrency=2 --prefetch=2`, `-Q utility_queue,callback_queue` | `--concurrency=2`, `-Q utility_queue` | ❌ |
| **합계(최대)** | **17** (= 사용자 설계 의도) | **8** (전부 고정) | ❌ |
| **합계(최소)** | 9 | 8 | — |

- **설계 의도**: 총 17 워커, 병목 시 generation 3→8 / publish 2→5 로 **유동 확장**.
- **서버 현실**: 8개 고정, autoscale 전무. 병목이 와도 워커가 늘지 않음.
- "유틸 워커만이 아니라 다른 워커도 모두 같은 문제" = **서버에서 전 워커가 동일하게 autoscale 미적용·고정**이라는 의미. 확인됨.

### 1-3. callback_queue 소비자 부재 (문제 B)

- 서버 어느 워커도 callback_queue를 구독하지 않음 (레포 설계는 utility가 `utility_queue,callback_queue` 동시 구독).
- **단, 현재 데이터 유실은 없음**: `on_generation_complete`/`handle_dead_letter`는 **정의만 되어 있고 코드 어디서도 `.delay()`로 디스패치되지 않음**. 따라서 callback_queue 적체 = 0 (서버 Redis LLEN 직접 확인).
- 즉 **휴면 결함**: 향후 누군가 이 콜백을 디스패치하도록 코드를 추가하면, 서버에선 소비자가 없어 태스크가 Redis에 영구 적체된다. 설계 일관성 차원에서 utility에 callback_queue 구독을 복원해 둬야 함.
- 참고: `bulk_collect/cycle_tuning.py`가 callback_queue LLEN을 백로그 신호로 모니터링하므로, 콜백이 디스패치되는데 소비자가 없으면 대량수집 튜닝이 오작동할 수 있음.

### 1-4. 대량 동시 작업(수십~수백 블로그) 집중 처리 로직 점검

**현재 구조 (정상 동작하는 안전장치):**
- `generate_content`: `BlogLock`(Redis `SET NX EX`, 블로그+작업유형별 키) + `AIRateLimiter`로 보호. 같은 블로그 중복 생성 방지, AI API rate limit 방지. 락 충돌 시 `retry(countdown=30, max_retries=5)`.
- `republish_post` / `generate_image`: 동일하게 `BlogLock`(publish/image)으로 블로그당 직렬화.
- 스케줄러(`flow_scheduler.py`)는 `_acquire_module_dispatch_lock`으로 모듈 단위 중복 디스패치 방지 후 `task_dispatcher`로 큐 투입.

**병목 지점 (구조적 한계):**
- 안전장치(락·rate limit·큐) 자체는 견고. **진짜 병목은 서버 워커 수**.
- 예: 100개 블로그가 동시에 생성 트리거 → generation_queue에 100 태스크 적재 → 서버 워커 concurrency=2 → **한 번에 2건만 처리**, 나머지 98건 대기. 생성 1건 ≈ 1~2분이면 큐 배출에 수십 분~1시간+.
- 설계대로 autoscale 8이면 처리량 4배. 즉 **집중 처리 로직의 결함이 아니라, 서버 워커 수가 설계의 절반 이하로 묶여 처리량이 부족**한 것이 핵심.

---

## 2. 지역 데이터 서버 누락 원인 (문제 C) — "왜 로컬엔 있고 서버엔 없나"

### 2-1. 증거 (서버 컨테이너 직접 조회)
```
$ docker exec blogauto-app-1 ls /app/shared/data/korean_locations.json
ls: cannot access ...: No such file or directory     ← 파일 없음
$ docker exec blogauto-app-1 ls /app/shared/
modules  services                                     ← data/ 디렉토리 자체가 없음
$ docker exec blogauto-app-1 ls /app/shared/services/location_service.py
... location_service.py                               ← 코드는 있음 (데이터만 없음)
```

### 2-2. 근본 원인 — `.gitignore`의 `*.json`
```
.gitignore:28:  *.json          # "# Test files" 의도였으나 전체 json 무차별 제외
$ git check-ignore -v shared/data/korean_locations.json
.gitignore:28:*.json   shared/data/korean_locations.json   ← 매칭됨 = git 미추적
```
- 파일이 **git에 없음** → GitHub Actions `actions/checkout`이 받지 못함 → Dockerfile `COPY shared/`가 **존재하지 않는 파일을 넣을 수 없음** → 이미지에 미포함.
- **로컬에선 정상**: `docker-compose.yml`이 `../../shared:/app/shared` 볼륨 마운트로 워킹트리의 실제 파일(추적 안 돼도 디스크엔 존재)을 직접 제공 → 차이를 인지 못 함.
- 2차 위험: `services/republish/.dockerignore`의 `data/`(슬래시 없음)도 `shared/data/`를 매칭해 제외하는 풋건이 있었음.

### 2-3. 영향
- `location_service.py`는 `Path(__file__).parent.parent/"data"/"korean_locations.json"`을 로드 → 서버에서 로드 실패 → 지역명 추출/정규화 degrade.
- 결과: "지역명이 다르면 그룹화하지 않음" 원칙(제목 이동/유사도 매칭의 기반)이 서버에서 무력화.

### 2-4. 적용한 수정 (로컬)
- `.gitignore`: `!shared/data/`, `!shared/data/**/*.json` 예외 추가 → 파일 추적 가능(확인 완료).
- `services/republish/.dockerignore`: `data/`→`/data/`, `media/`→`/media/`, `backups/`→`/backups/` 로 빌드 컨텍스트 루트 한정. shared 하위 보호.
- 다음 push → GitHub Actions 재빌드 → 서버 pull 시 자동 복구.

---

## 3. 재발 방지 — 왜 이런 일이 생겼나 (정직한 원인 분석)

1. **로컬-서버 환경 비대칭을 검증하지 않음.** 로컬은 볼륨 마운트, 서버는 이미지 빌드. "로컬에서 되니 됐다"가 곧 "서버에서도 된다"가 아님에도, 이미지에 실제로 포함됐는지(=git 추적·COPY 결과) 확인 안 함.
2. **서버 인프라 설정(`/opt/blogauto/docker-compose.yml`)이 버전 관리 밖에 있음.** 레포의 설계(17워커 autoscale)와 무관하게 서버에서 손수 축소 작성됐고, 이 차이를 추적할 수단이 없었음.
3. **배포 검증이 SHA 일치까지만.** 3-SHA 일치는 "코드 버전"은 보장하지만 "런타임 설정(워커 수)·번들 자산(데이터 파일)의 정합성"은 보장하지 못함.

→ 작업 지침 보강안은 §4 및 `CLAUDE.md`/`REGRESSION_PREVENTION.md` 갱신으로 반영.

---

## 4. 권고 조치

### 즉시 (전부 완료·서버 검증)
- [x] 지역 데이터 git 추적 복구(.gitignore/.dockerignore) — 커밋 3c450b5, 서버 이미지 내 존재 확인.
- [x] 서버 워커 17워커 autoscale 복원 + utility callback_queue 구독 — 커밋 04237fd. 부팅 배너로 확증: generation `{min=3,max=8}`, publish `{min=2,max=5}`, image 2, utility 2(+callback_queue). 합계 최소9/최대17.
- [x] 서버 `/opt/blogauto/docker-compose.yml`을 레포 SSOT(installer compose)로 동기화.
- [x] (배포 중 발견) 죽은 scheduler 서비스(`python -m app.scheduler.run`, 모듈 부재→크래시루프) 제거 — 커밋 2bd9aa3. 스케줄러는 app lifespan 구동, 별도 컨테이너 없음(A1.Flex 토폴로지).
- [x] 3-SHA 일치: 로컬=origin=서버이미지=2bd9aa3.

### 지침 보강 (재발 방지)
- 배포 검증에 **자산·런타임 정합성 체크** 추가: ① 이미지 내 필수 데이터 파일 존재 확인 ② 서버 워커 command가 설계와 일치하는지 확인.
- 런타임 의존 데이터는 **절대 광역 ignore에 걸리지 않게** 화이트리스트(`!경로`) 명시.
- 서버 인프라 설정 파일을 레포에서 단일 출처(SSOT)로 관리.

---

## 5. 서버 자원 사실 (autoscale 결정 근거)
- CPU: **2 vCPU**, RAM: 11GB(여유 10GB), 현재 전 큐 적체 0.
- generation/publish는 AI·HTTP I/O 바운드라 vCPU 수보다 높은 concurrency가 유효(대기 시간 동안 컨텍스트 스위칭). 메모리는 충분.
- 단, 사용자 설계의 "17"은 옛 1GB 서버가 아닌 현 11GB 환경 기준으로 무리 없음. autoscale 상한 적용 시 메모리 가드(`worker_max_memory_per_child`)가 이미 200MB로 설정돼 폭주 방지됨.
