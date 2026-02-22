"""
Phase B 통합 테스트: Flow 실행 시 Growth Profile 연동 검증 (27개)

테스트 대상:
- flows_execute._build_growth_profile_context() (Step 0)
- FlowGenerateExecutor.execute_for_blog / execute_for_blogs
- InventoryTrigger.check_inventory (GP 임계값)
- flow_service.add_modules (GP 1-per-flow 중복 검증)
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.routers.flows_execute import _build_growth_profile_context
from app.services.generation.flow_execution_context import (
    FlowExecutionContext, StageParams,
)
from app.services.generation.growth_profile_resolver import GrowthProfileResolver
from app.services.generation.growth_profile_defaults import get_default_profile
from app.services.generation.inventory_trigger import (
    InventoryTrigger, InventoryCheckResult, DEFAULT_INVENTORY_THRESHOLD,
)
from app.services.generation.flow_generate_executor import FlowGenerateExecutor
from app.services.flow_service import FlowService


# ============================================================
# Mock 헬퍼
# ============================================================

def _gp_module(settings=None):
    """GP 모듈 Mock"""
    m = MagicMock()
    m.id, m.name = 1, "테스트 GP"
    m.settings = settings if settings is not None else get_default_profile("balanced")
    m.module_type = MagicMock(code="growth_profile")
    return m


def _blog(bid, name, posts=0):
    """블로그 Mock"""
    b = MagicMock()
    b.id, b.name, b.total_post_count = bid, name, posts
    return b


def _flow(fid=1):
    """Flow Mock"""
    f = MagicMock()
    f.id, f.name = fid, "테스트 플로우"
    return f


def _prompt_module(mid=10):
    """prompt 모듈 Mock"""
    m = MagicMock()
    m.id, m.name = mid, "테스트 생성모듈"
    m.settings = {"generation_prompt": "제목: {title}\n글을 작성해주세요."}
    m.module_type = MagicMock(code="prompt")
    return m


def _all_true():
    """7x24 모든 시간 활성"""
    return [[True] * 24 for _ in range(7)]


def _all_false():
    """7x24 모든 시간 비활성"""
    return [[False] * 24 for _ in range(7)]


def _mbt(gp=None):
    """modules_by_type dict"""
    return {"growth_profile": [gp]} if gp else {}


def _inv_result(blog_id=1, inv=0, thr=10, needs=False, stage="gp_managed",
                tid=None, ttext=None):
    """InventoryCheckResult 생성 헬퍼"""
    return InventoryCheckResult(
        blog_id=blog_id, current_inventory=inv, threshold=thr,
        needs_generation=needs, growth_stage=stage,
        available_title_id=tid, available_title_text=ttext,
    )


def _executor_with_mock_inv(inv_result):
    """Mock InventoryTrigger가 설정된 FlowGenerateExecutor"""
    db = AsyncMock()
    ex = FlowGenerateExecutor(db, user_id=1)
    ex.inventory_trigger.check_inventory = AsyncMock(return_value=inv_result)
    return ex


def _balanced_stage(idx):
    """balanced 프로파일의 stages[idx]에서 StageParams 생성"""
    return StageParams.from_stage_dict(get_default_profile("balanced")["stages"][idx])


def _flow_service_mocks(gp_modules=None, prompt_modules=None,
                        existing_gp=False, existing_ids=None):
    """FlowService.add_modules 테스트용 Mock 일괄 생성"""
    db = AsyncMock()
    svc = FlowService(db)
    svc.get_flow = AsyncMock(return_value=_flow())

    user = MagicMock()
    user.id = 1

    existing_r = MagicMock()
    existing_r.fetchall.return_value = [(i,) for i in (existing_ids or [])]

    modules = (gp_modules or []) + (prompt_modules or [])
    mod_r = MagicMock()
    mod_r.scalars.return_value.all.return_value = modules

    side = [existing_r, mod_r]
    if gp_modules:
        gp_r = MagicMock()
        gp_r.first.return_value = MagicMock() if existing_gp else None
        side.append(gp_r)

    db.execute = AsyncMock(side_effect=side)
    db.commit, db.refresh = AsyncMock(), AsyncMock()

    req = MagicMock()
    req.module_ids = [m.id for m in modules]
    return svc, user, req, db


# ============================================================
# 클래스 1: TestBuildGrowthProfileContext (Step 0) - 7개
# ============================================================

class TestBuildGrowthProfileContext:
    """_build_growth_profile_context 검증"""

    @pytest.mark.asyncio
    async def test_gp_exists_active_time(self):
        """T01: GP + 활성 시간 -> FlowExecutionContext, blog_stages 매핑"""
        gp = get_default_profile("balanced")
        gp["schedule_matrix"] = _all_true()
        r = await _build_growth_profile_context(
            _mbt(_gp_module(gp)), [_blog(1, "A", 30), _blog(2, "B", 100)], _flow()
        )
        assert isinstance(r, FlowExecutionContext)
        assert r.flow_id == 1 and len(r.blog_stages) == 2
        assert r.blog_stages[1].stage_name == "rapid_growth"
        assert r.blog_stages[2].stage_name == "growth"

    @pytest.mark.asyncio
    async def test_gp_missing_returns_none(self):
        """T02: GP 없음 -> None"""
        assert await _build_growth_profile_context({}, [_blog(1, "A")], _flow()) is None

    @pytest.mark.asyncio
    async def test_gp_inactive_time_returns_none(self):
        """T03: 비활성 시간대 -> None"""
        gp = get_default_profile("balanced")
        gp["schedule_matrix"] = _all_false()
        r = await _build_growth_profile_context(
            _mbt(_gp_module(gp)), [_blog(1, "A", 30)], _flow()
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_gp_no_blogs_returns_none(self):
        """T04: 블로그 없음 -> None"""
        gp = get_default_profile("balanced")
        gp["schedule_matrix"] = _all_true()
        assert await _build_growth_profile_context(
            _mbt(_gp_module(gp)), [], _flow()
        ) is None

    @pytest.mark.asyncio
    async def test_gp_invalid_stages_returns_none(self):
        """T05: stages 검증 실패 (빈 구간) -> None"""
        gp = {
            "schedule_matrix": _all_true(),
            "stages": [
                {"name": "s1", "label": "S1", "post_count_min": 0, "post_count_max": 50},
                {"name": "s2", "label": "S2", "post_count_min": 55, "post_count_max": None},
            ],
        }
        assert await _build_growth_profile_context(
            _mbt(_gp_module(gp)), [_blog(1, "A", 30)], _flow()
        ) is None

    @pytest.mark.asyncio
    async def test_gp_no_schedule_matrix_always_active(self):
        """T06: schedule_matrix 없음 -> 정상 반환"""
        gp = get_default_profile("balanced")
        gp.pop("schedule_matrix", None)
        r = await _build_growth_profile_context(
            _mbt(_gp_module(gp)), [_blog(1, "A", 30)], _flow()
        )
        assert isinstance(r, FlowExecutionContext)
        assert 1 in r.blog_stages

    @pytest.mark.asyncio
    async def test_gp_empty_settings_returns_none(self):
        """T07: settings 비어있음 -> None"""
        assert await _build_growth_profile_context(
            _mbt(_gp_module(settings={})), [_blog(1, "A", 30)], _flow()
        ) is None


# ============================================================
# 클래스 2: TestPromptModuleWithGP (생성 모듈 연동) - 6개
# ============================================================

class TestPromptModuleWithGP:
    """prompt 모듈 + GP 컨텍스트 연동"""

    @pytest.mark.asyncio
    async def test_generate_enabled_true_runs(self):
        """T08: generate.enabled=true -> 실행기 호출"""
        inv = _inv_result(needs=True, tid=1, ttext="테스트 제목입니다 충분히 긴 제목")
        ex = _executor_with_mock_inv(inv)

        gen_r = MagicMock(
            success=True, recombined_title="재조합", reference_count=3,
            content_length=500, generation_time_seconds=5,
            crawling_post_id=1, generation_history_id=1, ai_model_content="gpt-4o-mini",
        )
        with patch("app.services.generation.flow_generate_executor.ContentGenerator") as CG:
            CG.return_value.generate = AsyncMock(return_value=gen_r)
            r = await ex.execute_for_blog(
                _prompt_module(), _blog(1, "A", 30), stage_params=_balanced_stage(0)
            )
        assert r["success"] is True and r["skipped"] is False
        ex.inventory_trigger.check_inventory.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_enabled_false_skips(self):
        """T09: generate.enabled=false -> 스킵"""
        stage = {
            "name": "off", "label": "비활성", "post_count_min": 0, "post_count_max": None,
            "generate": {"enabled": False},
            "publish": {"enabled": True, "interval_mode": "auto", "daily_count": 2},
            "republish": {"enabled": True, "interval_mode": "auto", "daily_count": 2},
        }
        sp = StageParams.from_stage_dict(stage)
        assert sp.generate.enabled is False
        ctx = GrowthProfileResolver.build_execution_context(
            1, {"stages": [stage]}, {1: 200}
        )
        assert ctx.get_stage_for_blog(1).generate.enabled is False

    @pytest.mark.asyncio
    async def test_generate_min_inventory_passed(self):
        """T10: min_inventory=10 전달 확인"""
        ex = _executor_with_mock_inv(_inv_result(inv=15, needs=False))
        sp = _balanced_stage(0)
        assert sp.generate.min_inventory == 10
        await ex.execute_for_blog(_prompt_module(), _blog(1, "A", 30), stage_params=sp)
        ex.inventory_trigger.check_inventory.assert_awaited_once_with(1, min_inventory=10)

    @pytest.mark.asyncio
    async def test_generate_inventory_sufficient_skips(self):
        """T11: 재고 충분 -> skipped=True"""
        ex = _executor_with_mock_inv(_inv_result(inv=15, needs=False))
        r = await ex.execute_for_blog(
            _prompt_module(), _blog(1, "A", 30), stage_params=_balanced_stage(0)
        )
        assert r["success"] is True and r["skipped"] is True and r["inventory"] == 15

    @pytest.mark.asyncio
    async def test_multiple_blogs_different_stages(self):
        """T12: 30글/200글 -> 다른 stage_params"""
        ctx = GrowthProfileResolver.build_execution_context(
            1, get_default_profile("balanced"), {1: 30, 2: 200}
        )
        assert ctx.get_stage_for_blog(1).stage_name == "rapid_growth"
        assert ctx.get_stage_for_blog(1).generate.min_inventory == 10
        assert ctx.get_stage_for_blog(2).stage_name == "stable"
        assert ctx.get_stage_for_blog(2).generate.min_inventory == 3

    def test_boundary_blog_stage_mapping(self):
        """T12b: 50글/51글 경계값 inclusive"""
        ctx = GrowthProfileResolver.build_execution_context(
            1, get_default_profile("balanced"), {1: 50, 2: 51}
        )
        assert ctx.get_stage_for_blog(1).stage_name == "rapid_growth"
        assert ctx.get_stage_for_blog(2).stage_name == "growth"


# ============================================================
# 클래스 3: TestInventoryTriggerGPIntegration - 4개
# ============================================================

class TestInventoryTriggerGPIntegration:
    """InventoryTrigger GP 임계값 동작"""

    def _trigger(self, inventory_count=0):
        """Mock DB로 InventoryTrigger 생성"""
        db = AsyncMock()
        sr = MagicMock()
        sr.scalar.return_value = inventory_count
        db.execute = AsyncMock(return_value=sr)
        t = InventoryTrigger(db)
        t._find_available_title = AsyncMock(return_value=None)
        return t

    @pytest.mark.asyncio
    async def test_min_inventory_from_gp(self):
        """T13: min_inventory=10 -> threshold=10"""
        r = await self._trigger(0).check_inventory(1, min_inventory=10)
        assert r.threshold == 10 and r.growth_stage == "gp_managed"

    @pytest.mark.asyncio
    async def test_min_inventory_none_uses_default(self):
        """T14: None -> DEFAULT_INVENTORY_THRESHOLD"""
        r = await self._trigger(0).check_inventory(1, min_inventory=None)
        assert r.threshold == DEFAULT_INVENTORY_THRESHOLD and r.growth_stage == "default"

    @pytest.mark.asyncio
    async def test_bgs_fallback_removed(self):
        """T15: BGS 무시, GP값만 사용"""
        r = await self._trigger(5).check_inventory(1, min_inventory=8)
        assert r.threshold == 8 and r.growth_stage == "gp_managed"
        assert r.needs_generation is False  # 제목 없어서 False

    @pytest.mark.asyncio
    async def test_growth_stage_label_gp_managed(self):
        """T16: GP 임계값 -> 'gp_managed', 재고충분 -> 불필요"""
        r = await self._trigger(20).check_inventory(1, min_inventory=5)
        assert r.growth_stage == "gp_managed" and r.needs_generation is False


# ============================================================
# 클래스 4: TestFlowGenerateExecutorGP - 4개
# ============================================================

class TestFlowGenerateExecutorGP:
    """FlowGenerateExecutor GP 연동"""

    @pytest.mark.asyncio
    async def test_stage_params_passed_to_inventory(self):
        """T17: stage_params -> min_inventory 전달"""
        ex = _executor_with_mock_inv(_inv_result(inv=20, needs=False))
        await ex.execute_for_blog(_prompt_module(), _blog(1, "A", 30), _balanced_stage(0))
        ex.inventory_trigger.check_inventory.assert_awaited_once_with(1, min_inventory=10)

    @pytest.mark.asyncio
    async def test_stage_params_none_uses_default(self):
        """T18: stage_params=None -> min_inventory=None"""
        ex = _executor_with_mock_inv(_inv_result(inv=5, thr=3, stage="default", needs=False))
        await ex.execute_for_blog(_prompt_module(), _blog(1, "A", 30), stage_params=None)
        ex.inventory_trigger.check_inventory.assert_awaited_once_with(1, min_inventory=None)

    @pytest.mark.asyncio
    async def test_execute_for_blogs_with_stage_map(self):
        """T19: blog_stage_map -> 올바른 매핑"""
        ex = _executor_with_mock_inv(_inv_result(inv=20, needs=False))
        blogs = [_blog(1, "A", 30), _blog(2, "B", 100)]
        stage_map = {1: _balanced_stage(0), 2: _balanced_stage(1)}

        results = await ex.execute_for_blogs(_prompt_module(), blogs, blog_stage_map=stage_map)
        assert len(results) == 2
        assert results[0]["blog_id"] == 1 and results[1]["blog_id"] == 2

        calls = ex.inventory_trigger.check_inventory.await_args_list
        assert calls[0].args[0] == 1 and calls[0].kwargs["min_inventory"] == 10
        assert calls[1].args[0] == 2 and calls[1].kwargs["min_inventory"] == 5

    def test_interval_mode_available_in_stage_params(self):
        """T19b: interval_mode auto/manual 존재 확인"""
        rapid = _balanced_stage(0)
        assert rapid.generate.interval_mode == "auto"
        assert rapid.publish.interval_mode == "manual"
        stable = _balanced_stage(2)
        assert stable.generate.interval_mode == "manual"
        assert stable.generate.interval_minutes == 360


# ============================================================
# 클래스 5: TestGP1PerFlowValidation - 4개
# ============================================================

class TestGP1PerFlowValidation:
    """add_modules GP 1-per-flow 중복 검증"""

    @pytest.mark.asyncio
    async def test_add_first_gp_module_succeeds(self):
        """T20: GP 없음 + GP 추가 -> 정상"""
        gp = _gp_module(); gp.id = 5
        svc, user, req, db = _flow_service_mocks(gp_modules=[gp], existing_gp=False)
        r = await svc.add_modules(user, 1, req)
        assert r is not None
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_second_gp_module_fails(self):
        """T21: GP 있음 + GP 추가 -> 400"""
        from fastapi import HTTPException
        gp = _gp_module(); gp.id = 5
        svc, user, req, _ = _flow_service_mocks(gp_modules=[gp], existing_gp=True)
        with pytest.raises(HTTPException) as e:
            await svc.add_modules(user, 1, req)
        assert e.value.status_code == 400 and "이미 성장 프로파일" in e.value.detail

    @pytest.mark.asyncio
    async def test_add_two_gp_modules_at_once_fails(self):
        """T22: GP 2개 동시 -> 400"""
        from fastapi import HTTPException
        gp1 = _gp_module(); gp1.id = 5
        gp2 = _gp_module(); gp2.id = 6
        svc, user, req, _ = _flow_service_mocks(gp_modules=[gp1, gp2])
        with pytest.raises(HTTPException) as e:
            await svc.add_modules(user, 1, req)
        assert e.value.status_code == 400 and "1개만" in e.value.detail

    @pytest.mark.asyncio
    async def test_add_non_gp_module_succeeds(self):
        """T23: prompt 추가 -> 정상 (GP 검증 우회)"""
        svc, user, req, db = _flow_service_mocks(prompt_modules=[_prompt_module(10)])
        r = await svc.add_modules(user, 1, req)
        assert r is not None
        db.commit.assert_awaited_once()


# ============================================================
# 클래스 6: TestEdgeCases - 2개
# ============================================================

class TestEdgeCases:
    """GP 연동 엣지 케이스"""

    @pytest.mark.asyncio
    async def test_blog_not_in_context_uses_none(self):
        """T24: 미등록 blog_id -> stage_params=None -> min_inventory=None"""
        ctx = GrowthProfileResolver.build_execution_context(
            1, get_default_profile("balanced"), {1: 30}
        )
        assert ctx.get_stage_for_blog(999) is None

        ex = _executor_with_mock_inv(_inv_result(blog_id=999, inv=5, thr=3, stage="default"))
        await ex.execute_for_blog(_prompt_module(), _blog(999, "X", 100), stage_params=None)
        ex.inventory_trigger.check_inventory.assert_awaited_once_with(999, min_inventory=None)

    def test_gp_with_single_stage_all_blogs_same(self):
        """T25: 단일 구간 -> 모든 블로그 동일 stage"""
        gp = {"stages": [{
            "name": "universal", "label": "범용",
            "post_count_min": 0, "post_count_max": None,
            "generate": {"enabled": True, "min_inventory": 7,
                         "interval_mode": "auto", "daily_count": 3},
            "publish": {"enabled": True, "interval_mode": "auto", "daily_count": 2},
            "republish": {"enabled": True, "interval_mode": "auto", "daily_count": 2},
        }]}
        ctx = GrowthProfileResolver.build_execution_context(1, gp, {1: 0, 2: 50, 3: 500})
        for bid in [1, 2, 3]:
            s = ctx.get_stage_for_blog(bid)
            assert s.stage_name == "universal" and s.generate.min_inventory == 7
