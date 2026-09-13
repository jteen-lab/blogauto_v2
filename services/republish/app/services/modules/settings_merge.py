"""모듈 설정 병합 — 화면이 모르는 키를 지우지 않는다.

**왜 필요한가**: 저장 화면은 `settings` 를 통째로 새로 만들어 보낸다
(`form.js` 의 `data.settings = { keyword: {...} }`, `prompt-form.js` 의
조립부). 그래서 화면에 입력란이 없는 블록은 **저장 한 번에 사라진다.**

기능을 새로 넣을 때마다 화면을 먼저 만들지 않으면 설정이 날아가는 구조라,
서버에서 한 겹 막는다.

    들어온 것에 있는 최상위 키   → 화면이 관리하는 값. 그대로 쓴다
    들어온 것에 없는 최상위 키   → 화면이 모르는 값. 기존 것을 살린다

**최상위만 본다.** 깊게 병합하면 "체크를 껐는데 안 꺼진다" 가 된다.
블록 하나를 화면이 보내면 그 안은 화면 말이 맞다.

**지우려면 빈 값을 보내면 된다.** `{"prompt_rotation": {}}` 처럼 키를
포함해 보내면 덮어쓴다. 키를 아예 빼야 보존된다.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ...core.logger import get_logger

logger = get_logger("settings_merge", "app.log")


def merge(current: Optional[Dict[str, Any]],
          incoming: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """기존 설정 위에 들어온 설정을 얹는다.

    Args:
        current: DB 에 있던 설정
        incoming: 화면이 보낸 설정

    Returns:
        병합 결과. 둘 다 비면 빈 dict.
    """
    if not isinstance(current, dict) or not current:
        return dict(incoming) if isinstance(incoming, dict) else {}
    if not isinstance(incoming, dict):
        return dict(current)

    merged = dict(current)
    merged.update(incoming)

    kept = [k for k in current if k not in incoming]
    if kept:
        logger.info("[SETTINGS_MERGE] 화면이 모르는 키 %d개 보존 | %s",
                    len(kept), kept)
    return merged


def preserved_keys(current: Optional[Dict[str, Any]],
                   incoming: Optional[Dict[str, Any]]) -> list:
    """살아남은 키 목록. 화면·로그가 무엇이 지켜졌는지 말할 때 쓴다."""
    if not isinstance(current, dict) or not isinstance(incoming, dict):
        return []
    return sorted(k for k in current if k not in incoming)
