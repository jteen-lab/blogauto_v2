"""시드 키워드 저장소 폐기 + 모듈 단계 선택 회귀 테스트.

사용자 지시:
    1. 기존 시드 키워드 목록·테이블 제거
    2. 키워드 모듈이 수집/분류/측정을 모두 처리하되,
       각 단계를 개별 모듈로도 돌릴 수 있어야 한다
"""
import re
from pathlib import Path

import pytest

from app.services.keyword_lab.settings import (
    DEFAULT_STEPS, WORK_STEPS, KeywordModuleSettings,
)

BASE = Path(__file__).resolve().parents[2]

SOURCE_DIRS = ("app/services", "app/routers", "app/models", "app/schemas",
               "app/modules")


class TestSeedKeywordGone:
    def test_no_code_references(self):
        """모델이 사라지면 남은 참조는 전부 런타임 오류가 된다."""
        hits = []
        for folder in SOURCE_DIRS:
            for path in (BASE / folder).rglob("*.py"):
                if "__pycache__" in str(path):
                    continue
                if "SeedKeyword" in path.read_text(encoding="utf-8"):
                    hits.append(str(path.relative_to(BASE)))
        assert hits == [], f"남은 참조: {hits}"

    def test_model_removed(self):
        import app.models.keyword as module

        assert not hasattr(module, "SeedKeyword")

    def test_child_fk_removed(self):
        from app.models.keyword import CollectedKeyword

        assert "seed_keyword_id" not in CollectedKeyword.__table__.columns

    def test_template_removed(self):
        assert not (BASE / "app/templates/collection/_keywords.html").exists()

    def test_include_removed(self):
        html = (BASE / "app/templates/collection/index.html").read_text(
            encoding="utf-8")
        assert "_keywords.html" not in html
        assert "기존 시드 키워드 목록" not in html

    def test_seed_endpoints_gone(self):
        from app.routers.data_keywords import router

        paths = {r.path for r in router.routes}
        assert not [p for p in paths if "/seed" in p], paths

    def test_stats_uses_canonical(self):
        src = (BASE / "app/routers/data_keywords.py").read_text(
            encoding="utf-8")
        assert "KeywordCandidate" in src

    def test_migration_drops_child_fk_first(self):
        """자식 FK 를 먼저 끊지 않으면 부모를 못 지운다."""
        src = (BASE / "alembic/versions/065_drop_seed_keywords.py").read_text(
            encoding="utf-8")
        assert src.index("drop_column(CHILD") < src.index("drop_table(TABLE)")

    def test_migration_documents_preconditions(self):
        src = (BASE / "alembic/versions/065_drop_seed_keywords.py").read_text(
            encoding="utf-8")
        assert "이관 완료" in src and "되돌릴 수 없다" in src


class TestFeaturesMovedToCanonical:
    """지우기 전에 살아 있어야 할 기능은 정본으로 옮겼다."""

    @pytest.mark.parametrize("path,needle", [
        ("app/services/filter_apply_service.py", "KeywordCandidate"),
        ("app/services/keyword_extractor_service.py", "KeywordCandidate"),
        ("app/modules/data/keyword_loader.py", "KeywordCandidate"),
        ("app/services/keyword_collector_service.py", "mirror_keyword"),
    ])
    def test_uses_canonical(self, path, needle):
        assert needle in (BASE / path).read_text(encoding="utf-8")

    def test_extractor_writes_to_global_pool(self):
        src = (BASE / "app/services/keyword_extractor_service.py").read_text(
            encoding="utf-8")
        # 니치가 붙으면 그 니치를 가진 블로그가 가져다 쓴다
        assert "blog_id=None" in src


class TestStepSelection:
    """단계를 골라 끄면 개별 모듈이 된다."""

    def test_default_is_full_pipeline_without_rejudge(self):
        assert KeywordModuleSettings.parse({}).steps == list(DEFAULT_STEPS)
        assert "rejudge" not in DEFAULT_STEPS

    def test_single_step_module(self):
        cfg = KeywordModuleSettings.parse({"keyword": {"steps": ["collect"]}})
        assert cfg.steps == ["collect"]

    def test_order_is_fixed(self):
        cfg = KeywordModuleSettings.parse(
            {"keyword": {"steps": ["rejudge", "collect", "measure"]}})
        assert cfg.steps == ["collect", "measure", "rejudge"]

    def test_unknown_step_dropped(self):
        cfg = KeywordModuleSettings.parse(
            {"keyword": {"steps": ["collect", "해킹"]}})
        assert cfg.steps == ["collect"]

    def test_empty_falls_back(self):
        """전부 끄면 회차가 아무 일도 안 한다 — 기본값을 준다."""
        assert KeywordModuleSettings.parse(
            {"keyword": {"steps": []}}).steps == list(DEFAULT_STEPS)

    def test_legacy_rejudge_absorbed(self):
        cfg = KeywordModuleSettings.parse(
            {"keyword": {"rejudge_on_run": True}})
        assert cfg.steps == list(DEFAULT_STEPS) + ["rejudge"]

    def test_explicit_steps_win_over_legacy(self):
        cfg = KeywordModuleSettings.parse(
            {"keyword": {"steps": ["collect"], "rejudge_on_run": True}})
        assert cfg.steps == ["collect", "rejudge"]

    def test_round_trip(self):
        cfg = KeywordModuleSettings.parse({"keyword": {"steps": ["measure"]}})
        assert cfg.to_dict()["steps"] == ["measure"]

    def test_all_steps_known(self):
        assert set(WORK_STEPS) == {"collect", "measure", "classify", "rejudge"}

    def test_runner_uses_config_steps(self):
        src = (BASE / "app/services/keyword_lab/runner.py").read_text(
            encoding="utf-8")
        assert "cfg.steps" in src
        # rejudge 는 이제 steps 가 정한다(이중 게이트 제거)
        assert 'if "rejudge" in steps:' in src
        assert "cfg.rejudge_on_run" not in src

    def test_form_exposes_step_toggles(self):
        tpl = (BASE / "app/static/js/modules/keyword-form-template.js").read_text(
            encoding="utf-8")
        for flag in ("step_collect", "step_measure", "step_classify",
                     "step_rejudge"):
            assert flag in tpl
        js = (BASE / "app/static/js/modules/form.js").read_text(
            encoding="utf-8")
        assert "['step_collect', 'collect']" in js

    def test_form_explains_individual_modules(self):
        tpl = (BASE / "app/static/js/modules/keyword-form-template.js").read_text(
            encoding="utf-8")
        assert "그 단계 전용 모듈" in tpl
