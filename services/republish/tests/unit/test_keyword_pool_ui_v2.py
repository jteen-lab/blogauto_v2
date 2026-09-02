"""키워드 탭 개선 — 필터 통합·수동 수집·모듈 자동화 회귀 테스트.

사용자 지적:
    1. 요약 카드와 드롭다운이 같은 조건을 두 군데서 고르게 해 헷갈렸다
    2. 수집 자체를 손으로 돌릴 자리가 없었다
    3. 분류·측정·재판정이 자동 모듈에 반영돼야 한다
"""
import re
from pathlib import Path

import pytest

from app.services.keyword_lab.runner import KeywordModuleRunner
from app.services.keyword_lab.settings import KeywordModuleSettings

BASE = Path(__file__).resolve().parents[2]


def _tpl():
    return (BASE / "app/templates/collection/_keyword_pool.html").read_text(
        encoding="utf-8")


def _js():
    return (BASE / "app/static/js/collection/keyword_pool.js").read_text(
        encoding="utf-8")


class TestFilterUnified:
    """카드가 곧 필터다 — 같은 조건을 두 군데서 고르지 않는다."""

    def test_dropdowns_removed(self):
        tpl = _tpl()
        for gone in ("filters.verdict", "filters.classified",
                     "filters.measured"):
            assert f'x-model="{gone}"' not in tpl, gone

    def test_cards_toggle(self):
        assert "toggleCard(card)" in _tpl()
        assert "isCardActive(card)" in _tpl()

    def test_hold_card_added(self):
        # 드롭다운에만 있던 '보류' 가 카드로 올라왔다
        js = _js()
        assert "key: 'hold'" in js

    def test_combination_supported(self):
        """여러 카드를 켜면 AND 로 좁혀진다 — 드롭다운의 유일한 장점이었다."""
        js = _js()
        assert "this.filters[key] = this.filters[key] === value ? '' : value;" in js

    def test_active_filters_visible_as_chips(self):
        assert "activeChips()" in _js() and "activeChips()" in _tpl()

    def test_explains_combination(self):
        assert "모두 만족하는 것" in _tpl()


class TestManualCollect:
    """블로그오토의 모든 기능은 손으로도 돌릴 수 있어야 한다."""

    def test_panel_present(self):
        tpl = _tpl()
        assert "runCollect()" in tpl
        assert "collectForm.seeds" in tpl

    def test_uses_same_runner(self):
        js = _js()
        # 자동 모듈과 다른 코드를 타면 한쪽에서만 나는 버그가 생긴다
        assert "'/api/v1/keyword-lab/run'" in js
        assert "steps: ['collect']" in js

    def test_sources_selectable(self):
        js = _js()
        for code in ("google_trending", "naver_suggest", "google_suggest"):
            assert code in js

    def test_naver_ads_always_included(self):
        assert "const sources = ['naver_ads']" in _js()

    def test_shows_what_came_in(self):
        tpl = _tpl()
        assert "collectResult?.samples" in tpl
        assert "collectResult?.by_source" in tpl

    def test_polls_for_long_run(self):
        assert "pollRun(" in _js()


class TestModuleAutomation:
    """분류·측정·재판정이 자동으로도 돈다."""

    def test_default_steps_include_all(self):
        src = (BASE / "app/services/keyword_lab/runner.py").read_text(
            encoding="utf-8")
        assert '"feedback", "collect", "measure", "classify"' in src
        assert '"rejudge"' in src

    def test_measure_enriches_volume(self):
        """이관된 옛 시드는 검색량이 아예 없다 — 보강 없이는 영원히 미측정."""
        src = (BASE / "app/services/keyword_lab/runner.py").read_text(
            encoding="utf-8")
        assert "from .pool_ops import measure as pool_measure" in src

    def test_manual_and_auto_share_code(self):
        src = (BASE / "app/services/keyword_lab/runner.py").read_text(
            encoding="utf-8")
        # 데이터 관리 화면과 같은 pool_ops 를 쓴다
        assert "from .pool_ops import classify" in src
        assert "from .pool_ops import rejudge" in src

    def test_rejudge_is_opt_in(self):
        # 전체 행을 훑으므로 매 회차 돌릴 필요는 없다
        assert KeywordModuleSettings.parse({}).rejudge_on_run is False

    def test_rejudge_can_be_enabled(self):
        cfg = KeywordModuleSettings.parse(
            {"keyword": {"rejudge_on_run": True}})
        assert cfg.rejudge_on_run is True
        assert cfg.to_dict()["rejudge_on_run"] is True

    def test_summary_reports_new_steps(self):
        out = KeywordModuleRunner._aggregate([("-", {
            "success": True, "collect": {"saved": 40},
            "measure": {"measured": 50, "enriched": 30},
            "classify": {"matched": 12}, "rejudge": {"total": 6939},
            "titles": {}})])
        assert "검색량 보강 30건" in out["message"]
        assert "재판정 6939건" in out["message"]
        assert out["enriched"] == 30 and out["rejudged"] == 6939

    def test_quiet_when_nothing_happened(self):
        out = KeywordModuleRunner._aggregate([("-", {
            "success": True, "collect": {}, "measure": {}, "titles": {}})])
        assert "보강" not in out["message"] and "재판정" not in out["message"]

    def test_form_exposes_toggle(self):
        tpl = (BASE / "app/static/js/modules/keyword-form-template.js").read_text(
            encoding="utf-8")
        assert "formData.keyword.rejudge_on_run" in tpl
        js = (BASE / "app/static/js/modules/form.js").read_text(
            encoding="utf-8")
        assert "rejudge_on_run: !!k.rejudge_on_run" in js


class TestFileSize:
    @pytest.mark.parametrize("path", [
        "app/static/js/collection/keyword_pool.js",
        "app/templates/collection/_keyword_pool.html",
        "app/services/keyword_lab/runner.py",
        "app/services/keyword_lab/settings.py",
    ])
    def test_under_500_lines(self, path):
        lines = (BASE / path).read_text(encoding="utf-8").count("\n")
        assert lines <= 500, f"{path} = {lines}줄"
