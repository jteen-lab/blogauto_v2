"""니치 요약탭 — 무슨 니치가 부족한지 보여 주고 그 자리에서 채운다.

이전 화면은 접혀 있었고, 펼쳐도 '부족 32개' 같은 **개수**만 카드로
보여 줬다. 정작 알고 싶은 것은 무슨 니치인지였다. 카드 하나가 니치
하나가 되도록 바꾸면서 지켜야 할 것들을 못 박는다.
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "app/templates/collection/_niche_overview.html").read_text(
    encoding="utf-8")


class TestAlwaysVisible:
    def test_no_details_wrapper(self):
        """접혀 있으면 부족한 니치를 찾으러 들어가야 한다."""
        assert "<details" not in TEMPLATE

    def test_card_shows_three_things(self):
        """니치명 · 재고 · 연동 블로그 수."""
        card = TEMPLATE[TEMPLATE.index("<template x-for=\"row in cards()\""):
                        TEMPLATE.index("{# 펼침")]
        assert "row.subtopic_name" in card
        assert "row.titles" in card
        assert "블로그 ${row.blogs}" in card

    def test_cards_slide_when_many(self):
        assert "overflow-x-auto" in TEMPLATE

    def test_low_first(self):
        """부족한 것만 먼저 깐다."""
        assert "this.items.filter(r => r.is_low)" in TEMPLATE


class TestExpand:
    def test_only_the_clicked_niche(self):
        """전체 표가 아니라 누른 니치 한 줄만."""
        assert "r.subtopic_id === this.opened" in TEMPLATE

    def test_columns(self):
        for header in ("주제", "하위 주제", "재고", "연동 블로그"):
            assert f">{header}<" in TEMPLATE

    def test_blog_names_not_just_count(self):
        assert "current().blog_names" in TEMPLATE

    def test_actions_present(self):
        assert "run('collect')" in TEMPLATE
        assert "run('gen')" in TEMPLATE

    def test_generate_disabled_without_keywords(self):
        """재료가 없는데 누르면 0건만 나온다."""
        assert "!current().keywords" in TEMPLATE


class TestSettings:
    def test_entry_near_the_cards(self):
        assert "settingsOpen = !settingsOpen" in TEMPLATE

    def test_two_settings(self):
        assert "form.low_threshold" in TEMPLATE
        assert "form.card_limit" in TEMPLATE

    def test_defaults_registered(self):
        from app.services.system_settings_service import DEFAULTS

        assert DEFAULTS["niche_low_threshold"]["type"] == "int"
        assert DEFAULTS["niche_card_limit"]["type"] == "int"


class TestScope:
    """카드에서 돌린 실행이 그 니치만 채우는지."""

    def test_collect_settings_accept_subtopics(self):
        from app.services.title_collect.settings import TitleCollectSettings

        cfg = TitleCollectSettings.parse({"collect": {"subtopic_ids": ["7", 9]}})
        assert cfg.subtopic_ids == (7, 9)
        assert TitleCollectSettings.parse({}).subtopic_ids == ()

    def test_collector_narrows_seeds(self):
        src = (ROOT / "app/services/title_collect/collector.py").read_text(
            encoding="utf-8")
        assert "if cfg.subtopic_ids:" in src
        assert "_niche_seeds" in src

    def test_collector_falls_back_to_category_keywords(self):
        """부족 니치 31/32 는 채택 키워드가 0이다 — 여기서 멈추면 못 돈다."""
        src = (ROOT / "app/services/title_collect/collector.py").read_text(
            encoding="utf-8")
        body = src[src.index("async def _niche_seeds"):
                   src.index("async def _search")]
        assert "Keyword.subtopic_id.in_(ids)" in body
        assert "_CategorySeed" in body

    def test_generator_narrows_keywords(self):
        from app.services.keyword_lab.title_maker import TitleMaker

        assert hasattr(TitleMaker(None, None, 1), "subtopic_ids")
        src = (ROOT / "app/services/keyword_lab/title_maker.py").read_text(
            encoding="utf-8")
        assert src.count("_niche_scope(q,") == 2   # 단독 + 묶음 양쪽

    def test_runner_passes_scope(self):
        from app.services.title_gen.runner import TitleModuleRunner

        assert TitleModuleRunner(None, 1, (3,)).subtopic_ids == (3,)
        assert TitleModuleRunner(None, 1).subtopic_ids == ()


class TestRunSlots:
    def test_one_slot_per_niche(self):
        """사용자당 하나면 두 번째 카드가 '이미 실행 중' 으로 막힌다."""
        from app.routers.title_workbench import _key

        assert _key(1, 7) != _key(1, 9)
        assert _key(1, None) == _key(1, 0)

    def test_scope_reaches_both_sections(self):
        """한쪽만 좁히면 수집은 이 니치, 생성은 다른 니치가 된다."""
        from app.routers.title_workbench import RunRequest, _scoped

        out = _scoped(RunRequest(collect={"enabled": True},
                                 gen={"l1_enabled": True}, subtopic_id=7))
        assert out["collect"]["subtopic_ids"] == [7]
        assert out["gen"]["subtopic_ids"] == [7]

    def test_global_run_unchanged(self):
        """임시제목 탭 작업대는 예전 그대로 전역으로 돈다."""
        from app.routers.title_workbench import RunRequest, _scoped

        out = _scoped(RunRequest(collect={"enabled": True}))
        assert "subtopic_ids" not in (out["collect"] or {})

    def test_concurrency_capped(self):
        from app.routers.title_workbench import MAX_CONCURRENT

        assert 1 <= MAX_CONCURRENT <= 8


class TestSettingsWiring:
    """설정을 잘못 읽으면 화면 기준과 수집 기준이 갈라진다."""

    def test_get_int_argument_order(self):
        """시그니처는 (key, db, default) 다. 순서를 바꾸면 db 자리에
        정수가 들어가 조회가 통째로 예외로 떨어지고, 사용자가 저장한
        값 대신 기본값이 조용히 쓰인다."""
        import inspect

        from app.services.system_settings_service import SystemSettingsService

        params = list(inspect.signature(
            SystemSettingsService.get_int).parameters)
        assert params[:3] == ["key", "db", "default"]

        src = (ROOT / "app/routers/niche_summary.py").read_text(
            encoding="utf-8")
        assert '"niche_low_threshold", db, DEFAULT_LOW)' in src
        assert '"niche_card_limit", db, DEFAULT_CARDS)' in src


class TestDragToScroll:
    """PC 에서 스크롤바 화살표를 누르게 하지 않는다."""

    def test_scrollbar_hidden(self):
        assert ".niche-strip::-webkit-scrollbar { display: none; }" in TEMPLATE
        assert "scrollbar-width: none" in TEMPLATE

    def test_pointer_handlers_bound(self):
        for handler in ("@pointerdown", "@pointermove",
                        "@pointerup", "@pointercancel"):
            assert handler in TEMPLATE

    def test_touch_left_to_browser(self):
        """모바일은 기본 스와이프가 더 매끄럽다 — 가로채지 않는다."""
        assert "if (event.pointerType === 'touch') return;" in TEMPLATE

    def test_drag_does_not_open_a_card(self):
        """끌어서 넘긴 손을 떼는 순간 카드가 열리면 안 된다."""
        assert "if (this.suppressClick) { this.suppressClick = false; return; }" \
            in TEMPLATE
        assert "this.suppressClick = this.drag.moved > 5;" in TEMPLATE

    def test_grab_cursor(self):
        assert "dragging ? 'cursor-grabbing' : 'cursor-grab'" in TEMPLATE


class TestShowAllToggle:
    """부족 30개 · 노출 12개일 때 두 화면이 같아지던 자리."""

    def test_show_all_ignores_the_limit(self):
        block = TEMPLATE[TEMPLATE.index("        cards() {"):
                         TEMPLATE.index("        countLabel() {")]
        assert "if (this.showAll) return this.items;" in block
        # 제한은 '부족만 보기' 쪽에만 걸린다
        assert block.count("card_limit") == 1

    def test_toggle_does_not_refetch(self):
        """같은 응답을 다시 받아 오느라 전환이 늦어질 이유가 없다."""
        assert "showAll = !showAll; load()" not in TEMPLATE
        assert "@click=\"showAll = !showAll\"" in TEMPLATE

    def test_count_label_shows_hidden_ones(self):
        assert "shown < total ? `${total}개 중 ${shown}개`" in TEMPLATE
