"""S5 — 제목 생성/수집 모듈 회귀 테스트.

계획서: docs/plans/keyword_pipeline_restructure_review.md §5-2

핵심:
    수집 모듈이 제목까지 만들면 중간 결과를 걸러낼 자리가 없다 → 별도 모듈
    수집 제목은 재고로 쓰지 않고 "겹치지 말라" 는 각도 신호로만 쓴다
    생성 로직은 복사하지 않고 기존 TitleMaker·ClusterBuilder 를 재사용한다
"""
from pathlib import Path

import pytest

from app.services.title_gen import angles
from app.services.title_gen.runner import TitleModuleRunner, _aggregate
from app.services.title_gen.settings import TitleModuleSettings

BASE = Path(__file__).resolve().parents[2]


class TestSettings:
    def test_dry_run_defaults_on(self):
        # 검증 없이 재고를 오염시키는 쪽이 되돌리기 어렵다
        assert TitleModuleSettings.parse({}).dry_run is True

    def test_reads_nested_shape(self):
        cfg = TitleModuleSettings.parse(
            {"title": {"cluster_min_size": 2, "ai_provider": "google"}})
        assert cfg.cluster_min_size == 2 and cfg.ai_provider == "google"

    def test_schedule_interval(self):
        cfg = TitleModuleSettings.parse({"schedule": {"interval_minutes": 90}})
        assert cfg.interval_minutes == 90

    def test_threshold_out_of_range(self):
        for bad in (0, -1, 5, "x"):
            assert TitleModuleSettings.parse(
                {"title": {"cluster_threshold": bad}}).cluster_threshold == 0.34

    def test_empty_provider_is_none(self):
        assert TitleModuleSettings.parse(
            {"title": {"ai_provider": ""}}).ai_provider is None

    def test_round_trip(self):
        cfg = TitleModuleSettings.parse({"title": {"use_angles": False}})
        assert cfg.to_dict()["use_angles"] is False

    def test_adapter_matches_maker_fields(self):
        """생성 로직을 복사하지 않고 어댑터로 넘긴다."""
        cfg = TitleModuleSettings.parse({"title": {"titles_per_cluster": 7}})
        maker = cfg.as_maker_config()
        for field in ("dry_run", "ai_provider", "ai_model", "cluster_enabled",
                      "cluster_threshold", "cluster_min_size",
                      "cluster_max_size", "titles_per_cluster",
                      "titles_per_keyword", "min_inventory"):
            assert hasattr(maker, field), field
        assert maker.titles_per_cluster == 7


class TestAngles:
    def test_strips_tags_and_entities(self):
        assert angles.clean("<b>전기기사</b> 실기 &amp; 정리") == "전기기사 실기 정리"

    def test_hint_is_empty_without_titles(self):
        assert angles.hint([]) == ""

    def test_hint_asks_for_different_angle(self):
        text = angles.hint(["A 제목", "B 제목"])
        assert "겹치지 않는" in text
        assert "A 제목" in text

    def test_hint_respects_limit(self):
        text = angles.hint([f"제목 {i}" for i in range(30)], limit=3)
        assert text.count("- ") == 3

    @pytest.mark.asyncio
    async def test_fetch_drops_dupes_and_short(self):
        class _Search:
            async def search_blog(self, q, display=10, **k):
                return {"success": True, "items": [
                    {"title": "<b>전기기사</b> 실기 정리"},
                    {"title": "전기기사 실기 정리"},      # 중복
                    {"title": "짧음"},                    # 너무 짧음
                    {"title": "전기기사 필기 후기입니다"},
                ]}

        out = await angles.fetch(_Search(), "전기기사")
        assert out == ["전기기사 실기 정리", "전기기사 필기 후기입니다"]

    @pytest.mark.asyncio
    async def test_fetch_failure_is_empty(self):
        class _Dead:
            async def search_blog(self, *a, **k):
                raise RuntimeError("차단")

        assert await angles.fetch(_Dead(), "전기기사") == []


class TestAggregate:
    def test_dry_run_stated(self):
        out = _aggregate([("A", {
            "success": True, "cluster": {"clusters": 2},
            "titles": {"made": 0, "dry_run": True, "blocked": 1, "queued": 2,
                       "preview": [{"title": "전기기사 실기 정리",
                                    "state": "ready"}]}})])
        assert "검증 모드 — 저장 안 함" in out["message"]
        assert "묶음 2개" in out["message"]
        assert out["dry_run"] is True

    def test_skip_reason_first(self):
        out = _aggregate([("A", {"success": True, "skipped": True,
                                 "message": "재고 충분 (500/30)"})])
        assert out["message"].startswith("실행 안 됨 — 재고 충분")

    def test_error_surfaced_when_nothing_made(self):
        out = _aggregate([("A", {
            "success": True, "cluster": {},
            "titles": {"made": 0, "preview": [],
                       "error": "AI 제공자가 지정되지 않았습니다"}})])
        assert "⚠ AI 제공자가 지정되지 않았습니다" in out["message"]

    def test_all_failed_is_failure(self):
        out = _aggregate([("A", {"success": False, "error": "키 없음"})])
        assert out["success"] is False and out["error"] == "키 없음"

    def test_preview_capped(self):
        rows = [("A", {"success": True, "cluster": {}, "titles": {
            "made": 0, "dry_run": True,
            "preview": [{"title": f"t{i}", "state": "ready"}
                        for i in range(200)]}})]
        assert len(_aggregate(rows)["preview"]) == 60


class TestRunner:
    def test_exposes_both_entries(self):
        assert hasattr(TitleModuleRunner, "run")
        assert hasattr(TitleModuleRunner, "run_for_blogs")

    def test_reuses_existing_services(self):
        src = (BASE / "app/services/title_gen/runner.py").read_text(
            encoding="utf-8")
        # 제목 생성 로직을 복사하지 않는다
        assert "from ..keyword_lab.title_maker import TitleMaker" in src
        assert "from ..keyword_lab.cluster_builder import ClusterBuilder" in src

    def test_inventory_gate_needs_a_blog(self):
        src = (BASE / "app/services/title_gen/runner.py").read_text(
            encoding="utf-8")
        assert "if not force and blog is not None" in src

    def test_angle_hook_wired(self):
        src = (BASE / "app/services/title_gen/runner.py").read_text(
            encoding="utf-8")
        assert "maker.angle_hint" in src

    def test_maker_accepts_hook(self):
        src = (BASE / "app/services/keyword_lab/title_maker.py").read_text(
            encoding="utf-8")
        assert "self.angle_hint" in src
        assert "async def _angles(self" in src


class TestWiring:
    def test_module_type_migration(self):
        src = (BASE / "alembic/versions/063_add_title_module_type.py").read_text(
            encoding="utf-8")
        assert 'CODE = "title_gen"' in src
        assert "in_use" in src   # 플로우가 물고 있으면 못 지운다

    def test_three_execution_paths(self):
        flows = (BASE / "app/routers/flows_execute.py").read_text(
            encoding="utf-8")
        sched = (BASE / "app/scheduler/flow_scheduler.py").read_text(
            encoding="utf-8")
        assert 'elif type_code == "title_gen":' in flows      # 단일 실행
        assert 'if "title_gen" in modules_by_type:' in flows  # 플로우 전체
        assert 'action_type == "title_gen"' in sched          # 오토런

    def test_single_run_forces(self):
        flows = (BASE / "app/routers/flows_execute.py").read_text(
            encoding="utf-8")
        assert "target_module, tg_blogs, db, force=True" in flows

    def test_router_registered(self):
        assert "title_gen_router" in (BASE / "app/main.py").read_text(
            encoding="utf-8")

    def test_form_and_popup(self):
        html = (BASE / "app/templates/modules/list.html").read_text(
            encoding="utf-8")
        assert "'title_gen', '제목 생성/수집'" in html
        assert "title-gen-form-template.js" in html

    def test_flow_form_tab(self):
        html = (BASE / "app/templates/flows/_form.html").read_text(
            encoding="utf-8")
        assert "activeModuleTab = 'title_gen'" in html

    def test_test_panel_present(self):
        tpl = (BASE / "app/static/js/modules/title-gen-form-template.js").read_text(
            encoding="utf-8")
        assert "runTitleTest()" in tpl
        assert "tgTest.result?.preview" in tpl

    @pytest.mark.parametrize("path", [
        "app/services/title_gen/runner.py",
        "app/services/title_gen/settings.py",
        "app/services/title_gen/angles.py",
        "app/routers/title_gen.py",
        "app/static/js/modules/title-gen-form-template.js",
    ])
    def test_files_under_500_lines(self, path):
        lines = (BASE / path).read_text(encoding="utf-8").count("\n")
        assert lines <= 500, f"{path} = {lines}줄"
