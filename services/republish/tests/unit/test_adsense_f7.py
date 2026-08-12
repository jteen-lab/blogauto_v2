"""F7 — 정보이득 프롬프트 + 애드센스 승인용 프리셋 테스트."""
import asyncio
from types import SimpleNamespace

from app.services.prompt_builder.blocks import (
    build_prompt,
    adsense_gain_directive,
    ADSENSE_GAIN_CODE,
)
from app.services.generation.growth_profile_defaults import (
    get_default_profile,
    get_available_profiles,
)
from app.services.generation import content_generator_helper as cgh


class TestF7Blocks:
    """정보이득 블록/build_prompt."""

    def test_directive_exists(self):
        d = adsense_gain_directive()
        assert d and "정보이득 지시문" in d

    def test_build_prompt_backward_compat(self):
        # quality 미지정 → 기존과 동일(정보이득 없음)
        assert "정보이득" not in build_prompt("x", "y", "z", "w")

    def test_quality_inserted_before_structure(self):
        p = build_prompt("x", "y", "z", "w", quality_code=ADSENSE_GAIN_CODE)
        assert "정보이득 지시문" in p
        assert p.index("정보이득 지시문") < p.index("STEP 1 ▸")

    def test_qnone_no_insert(self):
        assert "정보이득" not in build_prompt("x", "y", "z", "w", quality_code="Q-None")


class TestF7Preset:
    """애드센스 승인용 성장 프리셋."""

    def test_one_post_per_day(self):
        s = get_default_profile("adsense")["stages"][0]
        assert s["generate"]["daily_count"] == 1
        assert s["publish"]["daily_count"] == 1
        assert s["republish"]["enabled"] is False

    def test_available_includes_adsense(self):
        assert any(x["key"] == "adsense" for x in get_available_profiles())


class _StubAI:
    """generate 호출 시 프롬프트만 캡처하는 스텁."""

    def __init__(self):
        self.captured = None

    async def generate(self, *, prompt, **kw):
        self.captured = prompt
        return {"content": "x", "model": "m", "provider": "p"}


def _blog(status: str):
    return SimpleNamespace(
        adsense_status=status,
        ai_config={"writing_ai": {"provider": "p", "model": "m"}},
        name="테스트블로그",
    )


def _settings():
    return {"content_generation": {"user_prompt_template": "제목: {title}\n본문"}}


class TestF7Injection:
    """adsense_status 옵트인 자동 주입."""

    def _run(self, status: str) -> str:
        ai = _StubAI()
        asyncio.run(cgh.generate_content_with_meta(ai, "제목", "", _settings(), _blog(status)))
        return ai.captured

    def test_inject_when_preparing(self):
        assert "정보이득 지시문" in self._run("preparing")

    def test_inject_when_applied(self):
        assert "정보이득 지시문" in self._run("applied")

    def test_no_inject_when_none(self):
        assert "정보이득 지시문" not in self._run("none")

    def test_no_inject_when_approved(self):
        assert "정보이득 지시문" not in self._run("approved")

    def test_no_double_inject(self):
        ai = _StubAI()
        st = {"content_generation": {
            "user_prompt_template": "제목: {title}\n" + adsense_gain_directive()
        }}
        asyncio.run(cgh.generate_content_with_meta(ai, "제목", "", st, _blog("preparing")))
        assert ai.captured.count("정보이득 지시문") == 1
