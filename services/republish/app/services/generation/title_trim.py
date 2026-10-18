"""재조합 제목에 기계적으로 붙는 접두·꼬리를 지운다.

지시문으로 막아도 AI 가 습관처럼 다시 붙일 때가 있다. 모듈 설정
최상위 `title_strip_patterns`(정규식 목록)에 맞는 부분을 지운다.
설정이 없으면 아무것도 하지 않는다.

최상위에 두는 이유: 모듈 화면은 `title_recombine` 블록을 통째로 다시
보낸다. 그 안에 두면 화면에서 제목 설정을 한 번 저장할 때 사라진다
(최상위의 모르는 키는 settings_merge 가 살린다).

예) 이사노트: '이사 견적 받았다면 …', '… 이대로 괜찮은 걸까요'

순서도: docs/flowcharts/promo_link_autorun.md '제목 틀 정리'
"""
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: 모듈 설정의 자리(최상위)
SETTINGS_KEY = "title_strip_patterns"

#: 지우고 남은 제목이 이보다 짧으면 지우지 않는다
MIN_LEFT = 10


def patterns(settings: Optional[Dict[str, Any]]) -> list:
    """모듈 설정의 지울 틀 목록."""
    raw = (settings or {}).get(SETTINGS_KEY)
    return [str(p) for p in (raw or []) if str(p).strip()]


def trim(title: str, settings: Optional[Dict[str, Any]]) -> str:
    """설정된 틀을 지운 제목. 너무 짧아지거나 틀이 깨져 있으면 원래 제목.

    Args:
        title: 재조합 제목
        settings: 모듈 설정

    Returns:
        정리된 제목
    """
    text = (title or "").strip()
    rules = patterns(settings)
    if not text or not rules:
        return text
    out = text
    for rule in rules:
        try:
            out = re.sub(rule, " ", out)
        except re.error as e:
            logger.warning("[TITLE_TRIM] 틀 오류 무시 | %s | %s", rule, e)
    out = re.sub(r"\s+", " ", out).strip()
    if len(out) < MIN_LEFT:
        return text
    if out != text:
        logger.info("[TITLE_TRIM] '%s' → '%s'", text[:40], out[:40])
    return out
