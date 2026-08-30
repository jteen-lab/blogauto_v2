"""AI 제공자 목록이 한 곳에서만 관리되는지 (2026-08-30).

딥시크를 추가했을 때 AIProvider 에는 넣었는데 blog_settings 의 provider
정규식 패턴을 못 고쳐서, 블로그 설정 저장이 422 로 막혔다. 목록을 두 곳에
적으면 한쪽이 늦게 따라온다.

패턴을 enum 에서 만들도록 바꿨고, 이 테스트가 그 규칙을 지킨다.
"""
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.ai_api_key import AIProvider
from app.schemas.blog_settings import AIConfig, AIServiceConfig

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("provider", [p.value for p in AIProvider])
def test_every_registered_provider_is_accepted(provider):
    """enum 에 있는 제공자는 전부 저장 가능해야 한다."""
    cfg = AIServiceConfig(provider=provider, model="아무거나")
    assert cfg.provider == provider


def test_unknown_provider_still_rejected():
    """아무 값이나 통과시키면 오타가 조용히 저장된다."""
    with pytest.raises(ValidationError):
        AIServiceConfig(provider="bogus-provider")


def test_empty_provider_allowed():
    """미선택(None/빈 문자열)은 허용 — 기존 블로그가 그대로 열려야 한다."""
    assert AIServiceConfig(provider=None).provider is None
    assert AIServiceConfig(provider="").provider == ""


def test_full_ai_config_saves_with_deepseek():
    """422 가 났던 실제 형태 — 네 칸 모두 채운 저장 요청."""
    cfg = AIConfig(
        writing_ai={"provider": "deepseek", "model": "deepseek-v4-flash"},
        title_ai={"provider": "deepseek", "model": "deepseek-v4-flash"},
        reference_ai={"provider": "deepseek", "model": "deepseek-v4-flash"},
        image_ai={"provider": None, "model": None},
    )
    assert cfg.writing_ai.provider == "deepseek"
    assert cfg.reference_ai.model == "deepseek-v4-flash"


def test_pattern_is_derived_not_hardcoded():
    """패턴을 손으로 적어두면 다음 제공자 추가 때 또 막힌다."""
    src = (ROOT / "app/schemas/blog_settings.py").read_text(encoding="utf-8")
    assert 'pattern="^(openai|anthropic|google' not in src, (
        "provider 목록을 하드코딩하지 말고 AIProvider 에서 만들 것"
    )
    assert "for p in AIProvider" in src


def test_reference_summary_supports_every_provider():
    """참조자료 요약도 제공자를 고를 수 있어야 한다(폴백 포함)."""
    from app.services.reference_summary_service import ReferenceSummaryService

    src = (ROOT / "app/services/reference_summary_service.py").read_text(
        encoding="utf-8")
    assert '"deepseek"' in src
    assert hasattr(ReferenceSummaryService, "_call_deepseek")
