"""이어쓰기 — 짧은 초안을 버리지 않고 채운다 (2026-08-31).

고치기 전에는 게이트가 결과를 통째로 버리고 Celery 가 3회 재생성했다.
매번 검색 30회·크롤 10회를 되풀이하면서도 모델에게 "짧았다" 는 사실은
전하지 않았다.

순서도: docs/flowcharts/min_length_generation.md
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.generation.content_generator_helper import (
    extend_content,
    generate_content_with_meta,
)


def _blog(name: str = "수작남") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        ai_config={"writing_ai": {"provider": "openai", "model": "gpt-4o-mini"}},
    )


SETTINGS = {"content_generation": {"max_tokens": 4096, "temperature": 0.7}}


# ── 지시문 주입 ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_length_directive_is_injected_into_the_prompt() -> None:
    """게이트가 보는 숫자와 모델이 듣는 숫자를 한 곳에서 묶는다."""
    ai = SimpleNamespace(generate=AsyncMock(return_value={
        "content": "본문", "model": "gpt-4o-mini", "provider": "openai"}))

    await generate_content_with_meta(
        ai_service=ai, title="제목", reference_injection="",
        settings=SETTINGS, blog=_blog(),
    )

    prompt = ai.generate.await_args.kwargs["prompt"]
    assert "■ 분량 기준" in prompt
    assert "2,500자" in prompt, "기본 임계 1,800 × 1.4 가 들어가야 한다"
    assert "소제목" in prompt


@pytest.mark.asyncio
async def test_directive_follows_module_threshold() -> None:
    ai = SimpleNamespace(generate=AsyncMock(return_value={"content": "본문"}))
    settings = {**SETTINGS, "quality_gate": {"min_chars": 1200}}

    await generate_content_with_meta(
        ai_service=ai, title="제목", reference_injection="",
        settings=settings, blog=_blog(),
    )
    prompt = ai.generate.await_args.kwargs["prompt"]
    assert "1,700자" in prompt and "1,200자" in prompt


@pytest.mark.asyncio
async def test_directive_skipped_when_gate_disabled() -> None:
    """게이트를 끈 모듈에 발행 기준을 말하면 거짓말이 된다."""
    ai = SimpleNamespace(generate=AsyncMock(return_value={"content": "본문"}))
    settings = {**SETTINGS, "quality_gate": {"enabled": False}}

    await generate_content_with_meta(
        ai_service=ai, title="제목", reference_injection="",
        settings=settings, blog=_blog(),
    )
    assert "■ 분량 기준" not in ai.generate.await_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_directive_not_injected_twice() -> None:
    ai = SimpleNamespace(generate=AsyncMock(return_value={"content": "본문"}))
    settings = {**SETTINGS,
                "content_generation": {**SETTINGS["content_generation"],
                                       "user_prompt_template": "■ 분량 기준 이미 있음"}}
    await generate_content_with_meta(
        ai_service=ai, title="제목", reference_injection="",
        settings=settings, blog=_blog(),
    )
    assert ai.generate.await_args.kwargs["prompt"].count("■ 분량 기준") == 1


# ── 이어쓰기 ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_extend_appends_without_discarding_the_draft() -> None:
    ai = SimpleNamespace(generate=AsyncMock(return_value={
        "content": "## 추가 소제목\n더 쓴 내용"}))

    out = await extend_content(
        ai_service=ai, title="제목", draft="## 원래 소제목\n초안 내용",
        current_chars=1400, min_chars=1800, settings=SETTINGS, blog=_blog(),
    )

    assert "초안 내용" in out, "초안을 버리면 안 된다"
    assert "더 쓴 내용" in out
    assert out.index("초안 내용") < out.index("더 쓴 내용")


@pytest.mark.asyncio
async def test_extend_passes_the_draft_and_shortfall() -> None:
    """모델에게 몇 자 모자란지·무엇을 이미 썼는지 줘야 의미가 있다."""
    ai = SimpleNamespace(generate=AsyncMock(return_value={"content": "추가"}))
    await extend_content(
        ai_service=ai, title="순천 메가박스", draft="이미 쓴 본문",
        current_chars=1385, min_chars=1800, settings=SETTINGS, blog=_blog(),
    )
    prompt = ai.generate.await_args.kwargs["prompt"]
    assert "이미 쓴 본문" in prompt
    assert "1,385자" in prompt
    assert "1,115자" in prompt          # 2,500 - 1,385
    assert "순천 메가박스" in prompt


@pytest.mark.asyncio
async def test_extend_strips_leading_filler() -> None:
    """모델이 '이어서 작성하겠습니다' 같은 안내를 붙이는 경우가 있다."""
    ai = SimpleNamespace(generate=AsyncMock(return_value={
        "content": "이어서 작성하겠습니다.\n## 진짜 내용\n본문"}))
    out = await extend_content(
        ai_service=ai, title="제목", draft="초안", current_chars=1400,
        min_chars=1800, settings=SETTINGS, blog=_blog(),
    )
    assert "이어서 작성하겠습니다" not in out
    assert "진짜 내용" in out


@pytest.mark.asyncio
async def test_extend_returns_draft_when_api_fails() -> None:
    """이어쓰기 실패로 생성 전체를 죽이면 안 된다. 게이트가 최종 판단한다."""
    ai = SimpleNamespace(generate=AsyncMock(side_effect=RuntimeError("API 오류")))
    out = await extend_content(
        ai_service=ai, title="제목", draft="초안 그대로", current_chars=1400,
        min_chars=1800, settings=SETTINGS, blog=_blog(),
    )
    assert out == "초안 그대로"


@pytest.mark.asyncio
async def test_extend_returns_draft_when_response_empty() -> None:
    ai = SimpleNamespace(generate=AsyncMock(return_value={"content": "   "}))
    out = await extend_content(
        ai_service=ai, title="제목", draft="초안", current_chars=1400,
        min_chars=1800, settings=SETTINGS, blog=_blog(),
    )
    assert out == "초안"


@pytest.mark.asyncio
async def test_extend_does_not_reinject_length_directive() -> None:
    """이어쓰기는 자체 지시문을 쓴다. 둘이 겹치면 지시가 흐려진다."""
    ai = SimpleNamespace(generate=AsyncMock(return_value={"content": "추가"}))
    await extend_content(
        ai_service=ai, title="제목", draft="초안", current_chars=1400,
        min_chars=1800, settings=SETTINGS, blog=_blog(),
    )
    assert "■ 분량 기준" not in ai.generate.await_args.kwargs["prompt"]


# ── 파이프라인 연결 ──────────────────────────────────────
def test_generator_extends_before_blocking() -> None:
    """게이트가 차단하기 전에 이어쓰기를 한 번 거쳐야 한다.

    바로 차단하면 참조 수집(검색 30·크롤 10)까지 되풀이하는 전체
    재생성이 3회 돈다.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2]
              / "app/services/generation/generator.py").read_text(encoding="utf-8")

    extend_at = source.index("extend_content(")
    block_at = source.index('raise RuntimeError(f"품질 기준 미달')
    assert extend_at < block_at, "차단이 이어쓰기보다 먼저 온다"

    # 이어쓰기 뒤 다시 재어야 한다 — 재측정 없이 통과시키면 게이트가 무의미
    between = source[extend_at:block_at]
    assert "_gate_eval(" in between, "이어쓰기 뒤 재측정이 없다"


def test_generator_logs_length_on_success_too() -> None:
    """실패 때만 남기면 임계값을 데이터가 아니라 짐작으로 조정하게 된다."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2]
              / "app/services/generation/generator.py").read_text(encoding="utf-8")
    assert "본문 분량" in source
    assert "body_chars=body_chars" in source, "결과에 실려야 로그에 남는다"

    executor = (Path(__file__).resolve().parents[2]
                / "app/services/generation/flow_generate_executor.py"
                ).read_text(encoding="utf-8")
    assert "gen_result.body_chars" in executor


def test_extend_runs_only_once() -> None:
    """두 번 세 번 이어 붙이면 글이 늘어지고 비용도 는다."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2]
              / "app/services/generation/generator.py").read_text(encoding="utf-8")
    assert source.count("await extend_content(") == 1
