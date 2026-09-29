"""근거 기반 경험담 규칙 — 위험도 판정·블록 문구·프롬프트 맨 끝 주입."""
import asyncio
from types import SimpleNamespace

from app.services.generation import content_generator_helper as cgh
from app.services.generation import pipeline_tester_helpers as pth
from app.services.prompt_builder import blocks, blocks_voice
from app.services.prompt_builder import experience_rules as er


class TestClassify:
    def test_health(self):
        assert er.classify_risk("위고비 부작용 총정리") == er.RISK_HEALTH
        assert er.classify_risk("다이어트 식단", ["비만/다이어트"]) == er.RISK_HEALTH
        assert er.classify_risk("아기 해열제 복용", ["육아팁"]) == er.RISK_HEALTH

    def test_ymyl(self):
        assert er.classify_risk("전세 대출 한도 계산") == er.RISK_YMYL
        assert er.classify_risk("부가세 신고 기간") == er.RISK_YMYL
        assert er.classify_risk("층간소음 소송 배상") == er.RISK_YMYL

    def test_low(self):
        assert er.classify_risk("욕실 곰팡이 청소 방법") == er.RISK_LOW
        assert er.classify_risk("전기요금 절약 꿀팁") == er.RISK_LOW
        assert er.classify_risk("아기 낮잠 재우기", ["육아팁/육아노하우"]) == er.RISK_LOW


class TestBlock:
    def test_override_and_forbidden(self):
        b = er.build_block(er.RISK_LOW)
        assert "이 규칙은 위의 경험·페르소나 지시보다 우선한다." in b
        assert "(A) 후기 요약형" in b and "(B) 절차 체험형" in b
        assert "금지:" in b and "저도 먹어 봤는데 효과가 있었다" in b
        assert "건너뛴다" in b

    def test_ymyl_forbids_first_person(self):
        for risk in (er.RISK_YMYL, er.RISK_HEALTH):
            b = er.build_block(risk)
            assert "1인칭 경험 금지" in b
            assert "(C) 1인칭 생활 경험" not in b

    def test_low_allows_limited_first_person(self):
        b = er.build_block(er.RISK_LOW)
        assert "(C) 1인칭 생활 경험" in b and "1~2문장" in b

    def test_review_snippets_max3(self):
        b = er.build_block(er.RISK_LOW, ["가", "나", "", "다", "라"])
        assert "후기 재료" in b
        assert "- 다" in b and "- 라" not in b

    def test_append_idempotent(self):
        once = er.append_block("본문", "청소")
        assert er.append_block(once, "청소") == once


class _StubAI:
    captured = ""

    async def generate(self, *, prompt, **kw):
        self.captured = prompt
        return {"content": "x", "model": "m", "provider": "p"}


def _blog():
    return SimpleNamespace(ai_config={"writing_ai": {"provider": "p", "model": "m"}},
                           name="b")


def _settings():
    return {"info_gain_enabled": True, "aeo_enabled": True,
            "content_generation": {
                "user_prompt_template": "제목: {title}\n본인 경험을 녹여 쓰세요"}}


class TestAppendedLast:
    def test_generator_path(self):
        ai = _StubAI()
        asyncio.run(cgh.generate_content_with_meta(
            ai, "대출 금리 비교", "[참고 자료]\n후기", _settings(), _blog()))
        tail = ai.captured[ai.captured.index(er.BLOCK_HEADER):]
        assert tail.startswith(er.BLOCK_HEADER)
        assert "■ 분량 기준" not in tail and "1인칭 경험 금지" in tail

    def test_tester_path(self):
        ai = _StubAI()
        asyncio.run(pth.call_ai_generate(
            ai, "욕실 청소", "자료", _settings(), _blog()))
        assert er.BLOCK_HEADER in ai.captured
        assert ai.captured.rstrip().endswith(
            er.build_block(er.RISK_LOW).splitlines()[-1])


class TestBlocksNoFakeExperience:
    def _all(self):
        text = ""
        for mod in (blocks, blocks_voice):
            for name in dir(mod):
                v = getattr(mod, name)
                if isinstance(v, list):
                    text += "".join(str(x.get("body", "")) for x in v
                                    if isinstance(x, dict))
        return text

    def test_no_fabricated_experience_phrases(self):
        t = self._all()
        assert "저도 같은 경험이 있어서" not in t
        assert "본인 1인칭 시점" not in t
        assert "본인 경험·실패담" not in t
        assert "본인도 헷갈렸던" not in t
