"""승인 후 프롬프트 자동 전환 테스트 (2026-08-28).

배경: adsense_auto 는 토글(니치 강제·정보이득·AEO)만 바꿨다. 그래서 애드센스
승인용 전용 프롬프트를 걸어두면 **승인된 뒤에도 그 프롬프트가 계속 쓰였다.**
승인용 프롬프트는 심사 통과에 맞춰진 것이라 승인 후에는 니치 프롬프트로
돌아가야 한다.
"""
from types import SimpleNamespace

from app.services.generation import adsense_auto_settings as aas

APPROVAL_PROMPT = "승인용 프롬프트 본문"
NICHE_PROMPT = "승인 후 니치 프롬프트 본문"


def _settings(**kw):
    base = {
        "adsense_auto": True,
        "content_generation": {"user_prompt_template": APPROVAL_PROMPT},
    }
    base.update(kw)
    return base


def _blog(status):
    return SimpleNamespace(name="테스트블로그", adsense_status=status)


def _prompt(resolved):
    return (resolved.get("content_generation") or {}).get("user_prompt_template")


# ---------- 승인 전 ----------

def test_before_approval_keeps_prompt_and_forces_flags():
    resolved = aas.resolve_for_blog(
        _settings(post_approval_prompt=NICHE_PROMPT), _blog("preparing"),
    )
    assert _prompt(resolved) == APPROVAL_PROMPT
    assert resolved["niche_enabled"] is True
    assert resolved["info_gain_enabled"] is True
    assert resolved["aeo_enabled"] is True


# ---------- 승인 후 ----------

def test_after_approval_swaps_prompt():
    resolved = aas.resolve_for_blog(
        _settings(post_approval_prompt=NICHE_PROMPT), _blog("approved"),
    )
    assert _prompt(resolved) == NICHE_PROMPT
    assert resolved["niche_enabled"] is False
    assert resolved["info_gain_enabled"] is False


def test_after_approval_without_replacement_keeps_prompt():
    """비워두면 전환하지 않는다(하위호환)."""
    resolved = aas.resolve_for_blog(_settings(), _blog("approved"))
    assert _prompt(resolved) == APPROVAL_PROMPT


def test_blank_replacement_is_ignored():
    resolved = aas.resolve_for_blog(
        _settings(post_approval_prompt="   "), _blog("approved"),
    )
    assert _prompt(resolved) == APPROVAL_PROMPT


# ---------- 원본 보호 ----------

def test_original_settings_are_not_mutated():
    """모듈 설정은 사용자 것이다. 실행 시점 해석만 바뀌어야 한다."""
    original = _settings(post_approval_prompt=NICHE_PROMPT)
    aas.resolve_for_blog(original, _blog("approved"))
    assert original["content_generation"]["user_prompt_template"] == APPROVAL_PROMPT
    assert "niche_enabled" not in original


def test_auto_off_changes_nothing():
    settings = _settings(adsense_auto=False, post_approval_prompt=NICHE_PROMPT)
    resolved = aas.resolve_for_blog(settings, _blog("approved"))
    assert _prompt(resolved) == APPROVAL_PROMPT
    assert "niche_enabled" not in resolved


def test_swap_works_when_content_generation_missing():
    settings = {
        "adsense_auto": True, "post_approval_prompt": NICHE_PROMPT,
    }
    resolved = aas.resolve_for_blog(settings, _blog("approved"))
    assert _prompt(resolved) == NICHE_PROMPT
