"""키워드 모듈 P5 — 멀티 엔진 노출·성과 되먹임 테스트.

계획서: docs/plans/keyword_module_redesign_plan.md §5, §6-3

핵심:
    수요를 재는 엔진과 노출을 노리는 엔진이 어긋나 있었다.
    블로거는 IndexNow 키 파일을 못 올려 네이버 자동 통보가 불가능하다.
    내보낸 뒤 실제 노출을 회수해 다음 시드 순서에 반영한다.
"""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.keyword_lab import engines as E
from app.services.keyword_lab import feedback as F
from app.services.search_visibility import naver_readiness as R

BASE = Path(__file__).resolve().parents[2]


def _blog(platform="wordpress", seo=None, url="https://example.com"):
    return SimpleNamespace(id=1, platform=platform, seo_config=seo, url=url)


class TestTargetEngines:
    def test_default_is_google(self):
        # 워드프레스·블로거는 구글 색인 대상이다
        assert E.target_engines(_blog()) == ["google"]

    def test_reads_from_seo_config(self):
        blog = _blog(seo={"target_engines": ["naver", "google"]})
        assert E.target_engines(blog) == ["naver", "google"]

    def test_unknown_engine_dropped(self):
        blog = _blog(seo={"target_engines": ["naver", "해킹"]})
        assert E.target_engines(blog) == ["naver"]

    def test_empty_falls_back(self):
        assert E.target_engines(_blog(seo={"target_engines": []})) == ["google"]

    def test_set_persists(self):
        blog = _blog()
        E.set_target_engines(blog, ["naver"])
        assert blog.seo_config["target_engines"] == ["naver"]

    def test_set_keeps_other_seo_keys(self):
        blog = _blog(seo={"meta_desc": "x"})
        E.set_target_engines(blog, ["bing"])
        assert blog.seo_config["meta_desc"] == "x"

    def test_metric_engine_follows_first(self):
        assert E.metric_engine(_blog(seo={"target_engines": ["naver"]})) == "naver"

    def test_bing_uses_google_metrics(self):
        # 빙은 자체 키워드 지표가 없다
        assert E.metric_engine(_blog(seo={"target_engines": ["bing"]})) == "google"


class TestPlatformLimits:
    def test_wordpress_can_notify_naver(self):
        assert E.naver_notify_supported(_blog("wordpress")) is True

    def test_blogger_cannot(self):
        # IndexNow 키 파일을 호스트 루트에 올려야 하는데 블로거는 못 한다
        assert E.naver_notify_supported(_blog("blogger")) is False

    def test_warns_blogger_naver_combo(self):
        blog = _blog("blogger", {"target_engines": ["naver"]})
        assert any("블로거" in w for w in E.warnings(blog))

    def test_naver_tab_note_always_shown(self):
        blog = _blog("wordpress", {"target_engines": ["naver"]})
        assert any("웹사이트 탭" in w for w in E.warnings(blog))

    def test_no_warning_for_google_only(self):
        assert E.warnings(_blog("blogger")) == []

    def test_describe_shape(self):
        out = E.describe(_blog("wordpress", {"target_engines": ["naver"]}))
        assert out["metric_engine"] == "naver"
        assert out["naver_notify"] is True
        assert out["labels"] == ["네이버"]


class TestReadinessItems:
    def test_yeti_blocked_is_fail(self):
        result = R.naver_check.NaverCheckResult(
            ok=True, yeti_blocked=True, yeti_rule_source="Disallow: /")
        assert R._robots_item(result)["state"] == "fail"

    def test_yeti_allowed_is_ok(self):
        result = R.naver_check.NaverCheckResult(ok=True, yeti_blocked=False)
        assert R._robots_item(result)["state"] == "ok"

    def test_robots_unreadable_is_unknown(self):
        result = R.naver_check.NaverCheckResult(ok=False, error="타임아웃")
        assert R._robots_item(result)["state"] == "unknown"

    def test_missing_meta_is_unknown_not_fail(self):
        # 소유 확인은 파일·DNS 로도 가능하다. 메타 없음 ≠ 미등록
        result = R.naver_check.NaverCheckResult(ok=True,
                                                verification_meta=False)
        item = R._owner_item(result)
        assert item["state"] == "unknown" and item["manual"] is True

    def test_meta_present_is_ok(self):
        result = R.naver_check.NaverCheckResult(ok=True,
                                                verification_meta=True)
        assert R._owner_item(result)["state"] == "ok"


class TestFeedbackScore:
    def test_impressions_are_the_base(self):
        assert F.score_of(100, 90.0) == 100.0

    def test_top_position_gets_bonus(self):
        assert F.score_of(40, 8.0) == 60.0

    def test_boundary_position(self):
        assert F.score_of(10, 20.0) > 10.0
        assert F.score_of(10, 20.1) == 10.0

    def test_zero_impressions(self):
        assert F.score_of(0, 3.0) == 0.0

    def test_negative_is_clamped(self):
        assert F.score_of(-5, None) == 0.0

    def test_missing_position(self):
        assert F.score_of(25, None) == 25.0


class TestFeedbackMatching:
    def test_normalizes_spacing_and_symbols(self):
        assert F.norm("전기기사 실기!") == F.norm("전기기사실기")

    def test_index_keeps_highest_impressions(self):
        rows = [{"query": "a", "impressions": 3},
                {"query": "a", "impressions": 9}]
        assert F.index_rows(rows)["a"]["impressions"] == 9

    def test_index_skips_empty_query(self):
        assert F.index_rows([{"query": "", "impressions": 5}]) == {}

    def test_no_impression_score_is_zero_not_none(self):
        # "확인했더니 없더라" 와 "아직 안 재 봤다" 는 다른 사실이다
        assert F.NO_IMPRESSION_SCORE == 0.0


class TestSeedOrdering:
    def test_untested_sits_between_proven_and_failed(self):
        src = (BASE / "app/services/keyword_lab/expander.py").read_text(
            encoding="utf-8")
        # NULL(미측정)을 0.5로 두어 0점(노출 없음)보다 앞에 오게 한다
        assert "perf_score.is_(None), 0.5" in src
        assert "case(" in src


class TestWiring:
    def test_runner_runs_feedback_first(self):
        src = (BASE / "app/services/keyword_lab/runner.py").read_text(
            encoding="utf-8")
        # 되먹임을 앞에 붙인다 — 시드 우선순위가 그 결과를 쓴다
        assert '["feedback"] if cfg.feedback_enabled' in src
        assert src.index("_feedback(cfg, blog)") < src.index(
            'out["collect"]')

    def test_router_exposes_engine_and_readiness(self):
        src = (BASE / "app/routers/keyword_lab.py").read_text(encoding="utf-8")
        for path in ("/engines/{blog_id}", "/readiness/{blog_id}",
                     "/feedback"):
            assert path in src

    def test_gsc_raw_rows_reusable(self):
        src = (BASE / "app/services/keyword_lab/sources/gsc.py").read_text(
            encoding="utf-8")
        # 되먹임과 수집이 같은 호출을 쓴다
        assert "async def fetch_for_blog(" in src

    @pytest.mark.parametrize("path", [
        "app/services/keyword_lab/engines.py",
        "app/services/keyword_lab/feedback.py",
        "app/services/search_visibility/naver_readiness.py",
        "app/routers/keyword_lab.py",
    ])
    def test_files_under_500_lines(self, path):
        lines = (BASE / path).read_text(encoding="utf-8").count("\n")
        assert lines <= 500, f"{path} = {lines}줄"


class TestModuleListQuery:
    """모듈 드롭다운이 500 으로 죽지 않는다."""

    def test_module_has_no_is_deleted(self):
        from app.models.module import Module

        # 없는 컬럼을 걸면 AttributeError 로 엔드포인트가 500 이 된다
        assert not hasattr(Module, "is_deleted")

    def test_router_does_not_filter_by_is_deleted(self):
        src = (BASE / "app/routers/keyword_lab.py").read_text(encoding="utf-8")
        assert "Module.is_deleted" not in src


class TestCreateTypeSelector:
    """모듈 생성 팝업이 목록 타입과 어긋나지 않는다.

    팝업 옵션은 템플릿에 하드코딩돼 있어, 새 타입을 추가하면서 여기를
    빠뜨리면 **만들 수가 없다.** 실제로 키워드 타입이 그렇게 빠져 있었다.
    """

    def _popup_codes(self):
        html = (BASE / "app/templates/modules/list.html").read_text(
            encoding="utf-8")
        return set(re.findall(
            r"selectOption\('moduleTypeSelector',\s*'([a-z_]+)'", html))

    def _list_codes(self):
        js = (BASE / "app/static/js/modules/list.js").read_text(
            encoding="utf-8")
        line = re.search(r"const moduleTypes = \[([^\]]+)\]", js)
        assert line, "list.js 의 moduleTypes 배열을 찾지 못했다"
        return set(re.findall(r"'([a-z_]+)'", line.group(1)))

    def test_keyword_is_creatable(self):
        assert "keyword" in self._popup_codes()

    def test_popup_is_subset_of_list_types(self):
        """만들 수 있는 타입은 목록 탭에도 있어야 한다.

        반대는 성립하지 않는다 — 폐기된 타입(collect·bulk_collect)은
        새로 만들 수 없지만 이미 만든 모듈은 목록에 보여야 한다.
        """
        assert self._popup_codes() <= self._list_codes()

    def test_deprecated_types_cannot_be_created(self):
        popup = self._popup_codes()
        assert "collect" not in popup and "bulk_collect" not in popup
        # 대체 타입은 만들 수 있어야 한다
        assert {"keyword", "title_gen"} <= popup
