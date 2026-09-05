"""유입 분석 P1~P4 — 수집부터 재발행 판정까지.

재발행이 날짜만 보고 돌아 잘 되는 글도 갈아엎었다. 유입을 붙여 글마다
동작을 다르게 정한다. 여기서 지키는 것은 셋이다.

1. URL 을 못 맞추면 조용히 0건이 된다 → 멀쩡한 글이 '유입 없음' 이 된다
2. 데이터가 없을 때 0 으로 읽으면 안 된다 → 판정 보류여야 한다
3. '건드리지 않는다' 가 실제로 실행을 건너뛰어야 한다
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestUrlMatch:
    """세 곳이 서로 다른 모양으로 같은 글을 가리킨다."""

    @pytest.mark.parametrize("raw", [
        "https://carin4note.blogspot.com/2026/09/foo.html",   # 우리 DB·GSC
        "/2026/09/foo.html",                                   # GA4
        "https://carin4note.blogspot.com/2026/09/foo.html/",   # 슬래시
        "http://carin4note.blogspot.com/2026/09/foo.html",     # http
    ])
    def test_same_post_same_key(self, raw):
        from app.services.analytics.url_match import path_of

        assert path_of(raw) == "/2026/09/foo.html"

    def test_percent_encoding(self):
        """한글 URL 은 GSC 가 인코딩해서 준다."""
        from app.services.analytics.url_match import path_of

        assert (path_of("/%EC%A0%84%EA%B8%B0%EC%B0%A8")
                == path_of("/전기차"))

    def test_tracking_params_dropped(self):
        from app.services.analytics.url_match import strip_tracking

        assert strip_tracking("https://x/a?utm_source=g&id=3") \
            == "https://x/a?id=3"
        assert strip_tracking("https://x/a?m=1") == "https://x/a"

    def test_empty_is_none(self):
        from app.services.analytics.url_match import path_of

        assert path_of("") is None
        assert path_of(None) is None

    def test_match_report_counts_misses(self):
        """실패를 세지 않으면 정규화가 틀려도 알 수 없다."""
        from app.services.analytics.url_match import MatchReport

        report = MatchReport()
        report.hit()
        report.miss("/a")
        assert report.rate == 0.5
        assert report.to_dict()["missed_samples"] == ["/a"]


class TestDecision:
    """유입·노출을 보고 무엇을 할지 정한다."""

    def _perf(self, **kw):
        from app.services.analytics.performance import Performance

        kw.setdefault("days", 28)
        return Performance(url_id=1, **kw)

    def test_steady_traffic_is_left_alone(self):
        """이 작업의 핵심 — 지금까지 없던 선택지다."""
        from app.services.analytics.performance import ACT_KEEP, decide_action

        assert decide_action(
            self._perf(sessions=120, prev_sessions=118)).action == ACT_KEEP

    def test_mild_dip_is_not_decay(self):
        """8% 하락으로 글을 갈아엎으면 안 된다."""
        from app.services.analytics.performance import ACT_KEEP, decide_action

        assert decide_action(
            self._perf(sessions=92, prev_sessions=100)).action == ACT_KEEP

    def test_real_decay_is_augmented(self):
        from app.services.analytics.performance import (
            ACT_AUGMENT, decide_action,
        )

        assert decide_action(
            self._perf(sessions=60, prev_sessions=100)).action == ACT_AUGMENT

    def test_striking_distance_touches_title_only(self):
        """8~20위는 본문이 아니라 제목 문제다. 본문을 갈면 순위를 잃는다."""
        from app.services.analytics.performance import ACT_TITLE, decide_action

        perf = decide_action(
            self._perf(sessions=0, impressions=340, position=12.4))
        assert perf.action == ACT_TITLE

    def test_deep_position_is_augmented_not_rewritten(self):
        from app.services.analytics.performance import (
            ACT_AUGMENT, decide_action,
        )

        assert decide_action(
            self._perf(sessions=0, impressions=50, position=44.0)
        ).action == ACT_AUGMENT

    def test_no_traffic_no_impressions_rewrite(self):
        from app.services.analytics.performance import (
            ACT_REWRITE, decide_action,
        )

        assert decide_action(
            self._perf(sessions=0, impressions=0)).action == ACT_REWRITE

    def test_thin_data_defers(self):
        """없는 데이터를 0 으로 읽으면 멀쩡한 글이 재작성된다."""
        from app.services.analytics.performance import ACT_LEGACY, decide_action

        assert decide_action(
            self._perf(sessions=0, impressions=0, days=5)).action == ACT_LEGACY

    def test_thresholds_are_overridable(self):
        from app.services.analytics.performance import ACT_AUGMENT, decide_action

        perf = decide_action(self._perf(sessions=95, prev_sessions=100),
                             {"decay_ratio": 0.02})
        assert perf.action == ACT_AUGMENT


class TestRenewalWiring:
    """판정이 실제 재발행 동작으로 이어지는가."""

    def _plan(self, action):
        from app.services.renewal.renewal_plan import decide_renewal_plan

        return decide_renewal_plan("keep", True, "blogauto", "http://i",
                                   action=action)

    def test_keep_skips_execution(self):
        assert self._plan("keep").skip is True

    def test_others_do_not_skip(self):
        for action in ("augment", "title", "rewrite", "legacy"):
            assert self._plan(action).skip is False

    def test_augment_preserves_body(self):
        assert self._plan("augment").content_mode == "additional"

    def test_rewrite_replaces_body(self):
        assert self._plan("rewrite").content_mode == "new"

    def test_title_action_forces_recombine(self):
        """제목 문제인데 제목을 그대로 두면 아무것도 안 바뀐다."""
        plan = self._plan("title")
        assert plan.recombine_title is True
        assert plan.content_mode == "additional"

    def test_legacy_defers_to_module_settings(self):
        assert self._plan("legacy").content_mode == ""

    def test_service_skips_before_generating(self):
        """건너뛸 글에 AI 를 부르면 비용만 나간다."""
        src = (ROOT / "app/services/renewal/renewal_service.py").read_text(
            encoding="utf-8")
        skip_at = src.index("if plan.skip:")
        gen_at = src.index("RenewalGenerator(self.db, gen_user_id)")
        assert skip_at < gen_at

    def test_generator_forced_mode_has_fallback_text(self):
        """모듈에 문구가 없다고 판정이 무시되면 안 된다."""
        from app.services.renewal.renewal_generator import RenewalGenerator
        from app.services.renewal.renewal_plan import decide_renewal_plan

        plan = decide_renewal_plan("keep", True, "none", action="augment")
        _, extra, existing = RenewalGenerator._renewal_prompt(
            {}, "<p>본문</p>", plan)
        assert extra and existing


class TestIntentGap:
    """서치콘솔 실측으로 '답하지 않은 질문' 을 찾는다."""

    CONTENT = ("<h2>전기차 충전 요금</h2><p>완속 충전은 요금이 낮습니다. "
               "급속 충전은 빠르지만 비쌉니다.</p>")

    def _q(self, query, impressions=100):
        return {"query": query, "impressions": impressions, "position": 12.0}

    def test_answered_query_is_not_a_gap(self):
        from app.services.analytics.intent_gap import find_gaps

        gaps = find_gaps([self._q("전기차 충전 요금")], self.CONTENT)
        assert gaps == []

    def test_unanswered_query_is_a_gap(self):
        from app.services.analytics.intent_gap import find_gaps

        gaps = find_gaps([self._q("전기차 충전 카드 할인")], self.CONTENT)
        assert [g["query"] for g in gaps] == ["전기차 충전 카드 할인"]

    def test_noise_is_dropped(self):
        """한두 번 스친 검색어까지 채우면 글이 잡동사니가 된다."""
        from app.services.analytics.intent_gap import find_gaps

        assert find_gaps([self._q("아무거나", impressions=2)],
                         self.CONTENT) == []

    def test_empty_content_yields_nothing(self):
        """본문을 못 읽었는데 전부 갭이라고 하면 안 된다."""
        from app.services.analytics.intent_gap import find_gaps

        assert find_gaps([self._q("무엇이든")], "") == []

    def test_prompt_asks_for_answers_not_keywords(self):
        from app.services.analytics.intent_gap import find_gaps, to_prompt

        text = to_prompt(find_gaps([self._q("충전 카드 할인")], self.CONTENT))
        assert "자연스럽게" in text
        assert "목록으로 나열하지 말고" in text

    def test_empty_gaps_yield_empty_prompt(self):
        from app.services.analytics.intent_gap import to_prompt

        assert to_prompt([]) == ""


class TestSettings:
    def test_performance_is_off_by_default(self):
        """지표가 쌓이기 전에 켜면 근거 없는 판정이 된다."""
        from app.routers.blog_settings_renewal import (
            RenewalSettingsRequest, _normalize_config,
        )

        cfg = _normalize_config(RenewalSettingsRequest())
        assert cfg["performance"]["enabled"] is False

    def test_reversed_positions_are_corrected(self):
        """min>max 면 어떤 글도 '제목 손질' 로 안 잡혀 판정이 죽는다."""
        from app.routers.blog_settings_renewal import (
            RenewalSettingsRequest, _normalize_config,
        )

        th = _normalize_config(RenewalSettingsRequest(
            ctr_position_min=20, ctr_position_max=8))["performance"]["thresholds"]
        assert th["ctr_position_min"] < th["ctr_position_max"]


class TestCollector:
    def test_missing_sources_do_not_write_zeros(self):
        """연결이 없는데 0 을 적으면 '유입 없는 글' 이 된다."""
        src = (ROOT / "app/services/analytics/collector.py").read_text(
            encoding="utf-8")
        assert 'return {"skipped": "연결된 소스 없음", "rows": 0}' in src

    def test_low_match_rate_warns(self):
        src = (ROOT / "app/services/analytics/collector.py").read_text(
            encoding="utf-8")
        assert "URL 매칭률 낮음" in src

    def test_upsert_overwrites(self):
        """두 API 모두 최근 며칠치를 나중에 보정한다."""
        src = (ROOT / "app/services/analytics/collector.py").read_text(
            encoding="utf-8")
        body = src[src.index("async def _upsert"):]
        assert "existing.get((url_id, day))" in body

    def test_daily_job_registered(self):
        main = (ROOT / "app/main.py").read_text(encoding="utf-8")
        assert "analytics_collect_job" in main
