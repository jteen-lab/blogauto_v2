"""키워드 모듈 P3 — 멀티 소스 수집 테스트.

계획서: docs/plans/keyword_module_redesign_plan.md §4

핵심:
    한 소스만 쓰면 그 소스의 한계가 결과의 한계가 된다.
    구글 플래너 검색량은 구간값이라 절대 기준으로 쓰면 안 된다.
    서치콘솔은 유일한 실측 소스다.
"""
from pathlib import Path

import pytest

from app.services.keyword_lab.settings import KeywordModuleSettings
from app.services.keyword_lab.sources import base, gsc, registry
from app.services.keyword_lab.sources.base import KeywordIdea
from app.services.keyword_lab.sources.suggest import _to_ideas

BASE = Path(__file__).resolve().parents[2]


class TestNormalize:
    def test_trims_and_collapses(self):
        assert base.normalize('  전기기사   실기  ') == "전기기사 실기"

    def test_strips_quotes(self):
        assert base.normalize('"전기기사"') == "전기기사"

    def test_rejects_too_short(self):
        assert base.normalize("가") == ""

    def test_rejects_sentence(self):
        assert base.normalize("가" * 100) == ""

    def test_keeps_spaces(self):
        # 검색광고에 보낼 때만 공백을 없앤다. 여기서 없애면 구절형이 망가진다.
        assert " " in base.normalize("전기기사 실기 준비")


class TestDedupe:
    def test_keeps_the_one_with_volume(self):
        ideas = [
            KeywordIdea("전기기사", base.SRC_GOOGLE_SUGGEST),
            KeywordIdea("전기기사", base.SRC_NAVER_ADS, search_volume=900),
        ]
        out = base.dedupe(ideas)
        assert len(out) == 1 and out[0].search_volume == 900

    def test_case_insensitive(self):
        ideas = [KeywordIdea("VPN", base.SRC_GOOGLE_SUGGEST),
                 KeywordIdea("vpn", base.SRC_NAVER_SUGGEST)]
        assert len(base.dedupe(ideas)) == 1

    def test_keeps_distinct(self):
        ideas = [KeywordIdea("전기기사", base.SRC_NAVER_ADS),
                 KeywordIdea("전기산업기사", base.SRC_NAVER_ADS)]
        assert len(base.dedupe(ideas)) == 2


class TestSuggestParsing:
    def test_drops_the_seed_itself(self):
        out = _to_ideas(["전기기사", "전기기사 실기"], "전기기사",
                        base.SRC_GOOGLE_SUGGEST, "google", 10)
        assert [i.keyword for i in out] == ["전기기사 실기"]

    def test_respects_limit(self):
        words = [f"전기기사 {i}" for i in range(20)]
        assert len(_to_ideas(words, "전기기사", base.SRC_GOOGLE_SUGGEST,
                             "google", 5)) == 5

    def test_ignores_non_strings(self):
        out = _to_ideas([None, 3, {"a": 1}, "전기기사 실기"], "전기기사",
                        base.SRC_NAVER_SUGGEST, "naver", 10)
        assert len(out) == 1

    def test_records_seed(self):
        out = _to_ideas(["전기기사 실기"], "전기기사",
                        base.SRC_NAVER_SUGGEST, "naver", 10)
        assert out[0].seed == "전기기사"


class TestGscIdeas:
    def _rows(self):
        return [
            {"query": "전기기사 실기 일정", "impressions": 120, "clicks": 4,
             "position": 8.2},
            {"query": "잡음", "impressions": 1, "clicks": 0, "position": 90.0},
        ]

    def test_filters_low_impressions(self):
        out = gsc.to_ideas(self._rows())
        assert [i.keyword for i in out] == ["전기기사 실기 일정"]

    def test_keeps_performance_for_feedback(self):
        out = gsc.to_ideas(self._rows())
        assert out[0].extra["impressions"] == 120
        assert out[0].extra["position"] == 8.2

    def test_volume_left_empty(self):
        # 노출수는 검색량이 아니다. 보강 단계가 채운다.
        assert gsc.to_ideas(self._rows())[0].search_volume is None

    def test_engine_is_google(self):
        assert gsc.to_ideas(self._rows())[0].engine == "google"


class _FakeAds:
    def __init__(self, ok=True, rows=None):
        self.ok, self.rows, self.calls = ok, rows or [], 0

    def is_configured(self):
        return True

    async def get_keyword_stats(self, keywords, include_related=True):
        self.calls += 1
        if not self.ok:
            return {"success": False, "error": "403 인증 실패"}
        return {"success": True, "keywords": self.rows}


class TestEnrichVolumes:
    @pytest.mark.asyncio
    async def test_fills_missing_volume(self, monkeypatch):
        ideas = [KeywordIdea("전기기사 실기", base.SRC_GOOGLE_SUGGEST)]
        fake = _FakeAds(rows=[{"keyword": "전기기사실기",
                               "total_search_volume": 900,
                               "pc_search_volume": 300,
                               "mobile_search_volume": 600,
                               "competition": "중간"}])
        monkeypatch.setattr(
            "app.services.naver_ads_service.NaverAdsService",
            lambda settings: fake)
        out = await registry.enrich_volumes(None, ideas)
        assert out["filled"] == 1
        assert ideas[0].search_volume == 900
        assert ideas[0].volume_is_range is False

    @pytest.mark.asyncio
    async def test_skips_when_volume_present(self, monkeypatch):
        ideas = [KeywordIdea("전기기사", base.SRC_NAVER_ADS,
                             search_volume=100)]
        fake = _FakeAds()
        monkeypatch.setattr(
            "app.services.naver_ads_service.NaverAdsService",
            lambda settings: fake)
        out = await registry.enrich_volumes(None, ideas)
        assert out["filled"] == 0 and fake.calls == 0

    @pytest.mark.asyncio
    async def test_reports_error(self, monkeypatch):
        ideas = [KeywordIdea("전기기사 실기", base.SRC_GOOGLE_SUGGEST)]
        monkeypatch.setattr(
            "app.services.naver_ads_service.NaverAdsService",
            lambda settings: _FakeAds(ok=False))
        out = await registry.enrich_volumes(None, ideas)
        assert out["filled"] == 0 and out["errors"]

    @pytest.mark.asyncio
    async def test_respects_limit(self, monkeypatch):
        ideas = [KeywordIdea(f"키워드 {i}", base.SRC_GOOGLE_SUGGEST)
                 for i in range(30)]
        fake = _FakeAds()
        monkeypatch.setattr(
            "app.services.naver_ads_service.NaverAdsService",
            lambda settings: fake)
        await registry.enrich_volumes(None, ideas, limit=10)
        assert fake.calls == 2   # 10개 ÷ 5개씩


class TestGatherIsolatesFailures:
    @pytest.mark.asyncio
    async def test_one_source_failure_does_not_kill_the_round(self, monkeypatch):
        async def boom(*a, **k):
            raise RuntimeError("차단됨")

        monkeypatch.setattr(registry, "_run_source", boom)
        out = await registry.gather(None, None, None, ["전기기사"],
                                    [base.SRC_GOOGLE_SUGGEST])
        assert out["ideas"] == [] and out["errors"]

    @pytest.mark.asyncio
    async def test_empty_enabled_list(self):
        out = await registry.gather(None, None, None, ["전기기사"], [])
        assert out["ideas"] == [] and out["errors"] == []


class TestSourceSettings:
    def test_naver_ads_always_on(self):
        cfg = KeywordModuleSettings.parse(
            {"keyword": {"sources": ["google_suggest"]}})
        assert cfg.sources[0] == "naver_ads"

    def test_unknown_source_dropped(self):
        cfg = KeywordModuleSettings.parse(
            {"keyword": {"sources": ["gsc", "해킹"]}})
        assert "해킹" not in cfg.sources and "gsc" in cfg.sources

    def test_default_is_ads_only(self):
        assert KeywordModuleSettings.parse({}).sources == ["naver_ads"]

    def test_round_trip(self):
        cfg = KeywordModuleSettings.parse(
            {"keyword": {"sources": ["naver_ads", "gsc"]}})
        assert cfg.to_dict()["sources"] == ["naver_ads", "gsc"]


class TestPlannerRangeFlag:
    def test_planner_marks_range(self):
        from app.services.keyword_lab.sources.google_ads import _planner_row

        idea = _planner_row({"keyword": "전기기사", "avg_monthly_searches": 5000,
                             "competition": "HIGH"}, "전기기사")
        # 구간값을 절대 기준으로 쓰면 안 된다
        assert idea.volume_is_range is True
        assert idea.competition == "높음"

    def test_trends_has_no_volume(self):
        from app.services.keyword_lab.sources.google_ads import _trends_row

        idea = _trends_row({"keyword": "전기기사 일정", "trend_score": 80,
                            "source_keyword": "전기기사"}, False)
        assert idea.search_volume is None


class TestWiring:
    def test_service_calls_sources(self):
        src = (BASE / "app/services/keyword_lab/service.py").read_text(
            encoding="utf-8")
        assert "_collect_sources" in src and "enrich_volumes" in src

    def test_form_serializes_sources(self):
        js = (BASE / "app/static/js/modules/form.js").read_text(
            encoding="utf-8")
        assert "const sources = ['naver_ads']" in js
        assert "src_gsc" in js

    def test_gsc_reuses_existing_token(self):
        src = (BASE / "app/services/keyword_lab/sources/gsc.py").read_text(
            encoding="utf-8")
        # 추가 인증 없이 색인 점검이 쓰던 토큰을 그대로 쓴다
        assert "resolve_gsc_token" in src
        assert "searchAnalytics/query" in src

    @pytest.mark.parametrize("path", [
        "app/services/keyword_lab/service.py",
        "app/services/keyword_lab/ingest.py",
        "app/services/keyword_lab/sources/registry.py",
        "app/services/keyword_lab/sources/suggest.py",
        "app/services/keyword_lab/sources/gsc.py",
        "app/services/keyword_lab/sources/google_ads.py",
    ])
    def test_files_under_500_lines(self, path):
        lines = (BASE / path).read_text(encoding="utf-8").count("\n")
        assert lines <= 500, f"{path} = {lines}줄"
