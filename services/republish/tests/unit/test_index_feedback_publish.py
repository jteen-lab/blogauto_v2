"""색인 되먹임은 발행에 건다 — 생성이 아니라.

2026-09-08 실측: 12개 블로그 전부 색인 0건이라 되먹임이 생성을 하루 1개로
묶었고, 그 결과 미발행 재고가 0~3개까지 말랐다. 색인이 회복돼도 낼 글이
없다. 구글이 보는 것은 발행된 글이지 우리 DB 의 재고가 아니다.
"""
import pathlib

import pytest

from app.services.generation.index_feedback import (
    CAP_POOR, IndexVerdict, MIN_SAMPLE, STOP_AFTER_DAYS, _verdict,
    cap_note, effective_cap,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _v(cap=None, stop=False, reason="", ratio=0.0):
    return IndexVerdict(20, 0, ratio, cap, stop, reason)


class TestWhereItApplies:
    def test_generation_no_longer_capped(self):
        """생성은 재고 상한이 막는다. 되먹임까지 걸면 이중이다."""
        src = (ROOT / "app/services/generation/flow_generate_executor.py"
               ).read_text(encoding="utf-8")
        assert "IndexFeedback" not in src
        assert "verdict.cap" not in src

    def test_generation_still_stops_on_full_inventory(self):
        """되먹임을 뺐다고 무한 생성이 되면 안 된다."""
        src = (ROOT / "app/services/generation/flow_generate_executor.py"
               ).read_text(encoding="utf-8")
        assert "check_result.needs_generation" in src
        assert "min_inventory" in src

    def test_publish_applies_it(self):
        src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(
            encoding="utf-8")
        assert "publish_caps" in src
        assert "effective_cap" in src

    def test_one_blog_cap_does_not_stop_the_flow(self):
        """예전에는 한 블로그가 한도에 걸리면 return 으로 전체가 멈췄다."""
        src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(
            encoding="utf-8")
        block = src[src.index("publish_caps.get("):]
        head = block[:block.index("# 재고 ON/OFF")]
        assert "continue" in head
        assert "return" not in head


class TestEffectiveCap:
    @pytest.mark.parametrize("gp,cap,expected", [
        (2, 1, 1),        # 되먹임이 더 엄격
        (1, 2, 1),        # GP 가 더 엄격
        (2, None, 2),     # 되먹임 제한 없음
        (None, 1, 1),     # GP 미설정
        (None, None, None),
    ])
    def test_takes_the_smaller(self, gp, cap, expected):
        assert effective_cap(gp, _v(cap=cap) if cap is not None
                             else _v()) == expected

    def test_feedback_off_keeps_gp(self):
        assert effective_cap(2, None) == 2


class TestLogMessage:
    """막을 때는 사유를 남긴다. 조용히 멈추면 고장과 구분되지 않는다."""

    def test_states_gp_and_actual(self):
        note = cap_note(2, _v(cap=1, reason="색인 0건 — 하루 1개로 제한"))
        assert "색인 0건" in note
        assert "성장 프로파일 2개" in note
        assert "되먹임 1개" in note

    def test_no_note_when_not_reduced(self):
        assert cap_note(1, _v(cap=1, reason="x")) == " — x"

    def test_silent_when_unrestricted(self):
        assert cap_note(2, _v(cap=None)) == ""
        assert cap_note(2, None) == ""


class TestVerdictTiers:
    @pytest.mark.parametrize("checked,indexed,days,expected_cap", [
        (20, 10, 5, None),      # 50% — 정상
        (20, 3, 5, 1),          # 15% — 절반(base 2 → 1)
        (20, 1, 5, CAP_POOR),   # 5%
        (20, 0, 5, CAP_POOR),   # 0%, 아직 짧다
        (MIN_SAMPLE - 1, 0, 90, None),   # 표본 부족 — 새 블로그를 막지 않는다
    ])
    def test_tiers(self, checked, indexed, days, expected_cap):
        assert _verdict(checked, indexed, days, 2).cap == expected_cap

    def test_stop_after_long_zero(self):
        found = _verdict(20, 0, STOP_AFTER_DAYS, 2)
        assert found.stop is True
        assert "발행을 멈춥니다" in found.reason


class TestZeroStreakMeasurement:
    """지속 일수를 30일 창 안에서 재면 30을 넘을 수 없다."""

    def test_measured_outside_the_window(self):
        src = (ROOT / "app/services/generation/index_feedback.py").read_text(
            encoding="utf-8")
        block = src[src.index("if checked and not indexed:"):]
        head = block[:block.index("verdict = _verdict")]
        # 전체 이력을 보는 별도 질의여야 한다
        assert "published_at >= since" not in head
        assert "func.min(SearchVisibilityUrl.published_at)" in head

    def test_window_query_no_longer_takes_min(self):
        src = (ROOT / "app/services/generation/index_feedback.py").read_text(
            encoding="utf-8")
        window = src[src.index("since = datetime.now"):
                     src.index("if checked and not indexed:")]
        assert "func.min" not in window


class TestStopIsOptIn:
    """실측상 12개 블로그가 36~79일째 0건 — 그대로 켜면 전부 멈춘다."""

    def test_stop_has_its_own_switch(self):
        from app.services.generation.index_feedback import (
            SETTING_KEY, SETTING_STOP_KEY,
        )
        assert SETTING_STOP_KEY != SETTING_KEY

    def test_default_is_off(self):
        src = (ROOT / "app/services/generation/index_feedback.py").read_text(
            encoding="utf-8")
        block = src[src.index("async def stop_enabled"):]
        head = block[:block.index("async def is_enabled")]
        assert "return False" in head, "기본은 꺼짐이어야 한다"

    def test_downgraded_verdict_says_so(self):
        src = (ROOT / "app/services/generation/index_feedback.py").read_text(
            encoding="utf-8")
        assert "정지 조건 충족, 정지는 꺼져 있음" in src


class TestManualRunCarriesProfile:
    """수동 실행만 GP 가 빠져 로그에 사유가 안 찍혔다."""

    def test_no_hardcoded_none(self):
        src = (ROOT / "app/routers/flows_execute.py").read_text(
            encoding="utf-8")
        assert "stage_params_dict=None" not in src

    def test_uses_same_resolver_as_scheduler(self):
        src = (ROOT / "app/routers/flows_execute.py").read_text(
            encoding="utf-8")
        block = src[src.index("async def _resolve_blog_stages"):]
        head = block[:block.index("async def _build_growth_profile_context")]
        assert "resolve_stage_for_blog" in head
        assert "count_active_hours" in head
