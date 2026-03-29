"""Phase D 통합 테스트: 발행(Publish) + 워밍업(Warmup) 검증 (26개)"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import pytz

from app.services.generation.warmup_manager import WarmupManager, WarmupStatus
from app.services.generation.publisher import Publisher
from app.services.generation.flow_execution_context import (
    FlowExecutionContext, StageParams,
)
from app.services.generation.growth_profile_resolver import GrowthProfileResolver
from app.services.generation.growth_profile_defaults import get_default_profile
from app.models.flow_execution_state import FlowExecutionState
from app.routers.flows_execute import _check_fes_interval, _update_fes_after_execution

KST = pytz.timezone("Asia/Seoul")
INV_PATH = "app.services.generation.publisher.InventoryManager"


# Mock 헬퍼 -----------------------------------------------------------

def _blog(bid, name="블로그"):
    b = MagicMock()
    b.id, b.name = bid, name
    b.platform = MagicMock(value="naver")
    return b

def _ws(enabled=True, days=14, initial=1, max_d=3, ramp=0.5):
    """워밍업 설정 dict"""
    return {"enabled": enabled, "warmup_days": days,
            "initial_daily_posts": initial, "max_daily_posts": max_d,
            "ramp_rate": ramp}

def _wstatus(active=False, elapsed=0, dmax=0, pub=0, can=True, eff=None):
    """WarmupStatus 축약 생성"""
    return WarmupStatus(is_active=active, days_elapsed=elapsed,
                        daily_max=dmax, today_published=pub,
                        can_publish=can, effective_interval=eff)

def _fes(flow_id=1, action_type="publish", blog_id=1, next_at=None, paused=False):
    s = MagicMock(spec=FlowExecutionState)
    s.flow_id, s.action_type, s.blog_id = flow_id, action_type, blog_id
    s.next_execution_at, s.is_paused = next_at, paused
    s.last_executed_at = None
    s.total_executions = s.successful_executions = s.failed_executions = 0
    s.record_execution = MagicMock()
    s.calculate_next_execution = MagicMock()
    return s

def _gp_ctx(jitter=None, blog_stages=None):
    return FlowExecutionContext(
        flow_id=1, growth_profile=get_default_profile("balanced"),
        schedule_matrix=[[True] * 24 for _ in range(7)],
        jitter=jitter or {"enabled": False},
        blog_stages=blog_stages or {},
    )

def _bstage(idx, ah=16):
    return StageParams.from_stage_dict(
        get_default_profile("balanced")["stages"][idx], ah)

async def _check_warmup(mgr, blog_id, ws, ah, first_pub, today_cnt=0):
    """WarmupManager.check_warmup 공통 래퍼"""
    with patch.object(mgr, "_get_first_publish_date", return_value=first_pub), \
         patch.object(mgr, "_count_today_publishes", return_value=today_cnt):
        return await mgr.check_warmup(blog_id, ws, ah)


# 클래스 1: TestWarmupDetection (5개) ------------------------------------

class TestWarmupDetection:
    """워밍업 대상 판별 검증"""

    @pytest.mark.asyncio
    async def test_no_publish_history_is_warmup_target(self):
        """T01: 발행 이력 0건 -> is_active=True, days_elapsed=-1"""
        st = await _check_warmup(WarmupManager(AsyncMock()), 1, _ws(), 16, None)
        assert st.is_active is True and st.days_elapsed == -1

    @pytest.mark.asyncio
    async def test_within_warmup_days(self):
        """T02: 첫 발행 후 3일, warmup_days=14 -> is_active=True, days_elapsed=3"""
        fp = datetime.now(KST) - timedelta(days=3)
        st = await _check_warmup(WarmupManager(AsyncMock()), 1, _ws(days=14), 16, fp)
        assert st.is_active is True and st.days_elapsed == 3

    @pytest.mark.asyncio
    async def test_warmup_completed(self):
        """T03: 첫 발행 후 15일, warmup_days=14 -> is_active=False"""
        fp = datetime.now(KST) - timedelta(days=15)
        st = await _check_warmup(WarmupManager(AsyncMock()), 1, _ws(days=14), 16, fp)
        assert st.is_active is False

    @pytest.mark.asyncio
    async def test_warmup_disabled(self):
        """T04: warmup.enabled=false -> is_active=False"""
        mgr = WarmupManager(AsyncMock())
        st = await mgr.check_warmup(1, _ws(enabled=False), 16)
        assert st.is_active is False

    @pytest.mark.asyncio
    async def test_warmup_settings_missing(self):
        """T05: warmup 설정 없음 (빈 dict) -> is_active=False"""
        mgr = WarmupManager(AsyncMock())
        st = await mgr.check_warmup(1, {}, 16)
        assert st.is_active is False


# 클래스 2: TestRampRateCalculation (5개) --------------------------------

class TestRampRateCalculation:
    """ramp_rate 기반 일일 발행 수 계산 검증"""

    def test_day_0_initial_daily_posts(self):
        """T06: Day 0(미발행), initial=1, ramp_rate=0.5 -> daily_max=1"""
        assert WarmupManager._calculate_daily_max(-1, 1, 3, 0.5) == 1

    def test_day_2_increment(self):
        """T07: Day 2, initial=1, ramp_rate=0.5 -> daily_max=2"""
        assert WarmupManager._calculate_daily_max(2, 1, 10, 0.5) == 2

    def test_max_daily_posts_cap(self):
        """T08: Day 100, initial=1, max=3, ramp_rate=0.5 -> daily_max=3"""
        assert WarmupManager._calculate_daily_max(100, 1, 3, 0.5) == 3

    @pytest.mark.asyncio
    async def test_warmup_publish_interval(self):
        """T09: daily_max=1, active_hours=16 -> effective_interval=960"""
        st = await _check_warmup(
            WarmupManager(AsyncMock()), 1, _ws(initial=1, ramp=0.5), 16, None)
        assert st.effective_interval == 960  # floor(16*60/1)

    @pytest.mark.asyncio
    async def test_warmup_interval_with_different_active_hours(self):
        """T10: daily_max=3, active_hours=12 -> effective_interval=240"""
        fp = datetime.now(KST) - timedelta(days=4)
        st = await _check_warmup(
            WarmupManager(AsyncMock()), 1,
            _ws(initial=1, max_d=5, ramp=0.5), 12, fp)
        assert st.daily_max == 3 and st.effective_interval == 240


# 클래스 3: TestPublishGPContext (4개) -----------------------------------

class TestPublishGPContext:
    """발행 모듈 GP 컨텍스트 연동 검증"""

    def test_publish_enabled_executes(self):
        """T11: balanced profile publish.enabled=true -> 발행 가능"""
        assert _bstage(0).publish.enabled is True

    def test_publish_disabled_skips(self):
        """T12: publish.enabled=false -> 스킵"""
        sp = _bstage(2)  # balanced stable
        assert sp.publish.enabled is False

    def test_stage_mapping_correct(self):
        """T13: balanced profile 스테이지별 publish 설정 확인"""
        assert _bstage(0).publish.enabled is True   # rapid_growth
        assert _bstage(1).publish.enabled is True   # growth
        assert _bstage(2).publish.enabled is False   # stable

    def test_publish_without_gp_rejected(self):
        """T14: GP 없이 publish 모듈 -> stage 없으므로 None"""
        assert _gp_ctx().get_stage_for_blog(1) is None


# 클래스 4: TestPublisherService (4개) -----------------------------------

class TestPublisherService:
    """Publisher 서비스 로직 검증"""

    @pytest.mark.asyncio
    async def test_publish_with_inventory(self):
        """T15: 재고 있음, warmup 비활성 -> success=True, post_id 반환"""
        post = MagicMock(); post.id, post.title = 100, "테스트 포스트 제목"
        with patch(f"{INV_PATH}.get_post_for_publish",
                   new_callable=AsyncMock, return_value=post):
            r = await Publisher(AsyncMock()).publish_for_blog(
                _blog(1, "테스트"), _wstatus(can=True))
        assert r["success"] is True and r["post_id"] == 100
        assert "skipped" not in r

    @pytest.mark.asyncio
    async def test_publish_no_inventory_skips(self):
        """T16: 재고 없음 -> skipped=True"""
        with patch(f"{INV_PATH}.get_post_for_publish",
                   new_callable=AsyncMock, return_value=None):
            r = await Publisher(AsyncMock()).publish_for_blog(
                _blog(1, "빈블로그"), _wstatus(can=True))
        assert r["skipped"] is True

    @pytest.mark.asyncio
    async def test_warmup_daily_max_exceeded_skips(self):
        """T17: warmup 활성, can_publish=false -> skipped=True"""
        ws = _wstatus(active=True, elapsed=2, dmax=2, pub=2, can=False, eff=480)
        r = await Publisher(AsyncMock()).publish_for_blog(_blog(1, "워밍업"), ws)
        assert r["skipped"] is True and "한도" in r["message"]

    @pytest.mark.asyncio
    async def test_publish_returns_crawled_post(self):
        """T18: 발행 결과에 crawled_post 객체 포함"""
        post = MagicMock(); post.id, post.title = 200, "발행 대상 글"
        with patch(f"{INV_PATH}.get_post_for_publish",
                   new_callable=AsyncMock, return_value=post):
            r = await Publisher(AsyncMock()).publish_for_blog(
                _blog(1, "발행"), _wstatus(can=True))
        assert r["crawled_post"] is post


# 클래스 5: TestFESIntervalCheck (5개) -----------------------------------

class TestFESIntervalCheck:
    """FES 간격 체크 헬퍼 함수 검증"""

    def test_interval_elapsed_allows_execution(self):
        """T19: next_execution_at 경과 -> True"""
        now = datetime.now(KST)
        assert _check_fes_interval(
            _fes(next_at=now - timedelta(minutes=10)), now) is True

    def test_interval_not_elapsed_blocks(self):
        """T20: next_execution_at 미경과 -> False"""
        now = datetime.now(KST)
        assert _check_fes_interval(
            _fes(next_at=now + timedelta(minutes=30)), now) is False

    def test_blog_id_independent_tracking(self):
        """T21: 같은 flow+module, 다른 blog_id -> 독립 FES"""
        now = datetime.now(KST)
        sa = _fes(blog_id=1, next_at=now - timedelta(minutes=5))
        sb = _fes(blog_id=2, next_at=now + timedelta(minutes=30))
        assert _check_fes_interval(sa, now) is True
        assert _check_fes_interval(sb, now) is False
        assert sa.blog_id != sb.blog_id

    def test_jitter_applied_in_range(self):
        """T22: jitter 설정 시 next_execution_at 계산됨"""
        state = FlowExecutionState()
        state.flow_id, state.action_type, state.blog_id = 1, "publish", 1
        state.total_executions = state.successful_executions = 0
        state.failed_executions = 0
        state.is_paused = False
        state.last_executed_at = datetime.now(KST)
        state.next_execution_at = None
        ctx = _gp_ctx(jitter={"enabled": True, "min_percent": -20,
                               "max_percent": 30})
        _update_fes_after_execution(state, True, 100, ctx)
        assert state.next_execution_at is not None

    def test_first_execution_immediate(self):
        """T23: FES.next_execution_at=None -> True (첫 실행)"""
        assert _check_fes_interval(
            _fes(next_at=None), datetime.now(KST)) is True


# 클래스 6: TestWarmupGenerateNonInterference (3개) ----------------------

class TestWarmupGenerateNonInterference:
    """워밍업이 generate/republish에 간섭하지 않는지 검증"""

    def test_generate_unaffected_during_warmup(self):
        """T24: 워밍업 활성 블로그에서 generate는 스테이지대로 동작"""
        ctx = GrowthProfileResolver.build_execution_context(
            1, get_default_profile("balanced"), {1: 10})
        sp = ctx.get_stage_for_blog(1)
        assert sp.stage_name == "rapid_growth"
        assert sp.generate.enabled is True and sp.generate.daily_count == 5

    def test_republish_unaffected_during_warmup(self):
        """T25: 워밍업 활성 블로그에서 republish는 워밍업과 무관"""
        ctx = GrowthProfileResolver.build_execution_context(
            1, get_default_profile("balanced"), {1: 10})
        sp = ctx.get_stage_for_blog(1)
        assert sp.republish.enabled is True and sp.republish.daily_count == 3

    @pytest.mark.asyncio
    async def test_warmup_end_transitions_to_stage(self):
        """T26: warmup_days 경과 후 publish가 스테이지 interval로 전환"""
        fp = datetime.now(KST) - timedelta(days=15)
        st = await _check_warmup(
            WarmupManager(AsyncMock()), 1, _ws(days=14), 16, fp)
        assert st.is_active is False and st.effective_interval is None
        assert st.can_publish is True
        # 스테이지 interval로 전환 확인
        ctx = GrowthProfileResolver.build_execution_context(
            1, get_default_profile("balanced"), {1: 10})
        assert ctx.get_stage_for_blog(1).publish.computed_interval is not None
