"""애드센스 승인용 프롬프트 선택 (2026-08-30 재설계).

이전 설계는 `user_prompt_template` 에 승인용 프롬프트를 넣고 승인되면 다른
프롬프트로 **교체**하는 방식이었다. 교체 시점·대상·실패 처리가 모두 필요해
복잡했고, 모듈이 여러 블로그를 담당하면 성립하지도 않았다.

재설계(사용자 제안):
    user_prompt_template            = **평소 쓰는 프롬프트**(승인 후 기본값)
    settings.adsense_approval_preset = 승인 전에만 쓸 프리셋 코드

    승인 전 + 프리셋 지정  → 그 프리셋 프롬프트로 생성
    그 외                 → user_prompt_template 그대로

교체가 사라지므로 승인되는 순간 자동으로 평소 프롬프트로 돌아간다.
"돌아갈 프롬프트가 없어 생성을 멈추는" 상황도 생기지 않는다 —
평소 프롬프트는 항상 존재하기 때문이다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...core.logger import get_logger
from ..prompt_builder.presets import PRESETS

logger = get_logger("adsense_prompt_switch", "app.log")

APPROVED_STATUS = "approved"
APPROVAL_PRESET_KEY = "adsense_approval_preset"


def is_approved(blog: Any) -> bool:
    """블로그가 애드센스 승인 상태인지."""
    return getattr(blog, "adsense_status", None) == APPROVED_STATUS


def approval_presets() -> List[Dict[str, Any]]:
    """승인용으로 고를 수 있는 프리셋(완성 프롬프트를 가진 것)."""
    return [p for p in PRESETS if p.get("full_prompt")]


def find_preset(code: str) -> Optional[Dict[str, Any]]:
    """코드로 승인용 프리셋을 찾는다."""
    if not code:
        return None
    for preset in approval_presets():
        if preset.get("code") == code:
            return preset
    return None


def selected_code(settings: Optional[Dict[str, Any]]) -> str:
    """모듈에 지정된 승인용 프리셋 코드. 없으면 빈 문자열."""
    return ((settings or {}).get(APPROVAL_PRESET_KEY) or "").strip()


def approval_prompt(settings: Optional[Dict[str, Any]]) -> str:
    """지정된 승인용 프리셋의 프롬프트 본문. 없거나 코드가 틀리면 빈 문자열."""
    preset = find_preset(selected_code(settings))
    return (preset or {}).get("full_prompt") or ""


def should_use_approval(settings: Optional[Dict[str, Any]], blog: Any) -> bool:
    """지금 승인용 프롬프트를 써야 하는지.

    승인 전이고 프리셋이 지정돼 있을 때만 참이다.
    """
    if is_approved(blog):
        return False
    return bool(approval_prompt(settings))


def resolve(settings: Dict[str, Any], blog: Any) -> Dict[str, Any]:
    """블로그 상태에 맞는 프롬프트를 적용한 settings 를 만든다(원본 불변).

    승인 전 + 프리셋 지정이면 승인용 프롬프트로, 그 외에는 원본 그대로.
    """
    if not should_use_approval(settings, blog):
        return settings

    updated = dict(settings)
    generation = dict(updated.get("content_generation") or {})
    generation["user_prompt_template"] = approval_prompt(settings)
    updated["content_generation"] = generation

    logger.info(
        "[ADSENSE_PROMPT] 승인용 프롬프트 사용 | blog=%s | preset=%s | 상태=%s",
        getattr(blog, "name", "?"), selected_code(settings),
        getattr(blog, "adsense_status", "?"),
    )
    return updated


def invalid_preset_reason(settings: Optional[Dict[str, Any]]) -> Optional[str]:
    """지정된 코드가 실제 프리셋에 없으면 사유를 돌려준다.

    프리셋 카탈로그가 바뀌어 코드가 사라지면 조용히 평소 프롬프트로 생성된다.
    그러면 승인용을 쓰고 있다고 착각하게 되므로 화면·로그로 알린다.
    """
    code = selected_code(settings)
    if not code:
        return None
    if find_preset(code):
        return None
    return (
        f"지정된 애드센스 승인용 프리셋('{code}')을 찾을 수 없습니다. "
        f"프롬프트/생성 모듈에서 다시 선택하세요"
    )
