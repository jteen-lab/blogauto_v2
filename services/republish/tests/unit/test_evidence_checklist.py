"""근거 체크리스트 — 검색 전에 무엇을 알아야 하는지 정한다."""
import pytest

from app.services.reference import checklist_runner as CR
from app.services.reference import evidence_checklist as CK


class FakeAI:
    def __init__(self, *replies, boom=False):
        self.replies = list(replies)
        self.boom = boom
        self.calls = []

    async def generate(self, **kw):
        self.calls.append(kw)
        if self.boom:
            raise RuntimeError("죽음")
        return {"content": self.replies.pop(0) if self.replies else ""}


class FakeResult:
    def __init__(self, title, link, desc=""):
        self.title, self.link, self.description = title, link, desc


class FakeSearch:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else []
        self.plans = []

    async def search_many(self, plan, count=20):
        self.plans.append(list(plan))
        return {key: list(self.rows) for key in plan}


SHEET_TEXT = """- 원상회복 의무의 법적 근거 [law]
- 통상손모는 누구 책임인가 [law]
- 계약서 특약이 있으면 달라지는가 [web]
- 보증금 임의공제 대응 절차 [news]"""


class TestParse:
    def test_소스를_읽는다(self):
        items = CK.parse(SHEET_TEXT)
        assert len(items) == 4
        assert [i.source for i in items] == ["law", "law", "web", "news"]

    def test_소스가_없으면_web(self):
        assert CK.parse("- 그냥 항목입니다")[0].source == "web"

    def test_모르는_소스는_web(self):
        assert CK.parse("- 항목입니다 [twitter]")[0].source == "web"

    def test_번호와_불릿을_걷어낸다(self):
        assert CK.parse("1. 첫 항목입니다 [web]")[0].ask == "첫 항목입니다"

    def test_상한을_지킨다(self):
        text = "\n".join(f"- 항목 번호 {i} 입니다 [web]" for i in range(20))
        assert len(CK.parse(text)) == CK.MAX_ITEMS

    def test_중복을_제거한다(self):
        assert len(CK.parse("- 같은 항목입니다\n- 같은 항목입니다")) == 1


class TestChecklist:
    def _sheet(self):
        return CK.Checklist(title="원룸 퇴거 청소비", items=CK.parse(SHEET_TEXT))

    def test_질의는_항목_수만큼(self):
        assert len(self._sheet().queries()) == 4

    def test_질의에_소스가_붙는다(self):
        assert self._sheet().queries()[0][0] == "law"

    def test_미충족만_고를_수_있다(self):
        sheet = self._sheet()
        sheet.items[0].filled = True
        assert len(sheet.queries(only_unfilled=True)) == 3

    def test_채움_비율을_센다(self):
        sheet = self._sheet()
        sheet.items[0].filled = True
        sheet.items[1].filled = True
        assert sheet.coverage == 0.5

    def test_뼈대는_채워진_항목만(self):
        sheet = self._sheet()
        sheet.items[1].filled = True
        assert sheet.outline() == ["통상손모는 누구 책임인가"]

    def test_전부_채우면_완료(self):
        sheet = self._sheet()
        for item in sheet.items:
            item.filled = True
        assert sheet.is_complete


class TestVerdicts:
    def test_채움과_빈칸을_읽는다(self):
        assert CK.parse_verdicts("1. 채움\n2. 빈칸\n3. 채움", 3) \
            == [True, False, True]

    def test_모자라면_빈칸으로_채운다(self):
        assert CK.parse_verdicts("1. 채움", 3) == [True, False, False]

    def test_못_읽으면_빈칸(self):
        assert CK.parse_verdicts("알 수 없음", 2) == [False, False]


class TestRetryPolicy:
    def test_빈칸이_있으면_재검색한다(self):
        sheet = CK.Checklist(title="t", items=CK.parse(SHEET_TEXT))
        assert CK.should_retry(sheet)

    def test_상한을_넘기면_멈춘다(self):
        sheet = CK.Checklist(title="t", items=CK.parse(SHEET_TEXT))
        sheet.rounds = CK.MAX_RETRY_ROUNDS
        assert not CK.should_retry(sheet)

    def test_다_채우면_재검색하지_않는다(self):
        sheet = CK.Checklist(title="t", items=CK.parse(SHEET_TEXT))
        for item in sheet.items:
            item.filled = True
        assert not CK.should_retry(sheet)

    def test_재검색은_소스를_넓힌다(self):
        sheet = CK.Checklist(title="t", items=CK.parse("- 법 근거 확인 [law]"))
        assert CK.broaden(sheet)[0][0] == "web"


class TestInjection:
    def test_채운_항목이_뼈대가_된다(self):
        sheet = CK.Checklist(title="t", items=CK.parse(SHEET_TEXT))
        sheet.items[0].filled = True
        got = CK.to_prompt_injection(sheet)
        assert "글의 뼈대" in got
        assert "원상회복 의무의 법적 근거" in got

    def test_빈_목록은_지시문도_없다(self):
        assert CK.to_prompt_injection(CK.Checklist(title="t")) == ""


@pytest.mark.asyncio
class TestBuildJudge:
    async def test_provider_가_없으면_호출하지_않는다(self):
        ai = FakeAI(SHEET_TEXT)
        sheet = await CK.build(ai, "제목", provider="")
        assert sheet.items == []
        assert ai.calls == []

    async def test_AI가_죽어도_빈_목록을_돌려준다(self):
        sheet = await CK.build(FakeAI(boom=True), "제목", provider="openai")
        assert sheet.items == []

    async def test_판정이_채움을_반영한다(self):
        sheet = CK.Checklist(title="t", items=CK.parse(SHEET_TEXT))
        ai = FakeAI("1. 채움\n2. 빈칸\n3. 채움\n4. 빈칸")
        await CK.judge(ai, sheet, "자료 본문", provider="openai")
        assert [i.filled for i in sheet.items] == [True, False, True, False]
        assert sheet.coverage == 0.5

    async def test_판정은_온도를_0으로_쓴다(self):
        sheet = CK.Checklist(title="t", items=CK.parse(SHEET_TEXT))
        ai = FakeAI("1. 채움")
        await CK.judge(ai, sheet, "자료", provider="openai")
        assert ai.calls[0]["temperature"] == 0.0


@pytest.mark.asyncio
class TestRunner:
    async def test_목록이_비면_검색하지_않는다(self):
        search = FakeSearch()
        got = await CR.run(FakeAI(""), search, "제목", provider="openai")
        assert got.results == []
        assert search.plans == []
        assert got.ai_calls == 1

    async def test_항목별로_동시에_던진다(self):
        search = FakeSearch([FakeResult("자료", "http://a")])
        ai = FakeAI(SHEET_TEXT, "1. 채움\n2. 채움\n3. 채움\n4. 채움")
        got = await CR.run(ai, search, "원룸 퇴거 청소비", provider="openai")
        assert len(search.plans[0]) == 4          # 항목 수만큼 한 번에
        assert got.sheet.is_complete
        assert got.ai_calls == 2                  # 목록 + 판정
        assert got.usable

    async def test_빈칸이_남으면_한_번만_재검색한다(self):
        search = FakeSearch([FakeResult("자료", "http://a")])
        ai = FakeAI(SHEET_TEXT,
                    "1. 채움\n2. 빈칸\n3. 빈칸\n4. 빈칸",
                    "1. 채움\n2. 빈칸\n3. 빈칸")
        got = await CR.run(ai, search, "제목입니다", provider="openai")
        assert len(search.plans) == 2             # 최초 + 재검색 1회
        assert got.sheet.rounds == 1
        assert got.ai_calls == 3                  # 목록 + 판정 2회

    async def test_같은_링크는_중복으로_담지_않는다(self):
        search = FakeSearch([FakeResult("자료", "http://a")])
        ai = FakeAI(SHEET_TEXT, "1. 채움\n2. 채움\n3. 채움\n4. 채움")
        got = await CR.run(ai, search, "제목입니다", provider="openai")
        assert len(got.results) == 1

    async def test_절반_미만이면_쓸_수_없다고_본다(self):
        search = FakeSearch([FakeResult("자료", "http://a")])
        ai = FakeAI(SHEET_TEXT,
                    "1. 채움\n2. 빈칸\n3. 빈칸\n4. 빈칸",
                    "1. 빈칸\n2. 빈칸\n3. 빈칸")
        got = await CR.run(ai, search, "제목입니다", provider="openai")
        assert not got.usable


class TestAITraces:
    def test_상투어가_임계를_넘으면_잡는다(self):
        from app.services.generation import quality_gate as QG

        글 = "이 부분은 중요합니다. 권합니다. 경우가 많습니다."
        assert QG.check_ai_traces(글)

    def test_한두개는_넘어간다(self):
        from app.services.generation import quality_gate as QG

        assert QG.check_ai_traces("이 부분만 보면 됩니다.") == []

    def test_말줄임표를_잡는다(self):
        from app.services.generation import quality_gate as QG

        assert any("말줄임표" in r for r in QG.check_ai_traces("그렇습니다…"))

    def test_금지_태그를_잡는다(self):
        from app.services.generation import quality_gate as QG

        got = QG.check_ai_traces('<blockquote>인용</blockquote>')
        assert any("인용문" in r for r in got)

    def test_기본은_경고이고_차단이_아니다(self):
        from app.services.generation import quality_gate as QG

        글 = "이 부분은 중요합니다. 권합니다. 경우가 많습니다. " + "가" * 2000
        got = QG.evaluate("제목", 글)
        assert not got.blocked
        assert got.warnings

    def test_설정을_켜면_차단한다(self):
        from app.services.generation import quality_gate as QG

        글 = "이 부분은 중요합니다. 권합니다. 경우가 많습니다. " + "가" * 2000
        got = QG.evaluate("제목", 글, trace_blocks=True)
        assert got.blocked

    def test_설정_해석(self):
        from app.services.generation import quality_gate as QG

        assert QG.resolve_settings({})["trace_blocks"] is False
        assert QG.resolve_settings(
            {"quality_gate": {"trace_blocks": True}})["trace_blocks"] is True
