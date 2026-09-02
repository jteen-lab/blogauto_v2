"""S6 — 키워드 관리 화면 흡수와 구모듈 폐기 회귀 테스트.

계획서: docs/plans/keyword_pipeline_restructure_review.md §5-3

핵심:
    같은 개념을 두 화면이 따로 보여주고 있었다 → 데이터 관리로 흡수
    구 수집 모듈은 새로 만들 수 없게 하되, **이미 만든 것은 계속 돌아야 한다**
"""
import re
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2]


class TestScreenAbsorbed:
    def test_keyword_lab_redirects(self):
        src = (BASE / "app/routers/keyword_lab.py").read_text(encoding="utf-8")
        assert "RedirectResponse" in src
        assert "/collection?tab=keywords" in src

    def test_nav_link_removed(self):
        html = (BASE / "app/templates/base.html").read_text(encoding="utf-8")
        assert "/keyword-lab" not in html

    def test_exposure_panel_moved(self):
        tpl = (BASE / "app/templates/collection/_keyword_pool.html").read_text(
            encoding="utf-8")
        for key in ("saveEngines()", "loadReadiness()", "collectFeedback()"):
            assert key in tpl

    def test_exposure_methods_present(self):
        js = (BASE / "app/static/js/collection/keyword_pool.js").read_text(
            encoding="utf-8")
        for key in ("loadEngines", "saveEngines", "loadReadiness",
                    "collectFeedback"):
            assert key in js

    def test_api_still_served(self):
        """화면만 옮겼다. API 는 그대로 쓴다."""
        from app.routers.keyword_lab import router

        paths = {r.path for r in router.routes}
        assert "/api/v1/keyword-lab/engines/{blog_id}" in paths
        assert "/api/v1/keyword-lab/readiness/{blog_id}" in paths


class TestLegacyModulesRetired:
    def _popup(self):
        html = (BASE / "app/templates/modules/list.html").read_text(
            encoding="utf-8")
        return set(re.findall(
            r"selectOption\('moduleTypeSelector',\s*'([a-z_]+)'", html))

    def test_cannot_create_collect(self):
        assert "collect" not in self._popup()

    def test_cannot_create_bulk_collect(self):
        assert "bulk_collect" not in self._popup()

    def test_replacements_available(self):
        assert {"keyword", "title_gen"} <= self._popup()

    def test_existing_modules_still_listed(self):
        """이미 만든 모듈은 계속 보이고 돌아야 한다."""
        js = (BASE / "app/static/js/modules/list.js").read_text(
            encoding="utf-8")
        types = re.search(r"const moduleTypes = \[([^\]]+)\]", js).group(1)
        assert "'collect'" in types and "'bulk_collect'" in types

    def test_tabs_marked_deprecated(self):
        html = (BASE / "app/templates/modules/list.html").read_text(
            encoding="utf-8")
        assert "수집 (폐기 예정)" in html
        assert "대량 수집 (폐기 예정)" in html

    def test_reason_explained_to_user(self):
        html = (BASE / "app/templates/modules/list.html").read_text(
            encoding="utf-8")
        assert "대체돼" in html
        assert "이미 만든 모듈은 계속 동작합니다" in html

    def test_execution_paths_intact(self):
        """폐기는 생성만 막는 것이다. 실행 경로를 지우면 운영이 멈춘다."""
        flows = (BASE / "app/routers/flows_execute.py").read_text(
            encoding="utf-8")
        assert '_execute_collect_module' in flows
        assert 'type_code == "bulk_collect"' in flows
