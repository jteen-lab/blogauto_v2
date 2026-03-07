# Growth Profile - Phase C 구현 프롬프트

> **Phase**: C (재발행 연동 - GP 기반 필터링 + 레거시 컬럼 정리)
> **설계 문서**: growth_stage_strategy_plan.md v3.1
> **선행 Phase**: B (완료 - Flow 실행 연동 스케줄러 통합)
> **선행 작업**: Phase M (데이터 마이그레이션) - Phase C 실행 전 반드시 완료
> **작성일**: 2026-02-21
> **상태**: 구현 대기

---

## 개요

Phase C는 Phase B에서 생성(prompt) 모듈에 적용한 GP 연동 패턴을 **재발행(republish) 모듈**에 동일하게 적용하고,
Growth Profile로 완전 대체된 레거시 컬럼(`post_range_start`, `post_range_end`)을 코드와 DB에서 제거하는 단계입니다.

**핵심 목표:**
1. republish 실행부에서 GP `republish.enabled` 체크 (Phase B의 prompt 패턴 재사용)
2. `post_range_start/end` 기반 블로그 필터링 → GP 스테이지 기반으로 완전 전환
3. `Module.post_range_start`, `Module.post_range_end` 컬럼을 코드/DB에서 제거
4. `Module.calculated_interval_minutes` 프로퍼티 제거 (GP `computed_interval`로 대체)
5. 스키마/서비스에서 post_range 관련 로직 정리

> **`republish.interval_mode` 참고**: Phase B에서 `generate.interval_mode`와 마찬가지로,
> `StageParams.republish.interval_mode`과 `republish.computed_interval`에 이미 값이 들어있으나,
> 간격 기반 실행 판단(마지막 실행으로부터 interval 경과 체크)은 FES 블로그 레벨 확장이 필요합니다.
> Phase C에서는 `republish.enabled` 체크와 post_range 대체에 집중하며,
> 실제 interval 경과 체크 로직은 FES 확장과 함께 Phase D에서 구현합니다.

**Phase C에서 DB 변경이 있습니다.** Alembic 마이그레이션으로 `post_range_start`, `post_range_end` 컬럼 제거.

> **주의: Phase M (데이터 마이그레이션)이 반드시 Phase C 전에 완료되어야 합니다.**
> Phase M에서 기존 post_range 기반 모듈 데이터를 Growth Profile stages로 변환합니다.
> Phase C는 이미 마이그레이션이 완료되었다고 가정하고 레거시 컬럼을 제거합니다.
> 작업 순서: A → B → M → C → D → E (작업계획서 Section 10 전체 일정 참조)

> **주의: `flows_execute.py`는 현재 1,324줄입니다.** post_range 필터링 제거(-50줄)와 GP 체크 추가(+20줄)로
> 약 1,294줄 예상. 500줄 제한 초과이지만, 사용자 결정(W6, W10)에 따라 별도 리팩토링에서 처리.

---

## 생성/수정 파일 목록

| # | 파일 경로 | 타입 | 변경량 | 설명 |
|---|----------|------|--------|------|
| 1 | `app/routers/flows_execute.py` | 수정 | +20줄, -50줄 | republish 블록 GP 연동 + post_range 필터링 제거 |
| 2 | `app/models/module.py` | 수정 | -9줄 | post_range_start/end 컬럼 + calculated_interval_minutes 프로퍼티 제거 |
| 3 | `app/schemas/module.py` | 수정 | -20줄 | post_range 필드 + validate_post_range 제거 |
| 4 | `app/services/module_service.py` | 수정 | 변경 | post_range 관련 할당 로직 정리 |
| 5 | `alembic/versions/NNN_remove_post_range_columns.py` | 신규 | ~30줄 | DB 컬럼 제거 마이그레이션 |
| 6 | `tests/integration/test_phase_c_republish_gp.py` | 신규 | ~350줄 | 테스트 25개 |

---

## Phase A/B 완성 파일 (참조용, 수정하지 않음)

| 파일 | import 대상 / 참조 사항 |
|------|----------------------|
| `app/services/generation/flow_execution_context.py` | `FlowExecutionContext`, `StageParams`, `ModuleIntervalParams` |
| `app/services/generation/growth_profile_resolver.py` | `GrowthProfileResolver` (Phase C에서 직접 사용 안 함) |
| `app/services/generation/flow_generate_executor.py` | Phase B에서 prompt 모듈에 적용한 GP 연동 패턴 참조 |
| `app/services/generation/inventory_trigger.py` | Phase C에서 직접 사용 안 함 |

---

## 파일 1: flows_execute.py 수정

### 경로: `app/routers/flows_execute.py`
### 변경 개요: republish 블록을 GP 컨텍스트 기반으로 변경 + post_range 필터링 제거

### 설계 출처: 작업계획서 Section 6-1 Step 5 (republish 실행), Section 10 Phase C

### 1-1. republish 블록 변경 (라인 327~430)

Phase B에서 prompt 모듈에 적용한 것과 동일한 패턴으로 변경합니다.
핵심: `post_range_start/end` 기반 필터링을 **완전 제거**하고, GP 컨텍스트 기반으로 교체합니다.

**변경 전** (현재 코드, 라인 327~430):

```python
            # 7. republish 모듈 실행 (블로그 필수, 모듈별 포스트 범위 필터링)
            if "republish" in modules_by_type:
                if not blogs:
                    logger.warning(f"[FLOW_BG] 재발행 모듈이 있지만 블로그가 없음: {flow_id}")
                    for republish_module in modules_by_type["republish"]:
                        fail_count += 1
                        total_processed += 1
                        await _save_autorun_log(...)
                else:
                    # 각 재발행 모듈별로 해당 포스트 범위의 블로그만 실행
                    for republish_module in modules_by_type["republish"]:
                        # 모듈의 직접 속성에서 포스트 범위 가져오기 (settings가 아님)
                        post_range_start = republish_module.post_range_start
                        post_range_end = republish_module.post_range_end

                        logger.info(
                            f"[FLOW_BG] 재발행 모듈: {republish_module.name} | "
                            f"범위: {post_range_start}~{post_range_end if post_range_end else '무제한'}"
                        )

                        # 블로그 필터링: 포스트 범위에 해당하는 블로그만 선택
                        filtered_blogs = []
                        for blog in blogs:
                            post_count = blog.total_post_count or 0
                            if post_range_end is None:
                                if post_count >= post_range_start:
                                    filtered_blogs.append(blog)
                            else:
                                if post_range_start <= post_count <= post_range_end:
                                    filtered_blogs.append(blog)

                        if not filtered_blogs:
                            logger.info(f"[FLOW_BG] 모듈 '{republish_module.name}'에 해당하는 블로그 없음")
                            continue

                        for blog in filtered_blogs:
                            result = await _execute_republish_for_blog(blog)
                            ...
```

**변경 후**:

```python
            # 7. republish 모듈 실행 (GP 컨텍스트 기반 재발행)
            if "republish" in modules_by_type:
                if not blogs:
                    logger.warning(f"[FLOW_BG] 재발행 모듈이 있지만 블로그가 없음: {flow_id}")
                    for republish_module in modules_by_type["republish"]:
                        fail_count += 1
                        total_processed += 1
                        await _save_autorun_log(
                            db=db,
                            user_id=user_id,
                            flow_id=flow.id,
                            flow_name=flow.name,
                            module_name=republish_module.name,
                            blog_name="-",
                            result={"success": False, "message": "플로우에 연결된 블로그가 없습니다"},
                            duration_ms=0,
                            action="republish"
                        )
                else:
                    for republish_module in modules_by_type["republish"]:
                        logger.info(f"[FLOW_BG] 재발행 모듈 실행: {republish_module.name}")

                        for blog in blogs:
                            # GP 컨텍스트에서 블로그별 StageParams 조회
                            stage_params = gp_context.get_stage_for_blog(blog.id)

                            # republish.enabled 체크
                            if stage_params and not stage_params.republish.enabled:
                                logger.info(
                                    f"[FLOW_BG] 재발행 비활성 | blog={blog.name} | "
                                    f"stage={stage_params.stage_name}"
                                )
                                total_processed += 1
                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=republish_module.name,
                                    blog_name=blog.name,
                                    result={
                                        "success": True,
                                        "skipped": True,
                                        "message": f"재발행 비활성 (stage: {stage_params.stage_name})",
                                    },
                                    duration_ms=0,
                                    action="republish"
                                )
                                continue

                            blog_start_time = datetime.now()
                            logger.info(
                                f"[FLOW_BG] 재발행 처리: {blog.name} | "
                                f"module={republish_module.name} | "
                                f"stage={stage_params.stage_name if stage_params else 'unknown'}"
                            )

                            try:
                                result = await _execute_republish_for_blog(blog)
                                blog_duration_ms = int(
                                    (datetime.now() - blog_start_time).total_seconds() * 1000
                                )

                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=republish_module.name,
                                    blog_name=blog.name,
                                    result=result,
                                    duration_ms=blog_duration_ms,
                                    action="republish"
                                )

                                if result.get("success"):
                                    success_count += 1
                                    logger.info(f"[FLOW_BG] 재발행 성공 | blog={blog.name}")
                                else:
                                    fail_count += 1
                                    logger.warning(f"[FLOW_BG] 재발행 실패 | blog={blog.name}")

                                total_processed += 1

                            except Exception as e:
                                fail_count += 1
                                total_processed += 1
                                blog_duration_ms = int(
                                    (datetime.now() - blog_start_time).total_seconds() * 1000
                                )
                                logger.error(
                                    f"[FLOW_BG] 재발행 오류 | blog={blog.name} | error={e}"
                                )

                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=republish_module.name,
                                    blog_name=blog.name,
                                    result={"success": False, "message": str(e)},
                                    duration_ms=blog_duration_ms,
                                    action="republish"
                                )
```

**핵심 변경 3가지:**
1. `post_range_start/end` 기반 블로그 필터링 로직 **전체 제거** (~30줄 삭제)
2. `gp_context.get_stage_for_blog(blog.id)` → `stage_params.republish.enabled` 체크 추가
3. `republish.enabled=false` 시 즉시 스킵 + autorun_log에 스킵 사유 기록

> **post_range 대체 원리**: 기존 `post_range_start/end`로 하던 블로그 필터링은
> GP Step 0 (`_build_growth_profile_context()`)에서 이미 수행됩니다.
> Step 0은 각 블로그의 `total_post_count`를 기반으로 GP stages에서 매칭되는 스테이지를 결정하고,
> 해당 스테이지의 `republish.enabled`가 `false`이면 스킵합니다.
> GP의 `stages[n].post_count_min/max`가 기존 `post_range_start/end`와 동일한 역할을 하므로,
> 별도의 post_range 필터링이 불필요합니다.

---

## 파일 2: module.py 수정

### 경로: `app/models/module.py`
### 변경 개요: post_range 컬럼 제거 + calculated_interval_minutes 프로퍼티 제거

### 설계 출처: 작업계획서 Section 7-4, Section 10 Phase C

### 2-1. post_range 컬럼 제거 (라인 42~43)

**제거할 코드:**

```python
    post_range_start = Column(Integer, default=1, comment="포스트 범위 시작")
    post_range_end = Column(Integer, nullable=True, comment="포스트 범위 끝")
```

### 2-2. calculated_interval_minutes 프로퍼티 제거 (라인 83~89)

**제거할 코드:**

```python
    @property
    def calculated_interval_minutes(self) -> int:
        """자동 모드일 때 간격 계산"""
        if self.interval_mode == "auto" and self.auto_daily_count:
            # 24시간 = 1440분 / 일일 목표 횟수
            return max(5, int(1440 / self.auto_daily_count))
        return self.manual_interval_minutes or 60
```

> **`calculated_interval_minutes` 제거 사유**: GP의 `ModuleIntervalParams.computed_interval`이 이 계산을 대체합니다.
> 또한 기존 계산식에 버그가 있습니다: 24시간 고정(`1440 / daily_count`)이지만,
> 실제로는 활성 시간 기반(`active_hours * 60 / daily_count`)이어야 합니다.
> GP의 `ModuleIntervalParams.from_stage_dict()`가 활성 시간 기반으로 올바르게 계산합니다
> (작업계획서 Section 10 Phase A 참조).

> **주의**: `interval_mode`, `auto_daily_count`, `manual_interval_minutes`, `schedule_matrix`,
> `jitter_*`, `active_hours_*`, `blackout_days`, `cooldown_days`, `min_post_count` 등
> 기타 레거시 컬럼은 **Phase C에서 제거하지 않습니다**.
> 이 컬럼들은 현재 UI(Phase E)와 autorun 엔진에서 사용 중이며,
> Phase E(UI) 및 autorun 엔진 리팩토링 이후 별도 정리합니다.
>
> **전략 문서 완료 기준 범위 조정 (라인 1219)**:
> 전략 문서의 Phase C 완료 기준 중 *"기존 재발행 모듈의 자체 스케줄러 관련 코드가 제거되었는지 확인"*은
> Phase C에서 **`post_range_start/end` 컬럼 + `calculated_interval_minutes` 프로퍼티 제거**에 한정합니다.
> `Module.settings`의 `interval_mode`, `schedule_matrix` 등 설정 레벨 코드는
> Phase E(UI 연동) 및 autorun 엔진 리팩토링 시 처리합니다.

---

## 파일 3: module.py (스키마) 수정

### 경로: `app/schemas/module.py`
### 변경 개요: post_range 필드 및 validator 제거

### 3-1. ModuleCreateRequest에서 제거 (라인 50~51)

**제거할 코드:**

```python
    post_range_start: int = Field(1, ge=1, description="포스트 범위 시작")
    post_range_end: Optional[int] = Field(None, ge=1, description="포스트 범위 끝")
```

### 3-2. validate_post_range validator 제거 (라인 75~82)

**제거할 코드:**

```python
    @field_validator("post_range_end")
    @classmethod
    def validate_post_range(cls, v, info):
        """포스트 범위 유효성 검사"""
        if v is not None and "post_range_start" in info.data:
            if v <= info.data["post_range_start"]:
                raise ValueError("post_range_end must be greater than post_range_start")
        return v
```

### 3-3. ModuleUpdateRequest에서 제거 (라인 110~111)

**제거할 코드:**

```python
    post_range_start: Optional[int] = Field(None, ge=1)
    post_range_end: Optional[int] = Field(None, ge=1)
```

---

## 파일 4: module_service.py 수정

### 경로: `app/services/module_service.py`
### 변경 개요: post_range 관련 할당 로직 정리

`module_service.py`에서 `post_range_start`, `post_range_end` 값을 Module에 할당하는 코드를 제거합니다.

**검색 대상**: `module_service.py` 내에서 `post_range_start` 또는 `post_range_end`를 참조하는 모든 라인을 찾아 제거합니다.

> **주의**: Module CRUD 로직의 전체 구조는 유지합니다. post_range 관련 할당 라인만 정확히 제거하세요.
> 모듈 생성/수정 메서드에서 `post_range_start`와 `post_range_end`를 Module 인스턴스에 설정하는 코드가 대상입니다.

---

## 파일 5: Alembic 마이그레이션

### 경로: `alembic/versions/NNN_remove_post_range_columns.py` (신규)
### 예상 줄 수: ~30줄

### 설계 출처: 작업계획서 Section 10 Phase C

```python
"""post_range_start, post_range_end 컬럼 제거

Growth Profile의 stages.post_count_min/max로 완전 대체.
Phase M에서 기존 데이터 마이그레이션 완료 후 실행.

Revision ID: [auto-generated]
Revises: [이전 revision]
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    op.drop_column("modules", "post_range_start")
    op.drop_column("modules", "post_range_end")


def downgrade():
    op.add_column(
        "modules",
        sa.Column("post_range_start", sa.Integer(), server_default="1", nullable=True)
    )
    op.add_column(
        "modules",
        sa.Column("post_range_end", sa.Integer(), nullable=True)
    )
```

> **주의**: 이 마이그레이션은 Phase M (데이터 마이그레이션) 완료 후에만 실행해야 합니다.
> Phase M에서 기존 post_range 데이터가 Growth Profile stages로 변환되었음이 확인된 후 적용합니다.

> **Alembic revision 생성**: 실제 구현 시 `alembic revision --autogenerate -m "remove post_range columns"` 명령으로
> revision ID와 depends_on을 자동 생성하세요.

---

## 파일 6: 테스트

### 경로: `tests/integration/test_phase_c_republish_gp.py`
### 예상 줄 수: ~350줄

### 테스트 목록 (25개)

#### 클래스 1: TestRepublishGPContext (재발행 GP 연동 - 6개)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T01 | `test_republish_enabled_true_runs` | republish.enabled=true인 블로그 | `_execute_republish_for_blog()` 호출됨 |
| T02 | `test_republish_enabled_false_skips` | republish.enabled=false인 블로그 | 재발행 스킵, autorun_log에 `skipped=True` 기록 |
| T03 | `test_multiple_blogs_different_stages` | Blog A(30글=rapid_growth), Blog B(200글=stable, republish 비활성) | A만 재발행, B는 스킵 |
| T04 | `test_stage_params_none_runs_default` | stage_params=None (컨텍스트에 없는 블로그) | 기본 동작 (재발행 실행) |
| T05 | `test_all_blogs_disabled_no_execution` | 모든 블로그 republish.enabled=false | `_execute_republish_for_blog()` 호출 0회 |
| T06 | `test_skipped_blog_logged_to_autorun` | republish.enabled=false | `_save_autorun_log()`에 `skipped=True`, `message`에 stage명 포함 |

#### 클래스 2: TestRepublishPostRangeRemoval (post_range 제거 확인 - 4개)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T07 | `test_module_no_post_range_start_attr` | Module 인스턴스 | `hasattr(module, 'post_range_start')` is False |
| T08 | `test_module_no_post_range_end_attr` | Module 인스턴스 | `hasattr(module, 'post_range_end')` is False |
| T09 | `test_create_schema_no_post_range` | ModuleCreateRequest 필드 목록 | `post_range_start`/`post_range_end` 없음 |
| T10 | `test_update_schema_no_post_range` | ModuleUpdateRequest 필드 목록 | `post_range_start`/`post_range_end` 없음 |

#### 클래스 3: TestRepublishStageMapping (스테이지 매핑 - 5개)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T11 | `test_rapid_growth_republish_enabled` | 급성장기(0~50) + republish.enabled=true | 재발행 실행 |
| T12 | `test_stable_publish_disabled_republish_enabled` | 안정기 + publish.enabled=false + republish.enabled=true | 재발행 정상 실행 (publish와 독립) |
| T13 | `test_seed_stage_republish_disabled` | 시드기(0~30) + republish.enabled=false | 재발행 스킵 |
| T14 | `test_boundary_50_rapid_growth` | 50글 블로그, rapid_growth max=50 | rapid_growth 스테이지 적용 (inclusive, Q3 규칙) |
| T15 | `test_boundary_51_growth` | 51글 블로그, growth min=51 | growth 스테이지 적용 |

#### 클래스 4: TestRepublishIntervalParams (간격 파라미터 확인 - 4개)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T16 | `test_interval_mode_available` | stage_params.republish | `interval_mode`에 `"auto"` 또는 `"manual"` 값 존재 |
| T17 | `test_computed_interval_auto_mode` | interval_mode="auto", daily_count=3, 활성 16시간 | `computed_interval` = 320분 (`960 / 3`) |
| T18 | `test_computed_interval_manual_mode` | interval_mode="manual", interval_minutes=120 | `computed_interval` = 120분 |
| T19 | `test_disabled_stage_no_interval` | republish.enabled=false | `interval_mode=None`, `computed_interval=None` |

#### 클래스 5: TestCalculatedIntervalRemoval (프로퍼티 제거 확인 - 1개)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T20 | `test_module_no_calculated_interval_property` | Module 인스턴스 | `hasattr(module, 'calculated_interval_minutes')` is False |

#### 클래스 6: TestRepublishEdgeCases (엣지 케이스 - 5개)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T21 | `test_single_stage_all_blogs_same` | 단일 구간 GP (0~null) + republish.enabled=true | 모든 블로그에 동일 republish 설정 적용 |
| T22 | `test_blog_not_in_context` | blog_id가 blog_stages에 없음 | stage_params=None, 기본 동작 (재발행 실행) |
| T23 | `test_republish_success_counted` | 재발행 성공 | success_count 증가 |
| T24 | `test_republish_failure_counted` | 재발행 실패 (예외 발생) | fail_count 증가, 에러 로그 기록 |
| T25 | `test_mixed_enabled_disabled_blogs` | Blog A enabled, Blog B disabled, Blog C enabled | A, C만 실행, B는 스킵, 총 2회 실행 |

### 테스트 실행 명령

```bash
cd /home/jteen/blogauto_v2/services/republish

# Phase C 테스트만
python3 -m pytest tests/integration/test_phase_c_republish_gp.py -v

# Phase A+B+C 전체 (기존 테스트 영향 없음 확인)
python3 -m pytest tests/integration/test_growth_profile_resolver.py tests/integration/test_phase_b_flow_execution.py tests/integration/test_phase_c_republish_gp.py -v
```

---

## post_range 참조 파일 정리 범위

### Phase C 범위 (백엔드 핵심)

| 파일 | 참조 위치 | Phase C 처리 |
|------|---------|------------|
| `app/routers/flows_execute.py` | 라인 349-376 (post_range 필터링) | GP 기반으로 완전 대체 (파일 1) |
| `app/models/module.py` | 라인 42-43 (컬럼 정의) | 컬럼 제거 (파일 2) |
| `app/schemas/module.py` | 라인 50-51, 75-82, 110-111 | 필드/validator 제거 (파일 3) |
| `app/services/module_service.py` | CRUD 할당 로직 | post_range 할당 제거 (파일 4) |

### Phase C 범위 밖 (별도 정리)

| 파일 | 사유 |
|------|------|
| `app/static/js/modules/form.js` | Phase E (UI) |
| `app/static/js/modules/list.js` | Phase E (UI) |
| `app/static/js/flows/form.js` | Phase E (UI) |
| `app/static/js/flows/list.js` | Phase E (UI) |
| `app/static/js/autorun/main.js` | Phase E (UI) |
| `app/templates/modules/_form.html` | Phase E (UI) |
| `app/templates/groups/form.html` | Phase E (UI) |
| `app/engine/republish_orchestrator.py` | autorun 엔진 리팩토링 시 처리 |
| `app/engine/branching_orchestrator.py` | autorun 엔진 리팩토링 시 처리 |
| `app/engine/flow_engine.py` | autorun 엔진 리팩토링 시 처리 |
| `app/engine/execution_context.py` | autorun 엔진 리팩토링 시 처리 |
| `app/scheduler/flow_scheduler.py` | autorun 엔진 리팩토링 시 처리 |
| `app/services/autorun_service.py` | autorun 엔진 리팩토링 시 처리 |
| `scripts/debug_run.py` | 디버그 스크립트, 사용 시 수정 |
| `scripts/migrate_to_module_flow.py` | 과거 마이그레이션, 수정 불필요 |
| `alembic/versions/001_*.py` | 과거 마이그레이션, 수정 불필요 |
| `tests/test_branching_orchestrator.py` | autorun 엔진 테스트, 별도 정리 |
| `tests/test_helpers/context_mock.py` | 테스트 헬퍼, 별도 정리 |

> **참고**: `app/engine/` 디렉토리의 파일들은 autorun(자동 실행) 시스템으로,
> `_execute_flow_background()`와는 별도의 실행 경로입니다.
> Phase C는 `_execute_flow_background()` 경로에 집중합니다.
> engine 파일들의 post_range 참조는 autorun 엔진 리팩토링 시 일괄 정리합니다.
>
> **런타임 영향**: Phase C에서 `Module.post_range_start/end` 컬럼이 DB에서 제거되면,
> engine 파일들이 이 속성에 접근할 때 `AttributeError`가 발생합니다.
> 현재 autorun 엔진은 비활성 상태(`app/scheduler/republish_job.py` 라인 14 참조)이므로
> 즉시 영향은 없지만, autorun 활성화 전에 engine 파일 정리가 필요합니다.

---

## FES 간격 판단 구현 현황

### 현재 상황

Phase B에서 생성 모듈의 `interval_mode`/`computed_interval` 값이 StageParams에 포함되어
올바르게 전달됨을 검증했습니다 (테스트 T19b). 동일하게 republish의 `interval_mode`/`computed_interval`도
이미 `StageParams.republish` 객체에 포함되어 있습니다.

현재 `FlowExecutionState` 모델(`app/models/flow_execution_state.py`)은 `(flow_id, module_id)` 단위로 추적합니다.
GP는 블로그별로 다른 간격이 적용되므로, `(flow_id, module_id, blog_id)` 레벨 추적이 필요합니다.

### Phase C 결정

**FES 블로그 레벨 확장 + 간격 경과 체크는 Phase C 범위 밖입니다.**

이유:
1. FES에 `blog_id` 컬럼을 추가하면 Alembic 마이그레이션 + 기존 FES 로직 변경이 필요
2. 현재 `_execute_flow_background()`는 FES 없이 동작 (수동 실행 경로)
3. FES 확장은 생성/발행/재발행 **3개 모듈 모두**에 적용되므로, Phase D에서 통합 구현이 효율적
4. Phase C는 "GP 기반 enabled 체크 + post_range 대체 + 레거시 컬럼 정리"에 집중

**Phase C에서는 매 실행마다** `republish.enabled=true`인 모든 블로그에 대해 재발행을 실행합니다.
interval 경과 체크(마지막 실행 이후 충분한 시간이 지났는지)는 Phase D에서 FES 확장과 함께 구현합니다.

Phase C에서 구현하는 테스트 T16~T19는 `StageParams.republish`에 interval 관련 값이
**올바르게 포함**되어 있는지만 검증합니다. 실제 간격 판단 로직은 검증하지 않습니다.

---

## 구현 순서

```
1. module.py (모델) 수정              (독립, 컬럼 + 프로퍼티 제거)
2. module.py (스키마) 수정            (독립, 필드 + validator 제거)
3. module_service.py 수정             (1, 2에 의존, post_range 할당 제거)
4. flows_execute.py 수정              (독립, GP republish 블록)
5. Alembic 마이그레이션 생성           (1에 의존, DB 컬럼 제거)
6. 테스트 작성 및 실행                  (1~4 완료 후)
```

**1, 2, 4는 병렬 구현 가능.**

---

## 완료 기준 체크리스트 (작업계획서 Section 10 Phase C 기준)

- [ ] `republish.enabled=true`인 구간에서만 재발행이 실행되는지 검증
- [ ] `republish.enabled=false`인 구간에서 재발행이 실행되지 않는지 검증 (스킵 로그 확인)
- [ ] GP StageParams의 `republish.interval_mode`, `republish.computed_interval`이 올바르게 포함되어 있는지 검증 (실제 사용은 Phase D)
- [ ] post_range 기반 블로그 필터링이 `flows_execute.py`에서 완전히 제거되었는지 확인
- [ ] **`Module.post_range_start`/`post_range_end` 컬럼이 모델 코드에서 제거되었는지 확인**
- [ ] **`Module.calculated_interval_minutes` 프로퍼티가 제거되었는지 확인**
- [ ] 스키마 `ModuleCreateRequest`에서 post_range 필드가 제거되었는지 확인
- [ ] 스키마 `ModuleUpdateRequest`에서 post_range 필드가 제거되었는지 확인
- [ ] `validate_post_range` validator가 제거되었는지 확인
- [ ] `module_service.py`에서 post_range 할당 코드가 제거되었는지 확인
- [ ] Alembic 마이그레이션 파일 생성 완료 (upgrade/downgrade 양방향)
- [ ] 각 파일 500줄 미만 확인 (flows_execute.py 예외 - W6 결정)
- [ ] 각 함수 50줄 미만 확인
- [ ] 타입 힌트 전수 적용
- [ ] Docstring 전수 작성
- [ ] 테스트 25개 작성 및 전체 통과
- [ ] Phase A 테스트 (30개) 영향 없음 확인
- [ ] Phase B 테스트 (27개) 영향 없음 확인
