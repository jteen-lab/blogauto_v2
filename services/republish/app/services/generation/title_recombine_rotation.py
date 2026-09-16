"""제목 재조합 묶음 — 프롬프트 템플릿과 같은 번호를 쓴다.

프롬프트 템플릿은 제목의 키워드로 갈리는데(`prompt_rotation`) 제목
재조합 설정은 하나뿐이었다. 견적 글과 청소 글은 뼈대가 다른데 제목만
같은 틀에서 나왔다.

묶음 하나는 넷이다 — 제목 스타일·제목 길이·스타일별 지시·추가 지시.

    "title_recombine": {
      "enabled": true,
      "styles": ["practical"],          # 묶음 1(기본) = 지금 있던 값 그대로
      "variants": [
        {"label": "청소용", "styles": ["question"], "min_length": 20,
         "max_length": 35, "style_prompts": {...}, "custom_prompt": "..."}
      ]
    }

`variants[0]` 이 템플릿 2 와 짝이다(템플릿 1 은 최상위 값). 템플릿 3 이
걸렸는데 묶음 3 이 없으면 **묶음 1** 로 물러선다 — 제목이 안 만들어지는
것보다 낫다.

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


def pick(settings: Optional[Dict[str, Any]],
         index: int) -> Optional[Dict[str, Any]]:
    """템플릿 번호에 짝지어진 묶음. 0(기본)이거나 없으면 None."""
    if not index or index < 1:
        return None
    rows = bundles(settings)
    if index - 1 >= len(rows):
        return None
    return rows[index - 1]


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
    logger.info("[TITLE_BUNDLE] 묶음 %d 적용 | %s | 바뀐 칸=%s",
                index + 1, bundle.get("label") or "이름 없음", ",".join(used))
    return updated


def describe(settings: Optional[Dict[str, Any]]) -> str:
    """화면에 보여 줄 한 줄."""
    count = len(bundles(settings))
    return f"제목 묶음 {count + 1}개" if count else "제목 묶음 1개(기본)"
