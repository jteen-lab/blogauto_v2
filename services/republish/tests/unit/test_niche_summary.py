"""니치 현황·부족 니치 우선 수집 회귀 테스트.

**블로그 0인 재고는 죽은 재고다.** 아무도 꺼내 쓰지 않는다. 그래서
'부족' 은 쓰는 블로그가 있는 니치에만 매긴다 — 없는 곳을 채우면 재고만
늘고 발행은 늘지 않는다.

화면과 수집이 **같은 기준**을 써야 한다. 다르면 화면은 부족하다는데
수집은 다른 곳을 채운다.

계획서: docs/plans/title_tab_workplan.md §9
"""
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]


class TestSummaryRules:
    def test_router_registered(self):
        from app.main import app

        assert "/api/v1/data/niches" in {r.path for r in app.routes}

    def test_orphan_and_low_are_distinct(self):
        """부족(채워야 함)과 죽은 재고(채울 이유 없음)는 다른 상태다."""
        from app.routers.niche_summary import NicheRow

        low = NicheRow(topic_id=1, topic_name="t", subtopic_id=2,
                       subtopic_name="s", titles=3, blogs=2, is_low=True)
        orphan = NicheRow(topic_id=1, topic_name="t", subtopic_id=3,
                          subtopic_name="s", titles=300, blogs=0,
                          is_orphan=True)
        assert low.is_low and not low.is_orphan
        assert orphan.is_orphan and not orphan.is_low

    def test_deleted_niches_excluded(self):
        """매처가 안 쓰는 분류를 보여 주면 그쪽을 채우려 든다."""
        src = (BASE / "app/routers/niche_summary.py").read_text(
            encoding="utf-8")
        assert "SubTopic.is_deleted.is_(False)" in src
        assert "Topic.is_deleted.is_(False)" in src

    def test_only_available_counted(self):
        """이미 쓴 제목은 재고가 아니다."""
        src = (BASE / "app/routers/niche_summary.py").read_text(
            encoding="utf-8")
        assert 'MainTitle.status == "available"' in src


class TestDemandSharedWithCollector:
    def test_low_requires_a_blog(self):
        """쓰는 블로그가 없으면 채워 봐야 죽은 재고다."""
        src = (BASE / "app/services/title_collect/niche_demand.py").read_text(
            encoding="utf-8")
        assert "if blog_count and (count or 0) < max(1, threshold)" in src

    def test_failure_does_not_stop_collection(self):
        """우선순위를 못 정해도 수집은 계속해야 한다."""
        src = (BASE / "app/services/title_collect/niche_demand.py").read_text(
            encoding="utf-8")
        assert "return set()" in src

    def test_same_threshold_default(self):
        """화면과 수집이 다른 기준을 쓰면 어긋난다."""
        from app.routers.niche_summary import DEFAULT_LOW
        from app.services.title_collect.niche_demand import DEFAULT_LOW as D2
        from app.services.title_collect.settings import DEFAULT_LOW_NICHE

        assert DEFAULT_LOW == D2 == DEFAULT_LOW_NICHE

    def test_collector_falls_back_when_none_low(self):
        """부족한 곳이 없다고 회차가 노는 것은 낭비다."""
        src = (BASE / "app/services/title_collect/collector.py").read_text(
            encoding="utf-8")
        assert "부족 니치만으로 못 채우면" in src
        assert "low_subtopics" in src

    def test_setting_round_trip(self):
        from app.services.title_collect.settings import TitleCollectSettings

        cfg = TitleCollectSettings.parse(
            {"collect": {"prioritize_low_niche": False,
                         "low_niche_threshold": 50}})
        assert cfg.prioritize_low_niche is False
        assert cfg.to_dict()["low_niche_threshold"] == 50


class TestUiParity:
    def test_panel_included(self):
        src = (BASE / "app/templates/collection/_titles_main.html").read_text(
            encoding="utf-8")
        assert "_niche_overview.html" in src

    def test_toggle_in_both_forms(self):
        """작업대와 모듈 폼이 같아야 한다."""
        bench = (BASE
                 / "app/templates/collection/_title_workbench.html").read_text(
            encoding="utf-8")
        module = (BASE
                  / "app/static/js/modules/title-gen-form-template.js").read_text(
            encoding="utf-8")
        assert 'x-model="collect.prioritize_low_niche"' in bench
        assert 'x-model="formData.title.collect.prioritize_low_niche"' in module

    def test_serialized_in_module_form(self):
        js = (BASE / "app/static/js/modules/form.js").read_text(
            encoding="utf-8")
        assert "prioritize_low_niche: !!c.prioritize_low_niche" in js
        assert "low_niche_threshold: c.low_niche_threshold" in js
