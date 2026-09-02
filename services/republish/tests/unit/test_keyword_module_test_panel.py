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

    def test_shows_keywords_and_sources(self):
        """키워드 모듈은 수집·측정·분류가 전부다 — 제목은 제목 모듈이 보여준다."""
        tpl = self._tpl()
        for key in ("kwTest.result?.samples", "kwTest.result?.by_source",
                    "kwTest.result?.message"):
            assert key in tpl, key
        title = (BASE / "app/static/js/modules/title-gen-form-template.js").read_text(
            encoding="utf-8")
        assert "tgTest.result?.preview" in title

    def test_ai_select_moved_to_title_module(self):
        """제목 생성 AI 는 키워드 모듈에서 제거됐다."""
        assert "ai_provider" not in self._tpl()
        title = (BASE / "app/static/js/modules/title-gen-form-template.js").read_text(
            encoding="utf-8")
        assert "formData.title.ai_provider" in title

    def test_models_loaded_for_title_type(self):
        js = self._form()
        assert "if (typeCode === 'title_gen') {" in js
        assert "loadKeywordModels()" in js

    def test_state_declared(self):
        assert re.search(r"kwTest:\s*\{[^}]*busy", self._form())


class TestRunEndpointShape:
    def test_uses_same_runner_entry(self):
        src = (BASE / "app/routers/keyword_lab.py").read_text(encoding="utf-8")
        # 화면·플로우·오토런이 같은 응답 모양을 써야 한다
        assert "runner.run_for_blogs(settings, blogs" in src


class TestAiSelectKeepsSavedValue:
    """저장된 AI 설정이 폼을 다시 열 때 사라지지 않는다.

    모델 목록은 비동기로 온다. 그 전에 select 에 매칭 option 이 없으면
    브라우저가 value 를 '' 로 만들고 x-model 이 빈 값을 formData 에
    되쓴다. 그대로 저장하면 실제로 지워진다.
    """

    def _js(self):
        return (BASE / "app/static/js/modules/form.js").read_text(
            encoding="utf-8")

    def test_provider_list_includes_saved(self):
        """저장된 값이 옵션에 없으면 select 가 빈 값을 되쓴다.

        키워드 모듈의 AI 선택은 제거됐고(제목 모듈이 맡는다) 같은 보호는
        제목 모듈 쪽에 남아 있다.
        """
        js = self._js()
        assert "const saved = this.formData?.title?.ai_provider;" in js
        assert "if (saved) set.add(saved);" in js

    def test_model_list_includes_saved(self):
        js = self._js()
        assert "if (saved && !list.includes(saved)) list.unshift(saved);" in js

    def test_reason_is_documented(self):
        assert "formData 에 되써 버린다" in self._js()
