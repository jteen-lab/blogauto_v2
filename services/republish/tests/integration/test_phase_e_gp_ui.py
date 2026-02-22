"""
Phase E 통합 테스트: Growth Profile UI API + 설정 직렬화 검증 (15개)
"""
import copy
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.generation.growth_profile_defaults import (
    DEFAULT_PROFILES,
    get_default_profile,
    get_available_profiles,
)
from app.services.generation.growth_profile_resolver import GrowthProfileResolver
from app.services.generation.flow_execution_context import (
    FlowExecutionContext,
    StageParams,
    ModuleIntervalParams,
)
from app.api.growth_profile import _format_module_info


# ============================================================
# 클래스 1: TestPresetAPI (4개)
# ============================================================

class TestPresetAPI:
    """프리셋 API 검증"""

    def test_get_presets_list(self):
        """T01: get_available_profiles → 3종 반환"""
        profiles = get_available_profiles()
        keys = [p["key"] for p in profiles]
        assert set(keys) == {"aggressive", "balanced", "conservative"}
        assert len(profiles) == 3
        # 각 프로파일에 필수 필드 존재
        for p in profiles:
            assert "name" in p
            assert "description" in p
            assert "stages_count" in p

    def test_get_preset_detail_balanced(self):
        """T02: balanced 프리셋 → schedule_matrix + stages + warmup 포함"""
        profile = get_default_profile("balanced")
        assert "schedule_matrix" in profile
        assert "stages" in profile
        assert "warmup" in profile
        assert len(profile["schedule_matrix"]) == 7
        assert all(len(row) == 24 for row in profile["schedule_matrix"])
        assert len(profile["stages"]) == 3
        assert profile["warmup"]["enabled"] is True

    def test_get_preset_detail_invalid(self):
        """T03: 존재하지 않는 프리셋 키 → KeyError"""
        with pytest.raises(KeyError):
            get_default_profile("nonexistent")

    def test_preset_stages_valid(self):
        """T04: 각 프리셋의 stages 연속성 검증"""
        for key in ["aggressive", "balanced", "conservative"]:
            profile = get_default_profile(key)
            valid, error = GrowthProfileResolver.validate_stages(
                profile["stages"]
            )
            assert valid is True, f"{key}: {error}"


# ============================================================
# 클래스 2: TestPreviewAPI (4개)
# ============================================================

class TestPreviewAPI:
    """프리뷰 API 검증"""

    def test_preview_with_blogs(self):
        """T05: balanced + 3개 블로그 → 올바른 스테이지 매핑"""
        settings = get_default_profile("balanced")
        blog_counts = {1: 30, 2: 100, 3: 200}
        ctx = GrowthProfileResolver.build_execution_context(
            flow_id=1, gp_settings=settings, blog_post_counts=blog_counts,
        )
        # balanced: rapid_growth(0~50), growth(51~150), stable(151~None)
        assert ctx.get_stage_for_blog(1).stage_name == "rapid_growth"
        assert ctx.get_stage_for_blog(2).stage_name == "growth"
        assert ctx.get_stage_for_blog(3).stage_name == "stable"

    def test_preview_no_flow_id(self):
        """T06: flow_id 없이 → context 생성 가능 (flow_id=0)"""
        settings = get_default_profile("balanced")
        ctx = GrowthProfileResolver.build_execution_context(
            flow_id=0, gp_settings=settings, blog_post_counts={1: 30},
        )
        assert ctx.get_stage_for_blog(1) is not None

    def test_preview_empty_blogs(self):
        """T07: 블로그 0개 → 빈 blog_stages"""
        settings = get_default_profile("balanced")
        ctx = GrowthProfileResolver.build_execution_context(
            flow_id=1, gp_settings=settings, blog_post_counts={},
        )
        assert ctx.get_stage_for_blog(999) is None

    def test_preview_invalid_settings(self):
        """T08: 빈 stages → ValueError"""
        settings = {"stages": [], "schedule_matrix": None}
        with pytest.raises(ValueError):
            GrowthProfileResolver.build_execution_context(
                flow_id=1, gp_settings=settings, blog_post_counts={1: 30},
            )


# ============================================================
# 클래스 3: TestSettingsSerialization (4개)
# ============================================================

class TestSettingsSerialization:
    """설정 직렬화/역직렬화 검증 (JS toSettings/initFromSettings 로직 Python 검증)"""

    def _simulate_to_settings(self, settings: dict) -> dict:
        """JS toSettings() 로직을 Python으로 시뮬레이션"""
        result = {
            "schedule_matrix": settings.get("schedule_matrix"),
            "jitter": settings.get("jitter"),
            "stages": [],
            "warmup": settings.get("warmup", {"enabled": False}),
        }
        for s in settings.get("stages", []):
            stage = {
                "name": s["name"],
                "label": s["label"],
                "post_count_min": s["post_count_min"],
                "post_count_max": s["post_count_max"],
                "description": s.get("description", ""),
                "generate": {
                    "enabled": s["generate"]["enabled"],
                    "min_inventory": s["generate"].get("min_inventory") if s["generate"]["enabled"] else None,
                    "interval_mode": s["generate"].get("interval_mode") if s["generate"]["enabled"] else None,
                    "interval_minutes": s["generate"].get("interval_minutes") if s["generate"].get("interval_mode") == "manual" else None,
                    "daily_count": s["generate"].get("daily_count") if s["generate"].get("interval_mode") == "auto" else None,
                },
                "publish": {
                    "enabled": s["publish"]["enabled"],
                    "interval_mode": s["publish"].get("interval_mode") if s["publish"]["enabled"] else None,
                    "interval_minutes": s["publish"].get("interval_minutes") if s["publish"].get("interval_mode") == "manual" else None,
                    "daily_count": s["publish"].get("daily_count") if s["publish"].get("interval_mode") == "auto" else None,
                },
                "republish": {
                    "enabled": s["republish"]["enabled"],
                    "interval_mode": s["republish"].get("interval_mode") if s["republish"]["enabled"] else None,
                    "interval_minutes": s["republish"].get("interval_minutes") if s["republish"].get("interval_mode") == "manual" else None,
                    "daily_count": s["republish"].get("daily_count") if s["republish"].get("interval_mode") == "auto" else None,
                },
            }
            result["stages"].append(stage)
        if not result["warmup"].get("enabled"):
            result["warmup"] = {"enabled": False}
        return result

    def test_balanced_roundtrip(self):
        """T09: balanced → toSettings → 동일 구조 유지"""
        original = get_default_profile("balanced")
        serialized = self._simulate_to_settings(original)

        assert len(serialized["stages"]) == 3
        assert serialized["schedule_matrix"] == original["schedule_matrix"]
        assert serialized["warmup"]["enabled"] is True

        # stages[0] generate: enabled=True, interval_mode=auto
        gen = serialized["stages"][0]["generate"]
        assert gen["enabled"] is True
        assert gen["interval_mode"] == "auto"
        assert gen["daily_count"] == 5  # balanced rapid_growth
        assert gen["interval_minutes"] is None  # auto이므로

    def test_disabled_module_clears_interval(self):
        """T10: enabled=false → interval 관련 필드 모두 null"""
        settings = get_default_profile("balanced")
        # balanced stable stage의 publish.enabled=False
        serialized = self._simulate_to_settings(settings)
        stable_pub = serialized["stages"][2]["publish"]
        assert stable_pub["enabled"] is False
        assert stable_pub["interval_mode"] is None
        assert stable_pub["interval_minutes"] is None
        assert stable_pub["daily_count"] is None

    def test_stage_continuity_auto_fix(self):
        """T11: max=50, 다음 min=55 → validateContinuity 보정"""
        settings = get_default_profile("balanced")
        # 원본: stages[0].max=50, stages[1].min=51
        # 불일치 만들기: stages[1].min을 55로 변경
        settings["stages"][1]["post_count_min"] = 55
        valid, error = GrowthProfileResolver.validate_stages(
            settings["stages"]
        )
        assert valid is False
        assert "51" in error  # expected min 51

    def test_last_stage_max_null(self):
        """T12: 마지막 구간 max는 항상 null"""
        for key in ["aggressive", "balanced", "conservative"]:
            profile = get_default_profile(key)
            last_stage = profile["stages"][-1]
            assert last_stage["post_count_max"] is None


# ============================================================
# 클래스 4: TestFormatModuleInfo (3개)
# ============================================================

class TestFormatModuleInfo:
    """_format_module_info 헬퍼 함수 검증"""

    def _make_params(self, enabled, interval_mode=None,
                     daily_count=None, interval_minutes=None):
        """ModuleIntervalParams Mock 생성"""
        p = MagicMock()
        p.enabled = enabled
        p.interval_mode = interval_mode
        p.daily_count = daily_count
        p.interval_minutes = interval_minutes
        return p

    def test_disabled_returns_none(self):
        """T13: enabled=false → None 반환"""
        params = self._make_params(enabled=False)
        result = _format_module_info(params, "생성", 16)
        assert result is None

    def test_auto_mode_format(self):
        """T14: auto + daily_count=3 → '하루 3회'"""
        params = self._make_params(
            enabled=True, interval_mode="auto", daily_count=3
        )
        result = _format_module_info(params, "생성", 16)
        assert result == "하루 3회"

    def test_manual_mode_format(self):
        """T15: manual + interval_minutes=120 → '120분 간격'"""
        params = self._make_params(
            enabled=True, interval_mode="manual", interval_minutes=120
        )
        result = _format_module_info(params, "발행", 16)
        assert result == "120분 간격"
