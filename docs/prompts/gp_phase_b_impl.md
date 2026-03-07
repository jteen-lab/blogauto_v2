# Growth Profile - Phase B 구현 프롬프트

> **Phase**: B (Flow 실행 연동 - 스케줄러 통합)
> **설계 문서**: growth_stage_strategy_plan.md v3.1
> **선행 Phase**: A (완료 - 기반 구조 코어)
> **작성일**: 2026-02-21
> **상태**: 구현 완료 (2026-02-21)

---

## 개요

Phase B는 Phase A에서 만든 코어 구조(`FlowExecutionContext`, `GrowthProfileResolver`)를
실제 Flow 실행 파이프라인(`flows_execute.py`)에 연동하는 단계입니다.

**핵심 목표:**
1. `_execute_flow_background()`에 **Step 0** 삽입: GP 로드 → 활성 시간 체크 → 컨텍스트 생성
2. prompt(생성) 모듈이 `FlowExecutionContext`에서 `generate.enabled` + `generate.min_inventory` + `generate.interval_mode`를 참조하도록 변경
3. GP 미설정 Flow 즉시 거부 (W4 결정)
4. GP 1-per-flow 중복 검증 (Q2 결정)

> **`generate.interval_mode` 참고**: `StageParams.generate.interval_mode`에 이미 값이 들어있으나,
> 간격 기반 실행 판단(마지막 실행으로부터 interval 경과 체크)은 FES 확장이 필요하여 Phase C/D로 연기됨.
> Phase B에서는 `interval_mode` 값이 **올바르게 전달**되는지 검증만 수행하고, 실제 간격 판단 로직은 구현하지 않음.

**Phase B에서 DB 변경이 없습니다.** Alembic 마이그레이션 불필요.

> **주의: `flows_execute.py`는 현재 529줄입니다.** GP 코드 추가 시 ~600줄 예상.
> 500줄 제한 초과이지만, 사용자 결정(W6, W10)에 따라 Phase B에서는 우선 추가 후 별도 리팩토링 진행.

---

## 생성/수정 파일 목록

| # | 파일 경로 | 타입 | 변경량 | 설명 |
|---|----------|------|--------|------|
| 1 | `app/routers/flows_execute.py` | 수정 | +60줄 | Step 0 삽입 + GP 미설정 거부 + prompt 블록 변경 |
| 2 | `app/services/generation/flow_generate_executor.py` | 수정 | +25줄 | StageParams 파라미터 추가 + generate.enabled 체크 |
| 3 | `app/services/generation/inventory_trigger.py` | 수정 | +10줄, -30줄 | GP 기반 임계값 + BGS 폴백 로직 제거 |
| 4 | `app/services/flow_service.py` | 수정 | +20줄 | GP 1-per-flow 중복 검증 |
| 5 | `tests/integration/test_phase_b_flow_execution.py` | 신규 | ~380줄 | 테스트 27개 |

---

## Phase A 완성 파일 (참조용, 수정하지 않음)

| 파일 | import 대상 |
|------|-----------|
| `app/services/generation/flow_execution_context.py` | `FlowExecutionContext`, `StageParams`, `ModuleIntervalParams` |
| `app/services/generation/growth_profile_resolver.py` | `GrowthProfileResolver` |
| `app/services/generation/growth_profile_defaults.py` | (Phase B에서 직접 사용 안 함) |

---

## 파일 1: flows_execute.py 수정

### 경로: `app/routers/flows_execute.py`
### 변경 개요: Step 0 삽입 + GP 미설정 거부 + prompt 블록 변경

### 1-1. import 추가 (파일 상단)

```python
# 기존 import 아래에 추가
from app.services.generation.growth_profile_resolver import GrowthProfileResolver
from app.services.generation.flow_execution_context import FlowExecutionContext
```

### 1-2. Step 0 삽입 위치

**정확한 위치**: `_execute_flow_background()` 내부, 라인 175 (모듈 타입별 그룹화 로그 출력) 이후, 라인 177 (결과 집계 변수 초기화) 이전.

현재 코드:
```python
            logger.info(f"[FLOW_BG] 모듈 타입별: {', '.join(f'{k}={len(v)}' for k, v in modules_by_type.items())}")

            # 4. 결과 집계 변수
            success_count = 0
```

변경 후:
```python
            logger.info(f"[FLOW_BG] 모듈 타입별: {', '.join(f'{k}={len(v)}' for k, v in modules_by_type.items())}")

            # ============================================================
            # Step 0: Growth Profile 스케줄러 (핵심 변경)
            # ============================================================
            gp_context = await _build_growth_profile_context(
                modules_by_type, blogs, flow
            )
            if gp_context is None:
                # GP 미설정 또는 비활성 시간 → Flow 실행 중단
                return

            # 4. 결과 집계 변수
            success_count = 0
```

### 1-3. `_build_growth_profile_context()` 헬퍼 함수 (신규)

`_execute_flow_background()` 함수 아래에 별도 함수로 추가합니다.

```python
async def _build_growth_profile_context(
    modules_by_type: Dict[str, List[Module]],
    blogs: list,
    flow: Flow,
) -> Optional[FlowExecutionContext]:
    """
    Growth Profile Step 0: GP 로드 + 활성 시간 체크 + 컨텍스트 생성

    Returns:
        FlowExecutionContext: 정상 진행 시
        None: GP 미설정 / 비활성 시간대 / 블로그 없음 → Flow 실행 중단

    설계 문서: growth_stage_strategy_plan.md - Section 6-1 Step 0
    """
    from datetime import datetime
    import pytz

    KST = pytz.timezone("Asia/Seoul")

    # (1) Growth Profile 모듈 존재 확인 (W4: 미설정 시 즉시 중단)
    if "growth_profile" not in modules_by_type:
        logger.error(
            f"[FLOW_BG] Growth Profile 미설정 | flow_id={flow.id} | "
            f"이 Flow에 Growth Profile이 설정되지 않았습니다"
        )
        return None

    gp_module = modules_by_type["growth_profile"][0]
    gp_settings = gp_module.settings or {}

    if not gp_settings.get("stages"):
        logger.error(
            f"[FLOW_BG] Growth Profile에 stages가 없습니다 | "
            f"flow_id={flow.id} | module_id={gp_module.id}"
        )
        return None

    # (2) schedule_matrix 활성 시간 체크
    schedule_matrix = gp_settings.get("schedule_matrix")
    if schedule_matrix:
        now_kst = datetime.now(KST)
        weekday = now_kst.weekday()  # 0=월, 6=일
        hour = now_kst.hour

        # 유효성 확인 후 체크
        if (
            isinstance(schedule_matrix, list)
            and len(schedule_matrix) == 7
            and isinstance(schedule_matrix[weekday], list)
            and len(schedule_matrix[weekday]) == 24
        ):
            if not schedule_matrix[weekday][hour]:
                logger.info(
                    f"[FLOW_BG] 비활성 시간대 | flow_id={flow.id} | "
                    f"weekday={weekday} | hour={hour} | Flow 실행 스킵"
                )
                return None

    # (3) 블로그별 포스트 수 매핑 생성
    if not blogs:
        logger.warning(
            f"[FLOW_BG] Growth Profile 있지만 블로그 없음 | flow_id={flow.id}"
        )
        return None

    blog_post_counts = {
        blog.id: (blog.total_post_count or 0) for blog in blogs
    }

    # (4) FlowExecutionContext 생성 (GrowthProfileResolver 호출)
    try:
        context = GrowthProfileResolver.build_execution_context(
            flow_id=flow.id,
            gp_settings=gp_settings,
            blog_post_counts=blog_post_counts,
        )
    except ValueError as e:
        logger.error(
            f"[FLOW_BG] Growth Profile 컨텍스트 생성 실패 | "
            f"flow_id={flow.id} | error={e}"
        )
        return None

    # NOTE: Step 0의 (3) "간격 판단" (interval_mode 기반 마지막 실행 이후 경과 체크)은
    # FES(FlowExecutionState) 블로그 레벨 확장이 필요하여 Phase C/D로 연기.
    # Phase B에서는 generate.enabled 체크 + min_inventory 전달만 수행.
    # interval_mode/computed_interval 값은 StageParams에 포함되어 있으나 아직 사용하지 않음.

    logger.info(
        f"[FLOW_BG] Growth Profile Step 0 완료 | "
        f"flow_id={flow.id} | blogs={len(context.blog_stages)}개 | "
        f"module={gp_module.name}"
    )
    return context
```

### 1-4. prompt 모듈 실행 블록 변경 (라인 420~513)

**변경 전** (현재 코드):
```python
            # 8. prompt 모듈 실행 (블로그 필수, 재고 기반 글 생성)
            if "prompt" in modules_by_type:
                if not blogs:
                    ...
                else:
                    from app.services.generation.flow_generate_executor import FlowGenerateExecutor
                    gen_executor = FlowGenerateExecutor(db, user_id)

                    # generate 모듈에서 재고 설정 추출 (있으면)
                    gen_inv_settings = None
                    if "generate" in modules_by_type:
                        gen_mod = modules_by_type["generate"][0]
                        gen_inv_settings = gen_mod.settings or {}

                    for prompt_module in modules_by_type["prompt"]:
                        logger.info(f"[FLOW_BG] 생성 모듈 실행: {prompt_module.name}")

                        for blog in blogs:
                            ...
                            result = await gen_executor.execute_for_blog(
                                prompt_module, blog,
                                inventory_settings=gen_inv_settings,
                            )
```

**변경 후**:
```python
            # 8. prompt 모듈 실행 (GP 컨텍스트 기반 생성)
            if "prompt" in modules_by_type:
                if not blogs:
                    logger.warning(f"[FLOW_BG] 생성 모듈이 있지만 블로그가 없음: {flow_id}")
                    for prompt_module in modules_by_type["prompt"]:
                        fail_count += 1
                        total_processed += 1
                        await _save_autorun_log(
                            db=db,
                            user_id=user_id,
                            flow_id=flow.id,
                            flow_name=flow.name,
                            module_name=prompt_module.name,
                            blog_name="-",
                            result={"success": False, "message": "플로우에 연결된 블로그가 없습니다"},
                            duration_ms=0,
                            action="generate"
                        )
                else:
                    from app.services.generation.flow_generate_executor import FlowGenerateExecutor
                    gen_executor = FlowGenerateExecutor(db, user_id)

                    for prompt_module in modules_by_type["prompt"]:
                        logger.info(f"[FLOW_BG] 생성 모듈 실행: {prompt_module.name}")

                        for blog in blogs:
                            # GP 컨텍스트에서 블로그별 StageParams 조회
                            stage_params = gp_context.get_stage_for_blog(blog.id)

                            # generate.enabled 체크
                            if stage_params and not stage_params.generate.enabled:
                                logger.info(
                                    f"[FLOW_BG] 생성 비활성 | blog={blog.name} | "
                                    f"stage={stage_params.stage_name}"
                                )
                                total_processed += 1
                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=prompt_module.name,
                                    blog_name=blog.name,
                                    result={
                                        "success": True,
                                        "skipped": True,
                                        "message": f"생성 비활성 (stage: {stage_params.stage_name})",
                                    },
                                    duration_ms=0,
                                    action="generate"
                                )
                                continue

                            blog_start_time = datetime.now()
                            logger.info(
                                f"[FLOW_BG] 생성 처리: {blog.name} | "
                                f"module={prompt_module.name} | "
                                f"stage={stage_params.stage_name if stage_params else 'unknown'}"
                            )

                            try:
                                result = await gen_executor.execute_for_blog(
                                    prompt_module, blog,
                                    stage_params=stage_params,
                                )
                                blog_duration_ms = int(
                                    (datetime.now() - blog_start_time).total_seconds() * 1000
                                )

                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=prompt_module.name,
                                    blog_name=blog.name,
                                    result=result,
                                    duration_ms=blog_duration_ms,
                                    action="generate"
                                )

                                if result.get("success"):
                                    if result.get("skipped"):
                                        logger.info(
                                            f"[FLOW_BG] 생성 스킵 | blog={blog.name} | "
                                            f"{result.get('message')}"
                                        )
                                    else:
                                        success_count += 1
                                        logger.info(f"[FLOW_BG] 생성 성공 | blog={blog.name}")
                                else:
                                    fail_count += 1
                                    logger.warning(f"[FLOW_BG] 생성 실패 | blog={blog.name}")

                                total_processed += 1

                            except Exception as e:
                                fail_count += 1
                                total_processed += 1
                                blog_duration_ms = int(
                                    (datetime.now() - blog_start_time).total_seconds() * 1000
                                )
                                logger.error(
                                    f"[FLOW_BG] 생성 오류 | blog={blog.name} | error={e}"
                                )

                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=prompt_module.name,
                                    blog_name=blog.name,
                                    result={"success": False, "message": str(e)},
                                    duration_ms=blog_duration_ms,
                                    action="generate"
                                )
```

**핵심 변경 3가지:**
1. `gen_inv_settings` (generate 모듈의 settings) 조회 로직 **제거**
2. 블로그별 `stage_params = gp_context.get_stage_for_blog(blog.id)` 추가
3. `generate.enabled=false` 시 즉시 스킵
4. `execute_for_blog()` 호출 시 `inventory_settings` → `stage_params` 파라미터로 변경

---

## 파일 2: flow_generate_executor.py 수정

### 경로: `app/services/generation/flow_generate_executor.py`
### 변경 개요: StageParams 기반 재고 확인으로 전환

### 2-1. import 추가

```python
# 기존 import 아래에 추가
from .flow_execution_context import StageParams
```

### 2-2. execute_for_blog() 시그니처 변경

**변경 전:**
```python
    async def execute_for_blog(
        self,
        module: Module,
        blog: Blog,
        inventory_settings: Optional[dict] = None,
    ) -> Dict[str, Any]:
```

**변경 후:**
```python
    async def execute_for_blog(
        self,
        module: Module,
        blog: Blog,
        stage_params: Optional[StageParams] = None,
    ) -> Dict[str, Any]:
```

### 2-3. execute_for_blog() 내부 로직 변경

**변경 전** (라인 62~67):
```python
            # 1. 재고 확인 (generate 모듈 설정 우선, 없으면 prompt 모듈 설정)
            inv_settings = inventory_settings or module.settings or {}
            check_result = await self.inventory_trigger.check_inventory(
                blog_id, module_settings=inv_settings
            )
```

**변경 후:**
```python
            # 1. 재고 확인 (GP StageParams 기반)
            min_inventory = None
            growth_stage = "unknown"
            if stage_params:
                min_inventory = stage_params.generate.min_inventory
                growth_stage = stage_params.stage_name

            check_result = await self.inventory_trigger.check_inventory(
                blog_id, min_inventory=min_inventory,
            )
```

### 2-4. execute_for_blogs() 시그니처 변경

**변경 전:**
```python
    async def execute_for_blogs(
        self,
        module: Module,
        blogs: List[Blog],
        inventory_settings: Optional[dict] = None,
    ) -> List[Dict[str, Any]]:
```

**변경 후:**
```python
    async def execute_for_blogs(
        self,
        module: Module,
        blogs: List[Blog],
        blog_stage_map: Optional[Dict[int, StageParams]] = None,
    ) -> List[Dict[str, Any]]:
```

내부에서 호출 시:
```python
        for blog in blogs:
            stage = blog_stage_map.get(blog.id) if blog_stage_map else None
            result = await self.execute_for_blog(
                module, blog, stage_params=stage
            )
```

### 2-5. Docstring 업데이트

```python
    async def execute_for_blog(
        self,
        module: Module,
        blog: Blog,
        stage_params: Optional[StageParams] = None,
    ) -> Dict[str, Any]:
        """
        단일 블로그에 대해 생성 모듈 실행

        Args:
            module: prompt 타입 모듈
            blog: 대상 블로그
            stage_params: GP에서 결정된 스테이지 파라미터 (None이면 기본 임계값 사용)

        Returns:
            dict: 실행 결과
        """
```

---

## 파일 3: inventory_trigger.py 수정

### 경로: `app/services/generation/inventory_trigger.py`
### 변경 개요: GP 기반 임계값 직접 전달 + BGS 폴백 로직 제거

### 3-1. check_inventory() 시그니처 변경

**변경 전:**
```python
    async def check_inventory(
        self, blog_id: int,
        module_settings: Optional[dict] = None,
    ) -> InventoryCheckResult:
```

**변경 후:**
```python
    async def check_inventory(
        self, blog_id: int,
        min_inventory: Optional[int] = None,
    ) -> InventoryCheckResult:
```

### 3-2. check_inventory() 내부 변경

**변경 전** (라인 66~72):
```python
        # 1. 현재 재고 수량 조회
        inventory_count = await self._get_inventory_count(blog_id)

        # 2. 임계값 조회 (모듈 설정 우선, BlogGrowthSetting 폴백)
        threshold, growth_stage = await self._get_threshold(
            blog_id, module_settings
        )
```

**변경 후:**
```python
        # 1. 현재 재고 수량 조회
        inventory_count = await self._get_inventory_count(blog_id)

        # 2. 임계값 결정 (GP에서 직접 전달, 없으면 기본값)
        threshold = min_inventory if min_inventory is not None else DEFAULT_INVENTORY_THRESHOLD
        growth_stage = "gp_managed" if min_inventory is not None else "default"
```

### 3-3. `_get_threshold()` 메서드 처리

**`_get_threshold()` 메서드는 삭제합니다.** 전체 삭제 범위: 라인 173~267 (약 95줄).

GP가 유일한 스케줄러이므로:
- `module_settings`에서 inventory 읽기 → 불필요 (GP의 `generate.min_inventory`가 직접 전달됨)
- `BlogGrowthSetting` 폴백 → 불필요 (GP가 필수, Phase M에서 BGS 데이터 마이그레이션)
- `Blog` 조회로 `total_post_count` 읽기 → 불필요 (GP Step 0에서 이미 스테이지 결정 완료)

### 3-4. import 정리

삭제할 import:
```python
# 제거
from ...models.blog_growth_setting import BlogGrowthSetting
from sqlalchemy.orm import selectinload
```

`selectinload`가 `_get_threshold()` → `Blog.growth_setting` 조회에서만 사용되므로 제거 가능.

> **주의**: `_find_available_title()`과 `find_available_titles()`는 변경 없이 유지합니다.
> `_get_inventory_count()`도 변경 없이 유지합니다 (`CrawledPost.published_at.is_(None)` 조건 포함).

### 3-5. 변경 후 inventory_trigger.py 전체 check_inventory

```python
    async def check_inventory(
        self, blog_id: int,
        min_inventory: Optional[int] = None,
    ) -> InventoryCheckResult:
        """
        블로그의 재고 상태를 확인하고 생성 필요 여부를 판단

        Args:
            blog_id: 블로그 ID
            min_inventory: GP에서 결정된 최소 보유 수 (None이면 기본값 사용)

        Returns:
            InventoryCheckResult: 재고 확인 결과
        """
        # 1. 현재 재고 수량 조회
        inventory_count = await self._get_inventory_count(blog_id)

        # 2. 임계값 결정 (GP에서 직접 전달, 없으면 기본값)
        threshold = min_inventory if min_inventory is not None else DEFAULT_INVENTORY_THRESHOLD
        growth_stage = "gp_managed" if min_inventory is not None else "default"

        # 3. 생성 필요 여부 판단
        needs_generation = inventory_count < threshold

        logger.info(
            f"[INVENTORY] blog_id={blog_id} | "
            f"재고={inventory_count} | 기준={threshold} | "
            f"단계={growth_stage} | "
            f"생성필요={'예' if needs_generation else '아니오'}"
        )

        # 4. 생성이 필요하면 사용 가능한 제목 조회
        title_id = None
        title_text = None
        if needs_generation:
            title = await self._find_available_title(blog_id)
            if title:
                title_id = title.id
                title_text = title.title
            else:
                needs_generation = False
                logger.info(
                    f"[INVENTORY] blog_id={blog_id} | "
                    f"재고 부족이지만 사용 가능한 제목 없음"
                )

        return InventoryCheckResult(
            blog_id=blog_id,
            current_inventory=inventory_count,
            threshold=threshold,
            needs_generation=needs_generation,
            growth_stage=growth_stage,
            available_title_id=title_id,
            available_title_text=title_text,
        )
```

---

## 파일 4: flow_service.py 수정

### 경로: `app/services/flow_service.py`
### 변경 개요: add_modules()에 GP 1-per-flow 중복 검증 추가

### 4-1. add_modules() 메서드 수정

**삽입 위치**: 라인 466 (`valid_modules = ...` 조회) 이후, 라인 477 (모듈-플로우 연결 생성) 이전.

```python
            valid_module_ids = [m.id for m in valid_modules]

            if len(valid_module_ids) != len(new_module_ids):
                invalid_ids = set(new_module_ids) - set(valid_module_ids)
                raise HTTPException(
                    status_code=400,
                    detail=f"유효하지 않은 모듈 ID: {list(invalid_ids)}",
                )

            # --- GP 1-per-flow 중복 검증 (Phase B 추가) ---
            # 추가하려는 모듈 중 growth_profile 타입이 있는지 확인
            gp_modules_to_add = [
                m for m in valid_modules
                if m.module_type and m.module_type.code == "growth_profile"
            ]

            if gp_modules_to_add:
                # 기존 Flow에 이미 growth_profile 모듈이 있는지 확인
                existing_gp_query = (
                    select(FlowModule)
                    .join(Module, FlowModule.module_id == Module.id)
                    .join(ModuleType, Module.module_type_id == ModuleType.id)
                    .where(
                        FlowModule.flow_id == flow_id,
                        ModuleType.code == "growth_profile",
                    )
                )
                existing_gp_result = await self.db.execute(existing_gp_query)
                existing_gp = existing_gp_result.first()

                if existing_gp:
                    raise HTTPException(
                        status_code=400,
                        detail="이 Flow에는 이미 성장 프로파일이 설정되어 있습니다",
                    )

                # 추가하려는 GP 모듈이 2개 이상인지도 체크
                if len(gp_modules_to_add) > 1:
                    raise HTTPException(
                        status_code=400,
                        detail="성장 프로파일은 Flow당 1개만 추가할 수 있습니다",
                    )
            # --- GP 1-per-flow 중복 검증 끝 ---

            # 모듈-플로우 연결 생성
            for module_id in valid_module_ids:
```

### 4-2. import 추가

`flow_service.py` 상단에서 `ModuleType` import 확인:

```python
from ..models.module_type import ModuleType  # 이미 있으면 추가 불필요
```

> **주의**: `valid_modules` 조회 시 `module_type`이 로드되어 있어야 합니다.
> 현재 `Module` 조회에서 `selectinload(Module.module_type)`가 없으므로, 모듈 조회 쿼리에 추가 필요:

```python
            # 모듈 소유권 확인 (module_type도 함께 로드)
            module_query = (
                select(Module)
                .where(
                    and_(Module.id.in_(new_module_ids), Module.user_id == user.id)
                )
                .options(selectinload(Module.module_type))
            )
```

---

## 파일 5: 테스트

### 경로: `tests/integration/test_phase_b_flow_execution.py`
### 예상 줄 수: ~380줄

### 테스트 목록 (27개)

#### 클래스 1: TestBuildGrowthProfileContext (Step 0)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T01 | `test_gp_exists_active_time` | GP 모듈 있음 + 활성 시간 | FlowExecutionContext 반환, blog_stages 매핑 완료 |
| T02 | `test_gp_missing_returns_none` | GP 모듈 없음 (W4) | None 반환 (Flow 실행 중단) |
| T03 | `test_gp_inactive_time_returns_none` | GP 있으나 비활성 시간대 | None 반환 (Flow 실행 스킵) |
| T04 | `test_gp_no_blogs_returns_none` | GP 있으나 블로그 없음 | None 반환 |
| T05 | `test_gp_invalid_stages_returns_none` | stages 배열 검증 실패 | None 반환 (ValueError 처리됨) |
| T06 | `test_gp_no_schedule_matrix_always_active` | schedule_matrix 없음 | FlowExecutionContext 정상 반환 (항상 활성) |
| T07 | `test_gp_empty_settings_returns_none` | GP 모듈 settings 비어있음 | None 반환 |

#### 클래스 2: TestPromptModuleWithGP (생성 모듈 연동)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T08 | `test_generate_enabled_true_runs` | generate.enabled=true, 재고 부족 | 생성 실행됨 |
| T09 | `test_generate_enabled_false_skips` | generate.enabled=false | 생성 스킵 (로그에 "비활성" 기록) |
| T10 | `test_generate_min_inventory_passed` | stage_params.generate.min_inventory=10 | InventoryTrigger에 min_inventory=10 전달됨 |
| T11 | `test_generate_inventory_sufficient_skips` | 재고 >= min_inventory | 생성 스킵 (재고 충분) |
| T12 | `test_multiple_blogs_different_stages` | Blog A(30글=rapid), Blog B(200글=stable) | 각각 다른 stage_params 적용 |
| T12b | `test_boundary_blog_stage_mapping` | Blog A(50글=rapid_growth 경계), Blog B(51글=growth 시작) | Q3 경계값 inclusive 규칙이 Flow 실행에서도 올바르게 적용됨 |

#### 클래스 3: TestInventoryTriggerGPIntegration (임계값 변경)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T13 | `test_min_inventory_from_gp` | min_inventory=10 직접 전달 | threshold=10 사용 |
| T14 | `test_min_inventory_none_uses_default` | min_inventory=None | threshold=DEFAULT_INVENTORY_THRESHOLD |
| T15 | `test_bgs_fallback_removed` | BGS가 있어도 무시 | GP 임계값만 사용 |
| T16 | `test_growth_stage_label_gp_managed` | GP 기반 임계값 | growth_stage="gp_managed" |

#### 클래스 4: TestFlowGenerateExecutorGP (실행기 변경)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T17 | `test_stage_params_passed_to_inventory` | stage_params 전달 | min_inventory가 check_inventory에 전달됨 |
| T18 | `test_stage_params_none_uses_default` | stage_params=None | 기본 임계값으로 동작 |
| T19 | `test_execute_for_blogs_with_stage_map` | blog_stage_map 전달 | 블로그별 올바른 stage_params 사용 |
| T19b | `test_interval_mode_available_in_stage_params` | stage_params에서 interval_mode 확인 | stage_params.generate.interval_mode에 "auto"/"manual" 값 존재 확인 |

#### 클래스 5: TestGP1PerFlowValidation (중복 검증)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T20 | `test_add_first_gp_module_succeeds` | Flow에 GP 없음 + GP 추가 | 정상 추가 |
| T21 | `test_add_second_gp_module_fails` | Flow에 GP 이미 있음 + GP 추가 | HTTPException 400 |
| T22 | `test_add_two_gp_modules_at_once_fails` | 한번에 GP 2개 추가 | HTTPException 400 |
| T23 | `test_add_non_gp_module_succeeds` | GP 이미 있음 + prompt 모듈 추가 | 정상 추가 |

#### 클래스 6: TestEdgeCases (엣지 케이스)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T24 | `test_blog_not_in_context_uses_none` | blog_id가 blog_stages에 없음 | stage_params=None, 기본 임계값 사용 |
| T25 | `test_gp_with_single_stage_all_blogs_same` | 단일 구간 GP (0~null) | 모든 블로그에 동일 stage 적용 |

### 테스트 실행 명령

```bash
cd /home/jteen/blogauto_v2/services/republish
python3 -m pytest tests/integration/test_phase_b_flow_execution.py -v
```

---

## FES 블로그 레벨 확장 판단

### 현재 상황

- `FlowExecutionState`는 `(flow_id, module_id)` 단위로 추적
- GP는 블로그별로 다른 간격이 적용되므로, 블로그별 마지막 실행 시각 추적이 필요할 수 있음
- **그러나**, 현재 `_execute_flow_background()`에서 FES를 사용하지 않음 (autorun 엔진에서만 사용)

### Phase B 결정

**FES 블로그 레벨 확장은 Phase B 범위 밖입니다.**

이유:
1. 현재 Flow 수동 실행(`_execute_flow_background`)은 FES 없이 동작
2. FES는 autorun(자동 실행) 엔진에서 다음 실행 시각 계산에만 사용
3. autorun 엔진은 별도 리팩토링 대상 (Phase C/D에서 처리)
4. Phase B의 범위는 "GP Step 0 + 생성 모듈 연동"에 집중

**Step 0의 (3) "간격 판단" 미구현 사유:**
- 작업 계획서 Section 6-1의 Step 0 (3)번은 "각 모듈의 활성화 상태 + 간격 판단 → 마지막 실행 시각으로부터 간격 경과 체크 + jitter 적용"을 포함
- 이 기능은 FES에 `(flow_id, module_id, blog_id)` 레벨 추적이 필요
- Phase B에서는 `generate.enabled` 체크 + `min_inventory` 전달만 수행
- `interval_mode`와 `computed_interval` 값은 `StageParams`에 이미 포함되어 올바르게 전달됨 (테스트 T19b로 검증)
- 실제 간격 경과 체크 로직은 Phase C/D에서 FES 확장과 함께 구현

Phase B에서는 **매 실행마다** `GrowthProfileResolver.build_execution_context()`를 호출하여
현재 시점의 블로그별 스테이지를 계산합니다. 이전 실행 간격과의 비교는 Phase C/D에서 FES 확장과 함께 구현합니다.

---

## 구현 순서

```
1. inventory_trigger.py 수정           (독립, 시그니처 변경)
2. flow_generate_executor.py 수정      (1에 의존, 시그니처 변경)
3. flows_execute.py 수정               (1, 2에 의존, Step 0 + prompt 블록)
4. flow_service.py 수정                (독립, GP 1-per-flow 검증)
5. 테스트 작성 및 실행                   (1~4 완료 후)
```

**1, 4는 병렬 구현 가능.**

---

## 완료 기준 체크리스트 (작업계획서 Section 10 Phase B 기준)

- [ ] GP가 있는 Flow에서 `schedule_matrix` 기반 활성/비활성 판단이 올바른지 검증
- [ ] `generate.enabled=true`인 경우만 생성 모듈이 실행되는지 검증
- [ ] prompt 모듈 실행 시 `generate.min_inventory` + `generate.interval_mode`가 올바르게 전달되는지 검증 (interval_mode는 StageParams에 포함, 실제 간격 판단은 Phase C/D)
- [ ] **Growth Profile 없는 Flow 실행 시 즉시 중단되는지 검증** (W4)
- [ ] **Flow당 growth_profile 모듈이 2개 이상 추가되지 않는지 검증** (Q2)
- [ ] 각 파일 500줄 미만 확인 (flows_execute.py 예외 - W6 결정)
- [ ] 각 함수 50줄 미만 확인
- [ ] 타입 힌트 전수 적용
- [ ] Docstring 전수 작성
- [ ] 테스트 27개 작성 및 전체 통과
