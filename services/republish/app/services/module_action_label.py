"""모듈이 **실제로 한 일**의 이름.

동작로그에 모듈명을 적으면 무엇이 돌았는지 알 수 없다. 사용자가 모듈을
'제목/도메인 수집'·'URL추출기'·'제목 생성기'로 쪼개 놨어도, 이름은
사람이 붙인 것이라 설정과 어긋날 수 있다. 설정을 읽어 동작명을 만든다.

한 모듈이 여러 일을 하면 ' + ' 로 잇는다.
"""
from __future__ import annotations

from typing import Optional

# 제목 모듈의 섹션 → 동작명
_TITLE_ACTIONS = (
    ("collect", "search_enabled", "제목 수집"),
    ("collect", "extract_enabled", "URL 추출"),
    ("gen", "l1_enabled", "제목 생성"),
    ("gen", "l3_enabled", "뉴스 제목"),
)

# 키워드 모듈의 단계 → 동작명
_KEYWORD_STEPS = {
    "collect": "키워드 수집",
    "measure": "키워드 측정",
    "classify": "키워드 분류",
    "rejudge": "재판정",
}


def title_actions(settings: Optional[dict]) -> list:
    """제목 모듈이 이번에 할 일들."""
    from .title_collect.module_settings import normalize

    payload = normalize(settings)
    out = []
    for section, flag, label in _TITLE_ACTIONS:
        block = payload.get(section) or {}
        if not block.get("enabled"):
            continue
        # 수집은 두 스위치가 각각 켜지고, 생성은 l1/l3 가 각각 켜진다.
        if block.get(flag, flag == "l1_enabled"):
            out.append(label)
    return out


def keyword_actions(settings: Optional[dict]) -> list:
    """키워드 모듈이 이번에 할 단계들."""
    from .keyword_lab.settings import KeywordModuleSettings

    cfg = KeywordModuleSettings.parse(settings)
    return [_KEYWORD_STEPS[s] for s in cfg.steps if s in _KEYWORD_STEPS]


def label_for(action_type: str, settings: Optional[dict],
              fallback: str = "") -> str:
    """동작로그에 적을 이름.

    Args:
        action_type: "title_gen" 또는 "keyword".
        settings: 모듈 settings.
        fallback: 켜진 일이 하나도 없을 때 쓸 이름(보통 모듈명).

    Returns:
        "제목 수집" · "제목 수집 + URL 추출" 같은 문자열.
    """
    if action_type == "title_gen":
        actions = title_actions(settings)
    elif action_type == "keyword":
        actions = keyword_actions(settings)
    else:
        actions = []
    return " + ".join(actions) if actions else fallback
