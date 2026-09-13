"""연결 검증 — 새 모듈이 파이프라인에 실제로 물려 있는가."""
import pytest

from app.services.reference import checklist_runner as CR


class FakeAI:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    async def generate(self, **kw):
        self.calls.append(kw)
        return {"content": self.replies.pop(0) if self.replies else ""}


class FakeResult:
    def __init__(self, title, link):
        self.title, self.link, self.description = title, link, ""


class FakeSearch:
    def __init__(self, rows=None, web_rows=None):
        self.rows = rows or []
        self.web_rows = web_rows or []
        self.web_calls = 0
        self.plans = []

    async def search_many(self, plan, count=20):
        self.plans.append(list(plan))
        return {key: list(self.rows) for key in plan}

    async def search_webdoc(self, query, count=30):
        self.web_calls += 1
        return list(self.web_rows)


SHEET = """- 첫째 항목입니다 [law]
- 둘째 항목입니다 [web]"""


@pytest.mark.asyncio
class TestCollectEvidence:
    async def test_기본은_꺼져_있고_기존_검색을_쓴다(self):
        search = FakeSearch(web_rows=[FakeResult("웹", "http://w")])
        rows, sheet = await CR.collect_evidence(
            FakeAI(), search, "질의", "제목", {})
        assert search.web_calls == 1
        assert sheet is None
        assert len(rows) == 1

    async def test_AI_미지정이면_기존_검색으로_간다(self):
        search = FakeSearch(web_rows=[FakeResult("웹", "http://w")])
        settings = {"evidence_checklist": {"enabled": True}}
        rows, sheet = await CR.collect_evidence(
            FakeAI(SHEET), search, "질의", "제목", settings)
        assert search.web_calls == 1
        assert sheet is None

    async def test_켜지면_항목별로_던진다(self):
        search = FakeSearch(rows=[FakeResult("근거", "http://a")])
        settings = {"evidence_checklist": {"enabled": True,
                                           "ai_provider": "openai"}}
        ai = FakeAI(SHEET, "1. 채움\n2. 채움")
        rows, sheet = await CR.collect_evidence(
            ai, search, "질의", "원룸 퇴거 청소비", settings)
        assert len(search.plans[0]) == 2
        assert sheet is not None and sheet.is_complete
        assert search.web_calls == 0          # 충분하면 보충하지 않는다

    async def test_채움이_모자라면_기존_검색으로_보충한다(self):
        search = FakeSearch(rows=[FakeResult("근거", "http://a")],
                            web_rows=[FakeResult("웹", "http://w")])
        settings = {"evidence_checklist": {"enabled": True,
                                           "ai_provider": "openai"}}
        ai = FakeAI(SHEET, "1. 빈칸\n2. 빈칸", "1. 빈칸\n2. 빈칸")
        rows, sheet = await CR.collect_evidence(
            ai, search, "질의", "제목입니다", settings)
        assert search.web_calls == 1
        assert any(r.link == "http://w" for r in rows)

    async def test_목록이_비면_기존_검색으로_간다(self):
        search = FakeSearch(web_rows=[FakeResult("웹", "http://w")])
        settings = {"evidence_checklist": {"enabled": True,
                                           "ai_provider": "openai"}}
        rows, sheet = await CR.collect_evidence(
            FakeAI(""), search, "질의", "제목", settings)
        assert sheet is None
        assert search.web_calls == 1

    async def test_참조_설정의_AI를_물려받는다(self):
        search = FakeSearch(rows=[FakeResult("근거", "http://a")])
        settings = {"ai_provider": "deepseek", "ai_model": "chat",
                    "evidence_checklist": {"enabled": True}}
        ai = FakeAI(SHEET, "1. 채움\n2. 채움")
        await CR.collect_evidence(ai, search, "질의", "제목입니다", settings)
        assert ai.calls[0]["provider"] == "deepseek"


class TestResultOutline:
    def test_뼈대가_주입문에_들어간다(self):
        from app.services.generation.reference_collector import (
            ReferenceCollectionResult,
        )

        got = ReferenceCollectionResult(
            count=1, summaries=[], digest="자료 본문입니다",
            outline=["원상회복 의무의 법적 근거", "통상손모는 누구 책임인가"])
        text = got.to_prompt_injection()
        assert "글의 뼈대" in text
        assert "통상손모" in text

    def test_뼈대가_없으면_지시문도_없다(self):
        from app.services.generation.reference_collector import (
            ReferenceCollectionResult,
        )

        got = ReferenceCollectionResult(count=1, summaries=[],
                                        digest="자료 본문입니다")
        assert "글의 뼈대" not in got.to_prompt_injection()


class TestRotationWiring:
    def _executor(self):
        from app.services.generation.flow_generate_executor import (
            FlowGenerateExecutor,
        )
        return FlowGenerateExecutor.__new__(FlowGenerateExecutor)

    class Blog:
        name = "테스트"
        adsense_status = None
        cpa_enabled = False
        total_post_count = 1

    class Title:
        topic_id = 24
        title = "원룸 이사 견적"

    def _settings(self):
        return {"prompt_rotation": {
            "enabled": True, "mode": "sequential",
            "variants": [{"template": "첫째"}, {"template": "둘째"}]}}

    def test_로테이션이_실행기에_물려_있다(self):
        got = self._executor()._apply_rotation(
            self._settings(), self.Blog(), self.Title(), title_id=7)
        assert got["content_generation"]["user_prompt_template"] == "둘째"

    def test_승인용_프롬프트가_걸리면_로테이션을_건너뛴다(self):
        from app.services.prompt_builder.presets import PRESETS

        코드 = next((p["code"] for p in PRESETS if p.get("full_prompt")), None)
        if 코드 is None:
            import pytest as _pt
            _pt.skip("완성 프롬프트를 가진 프리셋이 없다")
        settings = self._settings()
        settings["adsense_approval_preset"] = 코드
        got = self._executor()._apply_rotation(
            settings, self.Blog(), self.Title(), title_id=7)
        assert got is settings          # 손대지 않는다

    def test_커서가_없으면_제목_id를_쓴다(self):
        class B(self.Blog):
            total_post_count = 0
        got = self._executor()._apply_rotation(
            self._settings(), B(), self.Title(), title_id=3)
        assert got["_rotation"]["index"] == 1      # 3 % 2
