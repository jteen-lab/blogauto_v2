"""모듈 안에서 바로 테스트하고 결과를 보는 경로 회귀 테스트.

배경: 플로우에서 돌려도 결과가 화면에 안 보였고, 제목 20건이 조용히
    실패했다. 원인은 두 가지였다.
    1. 블로그가 없으면 AI 제공자가 비는데 AI 서비스는 폴백을 하지 않는다
       → 모듈이 자기 AI 를 갖는다
    2. 결과를 볼 자리가 없었다 → 모듈 폼 안에 테스트 패널
"""
import re
from pathlib import Path
from types import SimpleNamespace

from app.services.keyword_lab.runner import KeywordModuleRunner
from app.services.keyword_lab.settings import KeywordModuleSettings
from app.services.keyword_lab.title_maker import TitleMaker

BASE = Path(__file__).resolve().parents[2]


class TestAiResolution:
    """제목 생성 AI 는 모듈 → 블로그 순으로 정한다."""

    def test_module_setting_wins(self):
        cfg = KeywordModuleSettings.parse(
            {"keyword": {"ai_provider": "google", "ai_model": "gemini"}})
        blog = SimpleNamespace(ai_config={"writing_ai": {"provider": "openai"}})
        assert TitleMaker.resolve_ai(cfg, blog)["provider"] == "google"

    def test_falls_back_to_blog(self):
        cfg = KeywordModuleSettings.parse({})
        blog = SimpleNamespace(
            ai_config={"writing_ai": {"provider": "openai", "model": "gpt"}})
        picked = TitleMaker.resolve_ai(cfg, blog)
        assert (picked["provider"], picked["model"]) == ("openai", "gpt")

    def test_none_when_neither(self):
        # 블로그 없이 시드만으로 도는 테스트가 여기 해당한다
        assert TitleMaker.resolve_ai(
            KeywordModuleSettings.parse({}), None)["provider"] is None

    def test_empty_string_is_not_a_provider(self):
        cfg = KeywordModuleSettings.parse({"keyword": {"ai_provider": ""}})
        assert cfg.ai_provider is None

    def test_round_trip(self):
        cfg = KeywordModuleSettings.parse(
            {"keyword": {"ai_provider": "google"}})
        assert cfg.to_dict()["ai_provider"] == "google"


class TestSilentFailureIsSurfaced:
    """20건이 조용히 실패해도 화면에 '제목 0편' 만 보이던 자리."""

    def test_maker_records_reason(self):
        src = (BASE / "app/services/keyword_lab/title_maker.py").read_text(
            encoding="utf-8")
        assert "self.last_error" in src
        assert "AI 제공자가 지정되지 않았습니다" in src

    def test_reason_reaches_the_summary(self):
        out = KeywordModuleRunner._aggregate([("-", {
            "success": True,
            "collect": {"saved": 100, "samples": ["전기기사"]},
            "measure": {"measured": 50},
            "titles": {"made": 0, "dry_run": True, "preview": [],
                       "error": "AI 제공자가 지정되지 않았습니다"}})])
        assert "⚠ AI 제공자가 지정되지 않았습니다" in out["message"]

    def test_no_warning_when_titles_exist(self):
        out = KeywordModuleRunner._aggregate([("-", {
            "success": True, "collect": {}, "measure": {},
            "titles": {"made": 0, "dry_run": True,
                       "preview": [{"title": "가", "state": "ready"}],
                       "error": None}})])
        assert "⚠" not in out["message"]


class TestResultCarriesEvidence:
    """숫자만이 아니라 무엇이 들어왔는지 돌려준다."""

    def _out(self):
        return KeywordModuleRunner._aggregate([("-", {
            "success": True,
            "collect": {"saved": 2, "samples": ["전기기사", "컴활"],
                        "by_source": {"naver_ads": 1, "google_suggest": 1}},
            "measure": {"measured": 2},
            "titles": {"made": 0, "dry_run": True, "preview": [
                {"title": "전기기사 실기 정리", "state": "ready",
                 "reason": "재고 후보"}]}})])

    def test_samples_returned(self):
        assert self._out()["samples"] == ["전기기사", "컴활"]

    def test_by_source_returned(self):
        assert self._out()["by_source"] == {"naver_ads": 1,
                                            "google_suggest": 1}

    def test_preview_returned(self):
        assert self._out()["preview"][0]["reason"] == "재고 후보"

    def test_samples_capped(self):
        rows = [("-", {"success": True, "measure": {}, "titles": {},
                       "collect": {"saved": 0,
                                   "samples": [f"k{i}" for i in range(100)]}})]
        assert len(KeywordModuleRunner._aggregate(rows)["samples"]) == 40


class TestModuleTestPanel:
    """모듈 폼 안에서 저장 없이 돌리고 결과를 본다."""

    def _form(self):
        return (BASE / "app/static/js/modules/form.js").read_text(
            encoding="utf-8")

    def _tpl(self):
        return (BASE / "app/static/js/modules/keyword-form-template.js").read_text(
            encoding="utf-8")

    def test_run_button_exists(self):
        assert "runKeywordTest()" in self._tpl()

    def test_uses_unsaved_form_values(self):
        js = self._form()
        # 저장 후 확인하면 실패한 설정이 이미 남는다
        assert "const payload = this.prepareRequestData();" in js
        assert "settings_override: payload.settings" in js

    def test_forces_execution(self):
        assert "force: true" in self._form()

    def test_shows_keywords_titles_and_sources(self):
        tpl = self._tpl()
        for key in ("kwTest.result?.samples", "kwTest.result?.preview",
                    "kwTest.result?.by_source", "kwTest.result?.message"):
            assert key in tpl, key

    def test_ai_select_present(self):
        tpl = self._tpl()
        assert "formData.keyword.ai_provider" in tpl
        assert "formData.keyword.ai_model" in tpl

    def test_models_loaded_for_keyword_type(self):
        js = self._form()
        assert "if (typeCode === 'keyword')" in js
        assert "loadKeywordModels()" in js

    def test_state_declared(self):
        assert re.search(r"kwTest:\s*\{[^}]*busy", self._form())


class TestRunEndpointShape:
    def test_uses_same_runner_entry(self):
        src = (BASE / "app/routers/keyword_lab.py").read_text(encoding="utf-8")
        # 화면·플로우·오토런이 같은 응답 모양을 써야 한다
        assert "runner.run_for_blogs(settings, blogs" in src
