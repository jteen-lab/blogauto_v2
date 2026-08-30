"""애드센스 승인 시 프롬프트 전환 판정 (2026-08-30).

배경: 생성에 쓰이는 프롬프트는 `content_generation.user_prompt_template` 한 칸뿐이다.
애드센스 승인용 전용 프롬프트를 걸어두면 승인된 뒤에도 그대로 쓰인다.
승인용은 심사 통과에 맞춰진 것이라 승인 후 니치 운영에는 맞지 않는다.

규칙
    승인 전            → 아무것도 하지 않는다(승인용 프롬프트 유지)
    승인 + 승인후 지정  → 프롬프트를 교체한다
    승인 + 미지정      → **생성을 정지**하고 사유를 남긴다
                         (조용히 부적절한 글을 계속 쌓는 것보다 멈추는 편이 낫다)

승인 방향만 전환한다. `approved` 에서 내려가도 되돌리지 않는다 — 자동 복귀하면
글 성격이 왜 바뀌었는지 사용자가 알 수 없다.

설계: docs/plans/prompt_switch_on_approval_plan.md §7
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ...core.logger import get_logger

logger = get_logger("adsense_prompt_switch", "app.log")

APPROVED_STATUS = "approved"
POST_APPROVAL_KEY = "post_approval_prompt"

# 승인용 전용 프롬프트의 고유 문구. 프리셋 코드가 저장되지 않아 본문으로 판정한다.
# 사용자가 일부 손봐도 견디도록 두 문구를 모두 확인한다.
APPROVAL_SIGNATURE: Tuple[str, ...] = (
    "정보이득(Information Gain)",
    "people-first",
)

BLOCK_REASON = (
    "애드센스 승인됨 — 승인 후 사용할 프롬프트가 지정되지 않았습니다. "
    "프롬프트/생성 모듈에서 지정하세요"
)


def _template(settings: Optional[Dict[str, Any]]) -> str:
    generation = (settings or {}).get("content_generation") or {}
    return generation.get("user_prompt_template") or ""


def is_approved(blog: Any) -> bool:
    """블로그가 애드센스 승인 상태인지."""
    return getattr(blog, "adsense_status", None) == APPROVED_STATUS


def uses_approval_prompt(settings: Optional[Dict[str, Any]]) -> bool:
    """지금 애드센스 승인용 전용 프롬프트를 쓰고 있는지."""
    template = _template(settings)
    if not template:
        return False
    return all(mark in template for mark in APPROVAL_SIGNATURE)


def replacement_prompt(settings: Optional[Dict[str, Any]]) -> str:
    """승인 후 사용할 프롬프트. 없으면 빈 문자열."""
    return ((settings or {}).get(POST_APPROVAL_KEY) or "").strip()


def block_reason(settings: Optional[Dict[str, Any]], blog: Any) -> Optional[str]:
    """생성을 멈춰야 하는 사유. 계속해도 되면 None.

    승인됐는데 승인용 프롬프트를 계속 쓰고, 돌아갈 프롬프트도 없는 경우만 멈춘다.
    """
    if not is_approved(blog):
        return None
    if not uses_approval_prompt(settings):
        return None
    if replacement_prompt(settings):
        return None
    return BLOCK_REASON


def needs_switch(settings: Optional[Dict[str, Any]], blog: Any) -> bool:
    """지금 프롬프트를 교체해야 하는 상태인지."""
    return (
        is_approved(blog)
        and uses_approval_prompt(settings)
        and bool(replacement_prompt(settings))
    )


def switched_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """승인 후 프롬프트로 교체한 새 settings 를 만든다(원본 불변)."""
    updated = dict(settings)
    generation = dict(updated.get("content_generation") or {})
    generation["user_prompt_template"] = replacement_prompt(settings)
    updated["content_generation"] = generation
    return updated


def module_blog_ids(settings: Optional[Dict[str, Any]]) -> list:
    """모듈이 담당하는 블로그 id 목록."""
    raw = (settings or {}).get("blogs") or []
    out = []
    for item in raw:
        value = item.get("id") if isinstance(item, dict) else item
        if value is not None:
            out.append(int(value))
    return out


def can_persist_switch(settings: Optional[Dict[str, Any]], blog: Any) -> bool:
    """DB에 실제로 교체해도 되는지.

    한 모듈이 여러 블로그를 담당하면 블로그마다 승인 상태가 다를 수 있어
    모듈 값을 통째로 바꾸는 것은 성립하지 않는다. 그때는 교체하지 않고
    실행 시점 해석에 맡긴다.
    """
    ids = module_blog_ids(settings)
    blog_id = getattr(blog, "id", None)
    return len(ids) == 1 and ids[0] == blog_id
