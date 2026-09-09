"""CPA 구분 — 숨기지 않고 표시한다.

전수 조사(2026-09-09): 구분이 필요한 것 5종, 공유해도 되는 것 7종.
모드 전환은 공유해도 될 것까지 숨기고, 조회 API 84개를 전수 검토해야 하며,
필터를 빠뜨리면 남의 데이터가 섞여 보이는데 화면은 멀쩡해 발견이 늦다.
"""
import pathlib

import pytest

from app.models.title import MainTitle, TempTitle
from app.services.cpa import scope

ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestDefaultShowsEverything:
    """기본은 전체다. 숨기지 않는 것이 이 방식의 요점이다."""

    @pytest.mark.parametrize("wanted", [None, "", "all", "이상한값"])
    def test_no_condition(self, wanted):
        assert scope.condition(MainTitle, wanted, {5}) is None

    @pytest.mark.parametrize("wanted", [None, "all"])
    def test_keep_everything(self, wanted):
        assert scope.keep(True, wanted) and scope.keep(False, wanted)


class TestCondition:
    def _sql(self, model, wanted, topics, offer=False):
        cond = scope.condition(model, wanted, topics, has_offer_column=offer)
        return str(cond) if cond is not None else ""

    def test_cpa_matches_referenced_subtopic_or_own_offer(self):
        sql = self._sql(MainTitle, "cpa", {5, 7}, offer=True)
        assert "subtopic_id IN" in sql and "cpa_offer_id IS NOT NULL" in sql

    def test_adsense_is_the_complement(self):
        sql = self._sql(MainTitle, "adsense", {5}, offer=True)
        assert sql.startswith("NOT (")

    def test_null_subtopic_stays_in_adsense(self):
        """하위주제 없는 일반 제목이 빠지면 목록이 통째로 어긋난다.

        NULL 가드가 없으면 `topic_id IN (...)` 이 NULL 이 되고
        NOT(NULL) 도 NULL 이라 그 행이 사라진다.
        """
        sql = self._sql(TempTitle, "adsense", {5})
        assert "IS NOT NULL" in sql, "NULL 가드가 있어야 한다"

    def test_no_cpa_data_yet(self):
        """CPA 니치가 하나도 없을 때 — cpa 는 빈 목록, adsense 는 전부."""
        assert self._sql(MainTitle, "cpa", set()) == "main_titles.id IS NULL"
        assert self._sql(MainTitle, "adsense", set()) == ""

    def test_topic_filter_is_derived(self):
        """주제는 소유되지 않는다. 오퍼가 쓰는 하위주제로 파생 판정한다."""
        from types import SimpleNamespace as NS

        rows = [NS(id=1), NS(id=2)]
        assert [t.id for t in scope.topic_filter(rows, "cpa", {1})] == [1]
        assert [t.id for t in scope.topic_filter(rows, "adsense", {1})] == [2]
        assert len(scope.topic_filter(rows, "all", {1})) == 2


class TestRowJudgement:
    def test_referenced_subtopic_decides(self):
        assert scope.is_cpa_row(5, {5, 7}) is True
        assert scope.is_cpa_row(9, {5, 7}) is False

    def test_own_offer_wins(self):
        """오퍼가 만든 제목은 하위주제가 없어도 CPA 다."""
        assert scope.is_cpa_row(None, set(), own_offer_id=3) is True

    def test_no_topic_no_offer(self):
        assert scope.is_cpa_row(None, {5}) is False

    def test_badge_text(self):
        assert scope.badge(True) == "CPA"
        assert scope.badge(False) == "애드센스"


class TestMark:
    ROWS = [{"subtopic_id": 5, "cpa_offer_id": None},
            {"subtopic_id": 9, "cpa_offer_id": None},
            {"subtopic_id": None, "cpa_offer_id": 3}]

    def test_labels_every_row(self):
        out = scope.mark(self.ROWS, {5})
        assert [r["scope_label"] for r in out] == ["CPA", "애드센스", "CPA"]

    def test_filter_cpa(self):
        assert len(scope.mark(self.ROWS, {5}, "cpa")) == 2

    def test_filter_adsense(self):
        assert len(scope.mark(self.ROWS, {5}, "adsense")) == 1

    def test_default_keeps_all(self):
        assert len(scope.mark(self.ROWS, {5})) == 3


class TestWiring:
    """목록 5곳에 붙었나. 붙지 않으면 배지가 안 보인다."""

    @pytest.mark.parametrize("path,needle", [
        ("app/routers/titles.py", "scope"),
        ("app/routers/data_titles.py", "scope"),
        ("app/routers/categories.py", "scope"),
        ("app/routers/blogs.py", "scope"),
    ])
    def test_api_has_scope(self, path, needle):
        assert needle in (ROOT / path).read_text(encoding="utf-8")

    def test_filter_is_applied_in_sql_not_python(self):
        """화면에서 거르면 페이지 수가 어긋난다."""
        src = (ROOT / "app/routers/titles.py").read_text(encoding="utf-8")
        assert "query = query.where(scope_cond)" in src

    @pytest.mark.parametrize("path", [
        "app/templates/collection/_titles.html",
        "app/templates/collection/_titles_main.html",
        "app/templates/blogs/_card.html",
    ])
    def test_screen_shows_badge(self, path):
        assert "scope_label" in (ROOT / path).read_text(encoding="utf-8")


class TestPageMoved:
    """별도 페이지가 균형을 깼다. 데이터 관리의 한 탭으로 옮긴다."""

    def test_global_menu_removed(self):
        base = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
        assert 'href="/cpa"' not in base

    def test_standalone_page_gone(self):
        assert not (ROOT / "app/templates/cpa").exists()
        assert not (ROOT / "app/routers/cpa_pages.py").exists()

    def test_tab_added(self):
        page = (ROOT / "app/templates/collection/index.html").read_text(
            encoding="utf-8")
        assert "activeTab === 'offers'" in page
        assert "_cpa_offers.html" in page


class TestSubtopicReference:
    """소유가 아니라 참조다.

    니치를 오퍼에 배타 귀속시키면 그 니치를 쓰던 블로그가 통째로 넘어간다.
    실측(2026-09-09): '생활 정보' 제목 879건·블로그 7개, '금융/대출' 을
    붙였더니 정식제목 1,023건이 CPA 로 넘어갔다.
    """

    ASSETS = (ROOT / "app/routers/cpa_assets.py").read_text(encoding="utf-8")
    SRC = (ROOT / "app/routers/cpa.py").read_text(encoding="utf-8")
    HTML = (ROOT / "app/templates/collection/_cpa_offers.html").read_text(
        encoding="utf-8")

    def test_endpoint_takes_subtopics(self):
        assert "async def set_subtopics" in self.ASSETS

    def test_exclusive_binding_is_gone(self):
        model = (ROOT / "app/models/category.py").read_text(encoding="utf-8")
        assert "cpa_offer_id" not in model, "주제는 소유되지 않는다"

    def test_only_existing_subtopics_kept(self):
        """지워진 하위주제를 참조하면 제목이 안 뽑힌다."""
        assert "실재하는 것만 남긴다" in self.ASSETS

    def test_new_subtopic_needs_a_topic(self):
        """자동 생성은 하지 않는다 — 트리가 지저분해진다."""
        assert "새 하위주제를 만들 주제를 고르세요" in self.ASSETS

    def test_titles_inherit_the_subtopic(self):
        assert "offer.subtopic_ids[0]" in self.SRC
        assert "subtopic_id=subtopic_id" in self.SRC

    def test_screen_says_it_is_a_reference(self):
        assert "소유가 아니라 참조" in self.HTML

    def test_screen_warns_without_subtopics(self):
        assert "쓸 하위주제가 없습니다" in self.HTML
