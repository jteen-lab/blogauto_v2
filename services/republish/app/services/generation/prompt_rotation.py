"""프롬프트 로테이션 — 목적 분기 + 변형 선택.

**두 축이다.**

    목적   애드센스용 / CPA용 / 정보성 — 글의 뼈대가 애초에 다르다
    변형   같은 목적 안에서도 글마다 구조를 바꾼다

애드센스 글은 `설명 → 근거 → 정리`, CPA 글은 `쟁점 → 근거 → 판단 기준 →
실행 조언 → CTA` 다. 이걸 프롬프트 하나로 덮으면 둘 다 어중간해진다.

`adsense_prompt_switch` 와 **겹치지 않는다.** 그쪽은 "승인 전에는 승인용
프롬프트를 쓴다"는 상태 전환이고, 여기는 "평소에 무엇을 쓸지"다. 승인 전
상태면 그쪽이 이긴다(승인이 걸린 문제라 우선순위가 높다).

설정 모양:

    "prompt_rotation": {
      "enabled": true,
      "mode": "sequential",
      "variants": [
        {"code": "howto-guide", "purpose": "adsense", "topic_ids": [24]},
        {"template": "직접 쓴 프롬프트 본문", "purpose": "cpa"},
        {"code": "case-study"}
      ]
    }

`code` 는 프롬프트 빌더 프리셋을 가리키고, `template` 은 본문을 직접 적는다.
둘 다 있으면 `template` 이 이긴다.

**커서는 여기서 보관하지 않는다.** 모듈 설정에 두면 동시 실행에서 경합이
난다. 호출부가 실행 상태에서 읽어 넘기고, 돌려받은 `next_cursor` 를 저장한다.

계획서: docs/plans/topic_discovery_and_structure_plan.md §3-2, §3-3
순서도: docs/flowcharts/topic_discovery.md §4
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...core.logger import get_logger
from ..prompt_builder.presets import PRESETS
from . import variant_picker as vp

logger = get_logger("prompt_rotation", "app.log")

ROTATION_KEY = "prompt_rotation"

PURPOSE_ADSENSE = "adsense"
PURPOSE_CPA = "cpa"
PURPOSE_INFO = "info"
ALL_PURPOSES = (PURPOSE_ADSENSE, PURPOSE_CPA, PURPOSE_INFO)

PURPOSE_LABEL = {
    PURPOSE_ADSENSE: "애드센스",
    PURPOSE_CPA: "CPA",
    PURPOSE_INFO: "정보성",
}


def config(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """설정에서 로테이션 블록을 읽는다."""
    return dict(((settings or {}).get(ROTATION_KEY) or {}))


def is_enabled(settings: Optional[Dict[str, Any]]) -> bool:
    """켜져 있고 변형이 둘 이상이어야 의미가 있다."""
    cfg = config(settings)
    if not cfg.get("enabled"):
        return False
    return len(cfg.get("variants") or []) >= 2


def variants(settings: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [v for v in (config(settings).get("variants") or [])
            if isinstance(v, dict)]


def resolve_purpose(blog: Any, settings: Optional[Dict[str, Any]]) -> str:
    """이 글의 목적. 설정이 우선, 없으면 블로그 성격에서 추정한다."""
    fixed = (config(settings).get("purpose") or "").strip().lower()
    if fixed in ALL_PURPOSES:
        return fixed
    if getattr(blog, "cpa_enabled", False):
        return PURPOSE_CPA
    if getattr(blog, "adsense_status", None):
        return PURPOSE_ADSENSE
    return PURPOSE_INFO


def _preset_prompt(code: str) -> str:
    """프리셋 코드 → 완성 프롬프트. 없으면 빈 문자열."""
    if not code:
        return ""
    for preset in PRESETS:
        if preset.get("code") == code:
            return preset.get("full_prompt") or ""
    return ""


def prompt_of(variant: Dict[str, Any]) -> str:
    """변형에서 프롬프트 본문을 꺼낸다. template 이 code 를 이긴다."""
    text = (variant.get("template") or "").strip()
    return text or _preset_prompt((variant.get("code") or "").strip())


def select(settings: Optional[Dict[str, Any]], blog: Any, *,
           topic_id: Optional[int] = None, keyword: str = "",
           cursor: int = 0) -> Optional[Dict[str, Any]]:
    """쓸 프롬프트를 고른다.

    Returns:
        {"template", "index", "mode", "next_cursor", "purpose", "reason"}
        또는 None(로테이션을 쓰지 않을 때 — 호출부는 기존 프롬프트로 간다)
    """
    if not is_enabled(settings):
        return None

    cfg = config(settings)
    purpose = resolve_purpose(blog, settings)
    got = vp.pick(variants(settings), cfg.get("mode"),
                  topic_id=topic_id, purpose=purpose,
                  keyword=keyword, cursor=cursor)
    if got is None:
        logger.info("[PROMPT_ROTATION] 후보 없음 | purpose=%s topic=%s",
                    purpose, topic_id)
        return None

    template = prompt_of(got.item)
    if not template:
        logger.warning("[PROMPT_ROTATION] 변형 %d 의 프롬프트가 비었다 | %s",
                       got.index, got.item.get("code"))
        return None

    logger.info("[PROMPT_ROTATION] %s | %s | %s",
                PURPOSE_LABEL.get(purpose, purpose),
                vp.MODE_LABEL.get(got.mode, got.mode), got.reason)
    return {"template": template, "index": got.index, "mode": got.mode,
            "next_cursor": got.next_cursor, "purpose": purpose,
            "reason": got.reason,
            "label": got.item.get("label") or got.item.get("code") or ""}


def apply(settings: Dict[str, Any], blog: Any, *,
          topic_id: Optional[int] = None, keyword: str = "",
          cursor: int = 0) -> Dict[str, Any]:
    """고른 프롬프트를 적용한 settings 를 만든다(원본 불변).

    `adsense_prompt_switch.resolve()` 와 같은 모양이라 호출부에서 이어
    붙이기 쉽다. 로테이션을 쓰지 않으면 원본을 그대로 돌려준다.
    """
    got = select(settings, blog, topic_id=topic_id, keyword=keyword,
                 cursor=cursor)
    if not got:
        return settings

    updated = dict(settings)
    generation = dict(updated.get("content_generation") or {})
    generation["user_prompt_template"] = got["template"]
    updated["content_generation"] = generation
    updated["_rotation"] = {k: v for k, v in got.items() if k != "template"}
    return updated


def describe(settings: Optional[Dict[str, Any]]) -> str:
    """화면에 보여 줄 한 줄 요약."""
    if not is_enabled(settings):
        return "로테이션 꺼짐"
    cfg = config(settings)
    mode = vp.normalize_mode(cfg.get("mode"))
    return (f"{vp.MODE_LABEL.get(mode, mode)} · "
            f"변형 {len(variants(settings))}개")
