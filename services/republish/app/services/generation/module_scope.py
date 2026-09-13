"""모듈 담당 범위 — 한 블로그에 프롬프트 모듈을 여럿 매단다.

**왜 필요한가**: 지금은 블로그를 고르면 그 블로그의 니치가 전부 한 모듈에
딸려 온다. 그래서 이사 글과 청소 글이 같은 프롬프트로 나간다. 니치가
다르면 글의 뼈대도 달라야 한다.

데이터 구조는 이미 준비돼 있다 — `resolve_module_niche()` 가 `topic_id`
**목록**을 돌려준다. 모자란 건 "그럼 이 제목은 어느 모듈이 맡나"를 정하는
규칙이다. 그게 이 파일이다.

    니치 강제 꺼짐  → 공용 모듈. 아무도 안 맡는 주제를 받는다
    니치 강제 켜짐  → 지정한 주제만 맡는다

**구체적인 쪽이 이긴다.** 이사 전담 모듈과 공용 모듈이 같이 있으면 이사
제목은 전담이 가져간다. 공용은 남는 것을 받는다.

계획서: docs/plans/topic_discovery_and_structure_plan.md §3-1
순서도: docs/flowcharts/topic_discovery.md §4
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ...core.logger import get_logger
from .adsense_niche import resolve_module_niche

logger = get_logger("module_scope", "app.log")


def scope_of(module_settings: Optional[Dict[str, Any]]) -> Optional[List[int]]:
    """이 모듈이 맡는 주제 목록. None 이면 공용이다."""
    return resolve_module_niche(module_settings)


def is_shared(module_settings: Optional[Dict[str, Any]]) -> bool:
    """공용 모듈인가(니치 강제가 꺼진 모듈)."""
    return scope_of(module_settings) is None


def handles(module_settings: Optional[Dict[str, Any]],
            topic_id: Optional[int]) -> bool:
    """이 모듈이 이 주제를 맡는가.

    공용 모듈은 전부 맡는다고 답한다. 실제로 누가 가져갈지는 `pick()` 이
    정한다 — 전담이 있으면 전담이 이긴다.
    """
    ids = scope_of(module_settings)
    if ids is None:
        return True
    if topic_id is None:
        return False
    return int(topic_id) in ids


def _settings_of(module: Any) -> Dict[str, Any]:
    return getattr(module, "settings", None) or {}


def pick(modules: Sequence[Any],
         topic_id: Optional[int]) -> Tuple[Optional[Any], str]:
    """이 주제를 맡을 모듈을 고른다.

    Args:
        modules: 플로우에 연결된 생성 모듈들
        topic_id: 제목의 하위 주제

    Returns:
        (모듈, 사유). 맡을 모듈이 없으면 (None, 사유)
    """
    rows = [m for m in (modules or []) if m is not None]
    if not rows:
        return None, "연결된 생성 모듈이 없습니다"
    if len(rows) == 1:
        return rows[0], "모듈이 하나뿐"

    dedicated = [m for m in rows
                 if not is_shared(_settings_of(m))
                 and handles(_settings_of(m), topic_id)]
    if dedicated:
        picked = dedicated[0]
        logger.info("[MODULE_SCOPE] 전담 모듈 | topic=%s | module=%s",
                    topic_id, getattr(picked, "id", "?"))
        return picked, f"주제 {topic_id} 전담"

    shared = [m for m in rows if is_shared(_settings_of(m))]
    if shared:
        return shared[0], "공용 모듈"

    return None, f"주제 {topic_id} 를 맡는 모듈이 없습니다"


def coverage(modules: Sequence[Any]) -> Dict[str, Any]:
    """어느 주제가 비어 있는지. 설정 화면이 이 값으로 경고한다.

    전담만 있고 공용이 없으면 지정하지 않은 주제의 글이 생성되지 않는다.
    조용히 멈추는 자리라 화면이 먼저 말해야 한다.
    """
    rows = [m for m in (modules or []) if m is not None]
    covered: List[int] = []
    has_shared = False
    for module in rows:
        ids = scope_of(_settings_of(module))
        if ids is None:
            has_shared = True
        else:
            covered.extend(ids)
    return {"modules": len(rows), "has_shared": has_shared,
            "covered_topic_ids": sorted(set(covered)),
            "warning": (None if has_shared or not covered else
                        "공용 모듈이 없습니다 — 지정하지 않은 주제는 "
                        "글이 생성되지 않습니다")}
