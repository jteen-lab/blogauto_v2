"""질문 발굴 — 키워드로는 나오지 않는 주제를 만드는 경로."""
import pytest

from app.services.keyword_lab import question_miner as QM
from app.services.keyword_lab.sources.community import CommunityQuestion
from app.services import title_source as TS


def _q(title, desc=""):
    return CommunityQuestion(title=title, link="http://x", description=desc,
                             source="naver_kin", seed="이사 견적")


class FakeAI:
    def __init__(self, content="", boom=False):
        self.content = content
        self.boom = boom
        self.calls = []

    async def generate(self, **kw):
        self.calls.append(kw)
        if self.boom:
            raise RuntimeError("죽음")
        return {"content": self.content}


class FakeGateMixin:
    """TitleGate 를 타지 않도록 _admit 만 갈아끼운다."""

    async def _admit(self, titles, row, dry_run):
        return {"admitted": len(titles),
                "preview": [{"title": t, "state": "ready"} for t in titles]}


class TestParseTitles:
    def test_번호와_불릿을_걷어낸다(self):
        got = QM.parse_titles("1. 첫 번째 제목입니다\n- 두 번째 제목입니다", 5)
        assert got == ["첫 번째 제목입니다", "두 번째 제목입니다"]

    def test_따옴표를_걷어낸다(self):
        assert QM.parse_titles('"같은 건물 위층 이사 비용"', 5) \
            == ["같은 건물 위층 이사 비용"]

    def test_너무_짧거나_길면_버린다(self):
        assert QM.parse_titles("짧음\n" + "가" * 200, 5) == []

    def test_중복을_제거한다(self):
        got = QM.parse_titles("같은 제목입니다\n같은 제목입니다", 5)
        assert len(got) == 1

    def test_개수를_지킨다(self):
        text = "\n".join(f"{i}번째 제목입니다" for i in range(10))
        assert len(QM.parse_titles(text, 3)) == 3


@pytest.mark.asyncio
class TestRun:
    def _miner(self, ai, questions):
        miner = QM.QuestionMiner(db=None, ai_service=ai, user_id=1)
        miner.__class__ = type("M", (FakeGateMixin, QM.QuestionMiner), {})

        async def _collect(*a, **k):
            return questions
        miner._collect = _collect
        return miner

    async def test_질문이_없으면_사유를_남긴다(self):
        miner = self._miner(FakeAI(), [])
        got = await miner.run(None, ["이사"], row=None, niche="이사")
        assert got.collected == 0
        assert "질문을 찾지" in got.error

    async def test_상황이_없는_질문은_걸러진다(self):
        miner = self._miner(FakeAI(), [_q("이사 견적 어떻게 하나요")])
        got = await miner.run(None, ["이사"], row=None, niche="이사")
        assert got.collected == 1
        assert got.concrete == 0
        assert "새로운 상황이 없습니다" in got.error

    async def test_이미_쓴_상황은_제외된다(self):
        from app.services.keyword_lab import situation as S

        질문 = _q("2층에서 3층으로 이사인데 장롱 3짝입니다")
        mark = S.extract(질문.text).fingerprint()
        miner = self._miner(FakeAI(), [질문])
        got = await miner.run(None, ["이사"], row=None, niche="이사",
                              known=[mark])
        assert got.concrete == 1
        assert got.fresh == 0

    async def test_provider_가_없으면_AI를_부르지_않는다(self):
        ai = FakeAI(content="제목이 나오면 안 됩니다")
        miner = self._miner(ai, [_q("2층에서 3층으로 이사, 장롱 3짝")])
        got = await miner.run(None, ["이사"], row=None, niche="이사")
        assert got.fresh == 1
        assert ai.calls == []
        assert got.titles == []

    async def test_상황이_있으면_제목까지_만든다(self):
        ai = FakeAI(content="같은 건물 위층 이사 비용 정리\n"
                            "장롱이 계단을 못 지날 때 대처법")
        miner = self._miner(ai, [_q("2층에서 3층으로 이사, 장롱 3짝")])
        got = await miner.run(None, ["이사"], row=None, niche="이사 견적",
                              provider="openai")
        assert got.fresh == 1
        assert len(got.titles) == 2
        assert got.admitted == 2
        assert got.fingerprints

    async def test_프롬프트에_상황이_들어간다(self):
        ai = FakeAI(content="어떤 제목입니다 여기에")
        miner = self._miner(ai, [_q("2층에서 3층으로 이사, 장롱 3짝")])
        await miner.run(None, ["이사"], row=None, niche="이사 견적",
                        provider="openai")
        prompt = ai.calls[0]["prompt"]
        assert "이사 견적" in prompt
        assert "상황:" in prompt
        assert "3짝" in prompt

    async def test_AI가_죽어도_회차는_결과를_돌려준다(self):
        miner = self._miner(FakeAI(boom=True),
                            [_q("2층에서 3층으로 이사, 장롱 3짝")])
        got = await miner.run(None, ["이사"], row=None, niche="이사",
                              provider="openai")
        assert got.titles == []
        assert "제목 생성에 실패" in got.error

    async def test_신호_빈도를_보고한다(self):
        ai = FakeAI(content="어떤 제목입니다 여기에")
        miner = self._miner(ai, [_q("2층에서 3층으로 이사, 장롱 3짝"),
                                 _q("2층에서 4층으로 옮기는데 침대 2개")])
        got = await miner.run(None, ["이사"], row=None, niche="이사",
                              provider="openai")
        assert got.signals.get("2층") == 2


class TestTitleSource:
    def test_질문_발굴_출처가_등록됐다(self):
        assert TS.SRC_QUESTION in TS.ALL_SOURCES
        assert TS.is_generated(TS.SRC_QUESTION)
        assert TS.label(TS.SRC_QUESTION) == "발굴 · 질문"

    def test_생성_묶음에_들어간다(self):
        assert TS.SRC_QUESTION in TS.codes_for_group("generated")
