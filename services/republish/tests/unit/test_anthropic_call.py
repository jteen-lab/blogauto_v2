"""클로드 호출부 최신화 (2026-10-20, 슈마즈 0단계).

새 클로드 모델은 샘플링 값을 보내면 400 을 낸다. 모델 이름별로
보낼 값을 고르는 규칙과, gpt·gemini 경로가 그대로인지 지킨다.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.ai_api_key import AIProvider
from app.services.ai.ai_service import AIService
from app.services.ai.anthropic_call import (
    DEFAULT_MODEL,
    response_text,
    sampling_kwargs,
)


def test_haiku_45_sends_temperature_only():
    out = sampling_kwargs("claude-haiku-4-5", 0.7, 0.9, 40)
    assert out == {"temperature": 0.7}


def test_sonnet_45_dated_sends_temperature_only():
    out = sampling_kwargs("claude-sonnet-4-5-20250929", 0.7, 0.9, 40)
    assert out == {"temperature": 0.7}


@pytest.mark.parametrize("model", [
    "claude-sonnet-5", "claude-opus-5", "claude-opus-5-5",
    "claude-opus-4-7", "claude-opus-4-8", "claude-fable-5-1",
])
def test_new_models_send_no_sampling(model):
    assert sampling_kwargs(model, 0.7, 0.9, 40) == {}


def test_old_models_keep_all_values():
    out = sampling_kwargs("claude-sonnet-4-20250514", 0.7, 0.9, 40)
    assert out == {"temperature": 0.7, "top_p": 0.9, "top_k": 40}


def test_response_text_joins_text_blocks_only():
    resp = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text="<p>앞</p>"),
            SimpleNamespace(type="text", text="<p>뒤</p> "),
        ],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
    )
    assert response_text(resp, "claude-sonnet-5") == "<p>앞</p><p>뒤</p>"


def test_response_text_logs_truncation(caplog):
    resp = SimpleNamespace(content=[SimpleNamespace(type="text", text="a")],
                           stop_reason="max_tokens", usage=None)
    with caplog.at_level("WARNING"):
        response_text(resp, "claude-haiku-4-5")
    assert "anthropic 잘림" in caplog.text


def _svc():
    svc = AIService(MagicMock(), user_id=1)
    svc.key_manager = MagicMock()
    svc.key_manager.get_available_key = AsyncMock(
        return_value=MagicMock(id=1, api_key="k"))
    svc.key_manager.mark_key_used = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_anthropic_default_model_is_haiku_45():
    svc = _svc()
    with patch.object(svc, "_call_anthropic", new=AsyncMock(return_value="본문")) as m:
        out = await svc._try_provider(AIProvider.ANTHROPIC, "p", None, 4096, 0.7)
    assert DEFAULT_MODEL == "claude-haiku-4-5"
    assert out["model"] == "claude-haiku-4-5"
    assert m.call_args.args[2] == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_call_anthropic_kwargs_for_haiku_and_article_tokens():
    svc = AIService(MagicMock(), user_id=1)
    fake = MagicMock()
    fake.messages.create = AsyncMock(return_value=SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        stop_reason="end_turn", usage=None))
    with patch("anthropic.AsyncAnthropic", return_value=fake):
        await svc._call_anthropic("k", "p", "claude-haiku-4-5", 4096, 0.7,
                                  "sys", top_p=0.9, top_k=40)
    kw = fake.messages.create.call_args.kwargs
    assert kw["temperature"] == 0.7
    assert "top_p" not in kw and "top_k" not in kw
    assert kw["max_tokens"] == 8000
    assert kw["system"] == "sys"


@pytest.mark.asyncio
async def test_call_anthropic_sonnet5_no_sampling_small_tokens_kept():
    svc = AIService(MagicMock(), user_id=1)
    fake = MagicMock()
    fake.messages.create = AsyncMock(return_value=SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        stop_reason="end_turn", usage=None))
    with patch("anthropic.AsyncAnthropic", return_value=fake):
        await svc._call_anthropic("k", "p", "claude-sonnet-5", 300, 0.7,
                                  top_p=0.9, top_k=40)
    kw = fake.messages.create.call_args.kwargs
    assert not {"temperature", "top_p", "top_k"} & set(kw)
    assert kw["max_tokens"] == 300


@pytest.mark.asyncio
async def test_openai_and_google_paths_unchanged():
    svc = _svc()
    with patch.object(svc, "_call_openai", new=AsyncMock(return_value="x")) as mo:
        out = await svc._try_provider(AIProvider.OPENAI, "p", None, 4096, 0.7,
                                      top_p=0.9)
    assert out["model"] == "gpt-4o-mini"
    assert mo.call_args.kwargs["top_p"] == 0.9
    with patch.object(svc, "_call_google", new=AsyncMock(return_value="x")) as mg:
        await svc._try_provider(AIProvider.GOOGLE, "p", None, 4096, 0.7,
                                top_p=0.9, top_k=40)
    assert mg.call_args.kwargs["top_k"] == 40
