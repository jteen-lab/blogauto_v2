"""
Growth Profile Resolver 통합 테스트 (Phase A)

GrowthProfileResolver의 스테이지 매핑, 간격 계산, 활성 시간 체크,
stages 연속성 검증, 기본 프로파일, 컨텍스트 빌드를 검증합니다.

테스트 대상:
- app/services/generation/growth_profile_resolver.py
- app/services/generation/flow_execution_context.py
- app/services/generation/growth_profile_defaults.py
"""
import pytest

from app.services.generation.flow_execution_context import (
    FlowExecutionContext,
    StageParams,
    ModuleIntervalParams,
)
from app.services.generation.growth_profile_resolver import GrowthProfileResolver
from app.services.generation.growth_profile_defaults import (
    DEFAULT_PROFILES,
    get_default_profile,
    get_available_profiles,
)


# ============================================================
# 공통 Fixtures
# ============================================================

def _make_stages() -> list:
    """테스트용 3단계 stages 배열 (balanced 프로파일 기준)"""
    return [
        {
            "name": "rapid_growth",
            "label": "급성장기",
            "post_count_min": 0,
            "post_count_max": 50,
            "generate": {
                "enabled": True,
                "min_inventory": 10,
                "interval_mode": "auto",
                "interval_minutes": None,
                "daily_count": 5,
            },
            "publish": {
                "enabled": True,
                "interval_mode": "manual",
                "interval_minutes": 120,
                "daily_count": None,
            },
            "republish": {
                "enabled": True,
                "interval_mode": "auto",
                "interval_minutes": None,
                "daily_count": 3,
            },
        },
        {
            "name": "growth",
            "label": "성장기",
            "post_count_min": 51,
            "post_count_max": 150,
            "generate": {
                "enabled": True,
                "min_inventory": 5,
                "interval_mode": "auto",
                "interval_minutes": None,
                "daily_count": 3,
            },
            "publish": {
                "enabled": True,
                "interval_mode": "auto",
                "interval_minutes": None,
                "daily_count": 2,
            },
            "republish": {
                "enabled": True,
                "interval_mode": "auto",
                "interval_minutes": None,
                "daily_count": 3,
            },
        },
        {
            "name": "stable",
            "label": "안정기",
            "post_count_min": 151,
            "post_count_max": None,
            "generate": {
                "enabled": True,
                "min_inventory": 3,
                "interval_mode": "manual",
                "interval_minutes": 360,
                "daily_count": None,
            },
            "publish": {
                "enabled": False,
                "interval_mode": "auto",
                "interval_minutes": None,
                "daily_count": None,
            },
            "republish": {
                "enabled": True,
                "interval_mode": "auto",
                "interval_minutes": None,
                "daily_count": 2,
            },
        },
    ]


def _make_schedule_matrix_16h() -> list:
    """6~21시 활성 (평일 16시간, 주말 14시간) 매트릭스"""
    matrix = []
    for day in range(7):
        if day < 5:
            row = [6 <= h <= 21 for h in range(24)]
        else:
            row = [7 <= h <= 20 for h in range(24)]
        matrix.append(row)
    return matrix


# ============================================================
# 클래스 1: TestResolveStageForBlog (스테이지 매핑) - T01~T08
# ============================================================

class TestResolveStageForBlog:
    """resolve_stage_for_blog: 포스트 수 → 스테이지 매핑"""

    def test_rapid_growth_stage(self):
        """T01: 급성장기 매핑 (30글)"""
        stages = _make_stages()
        result = GrowthProfileResolver.resolve_stage_for_blog(30, stages)
        assert result["name"] == "rapid_growth"

    def test_growth_stage(self):
        """T02: 성장기 매핑 (100글)"""
        stages = _make_stages()
        result = GrowthProfileResolver.resolve_stage_for_blog(100, stages)
        assert result["name"] == "growth"

    def test_stable_stage(self):
        """T03: 안정기 매핑 (200글)"""
        stages = _make_stages()
        result = GrowthProfileResolver.resolve_stage_for_blog(200, stages)
        assert result["name"] == "stable"

    def test_boundary_inclusive_max(self):
        """T04: 경계값 max inclusive (50글 = rapid_growth)"""
        stages = _make_stages()
        result = GrowthProfileResolver.resolve_stage_for_blog(50, stages)
        assert result["name"] == "rapid_growth"

    def test_boundary_next_stage(self):
        """T05: 경계값 전환 (51글 = growth)"""
        stages = _make_stages()
        result = GrowthProfileResolver.resolve_stage_for_blog(51, stages)
        assert result["name"] == "growth"

    def test_last_stage_null_max(self):
        """T06: 마지막 null max (9999글)"""
        stages = _make_stages()
        result = GrowthProfileResolver.resolve_stage_for_blog(9999, stages)
        assert result["name"] == "stable"

    def test_zero_posts(self):
        """T07: 포스트 0건 → 첫 스테이지"""
        stages = _make_stages()
        result = GrowthProfileResolver.resolve_stage_for_blog(0, stages)
        assert result["name"] == "rapid_growth"

    def test_single_stage(self):
        """T08: 단일 구간 (0~null)"""
        stages = [
            {
                "name": "only_stage",
                "label": "유일한 구간",
                "post_count_min": 0,
                "post_count_max": None,
                "generate": {"enabled": True, "interval_mode": "auto", "daily_count": 3},
            }
        ]
        result = GrowthProfileResolver.resolve_stage_for_blog(100, stages)
        assert result["name"] == "only_stage"


# ============================================================
# 클래스 2: TestComputeInterval (간격 계산) - T09~T13
# ============================================================

class TestComputeInterval:
    """ModuleIntervalParams.from_stage_dict: 간격 계산"""

    def test_manual_mode(self):
        """T09: manual 모드 → interval_minutes 그대로"""
        params = ModuleIntervalParams.from_stage_dict(
            {"enabled": True, "interval_mode": "manual", "interval_minutes": 120},
            active_hours=16,
        )
        assert params.computed_interval == 120

    def test_auto_mode_active_hours(self):
        """T10: auto 모드 → active_hours * 60 / daily_count"""
        params = ModuleIntervalParams.from_stage_dict(
            {"enabled": True, "interval_mode": "auto", "daily_count": 5},
            active_hours=16,
        )
        # 16 * 60 / 5 = 192
        assert params.computed_interval == 192

    def test_auto_mode_different_hours(self):
        """T11: auto 모드 다른 활성시간 (12시간, 3회)"""
        params = ModuleIntervalParams.from_stage_dict(
            {"enabled": True, "interval_mode": "auto", "daily_count": 3},
            active_hours=12,
        )
        # 12 * 60 / 3 = 240
        assert params.computed_interval == 240

    def test_auto_mode_minimum_5min(self):
        """T12: auto 최소값 보장 (200회/일 → max(5, 4.8) = 5)"""
        params = ModuleIntervalParams.from_stage_dict(
            {"enabled": True, "interval_mode": "auto", "daily_count": 200},
            active_hours=16,
        )
        assert params.computed_interval == 5

    def test_disabled_module(self):
        """T13: enabled=false → computed=None"""
        params = ModuleIntervalParams.from_stage_dict(
            {"enabled": False},
            active_hours=16,
        )
        assert params.enabled is False
        assert params.computed_interval is None


# ============================================================
# 클래스 3: TestActiveHours (활성 시간 체크) - T14~T17
# ============================================================

class TestActiveHours:
    """FlowExecutionContext.is_active_time, count_active_hours"""

    def test_active_hour_true(self):
        """T14: 활성 시간대 → True"""
        matrix = _make_schedule_matrix_16h()
        ctx = FlowExecutionContext(
            flow_id=1, schedule_matrix=matrix
        )
        # 월요일(0) 10시 → 활성
        assert ctx.is_active_time(weekday=0, hour=10) is True

    def test_inactive_hour_false(self):
        """T15: 비활성 시간대 → False"""
        matrix = _make_schedule_matrix_16h()
        ctx = FlowExecutionContext(
            flow_id=1, schedule_matrix=matrix
        )
        # 월요일(0) 3시 → 비활성
        assert ctx.is_active_time(weekday=0, hour=3) is False

    def test_no_matrix_always_active(self):
        """T16: matrix=None → 항상 True"""
        ctx = FlowExecutionContext(flow_id=1, schedule_matrix=None)
        assert ctx.is_active_time(weekday=0, hour=3) is True

    def test_count_active_hours(self):
        """T17: 평일 6~21시 활성 = 16시간"""
        matrix = _make_schedule_matrix_16h()
        count = GrowthProfileResolver.count_active_hours(matrix, weekday=0)
        assert count == 16


# ============================================================
# 클래스 4: TestValidateStages (연속성 검증) - T18~T22
# ============================================================

class TestValidateStages:
    """validate_stages: stages 배열 유효성 검증"""

    def test_valid_continuous_stages(self):
        """T18: 정상 연속 stages → (True, None)"""
        stages = _make_stages()
        valid, error = GrowthProfileResolver.validate_stages(stages)
        assert valid is True
        assert error is None

    def test_gap_detection(self):
        """T19: 빈 범위 감지 (0~50, 52~150) → gap"""
        stages = [
            {"name": "s1", "label": "S1", "post_count_min": 0, "post_count_max": 50},
            {"name": "s2", "label": "S2", "post_count_min": 52, "post_count_max": 150},
        ]
        valid, error = GrowthProfileResolver.validate_stages(stages)
        assert valid is False
        assert "52" in error and "51" in error

    def test_overlap_detection(self):
        """T20: 겹침 감지 (0~50, 50~150) → overlap"""
        stages = [
            {"name": "s1", "label": "S1", "post_count_min": 0, "post_count_max": 50},
            {"name": "s2", "label": "S2", "post_count_min": 50, "post_count_max": 150},
        ]
        valid, error = GrowthProfileResolver.validate_stages(stages)
        assert valid is False
        assert "50" in error and "51" in error

    def test_empty_stages(self):
        """T21: 빈 배열 → (False, 에러)"""
        valid, error = GrowthProfileResolver.validate_stages([])
        assert valid is False
        assert "비어있습니다" in error

    def test_single_stage_valid(self):
        """T22: 단일 구간 (0~null) → (True, None)"""
        stages = [
            {"name": "only", "label": "Only", "post_count_min": 0, "post_count_max": None},
        ]
        valid, error = GrowthProfileResolver.validate_stages(stages)
        assert valid is True
        assert error is None


# ============================================================
# 클래스 5: TestDefaultProfiles (기본 프로파일) - T23~T25
# ============================================================

class TestDefaultProfiles:
    """DEFAULT_PROFILES, get_default_profile, get_available_profiles"""

    def test_all_profiles_exist(self):
        """T23: aggressive, balanced, conservative 3종 존재"""
        assert "aggressive" in DEFAULT_PROFILES
        assert "balanced" in DEFAULT_PROFILES
        assert "conservative" in DEFAULT_PROFILES
        assert len(DEFAULT_PROFILES) == 3

    def test_profiles_stages_valid(self):
        """T24: 각 프로파일의 stages가 validate_stages 통과"""
        for key, profile in DEFAULT_PROFILES.items():
            valid, error = GrowthProfileResolver.validate_stages(
                profile["stages"]
            )
            assert valid is True, f"Profile '{key}' failed: {error}"

    def test_profiles_schedule_matrix_shape(self):
        """T25: 각 프로파일의 schedule_matrix가 7x24 형태"""
        for key, profile in DEFAULT_PROFILES.items():
            matrix = profile["schedule_matrix"]
            assert len(matrix) == 7, f"Profile '{key}': rows != 7"
            for day_idx, row in enumerate(matrix):
                assert len(row) == 24, (
                    f"Profile '{key}' day {day_idx}: cols != 24"
                )


# ============================================================
# 클래스 6: TestBuildExecutionContext (통합) - T26~T27
# ============================================================

class TestBuildExecutionContext:
    """build_execution_context: 전체 파이프라인 통합"""

    def test_build_context_multiple_blogs(self):
        """T26: 블로그 3개 (30글, 100글, 200글) → 올바른 스테이지 매핑"""
        gp_settings = get_default_profile("balanced")
        blog_post_counts = {10: 30, 20: 100, 30: 200}

        context = GrowthProfileResolver.build_execution_context(
            flow_id=1,
            gp_settings=gp_settings,
            blog_post_counts=blog_post_counts,
        )

        assert context.flow_id == 1
        assert len(context.blog_stages) == 3

        # blog 10: 30글 → rapid_growth
        assert context.blog_stages[10].stage_name == "rapid_growth"
        # blog 20: 100글 → growth
        assert context.blog_stages[20].stage_name == "growth"
        # blog 30: 200글 → stable
        assert context.blog_stages[30].stage_name == "stable"

        # has_growth_profile 확인
        assert context.has_growth_profile() is True

        # get_stage_for_blog 확인
        stage_10 = context.get_stage_for_blog(10)
        assert stage_10 is not None
        assert stage_10.generate.enabled is True

        # 존재하지 않는 blog_id → None
        assert context.get_stage_for_blog(999) is None

    def test_build_context_invalid_stages(self):
        """T27: stages 빈 구간 → ValueError"""
        gp_settings = {
            "schedule_matrix": _make_schedule_matrix_16h(),
            "jitter": {"enabled": True, "min_percent": -20, "max_percent": 30},
            "stages": [
                {"name": "s1", "label": "S1", "post_count_min": 0, "post_count_max": 50},
                {"name": "s2", "label": "S2", "post_count_min": 55, "post_count_max": 150},
            ],
        }
        with pytest.raises(ValueError, match="stages 검증 실패"):
            GrowthProfileResolver.build_execution_context(
                flow_id=1,
                gp_settings=gp_settings,
                blog_post_counts={10: 30},
            )


# ============================================================
# 클래스 7: TestHelperFunctions (유틸리티) - T28~T30
# ============================================================

class TestHelperFunctions:
    """기타 유틸리티 함수 테스트"""

    def test_get_default_profile_invalid_key(self):
        """T28: 존재하지 않는 프로파일 키 → KeyError"""
        with pytest.raises(KeyError, match="Unknown profile"):
            get_default_profile("nonexistent")

    def test_count_active_hours_no_matrix(self):
        """T29: schedule_matrix=None → 24 반환"""
        count = GrowthProfileResolver.count_active_hours(None)
        assert count == 24

    def test_validate_stages_first_min_not_zero(self):
        """T30: 첫 stage의 min=5 (0이 아님) → (False, 에러)"""
        stages = [
            {"name": "s1", "label": "S1", "post_count_min": 5, "post_count_max": None},
        ]
        valid, error = GrowthProfileResolver.validate_stages(stages)
        assert valid is False
        assert "0이어야 합니다" in error
