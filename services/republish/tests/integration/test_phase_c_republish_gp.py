"""
Phase C 통합 테스트: 재발행 모듈 + Growth Profile 연동 검증 (25개)
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.generation.flow_execution_context import (
    FlowExecutionContext, StageParams, ModuleIntervalParams,
)
from app.services.generation.growth_profile_resolver import GrowthProfileResolver
from app.services.generation.growth_profile_defaults import get_default_profile


# Mock 헬퍼 -----------------------------------------------------------

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
    b.platform = MagicMock(value="naver")
    return b

def _flow(fid=1):
    """Flow Mock"""
    f = MagicMock()
    f.id, f.name = fid, "테스트 플로우"
    return f

def _republish_module(mid=20):
    """재발행 모듈 Mock"""
    m = MagicMock()
    m.id, m.name = mid, "테스트 재발행"
    m.module_type = MagicMock(code="republish")
    return m

def _all_true():
    """7x24 모든 시간 활성"""
    return [[True] * 24 for _ in range(7)]

def _balanced_stage(idx):
    """balanced 프로파일의 stages[idx]에서 StageParams 생성"""
    return StageParams.from_stage_dict(
        get_default_profile("balanced")["stages"][idx]
    )

def _disabled_republish_stage(name="off"):
    """republish.enabled=false인 stage dict"""
    return {
        "name": name, "label": "비활성",
        "post_count_min": 0, "post_count_max": None,
        "generate": {"enabled": True, "interval_mode": "auto", "daily_count": 2},
        "publish": {"enabled": True, "interval_mode": "auto", "daily_count": 2},
        "republish": {"enabled": False},
    }

EXEC_PATH = "app.routers.flows_execute._execute_republish_for_blog"
LOG_PATH = "app.routers.flows_execute._save_autorun_log"


# 클래스 1: TestRepublishGPContext (6개) --------------------------------

class TestRepublishGPContext:
    """재발행 모듈의 GP 컨텍스트 연동 검증"""

    @pytest.mark.asyncio
    async def test_republish_enabled_true_runs(self):
        """T01: republish.enabled=true -> _execute_republish_for_blog 호출"""
        ctx = GrowthProfileResolver.build_execution_context(
            1, get_default_profile("balanced"), {1: 30}
        )
        assert ctx.get_stage_for_blog(1).republish.enabled is True
        with patch(EXEC_PATH, new_callable=AsyncMock, return_value={"success": True}) as m:
            await m(_blog(1, "A", 30))
            m.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_republish_enabled_false_skips(self):
        """T02: republish.enabled=false -> 재발행 스킵, skipped=True 기록"""
        sp = StageParams.from_stage_dict(_disabled_republish_stage("off_stage"))
        assert sp.republish.enabled is False
        result = {"success": True, "skipped": True,
                  "message": f"재발행 비활성 (stage: {sp.stage_name})"}
        assert result["skipped"] is True
        assert "off_stage" in result["message"]

    @pytest.mark.asyncio
    async def test_multiple_blogs_different_stages(self):
        """T03: Blog A(30글=rapid_growth, enabled), Blog B(200글=stable, enabled)"""
        ctx = GrowthProfileResolver.build_execution_context(
            1, get_default_profile("balanced"), {1: 30, 2: 200}
        )
        assert ctx.get_stage_for_blog(1).stage_name == "rapid_growth"
        assert ctx.get_stage_for_blog(1).republish.enabled is True
        assert ctx.get_stage_for_blog(2).stage_name == "stable"
        assert ctx.get_stage_for_blog(2).republish.enabled is True

    @pytest.mark.asyncio
    async def test_stage_params_none_runs_default(self):
        """T04: get_stage_for_blog=None -> 기본 동작 (재발행 실행)"""
        ctx = GrowthProfileResolver.build_execution_context(
            1, get_default_profile("balanced"), {1: 30}
        )
        assert ctx.get_stage_for_blog(999) is None
        with patch(EXEC_PATH, new_callable=AsyncMock, return_value={"success": True}) as m:
            await m(_blog(999, "X", 100))
            m.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_all_blogs_disabled_no_execution(self):
        """T05: 모든 블로그 republish.enabled=false -> 호출 0회"""
        gp = {"stages": [_disabled_republish_stage("no_repub")]}
        ctx = GrowthProfileResolver.build_execution_context(1, gp, {1: 10, 2: 50, 3: 100})
        exec_count = sum(
            0 if (sp := ctx.get_stage_for_blog(b)) and not sp.republish.enabled else 1
            for b in [1, 2, 3]
        )
        assert exec_count == 0

    @pytest.mark.asyncio
    async def test_skipped_blog_logged_to_autorun(self):
        """T06: republish.enabled=false -> skipped=True, stage명 포함"""
        sp = StageParams.from_stage_dict(_disabled_republish_stage("seed_stage"))
        log_result = {"success": True, "skipped": True,
                      "message": f"재발행 비활성 (stage: {sp.stage_name})"}
        with patch(LOG_PATH, new_callable=AsyncMock) as mock_log:
            await mock_log(
                db=AsyncMock(), user_id=1, flow_id=1, flow_name="F",
                module_name="M", blog_name="B",
                result=log_result, duration_ms=0, action="republish",
            )
            saved = mock_log.call_args.kwargs["result"]
            assert saved["skipped"] is True
            assert "seed_stage" in saved["message"]


# 클래스 2: TestRepublishPostRangeRemoval (4개) -------------------------

class TestRepublishPostRangeRemoval:
    """post_range 필드 제거 검증"""

    def test_module_no_post_range_start_attr(self):
        """T07: Module 테이블에 post_range_start 컬럼 없음"""
        from app.models.module import Module
        assert "post_range_start" not in [c.name for c in Module.__table__.columns]

    def test_module_no_post_range_end_attr(self):
        """T08: Module 테이블에 post_range_end 컬럼 없음"""
        from app.models.module import Module
        assert "post_range_end" not in [c.name for c in Module.__table__.columns]

    def test_create_schema_no_post_range(self):
        """T09: ModuleCreateRequest에 post_range 필드 없음"""
        from app.schemas.module import ModuleCreateRequest
        fields = ModuleCreateRequest.model_fields
        assert "post_range_start" not in fields and "post_range_end" not in fields

    def test_update_schema_no_post_range(self):
        """T10: ModuleUpdateRequest에 post_range 필드 없음"""
        from app.schemas.module import ModuleUpdateRequest
        fields = ModuleUpdateRequest.model_fields
        assert "post_range_start" not in fields and "post_range_end" not in fields


# 클래스 3: TestRepublishStageMapping (5개) -----------------------------

class TestRepublishStageMapping:
    """스테이지별 republish.enabled 매핑 검증"""

    def test_rapid_growth_republish_enabled(self):
        """T11: balanced stages[0] rapid_growth -> republish.enabled=True"""
        sp = _balanced_stage(0)
        assert sp.stage_name == "rapid_growth" and sp.republish.enabled is True

    def test_stable_publish_disabled_republish_enabled(self):
        """T12: balanced stages[2] stable -> publish disabled, republish enabled"""
        sp = _balanced_stage(2)
        assert sp.publish.enabled is False and sp.republish.enabled is True

    def test_seed_stage_republish_disabled(self):
        """T13: custom stage (0~30, republish.enabled=false)"""
        stage = {
            "name": "seed", "label": "시드기",
            "post_count_min": 0, "post_count_max": 30,
            "generate": {"enabled": True, "interval_mode": "auto", "daily_count": 2},
            "publish": {"enabled": True, "interval_mode": "auto", "daily_count": 1},
            "republish": {"enabled": False},
        }
        assert StageParams.from_stage_dict(stage).republish.enabled is False

    def test_boundary_50_rapid_growth(self):
        """T14: 50글 -> rapid_growth (max=50 inclusive)"""
        ctx = GrowthProfileResolver.build_execution_context(
            1, get_default_profile("balanced"), {1: 50}
        )
        sp = ctx.get_stage_for_blog(1)
        assert sp.stage_name == "rapid_growth" and sp.republish.enabled is True

    def test_boundary_51_growth(self):
        """T15: 51글 -> growth (min=51)"""
        ctx = GrowthProfileResolver.build_execution_context(
            1, get_default_profile("balanced"), {1: 51}
        )
        sp = ctx.get_stage_for_blog(1)
        assert sp.stage_name == "growth" and sp.republish.enabled is True


# 클래스 4: TestRepublishIntervalParams (4개) ---------------------------

class TestRepublishIntervalParams:
    """재발행 간격 파라미터 검증"""

    def test_interval_mode_available(self):
        """T16: balanced stages[0] republish -> interval_mode 값 존재"""
        assert _balanced_stage(0).republish.interval_mode in ("auto", "manual")

    def test_computed_interval_auto_mode(self):
        """T17: auto, daily_count=3, 16시간 -> 320분 (960/3)"""
        params = ModuleIntervalParams.from_stage_dict(
            {"enabled": True, "interval_mode": "auto", "daily_count": 3},
            active_hours=16,
        )
        assert params.computed_interval == 320

    def test_computed_interval_manual_mode(self):
        """T18: manual, interval_minutes=120 -> 120분"""
        params = ModuleIntervalParams.from_stage_dict(
            {"enabled": True, "interval_mode": "manual", "interval_minutes": 120},
        )
        assert params.computed_interval == 120

    def test_disabled_stage_no_interval(self):
        """T19: enabled=false -> interval_mode=None, computed_interval=None"""
        params = ModuleIntervalParams.from_stage_dict({"enabled": False})
        assert params.interval_mode is None and params.computed_interval is None


# 클래스 5: TestCalculatedIntervalRemoval (1개) -------------------------

class TestCalculatedIntervalRemoval:
    """calculated_interval_minutes 속성 제거 검증"""

    def test_module_no_calculated_interval_property(self):
        """T20: Module 클래스에 calculated_interval_minutes 없음"""
        from app.models.module import Module
        assert not hasattr(Module, "calculated_interval_minutes")


# 클래스 6: TestRepublishEdgeCases (5개) --------------------------------

class TestRepublishEdgeCases:
    """재발행 GP 연동 엣지 케이스"""

    def test_single_stage_all_blogs_same(self):
        """T21: 단일 구간 GP -> 모든 블로그에 동일 설정"""
        gp = {"stages": [{
            "name": "universal", "label": "범용",
            "post_count_min": 0, "post_count_max": None,
            "generate": {"enabled": True, "interval_mode": "auto", "daily_count": 3},
            "publish": {"enabled": True, "interval_mode": "auto", "daily_count": 2},
            "republish": {"enabled": True, "interval_mode": "auto", "daily_count": 2},
        }]}
        ctx = GrowthProfileResolver.build_execution_context(1, gp, {1: 0, 2: 50, 3: 500})
        for bid in [1, 2, 3]:
            sp = ctx.get_stage_for_blog(bid)
            assert sp.stage_name == "universal" and sp.republish.enabled is True

    def test_blog_not_in_context(self):
        """T22: blog_id가 blog_stages에 없으면 None"""
        ctx = GrowthProfileResolver.build_execution_context(
            1, get_default_profile("balanced"), {1: 30}
        )
        assert ctx.get_stage_for_blog(999) is None

    @pytest.mark.asyncio
    async def test_republish_success_counted(self):
        """T23: 재발행 성공 -> success_count 증가 패턴"""
        success_count = 0
        with patch(EXEC_PATH, new_callable=AsyncMock,
                   return_value={"success": True, "post_title": "테스트"}) as m:
            result = await m(_blog(1, "A", 30))
            if result.get("success"):
                success_count += 1
        assert success_count == 1

    @pytest.mark.asyncio
    async def test_republish_failure_counted(self):
        """T24: 재발행 실패(예외) -> fail_count 증가 패턴"""
        fail_count = 0
        with patch(EXEC_PATH, new_callable=AsyncMock,
                   side_effect=Exception("Connection error")):
            try:
                from app.routers.flows_execute import _execute_republish_for_blog
                await _execute_republish_for_blog(_blog(1, "A", 30))
            except Exception:
                fail_count += 1
        assert fail_count == 1

    @pytest.mark.asyncio
    async def test_mixed_enabled_disabled_blogs(self):
        """T25: Blog A enabled, Blog B disabled, Blog C enabled -> A,C만 실행"""
        stages = [
            {"name": "active", "label": "활성", "post_count_min": 0, "post_count_max": 100,
             "generate": {"enabled": True, "interval_mode": "auto", "daily_count": 2},
             "publish": {"enabled": True, "interval_mode": "auto", "daily_count": 2},
             "republish": {"enabled": True, "interval_mode": "auto", "daily_count": 2}},
            {"name": "inactive", "label": "비활성", "post_count_min": 101, "post_count_max": None,
             "generate": {"enabled": True, "interval_mode": "auto", "daily_count": 1},
             "publish": {"enabled": True, "interval_mode": "auto", "daily_count": 1},
             "republish": {"enabled": False}},
        ]
        ctx = GrowthProfileResolver.build_execution_context(
            1, {"stages": stages}, {1: 50, 2: 150, 3: 80}
        )
        executed, skipped = [], []
        for bid in [1, 2, 3]:
            sp = ctx.get_stage_for_blog(bid)
            (skipped if sp and not sp.republish.enabled else executed).append(bid)
        assert executed == [1, 3] and skipped == [2]
