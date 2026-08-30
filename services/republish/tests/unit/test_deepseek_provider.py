"""딥시크 제공자 + 피크 시간대 (2026-08-30).

딥시크는 OpenAI 호환 엔드포인트라 _call_openai 를 base_url 만 바꿔 재사용한다.
그 재사용이 끊기면(base_url 누락) OpenAI 로 요청이 나가 엉뚱한 과금이 되므로
호출 인자까지 확인한다.

피크 시간은 UTC 기준 정의를 KST 로 환산해 쓴다. 화면과 서버가 각자 계산하면
답이 갈리므로, 화면이 서버 값을 받아 쓰는지도 함께 지킨다.
"""
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.ai_api_key import AIProvider
from app.services.ai.ai_service import AIService
from app.services.ai.deepseek_pricing import (
    BASE_URL,
    DEFAULT_MODEL,
    KST_OFFSET,
    PEAK_UTC_RANGES,
    PEAK_WEEKDAYS,
    is_peak,
    peak_hours_kst,
    peak_summary,
)

ROOT = Path(__file__).resolve().parents[2]


def test_provider_enum_has_deepseek():
    assert AIProvider.DEEPSEEK.value == "deepseek"


def test_provider_order_resolves_deepseek():
    """설정에서 고른 deepseek 이 실제 제공자로 이어지는지."""
    svc = AIService(MagicMock(), user_id=1)
    assert svc._get_provider_order("deepseek") == [AIProvider.DEEPSEEK]
    assert svc._get_provider_order("DeepSeek") == [AIProvider.DEEPSEEK]
    assert svc._get_provider_order("unknown") == []


@pytest.mark.asyncio
async def test_deepseek_call_uses_deepseek_base_url():
    """base_url 이 빠지면 OpenAI 로 요청이 나간다 — 반드시 딥시크로 가야 한다."""
    svc = AIService(MagicMock(), user_id=1)
    key = MagicMock(id=1, api_key="sk-test")
    svc.key_manager = MagicMock()
    svc.key_manager.get_available_key = AsyncMock(return_value=key)
    svc.key_manager.mark_key_used = AsyncMock()

    with patch.object(svc, "_call_openai", new=AsyncMock(return_value="본문")) as m:
        out = await svc._try_provider(
            AIProvider.DEEPSEEK, "프롬프트", None, 4096, 0.7,
        )

    assert out["provider"] == "deepseek"
    assert out["model"] == DEFAULT_MODEL
    assert m.call_args.kwargs["base_url"] == BASE_URL


@pytest.mark.asyncio
async def test_openai_call_keeps_default_endpoint():
    """OpenAI 는 base_url 을 받지 않아야 한다(기존 동작 보존)."""
    svc = AIService(MagicMock(), user_id=1)
    key = MagicMock(id=1, api_key="sk-test")
    svc.key_manager = MagicMock()
    svc.key_manager.get_available_key = AsyncMock(return_value=key)
    svc.key_manager.mark_key_used = AsyncMock()

    with patch.object(svc, "_call_openai", new=AsyncMock(return_value="본문")) as m:
        await svc._try_provider(AIProvider.OPENAI, "프롬프트", None, 4096, 0.7)

    assert "base_url" not in m.call_args.kwargs


@pytest.mark.asyncio
async def test_deepseek_model_override_respected():
    """사용자가 pro 를 고르면 그대로 쓴다."""
    svc = AIService(MagicMock(), user_id=1)
    svc.key_manager = MagicMock()
    svc.key_manager.get_available_key = AsyncMock(
        return_value=MagicMock(id=1, api_key="k"))
    svc.key_manager.mark_key_used = AsyncMock()
    with patch.object(svc, "_call_openai", new=AsyncMock(return_value="x")):
        out = await svc._try_provider(
            AIProvider.DEEPSEEK, "p", "deepseek-v4-pro", 100, 0.7)
    assert out["model"] == "deepseek-v4-pro"


def test_peak_hours_match_utc_definition():
    """KST 환산이 UTC 정의와 어긋나지 않는지 직접 계산해 대조한다."""
    expected = sorted(
        (h + KST_OFFSET) % 24
        for start, end in PEAK_UTC_RANGES
        for h in range(start, end)
    )
    assert peak_hours_kst() == expected
    # 문서화된 값과도 일치 (UTC 01~04, 06~10 → KST 10·11·12, 15·16·17·18)
    assert peak_hours_kst() == [10, 11, 12, 15, 16, 17, 18]


def test_peak_only_on_weekdays():
    """주말은 항상 비피크다."""
    for h in peak_hours_kst():
        for d in PEAK_WEEKDAYS:
            assert is_peak(d, h)
        for d in (5, 6):
            assert not is_peak(d, h)


def test_non_peak_hours_are_not_peak():
    for h in range(24):
        if h not in peak_hours_kst():
            assert not is_peak(0, h)


def test_peak_summary_counts_only_active_cells():
    """활성 시간만 세고, 그중 피크를 가린다."""
    matrix = [[h in (10, 14, 20) for h in range(24)] for _ in range(7)]
    out = peak_summary(matrix)
    assert out["active"] == 21          # 3시간 × 7일
    assert out["peak"] == 5             # 10시가 평일 5일만 피크
    assert peak_summary(None) == {"active": 0, "peak": 0}


def test_api_endpoint_returns_server_definition():
    """화면이 받아 쓰는 값이 서버 상수와 같은지."""
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).get("/api/v1/ai-keys/deepseek/peak-hours")
    assert r.status_code == 200
    body = r.json()
    assert body["hours_kst"] == peak_hours_kst()
    assert body["weekdays"] == list(PEAK_WEEKDAYS)


def test_ui_reads_server_values_not_its_own():
    """화면이 피크 시간을 자체 하드코딩하지 않고 API 값을 쓰는지."""
    js = (ROOT / "app/static/js/modules/growth-profile-form.js").read_text(
        encoding="utf-8")
    assert "/api/v1/ai-keys/deepseek/peak-hours" in js
    assert "peakInfo.hours_kst" in js or "peakInfo.weekdays" in js
    # 시간 목록을 JS 안에 다시 적어두면 요금제 변경 시 어긋난다
    assert "[10, 11, 12, 15, 16, 17, 18]" not in js


def test_ui_offers_peak_controls():
    """표시 토글과 피크 해제 버튼이 화면에 있는지."""
    tpl = (ROOT / "app/static/js/modules/growth-profile-form-template.js").read_text(
        encoding="utf-8")
    assert "toggleDeepseekPeak" in tpl
    assert "clearPeakHours" in tpl
    assert "isPeakCell" in tpl


def test_cache_token_bumped():
    html = (ROOT / "app/templates/modules/list.html").read_text(encoding="utf-8")
    for name in ("growth-profile-form.js", "growth-profile-form-template.js"):
        m = re.search(re.escape(name) + r"\?v=(\w+)", html)
        assert m and m.group(1) >= "20260830", name


def test_deepseek_selectable_in_settings_ui():
    """키 등록·모델 선택 화면에 딥시크가 노출되는지."""
    modal = (ROOT / "app/templates/settings/modal.html").read_text(encoding="utf-8")
    assert "openAddKeyModal('deepseek')" in modal
    tab = (ROOT / "app/templates/blogs/settings/_tab_ai.html").read_text(
        encoding="utf-8")
    assert "deepseek-v4-flash" in tab


# ── 사고 모드로 답이 비던 문제 (2026-08-30) ──────────────────────────────
# 딥시크 v4 는 기본으로 사고(reasoning)를 하고 그 토큰이 max_tokens 예산을
# 함께 쓴다. 제목 재조합(max_tokens=200)에서 사고에 484자를 쓰고 본문이 0자로
# 돌아와 생성이 통째로 실패했다. 로그에는 "API 키 상태 확인 필요" 라고만 떠서
# 원인을 가렸다.

def test_reasoning_disabled_for_deepseek():
    """사고 모드를 끄지 않으면 짧은 작업에서 본문이 빈다."""
    from app.services.ai.deepseek_pricing import EXTRA_PARAMS

    assert EXTRA_PARAMS.get("reasoning_effort") == "none"


@pytest.mark.asyncio
async def test_deepseek_call_passes_extra_params():
    """옵션이 실제 호출까지 전달되는지 — 빠지면 사고 모드가 되살아난다."""
    from app.services.ai.deepseek_pricing import EXTRA_PARAMS

    svc = AIService(MagicMock(), user_id=1)
    svc.key_manager = MagicMock()
    svc.key_manager.get_available_key = AsyncMock(
        return_value=MagicMock(id=1, api_key="k"))
    svc.key_manager.mark_key_used = AsyncMock()

    with patch.object(svc, "_call_openai", new=AsyncMock(return_value="본문")) as m:
        await svc._try_provider(AIProvider.DEEPSEEK, "p", None, 200, 0.7)

    assert m.call_args.kwargs["extra_params"] == EXTRA_PARAMS


@pytest.mark.asyncio
async def test_openai_gets_no_extra_params():
    """OpenAI 에는 reasoning_effort 가 다른 의미라 넘기면 안 된다."""
    svc = AIService(MagicMock(), user_id=1)
    svc.key_manager = MagicMock()
    svc.key_manager.get_available_key = AsyncMock(
        return_value=MagicMock(id=1, api_key="k"))
    svc.key_manager.mark_key_used = AsyncMock()

    with patch.object(svc, "_call_openai", new=AsyncMock(return_value="본문")) as m:
        await svc._try_provider(AIProvider.OPENAI, "p", None, 200, 0.7)

    assert not m.call_args.kwargs.get("extra_params")


@pytest.mark.asyncio
async def test_extra_params_reach_the_api_call():
    """SDK 호출 인자에 실제로 실리는지 (중간에서 버려지면 소용없다)."""
    svc = AIService(MagicMock(), user_id=1)
    captured = {}

    class _Resp:
        class _Choice:
            finish_reason = "stop"
            message = MagicMock(content="응답", reasoning_content=None)
        choices = [_Choice()]

    async def _create(**kw):
        captured.update(kw)
        return _Resp()

    client = MagicMock()
    client.chat.completions.create = _create
    with patch("openai.AsyncOpenAI", return_value=client):
        out = await svc._call_openai(
            "k", "프롬프트", "deepseek-v4-flash", 200, 0.7,
            base_url="https://api.deepseek.com",
            extra_params={"reasoning_effort": "none"},
        )

    assert out == "응답"
    assert captured["reasoning_effort"] == "none"


@pytest.mark.asyncio
async def test_empty_response_is_logged_with_cause(caplog):
    """본문이 비면 원인을 남긴다 — 키 문제로 오해하지 않도록."""
    svc = AIService(MagicMock(), user_id=1)

    class _Resp:
        class _Choice:
            finish_reason = "length"
            message = MagicMock(content="", reasoning_content="사" * 484)
        choices = [_Choice()]

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_Resp())
    with patch("openai.AsyncOpenAI", return_value=client):
        with caplog.at_level("WARNING"):
            out = await svc._call_openai("k", "p", "deepseek-v4-flash", 200, 0.7)

    assert out == ""
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "빈 응답" in joined
    assert "length" in joined      # finish_reason
    assert "484" in joined         # 사고에 쓴 분량


def test_reference_summary_also_disables_reasoning():
    """참조자료 요약(max_tokens=800)도 같은 함정에 빠진다."""
    src = (ROOT / "app/services/reference_summary_service.py").read_text(
        encoding="utf-8")
    assert "EXTRA_PARAMS" in src
