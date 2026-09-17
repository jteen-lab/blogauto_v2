"""제목 재조합 묶음 — 프롬프트 템플릿과 같은 번호를 쓴다.

프롬프트 템플릿은 제목의 키워드로 갈리는데(`prompt_rotation`) 제목
재조합 설정은 하나뿐이었다. 견적 글과 청소 글은 뼈대가 다른데 제목만
같은 틀에서 나왔다.

묶음 하나는 넷이다 — 제목 스타일·제목 길이·스타일별 지시·추가 지시.

    "title_recombine": {
      "enabled": true,
      "styles": ["practical"],          # 묶음 1(기본) = 지금 있던 값 그대로
      "variants": [
        {"label": "청소용", "templates": [2, 4], "styles": ["question"],
         "min_length": 20, "max_length": 35, "style_prompts": {...},
         "custom_prompt": "..."}
      ]
    }

짝은 두 가지로 정해진다.

    templates 를 적으면   그 템플릿에서만 쓰인다(제자리는 포기)
    비워 두면             제자리 — variants[0] 은 템플릿 2 와 짝

템플릿 3 이 걸렸는데 맡은 묶음이 없으면 **묶음 1**(최상위 값)로 물러선다
— 제목이 안 만들어지는 것보다 낫다.

순서도: docs/flowcharts/title_recombine_rotation.md
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...core.logger import get_logger

logger = get_logger("title_recombine_rotation", "app.log")

KEY = "title_recombine"
VARIANTS_KEY = "variants"

#: 묶음이 덮어쓰는 칸. 나머지(enabled 등)는 묶음 1 것을 이어 쓴다
BUNDLE_FIELDS = ("styles", "min_length", "max_length",
                 "style_prompts", "custom_prompt")


def bundles(settings: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """묶음 2.. 목록. 묶음 1 은 최상위 값이라 여기 없다."""
    block = (settings or {}).get(KEY) or {}
    rows = block.get(VARIANTS_KEY)
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def wanted(bundle: Dict[str, Any]) -> List[int]:
    """이 묶음이 집어 든 템플릿 번호들. 안 골랐으면 빈 목록."""
    raw = bundle.get("templates")
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        try:
            num = int(item)
        except (TypeError, ValueError):
            continue
        if num >= 1 and num not in out:
            out.append(num)
    return out


def pick(settings: Optional[Dict[str, Any]],
         index: int) -> Optional[Dict[str, Any]]:
    """이 템플릿이 쓸 묶음. None 이면 묶음 1(최상위 값)을 쓴다.

    Args:
        settings: 모듈 설정
        index: 고른 템플릿의 자리(0 = 템플릿 1)

    고른 템플릿이 있는 묶음이 먼저다. 아무도 안 집었으면 제자리 묶음이
    맡는데, **제 자리라도 다른 템플릿을 골랐으면 비켜 준다** — 두 군데서
    쓰이면 어느 쪽이 맞는지 알 수 없다.
    """
    rows = bundles(settings)
    number = (index or 0) + 1

    # 0) 묶음 1(최상위)이 이 템플릿을 집었으면 묶음 1 이다.
    #    묶음 1 은 원래 아무도 맡지 않은 자리를 맡지만, 집어 두면
    #    다른 묶음이 같은 번호를 집어도 묶음 1 이 이긴다.
    base = (settings or {}).get(KEY) or {}
    if number in wanted(base):
        return None

    if not rows:
        return None

    # 1) 이 템플릿을 집어 든 묶음 — 여럿이면 위에 있는 쪽
    for row in rows:
        if number in wanted(row):
            return row

    # 2) 제자리 묶음. 템플릿 1 의 자리는 최상위 값이라 여기 없다
    if not index or index < 1 or index - 1 >= len(rows):
        return None
    row = rows[index - 1]
    return None if wanted(row) else row


def apply(settings: Dict[str, Any], index: int) -> Dict[str, Any]:
    """고른 묶음을 최상위 `title_recombine` 에 얹은 settings(원본 불변).

    재조합기는 최상위 값만 읽는다. 묶음을 그 자리에 올려 두면 재조합기를
    고치지 않고도 번호대로 갈린다.
    """
    bundle = pick(settings, index)
    if not bundle:
        return settings

    block = dict(settings.get(KEY) or {})
    used = []
    for field in BUNDLE_FIELDS:
        if field in bundle and bundle[field] not in (None, "", [], {}):
            block[field] = bundle[field]
            used.append(field)
    if not used:
        return settings

    updated = dict(settings)
    updated[KEY] = block
    logger.info("[TITLE_BUNDLE] 템플릿 %d → 묶음 '%s' | 고른 템플릿=%s | 바뀐 칸=%s",
                index + 1, bundle.get("label") or "이름 없음",
                wanted(bundle) or "제자리", ",".join(used))
    return updated


def describe(settings: Optional[Dict[str, Any]]) -> str:
    """화면에 보여 줄 한 줄."""
    count = len(bundles(settings))
    return f"제목 묶음 {count + 1}개" if count else "제목 묶음 1개(기본)"
