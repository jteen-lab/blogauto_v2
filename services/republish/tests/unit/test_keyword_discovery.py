"""S3·S4 — 수집+분류 전용 전환과 발견 축 회귀 테스트.

계획서: docs/plans/keyword_pipeline_restructure_review.md §3

핵심:
    수집 모듈이 제목까지 만들면 중간 결과를 걸러낼 자리가 없다 → 제목 분리
    발견(입력 없음)과 확장(시드 필요)은 입력이 달라 로직이 분리돼야 한다
    발견 결과는 니치 필터를 거쳐야 한다 — 취업 블로그에 "맛집" 이 들어왔다
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.keyword_lab.runner import KeywordModuleRunner
from app.services.keyword_lab.settings import KeywordModuleSettings
from app.services.keyword_lab.sources import base, discovery

BASE = Path(__file__).resolve().parents[2]


class TestTitleSeparation:
    """S3 — 수집 모듈은 제목을 만들지 않는다."""

    def test_default_steps_exclude_titles(self):
        src = (BASE / "app/services/keyword_lab/runner.py").read_text(
            encoding="utf-8")
        assert '["feedback", "collect", "measure", "classify"]' in src

    def test_make_titles_defaults_off(self):
        assert KeywordModuleSettings.parse({}).make_titles is False

    def test_legacy_modules_keep_working(self):
        # 이미 켜 둔 모듈은 계속 돌아야 한다
        cfg = KeywordModuleSettings.parse({"keyword": {"make_titles": True}})
        assert cfg.make_titles is True

    def test_classify_step_runs(self):
        src = (BASE / "app/services/keyword_lab/runner.py").read_text(
            encoding="utf-8")
        assert "_classify_leftovers" in src

    def test_summary_reports_classification(self):
        out = KeywordModuleRunner._aggregate([("-", {
            "success": True, "collect": {"saved": 100},
            "measure": {"measured": 50}, "classify": {"matched": 12},
            "titles": {}})])
        assert "분류 12건" in out["message"]
        assert out["classified"] == 12

    def test_no_title_noise_when_none_made(self):
        out = KeywordModuleRunner._aggregate([("-", {
            "success": True, "collect": {}, "measure": {}, "titles": {}})])
        assert "제목" not in out["message"]


class TestDiscoverySources:
    """S4 — 발견 축."""

    def test_registered(self):
        assert base.SRC_GOOGLE_TRENDING in base.ALL_SOURCES
        assert base.SRC_NAVER_DATALAB in base.ALL_SOURCES

    def test_labels_explain_role(self):
        assert "발견" in base.SOURCE_LABEL[base.SRC_GOOGLE_TRENDING]
        # 데이터랩은 발견이 아니라 검증이다
        assert "검증" in base.SOURCE_LABEL[base.SRC_NAVER_DATALAB]

    def test_settings_accept_discovery(self):
        cfg = KeywordModuleSettings.parse(
            {"keyword": {"sources": ["google_trending"]}})
        assert "google_trending" in cfg.sources

    def test_niche_filter_defaults_on(self):
        assert KeywordModuleSettings.parse({}).discovery_niche_filter is True

    def test_datalab_returns_nothing_as_discovery(self):
        # API 가 연관 키워드를 주지 않는다. 새 키워드를 만들 수 없다
        src = (BASE / "app/services/keyword_lab/sources/registry.py").read_text(
            encoding="utf-8")
        assert "데이터랩은 발견 소스가 아니다" in src

    def test_constraint_documented(self):
        src = (BASE / "app/services/keyword_lab/sources/discovery.py").read_text(
            encoding="utf-8")
        assert "연관 키워드를 주지 않는다" in src


class _Matcher:
    """분류표에 있는 말만 매칭시키는 가짜 분류기."""

    TABLE = {"전기기사": (1, 11), "컴활": (1, 12), "마라탕": (2, 21)}

    def __init__(self, *a, **k):
        pass

    async def match_and_apply_to_keyword(self, keyword):
        hit = self.TABLE.get(keyword)
        return (hit[0], hit[1], None) if hit else (None, None, None)


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Db:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def execute(self, *a, **k):
        return _Rows(self.rows)


def _idea(keyword):
    return base.KeywordIdea(keyword=keyword,
                            source=base.SRC_GOOGLE_TRENDING, engine="google")


class TestNicheFilter:
    """발견 결과에서 우리 니치만 남긴다."""

    @pytest.fixture(autouse=True)
    def _patch(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.category_matcher_service.CategoryMatcherService",
            _Matcher)

    @pytest.mark.asyncio
    async def test_drops_unknown_words(self):
        ideas = [_idea("전기기사"), _idea("아이돌 컴백")]
        out = await discovery.filter_by_niche(_Db(), 1, ideas)
        assert [i.keyword for i in out["kept"]] == ["전기기사"]
        assert out["dropped"] == 1

    @pytest.mark.asyncio
    async def test_records_category(self):
        out = await discovery.filter_by_niche(_Db(), 1, [_idea("컴활")])
        assert out["kept"][0].extra["subtopic_id"] == 12

    @pytest.mark.asyncio
    async def test_blog_limits_to_its_categories(self):
        # 블로그가 취업 니치(11,12)면 마라탕은 빠져야 한다
        db = _Db(rows=[(1, 11), (1, 12)])
        blog = SimpleNamespace(id=9)
        ideas = [_idea("전기기사"), _idea("마라탕")]
        out = await discovery.filter_by_niche(db, 1, ideas, blog)
        assert [i.keyword for i in out["kept"]] == ["전기기사"]

    @pytest.mark.asyncio
    async def test_empty_input(self):
        out = await discovery.filter_by_niche(_Db(), 1, [])
        assert out["kept"] == [] and out["dropped"] == 0


class TestForm:
    def test_discovery_toggles_present(self):
        tpl = (BASE / "app/static/js/modules/keyword-form-template.js").read_text(
            encoding="utf-8")
        assert "src_google_trending" in tpl
        assert "discovery_niche_filter" in tpl
        assert "발견" in tpl and "확장" in tpl

    def test_serialized(self):
        js = (BASE / "app/static/js/modules/form.js").read_text(
            encoding="utf-8")
        assert "['src_google_trending', 'google_trending']" in js
        assert "discovery_niche_filter: !!k.discovery_niche_filter" in js

    def test_title_section_marked_legacy(self):
        tpl = (BASE / "app/static/js/modules/keyword-form-template.js").read_text(
            encoding="utf-8")
        assert "'제목 생성/수집' 모듈" in tpl
