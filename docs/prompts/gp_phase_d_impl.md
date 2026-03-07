# Growth Profile Phase D: 발행 모듈 연동 + 워밍업 + FES 간격 체크

> **Phase**: D (발행 모듈 연동 + 워밍업 로직)
> **설계 문서**: growth_stage_strategy_plan.md v3.1
> **선행 Phase**: A (완료 - 30개 테스트), B (완료 - 27개 테스트), M (완료), C (완료 - 25개 테스트)
> **작성일**: 2026-02-22
> **상태**: 구현 대기

---

## 개요

### 목표

1. **publish 모듈 GP 연동**: Growth Profile의 `publish.enabled` + `publish.computed_interval` 기반 발행 실행
2. **워밍업 로직**: 신규 블로그(발행 이력 0건)의 일일 발행 수를 `ramp_rate`로 점진 증가
3. **FES 블로그 레벨 확장**: `FlowExecutionState`에 `blog_id` 컬럼 추가, 블로그별 독립 간격 추적
4. **FES 간격 체크 적용**: publish 블록(신규) + republish 블록(Phase C 연기분)에 interval 경과 체크

### Phase C에서 연기된 항목

Phase C 프롬프트 "FES 간격 판단 구현 현황" 섹션에서 다음을 Phase D로 연기:

- FES `blog_id` 컬럼 추가 (Alembic 마이그레이션)
- republish 블록의 FES interval 경과 체크
- **이유**: FES 확장은 생성/발행/재발행 3개 모듈 모두에 적용되므로, Phase D에서 통합 구현이 효율적

> **generate 블록 FES interval**: Phase D 범위 밖. generate 모듈은 기존 inventory 기반 트리거(`min_inventory` 비교)로 자연스럽게 빈도가 제한되며, 내부 동작이므로 플랫폼 탐지 리스크가 없다. 필요시 별도 Phase에서 추가.

### 핵심 동작 흐름

```
flows_execute.py → publish 디스패치 블록:
  1. gp_context.get_stage_for_blog(blog_id) → stage_params
  2. stage_params.publish.enabled 체크 → false면 스킵
  3. FES 간격 체크 (blog_id 단위): next_execution_at 경과 확인
  4. warmup_manager.check_warmup(blog_id, warmup_settings, active_hours)
     → 워밍업 활성이면 daily_max 기반 간격 적용 (스테이지 interval 대체)
  5. publisher.publish_for_blog(blog, stage_params, warmup_status)
     → InventoryManager.get_post_for_publish() → 플랫폼 API → mark_as_published()
  6. FES 업데이트: record_execution() + calculate_next_execution(effective_interval)
```

---

## 생성/수정 파일 목록

| # | 파일 경로 | 타입 | 변경량 | 설명 |
|---|----------|------|--------|------|
| 1 | `app/models/flow_execution_state.py` | 수정 | +15줄 | blog_id 컬럼 + unique 제약 + 인덱스 |
| 2 | `app/services/generation/warmup_manager.py` | 신규 | ~130줄 | 워밍업 판단 + ramp_rate + 간격 계산 |
| 3 | `app/services/generation/publisher.py` | 신규 | ~80줄 | 발행 오케스트레이터 (InventoryManager + WarmupManager 연동) |
| 4 | `app/routers/flows_execute.py` | 수정 | +100줄 | publish 디스패치 + FES 간격 헬퍼 + republish FES 보강 |
| 5 | `alembic/versions/022_fes_add_blog_id.py` | 신규 | ~35줄 | FES blog_id 마이그레이션 |
| 6 | `app/services/generation/__init__.py` | 수정 | +8줄 | Phase D export |
| 7 | `tests/fixtures/generation_pipeline_fixtures.py` | 수정 | +40줄 | Mock 팩토리 업데이트 |
| 8 | `tests/integration/test_phase_d_publish_warmup.py` | 신규 | ~350줄 | 통합 테스트 26개 |

---

## Phase A/B/C 완성 파일 (참조용, 수정하지 않음)

| 파일 | import 대상 / 참조 사항 |
|------|----------------------|
| `app/services/generation/flow_execution_context.py` | `FlowExecutionContext`, `StageParams`, `ModuleIntervalParams` - publish 블록에서 `stage_params.publish` 참조 |
| `app/services/generation/growth_profile_resolver.py` | `GrowthProfileResolver` - `_build_growth_profile_context()`에서 호출 |
| `app/services/generation/growth_profile_defaults.py` | `DEFAULT_PROFILES` - warmup 설정 기본값 참조 |
| `app/services/generation/inventory_manager.py` | `InventoryManager`, `PublishResult` - publisher에서 get_post_for_publish/on_publish_complete 호출 |
| `app/services/generation/inventory_trigger.py` | `InventoryTrigger`, `InventoryCheckResult` - on_publish_complete 내부에서 사용 |
| `app/models/crawled_post.py` | `CrawledPost` - 발행 대상 조회, published_at 기반 워밍업 판단 |
| `app/services/publish_service.py` | `PublishService` - 기존 WordPress/Blogger 발행 API (publisher에서 위임) |

---

## 파일 1: flow_execution_state.py 수정

### 경로: `app/models/flow_execution_state.py` (265줄 → ~280줄)
### 변경 개요: blog_id 컬럼 추가로 (flow_id, module_id, blog_id) 단위 추적 지원

### 1-1. blog_id 컬럼 추가

**변경 전** (39줄 이후):
```python
    module_id = Column(
        Integer,
        ForeignKey("modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
```

**변경 후** (module_id 아래에 추가):
```python
    module_id = Column(
        Integer,
        ForeignKey("modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    blog_id = Column(
        Integer,
        ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="블로그별 간격 추적용 (nullable: 기존 레코드 호환)"
    )
```

> **nullable=True 이유**: 기존 FES 레코드에는 blog_id가 없으므로, 하위 호환을 위해 nullable. Phase D 이후 신규 생성되는 FES 레코드는 항상 blog_id를 설정한다.

### 1-2. __table_args__에 복합 unique 제약 추가

```python
    __table_args__ = (
        # 신규: (flow_id, module_id, blog_id) 조합 유니크
        Index(
            'ix_fes_flow_module_blog',
            'flow_id', 'module_id', 'blog_id',
            unique=True,
        ),
    )
```

> **현재 FES 모델 상태**: `(flow_id, module_id)` unique 제약이 없으며 `__table_args__`도 미정의 상태. 따라서 Alembic 마이그레이션에서 기존 unique 제약 제거 작업은 불필요하다. 신규 `__table_args__`를 추가하여 3컬럼 복합 unique 인덱스만 정의한다.

### 1-3. 기존 메서드 영향 없음

`record_execution()`, `calculate_next_execution()`, `is_in_active_window()`, `pause()`, `resume()` 메서드는 blog_id와 무관하게 동작하므로 변경하지 않는다.

---

## 파일 2: warmup_manager.py 신규

### 경로: `app/services/generation/warmup_manager.py` (신규, ~130줄)
### 설계 출처: 작업계획서 Section 5-1 warmup 객체, Section 10 Phase D, Q4

### 2-1. WarmupStatus 데이터클래스

```python
@dataclass
class WarmupStatus:
    """워밍업 상태 판단 결과"""
    is_active: bool                     # 워밍업 활성 여부
    days_elapsed: int                   # 첫 발행 이후 경과일 (미발행: -1)
    daily_max: int                      # 오늘 허용 발행 수
    today_published: int                # 오늘 이미 발행한 수
    can_publish: bool                   # 추가 발행 가능 여부
    effective_interval: Optional[int]   # 워밍업 기반 간격 (분), 비활성이면 None
```

### 2-2. WarmupManager 클래스

```python
class WarmupManager:
    """
    워밍업 판단 서비스

    신규 블로그(발행 이력 0건)의 발행 수를 점진적으로 증가시켜
    블로그 플랫폼의 기계적 발행 탐지를 방지합니다.

    적용 범위: 발행(publish)에만 적용
    - 생성(generate): 영향 없음 (내부 동작)
    - 재발행(republish): 대상 아님 (신규 블로그에 재발행할 글 없음)

    워밍업 대상 기준 (사용자 결정 W7):
    - 발행 이력 0건인 블로그 = 워밍업 대상
    - 첫 발행일로부터 warmup_days 경과 = 워밍업 종료
    """

    def __init__(self, db: AsyncSession):
        self.db = db
```

### 2-3. check_warmup() 메서드

```python
    async def check_warmup(
        self,
        blog_id: int,
        warmup_settings: dict,
        active_hours: int,
    ) -> WarmupStatus:
        """
        블로그의 워밍업 상태를 판단합니다.

        Args:
            blog_id: 블로그 ID
            warmup_settings: GP settings.warmup 객체
            active_hours: 오늘의 활성 시간 수 (schedule_matrix 기반)

        Returns:
            WarmupStatus: 워밍업 판단 결과
        """
```

**check_warmup 판단 로직:**

```
1. warmup_settings.get("enabled") == False → WarmupStatus(is_active=False, ...)
2. _get_first_publish_date(blog_id) 조회
   - None (발행 이력 0건) → 워밍업 대상, days_elapsed=-1
     → daily_max = initial_daily_posts, effective_interval 계산
   - 있음 → 경과일 = (today - first_publish_date).days
     → 경과일 >= warmup_days → 워밍업 종료 (is_active=False)
     → 경과일 < warmup_days → 워밍업 중
3. 워밍업 중이면:
   - daily_max = min(initial + (days_elapsed × ramp_rate), max_daily_posts)
   - today_published = _count_today_publishes(blog_id)
   - can_publish = today_published < daily_max
   - effective_interval = (active_hours × 60) / daily_max
```

### 2-4. 내부 헬퍼 메서드

```python
    async def _get_first_publish_date(self, blog_id: int) -> Optional[datetime]:
        """블로그의 첫 발행 일시 조회 (CrawledPost.published_at 기준)"""
        # SELECT MIN(published_at) FROM crawled_posts
        # WHERE blog_id = :blog_id AND published_at IS NOT NULL

    async def _count_today_publishes(self, blog_id: int) -> int:
        """오늘 발행한 포스트 수 조회"""
        # SELECT COUNT(*) FROM crawled_posts
        # WHERE blog_id = :blog_id
        #   AND published_at >= today_start (00:00:00 KST)
        #   AND published_at IS NOT NULL

    @staticmethod
    def _calculate_daily_max(
        days_elapsed: int,
        initial_daily_posts: int,
        max_daily_posts: int,
        ramp_rate: float,
    ) -> int:
        """ramp_rate 기반 일일 허용 발행 수 계산"""
        # min(initial + (days_elapsed × ramp_rate), max_daily_posts)
        # 결과를 int()로 내림 (floor)
```

> **핵심 공식** (작업계획서 Section 10 Phase D):
> ```
> daily_max = min(initial + (경과일 × ramp_rate), max_daily_posts)
> effective_interval = (active_hours × 60) / daily_max
> ```
> 예) initial=1, max=3, ramp_rate=0.5, active_hours=16:
> - Day 0: daily_max=1, interval=960분
> - Day 2: daily_max=2, interval=480분
> - Day 4: daily_max=3, interval=320분

---

## 파일 3: publisher.py 신규

### 경로: `app/services/generation/publisher.py` (신규, ~80줄)
### 설계 출처: 작업계획서 Section 10 Phase D, Section 6-1 Step 4

### 3-1. Publisher 클래스

```python
class Publisher:
    """
    발행 오케스트레이터

    InventoryManager에서 발행 대상 포스트를 조회하고,
    워밍업 제약을 확인한 후, 플랫폼 API로 발행합니다.
    발행 완료 후 재고 상태를 반환합니다.

    워크플로우:
    1. InventoryManager.get_post_for_publish(blog_id) → CrawledPost
    2. WarmupManager.check_warmup() 기반 daily_max 초과 체크
    3. 플랫폼 API 발행 (기존 서비스 위임)
    4. InventoryManager.on_publish_complete(blog_id, post_id)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.inventory_mgr = InventoryManager(db)
```

### 3-2. publish_for_blog() 메서드

```python
    async def publish_for_blog(
        self,
        blog: Blog,
        warmup_status: WarmupStatus,
    ) -> Dict[str, Any]:
        """
        블로그에 생성된 글 1건을 발행합니다.

        Args:
            blog: 발행 대상 블로그
            warmup_status: 워밍업 상태 (WarmupManager.check_warmup() 결과)

        Returns:
            dict: {"success": bool, "skipped": bool?, "message": str, ...}
        """
```

**publish_for_blog 동작 로직:**

```
1. 워밍업 일일 한도 체크
   - warmup_status.is_active AND NOT warmup_status.can_publish
   → {"success": True, "skipped": True, "message": "워밍업 일일 한도 초과 (N/M)"}

2. 발행 대상 포스트 조회
   - inventory_mgr.get_post_for_publish(blog.id)
   → None이면 {"success": True, "skipped": True, "message": "발행할 글 없음 (재고 0)"}

3. 플랫폼 API 발행
   - 기존 _execute_republish_for_blog() 패턴 참조
   - blog.platform에 따라 WordPress/Blogger 라우팅
   - CrawledPost → GenerationHistory → 콘텐츠 조회 → API 호출

4. 발행 완료 처리
   - inventory_mgr.on_publish_complete(blog.id, post.id)
   → PublishResult 반환 (inventory_check.needs_generation 포함)

5. 결과 반환
   → {"success": True, "post_id": N, "inventory": N, "needs_generation": bool}
```

> **NOTE**: CrawledPost에는 `content` 필드가 없다. 생성된 HTML은 `generation_history_id` FK를 통해 GenerationHistory에서 참조한다. 실제 발행 시 콘텐츠 조회 로직은 기존 PublishService(app/services/publish_service.py) 패턴을 참조하여 구현한다.

> **NOTE**: 실제 WordPress/Blogger API 호출 구현은 기존 서비스(`_execute_republish_for_blog` 패턴)를 참조한다. Phase D에서는 발행 API 자체를 새로 만들지 않고, 기존 플랫폼 서비스를 활용한다.

---

## 파일 4: flows_execute.py 수정

### 경로: `app/routers/flows_execute.py` (1325줄 → ~1425줄)
### 변경 개요: publish 모듈 디스패치 블록 추가 + FES 간격 헬퍼 + republish FES 보강

### 4-1. FES 블로그 레벨 헬퍼 함수 (파일 하단, 기존 헬퍼 영역)

```python
async def _get_or_create_blog_fes(
    db: AsyncSession,
    flow_id: int,
    module_id: int,
    blog_id: int,
) -> FlowExecutionState:
    """
    (flow_id, module_id, blog_id) 단위의 FES를 조회하거나 생성합니다.

    Returns:
        FlowExecutionState: 기존 또는 신규 생성된 FES
    """
    # SELECT ... WHERE flow_id=:f AND module_id=:m AND blog_id=:b
    # 없으면 INSERT (next_execution_at=None → 첫 실행 즉시 허용)
```

```python
def _check_fes_interval(
    state: FlowExecutionState,
    now: datetime,
) -> bool:
    """
    FES 간격이 경과했는지 확인합니다.

    Returns:
        True: 실행 가능 (간격 경과 또는 첫 실행)
        False: 실행 불가 (간격 미경과)
    """
    # state.next_execution_at이 None이면 True (첫 실행)
    # state.is_paused이면 False
    # now >= state.next_execution_at이면 True
    # 아니면 False
```

```python
def _update_fes_after_execution(
    state: FlowExecutionState,
    success: bool,
    interval_minutes: int,
    gp_context: FlowExecutionContext,
) -> None:
    """
    실행 후 FES를 업데이트합니다.

    state.record_execution(success)
    state.calculate_next_execution(
        interval_minutes=interval_minutes,
        schedule_matrix=gp_context.schedule_matrix,
        jitter_enabled=gp_context.jitter.get("enabled", False),
        jitter_min_percent=gp_context.jitter.get("min_percent", -20),
        jitter_max_percent=gp_context.jitter.get("max_percent", 30),
    )
    """
```

### 4-2. publish 모듈 디스패치 블록

**삽입 위치**: republish 블록(327~431줄) **앞**에 삽입 (Step 4: publish → Step 5: republish 순서)

> **실행 순서 근거**: 작업계획서 Section 6-1의 실행 흐름:
> ```
> Step 3: prompt(생성) → Step 4: publish(발행) → Step 5: republish(재발행)
> ```
> 발행이 재발행보다 먼저 실행되어야 재고가 감소하고, 재발행은 기존 글을 대상으로 동작한다.

**블록 구조** (republish 블록 패턴 기반):

```python
            # 7. publish 모듈 실행 (GP 컨텍스트 기반 발행 + 워밍업)
            if "publish" in modules_by_type:
                if not blogs:
                    # 블로그 없음 처리 (republish 패턴과 동일)
                    ...
                else:
                    from app.services.generation.publisher import Publisher
                    from app.services.generation.warmup_manager import WarmupManager

                    for publish_module in modules_by_type["publish"]:
                        logger.info(f"[FLOW_BG] 발행 모듈 실행: {publish_module.name}")

                        # schedule_matrix에서 오늘의 활성 시간 수 계산
                        active_hours = _count_active_hours(gp_context.schedule_matrix)

                        # warmup 설정 로드
                        warmup_settings = (
                            gp_context.growth_profile.get("warmup", {})
                            if gp_context.growth_profile else {}
                        )

                        warmup_mgr = WarmupManager(db)
                        publisher = Publisher(db)

                        for blog in blogs:
                            # (1) GP publish.enabled 체크
                            stage_params = gp_context.get_stage_for_blog(blog.id)
                            if stage_params and not stage_params.publish.enabled:
                                # 스킵 로그 (republish 패턴과 동일)
                                ...
                                continue

                            # (2) FES 간격 체크
                            fes = await _get_or_create_blog_fes(
                                db, flow.id, publish_module.id, blog.id,
                            )
                            now = datetime.now(KST)
                            if not _check_fes_interval(fes, now):
                                logger.info(
                                    f"[FLOW_BG] 발행 간격 미경과 | blog={blog.name} | "
                                    f"next={fes.next_execution_at}"
                                )
                                continue

                            # (3) 워밍업 체크
                            warmup_status = await warmup_mgr.check_warmup(
                                blog.id, warmup_settings, active_hours,
                            )

                            # (4) 발행 실행
                            blog_start_time = datetime.now()
                            try:
                                result = await publisher.publish_for_blog(
                                    blog, warmup_status,
                                )
                                blog_duration_ms = int(
                                    (datetime.now() - blog_start_time).total_seconds() * 1000
                                )

                                # (5) FES 업데이트 (실행 성공/실패 모두)
                                if not result.get("skipped"):
                                    # 재고 0 또는 워밍업 한도 초과로 스킵된 경우 FES를 업데이트하지 않음.
                                    # 의도적 설계: 다음 Flow 실행 시 재고/한도를 다시 확인하여,
                                    # 재고가 확보되면 간격을 기다리지 않고 즉시 발행할 수 있게 한다.
                                    # 워밍업 활성이면 effective_interval, 아니면 computed_interval
                                    effective_interval = (
                                        warmup_status.effective_interval
                                        if warmup_status.is_active and warmup_status.effective_interval
                                        else stage_params.publish.computed_interval
                                    )
                                    _update_fes_after_execution(
                                        fes,
                                        success=result.get("success", False),
                                        interval_minutes=effective_interval or 60,
                                        gp_context=gp_context,
                                    )

                                # 로그 저장 + 카운트 (republish 패턴과 동일)
                                await _save_autorun_log(...)
                                if result.get("success"):
                                    success_count += 1
                                else:
                                    fail_count += 1
                                total_processed += 1

                            except Exception as e:
                                # 에러 처리 (republish 패턴과 동일)
                                ...
```

**핵심 변경 4가지:**
1. `stage_params.publish.enabled` 체크 (republish의 `stage_params.republish.enabled`와 동일 패턴)
2. `_get_or_create_blog_fes()` + `_check_fes_interval()` 호출 (신규)
3. `WarmupManager.check_warmup()` 호출 후 `Publisher.publish_for_blog()` 위임 (신규)
4. `_update_fes_after_execution()` - 워밍업이면 `effective_interval`, 아니면 `computed_interval` 사용 (신규)

### 4-3. 활성 시간 계산 헬퍼

```python
def _count_active_hours(schedule_matrix: Optional[list]) -> int:
    """
    오늘의 schedule_matrix에서 활성 시간 수를 계산합니다.

    Args:
        schedule_matrix: 7x24 bool 매트릭스 (없으면 24 반환)

    Returns:
        활성 시간 수 (최소 1)
    """
    # 현재 요일(월=0, 일=6) 기준으로 해당 행의 True 개수 반환
    # schedule_matrix가 None이면 24 반환
    # 결과가 0이면 1 반환 (0으로 나누기 방지)
```

### 4-4. republish 블록 FES interval 보강 (Phase C 연기분)

**현재 상태**: republish 블록(327~431줄)은 `stage_params.republish.enabled` 체크만 수행. FES 간격 체크 없이 매 실행마다 모든 enabled 블로그에 대해 재발행.

**변경**: publish 블록과 동일한 FES 패턴 추가.

**republish 블록의 blog 루프 내부에 추가** (기존 enabled 체크 이후):

```python
                            # republish.enabled 체크 (기존)
                            if stage_params and not stage_params.republish.enabled:
                                ...
                                continue

                            # FES 간격 체크 (Phase D 추가)
                            fes = await _get_or_create_blog_fes(
                                db, flow.id, republish_module.id, blog.id,
                            )
                            now = datetime.now(KST)
                            if not _check_fes_interval(fes, now):
                                logger.info(
                                    f"[FLOW_BG] 재발행 간격 미경과 | blog={blog.name} | "
                                    f"next={fes.next_execution_at}"
                                )
                                continue

                            # ... 기존 재발행 실행 로직 ...

                            # 실행 후 FES 업데이트 (Phase D 추가)
                            if result.get("success"):
                                _update_fes_after_execution(
                                    fes,
                                    success=True,
                                    interval_minutes=stage_params.republish.computed_interval or 60,
                                    gp_context=gp_context,
                                )
```

**핵심 변경 2가지:**
1. enabled 체크 이후 `_get_or_create_blog_fes()` + `_check_fes_interval()` 추가
2. 실행 성공 후 `_update_fes_after_execution()` 호출 추가

---

## 파일 5: Alembic 022 마이그레이션

### 경로: `alembic/versions/022_fes_add_blog_id.py` (신규, ~35줄)

```python
"""FES에 blog_id 컬럼 추가 (블로그별 간격 추적)

Revision ID: 022
Revises: 021
Create Date: 2026-02-22

Growth Profile Phase D: 블로그별 독립 간격 추적을 위해
FlowExecutionState에 blog_id FK 컬럼을 추가합니다.
"""

def upgrade():
    # 1. blog_id 컬럼 추가 (nullable)
    op.add_column(
        "flow_execution_states",
        sa.Column("blog_id", sa.Integer(),
                  sa.ForeignKey("blogs.id", ondelete="CASCADE"),
                  nullable=True),
    )
    # 2. 복합 인덱스 추가
    op.create_index(
        "ix_fes_flow_module_blog",
        "flow_execution_states",
        ["flow_id", "module_id", "blog_id"],
        unique=True,
    )

def downgrade():
    op.drop_index("ix_fes_flow_module_blog", "flow_execution_states")
    op.drop_column("flow_execution_states", "blog_id")
```

> **기존 FES 레코드 처리**: blog_id=NULL인 기존 레코드는 유지. Phase D 이후 신규 생성되는 FES는 항상 blog_id가 설정되며, `_get_or_create_blog_fes()` 헬퍼가 blog_id를 필수 인자로 받는다.

---

## 파일 6: __init__.py 수정

### 경로: `app/services/generation/__init__.py` (75줄 → ~83줄)

```python
# Phase D
from .warmup_manager import WarmupManager, WarmupStatus
from .publisher import Publisher

__all__ = [
    # ... 기존 유지 ...
    # Phase D
    "WarmupManager",
    "WarmupStatus",
    "Publisher",
]
```

---

## 파일 7: fixtures 업데이트

### 경로: `tests/fixtures/generation_pipeline_fixtures.py` (+40줄)

**추가할 팩토리 함수:**

```python
def create_mock_warmup_status(
    is_active: bool = False,
    days_elapsed: int = 0,
    daily_max: int = 3,
    today_published: int = 0,
    can_publish: bool = True,
    effective_interval: Optional[int] = None,
) -> WarmupStatus:
    """WarmupStatus Mock 팩토리"""

def create_mock_fes(
    flow_id: int = 1,
    module_id: int = 1,
    blog_id: Optional[int] = None,
    last_executed_at: Optional[datetime] = None,
    next_execution_at: Optional[datetime] = None,
    is_paused: bool = False,
) -> MagicMock:
    """FlowExecutionState Mock 팩토리"""

def create_warmup_settings(
    enabled: bool = True,
    warmup_days: int = 14,
    initial_daily_posts: int = 1,
    max_daily_posts: int = 3,
    ramp_rate: float = 0.5,
) -> dict:
    """warmup 설정 dict 팩토리"""
```

---

## 파일 8: 테스트

### 경로: `tests/integration/test_phase_d_publish_warmup.py` (신규, ~350줄)

### 테스트 목록 (26개)

#### 클래스 1: TestWarmupDetection (워밍업 대상 판단 - 5개)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T01 | `test_no_publish_history_is_warmup_target` | 발행 이력 0건 블로그 | is_active=True, days_elapsed=-1 |
| T02 | `test_within_warmup_days` | 첫 발행 후 3일 경과, warmup_days=14 | is_active=True, days_elapsed=3 |
| T03 | `test_warmup_completed` | 첫 발행 후 15일 경과, warmup_days=14 | is_active=False |
| T04 | `test_warmup_disabled` | warmup.enabled=false | is_active=False |
| T05 | `test_warmup_settings_missing` | warmup 설정 없음 (빈 dict) | is_active=False |

#### 클래스 2: TestRampRateCalculation (ramp_rate 계산 - 5개)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T06 | `test_day_0_initial_daily_posts` | Day 0, initial=1, ramp_rate=0.5 | daily_max=1 |
| T07 | `test_day_2_increment` | Day 2, initial=1, ramp_rate=0.5 | daily_max=2 |
| T08 | `test_max_daily_posts_cap` | Day 4+, initial=1, max=3, ramp_rate=0.5 | daily_max=3 |
| T09 | `test_warmup_publish_interval` | daily_max=1, active_hours=16 | effective_interval=960 |
| T10 | `test_warmup_interval_with_different_active_hours` | daily_max=3, active_hours=12 | effective_interval=240 |

#### 클래스 3: TestPublishGPContext (publish GP 연동 - 4개)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T11 | `test_publish_enabled_executes` | publish.enabled=true | 발행 실행됨 |
| T12 | `test_publish_disabled_skips` | publish.enabled=false | 스킵 + 로그 |
| T13 | `test_stage_mapping_correct` | rapid_growth vs stable | 각 스테이지 publish 설정 올바름 |
| T14 | `test_publish_without_gp_rejected` | GP 없이 publish 모듈 | 실행 거부 |

#### 클래스 4: TestPublisherService (Publisher 서비스 - 4개)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T15 | `test_publish_with_inventory` | 재고 있음, 워밍업 비활성 | 정상 발행 |
| T16 | `test_publish_no_inventory_skips` | 재고 0 (발행할 글 없음) | skipped=True |
| T17 | `test_warmup_daily_max_exceeded_skips` | 워밍업 활성, can_publish=false | skipped=True, "일일 한도 초과" |
| T18 | `test_publish_returns_inventory_check` | 발행 완료 후 | inventory_check 포함 결과 반환 |

#### 클래스 5: TestFESIntervalCheck (FES 간격 체크 - 5개)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T19 | `test_interval_elapsed_allows_execution` | next_execution_at 경과 | True (실행 허용) |
| T20 | `test_interval_not_elapsed_blocks` | next_execution_at 미경과 | False (실행 차단) |
| T21 | `test_blog_id_independent_tracking` | 같은 모듈, 다른 blog_id | 각자 독립 FES |
| T22 | `test_jitter_applied_in_range` | jitter enabled, min=-20, max=30 | next_execution_at이 [0.8x, 1.3x] 범위 |
| T23 | `test_first_execution_immediate` | FES 없음 (next_execution_at=None) | True (즉시 실행) |

#### 클래스 6: TestWarmupGenerateNonInterference (워밍업 generate 비간섭 - 3개)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T24 | `test_generate_unaffected_during_warmup` | 워밍업 활성 블로그 | generate는 스테이지 설정대로 동작 |
| T25 | `test_republish_unaffected_during_warmup` | 워밍업 활성 블로그 | republish는 워밍업과 무관 |
| T26 | `test_warmup_end_transitions_to_stage` | warmup_days 경과 직후 | publish가 스테이지 interval로 전환 |

---

## FES 간격 체크 아키텍처

### 현재 상태 (Phase C 완료 후)

```
flows_execute.py의 모듈별 블록:
  republish: GP enabled 체크만 구현 (FES 없음, 매 실행마다 재발행)
  prompt:    GP enabled + inventory 기반 트리거 (FES 없음)
  publish:   미구현
```

### Phase D 이후 상태

```
flows_execute.py의 모듈별 블록:
  publish:   GP enabled 체크 + FES 간격 체크 + 워밍업 (Phase D 신규)
  republish: GP enabled 체크 + FES 간격 체크 (Phase D FES 보강)
  prompt:    GP enabled + inventory 기반 트리거 (변경 없음)
```

### generate 블록 FES 미적용 이유

1. **inventory 기반 자연 제한**: `min_inventory` 조건으로 재고 충분하면 생성이 자동 정지되므로, 시간 기반 interval 없이도 빈도가 적절히 제한됨
2. **내부 동작**: 생성은 시스템 내부 동작이므로 플랫폼 탐지 리스크 없음
3. **기존 로직 안정성**: FlowGenerateExecutor + InventoryTrigger가 이미 안정적으로 동작 중
4. **별도 Phase에서 추가 가능**: generate에도 FES interval이 필요하면 동일 패턴으로 쉽게 추가 가능

### 기존 NOTE 제거

`flows_execute.py` 675~677줄의 기존 연기 NOTE를 제거:

```python
# 제거 대상:
# NOTE: Step 0의 (3) "간격 판단" (interval_mode 기반 마지막 실행 이후 경과 체크)은
# FES(FlowExecutionState) 블로그 레벨 확장이 필요하여 Phase C/D로 연기.
# interval_mode/computed_interval 값은 StageParams에 포함되어 있으나 아직 사용하지 않음.
```

→ Phase D에서 FES 간격 체크를 구현하므로, 이 NOTE는 삭제하고 실제 구현으로 대체.

---

## 구현 순서

```
1. flow_execution_state.py (모델)      (독립, blog_id 컬럼 추가)
2. Alembic 022 마이그레이션             (1에 의존)
3. warmup_manager.py (신규)            (독립, 순수 로직)
4. publisher.py (신규)                 (3에 의존, InventoryManager 연동)
5. flows_execute.py 수정               (1, 3, 4에 의존, publish 디스패치 + FES 간격)
6. __init__.py 수정                    (3, 4에 의존)
7. fixtures 업데이트                    (3, 4에 의존)
8. 테스트 작성 및 실행                   (1~6 완료 후)
```

**병렬 구현 가능:**
- 1, 3은 독립적이므로 병렬 구현 가능
- 2는 1 완료 후
- 4는 3 완료 후
- 5는 1, 3, 4 완료 후

---

## 완료 기준 체크리스트

### 작업계획서 Section 10 Phase D 기준

- [ ] publish 모듈이 Growth Profile의 `publish.enabled`를 올바르게 참조하여 발행을 제어하는지 검증
- [ ] publish 모듈이 `publish.interval_mode` / `publish.computed_interval`에 따라 간격이 올바르게 적용되는지 검증
- [ ] **워밍업 대상 판단**: 발행 이력 0건인 블로그가 올바르게 워밍업 대상으로 식별되는지 검증
- [ ] **ramp_rate 계산**: 경과일에 따라 일일 허용 발행 수가 올바르게 증가하는지 검증
- [ ] **워밍업 기간 중 publish 간격**: 워밍업 daily_max 기반 간격이 스테이지 설정을 올바르게 대체하는지 검증
- [ ] **워밍업 종료 시점**: warmup_days 경과 후 스테이지 설정으로 자연 전환되는지 검증
- [ ] **generate 비간섭**: 워밍업 기간 중에도 generate가 스테이지 설정대로 정상 동작하는지 검증

### Phase C 연기분

- [ ] FES에 `blog_id` 컬럼이 추가되었는지 확인
- [ ] FES `(flow_id, module_id, blog_id)` 복합 unique 인덱스 생성 확인
- [ ] Alembic 022 마이그레이션 파일 생성 완료 (upgrade/downgrade 양방향)
- [ ] publish 블록에서 FES 간격 체크가 동작하는지 검증 (간격 경과/미경과)
- [ ] republish 블록에서 FES 간격 체크가 동작하는지 검증 (Phase C 보강)
- [ ] 같은 모듈의 다른 blog_id가 독립된 FES로 추적되는지 검증

### 코드 품질

- [ ] 각 파일 500줄 미만 확인 (flows_execute.py 예외 - W6 결정)
- [ ] 각 함수 50줄 미만 확인
- [ ] 타입 힌트 전수 적용
- [ ] Docstring 전수 작성
- [ ] 테스트 26개 작성 및 전체 통과
- [ ] Phase A 테스트 (30개) 영향 없음 확인
- [ ] Phase B 테스트 (27개) 영향 없음 확인
- [ ] Phase C 테스트 (25개) 영향 없음 확인
