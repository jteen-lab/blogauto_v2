"""검색 결과에서 같은 글을 한 번만 남긴다.

네이버 검색은 같은 것을 두 가지 모양으로 겹쳐 준다(2026-09-26 실측).

    지식iN '이사 견적'   한 페이지(30건) 안에서 **제목이 같은 것 8건**
                        — 링크는 서로 달라 링크만 보면 못 걸러진다
    카페   start=61     앞 페이지와 **링크까지 같은 것 20건**
    웹     start=31     1건

그래서 링크와 (출처+제목) 두 가지로 본다. 순서는 건드리지 않는다 —
네이버가 준 순서가 곧 화면 순서다.

순서도: docs/flowcharts/workbench_source_modes.md
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from ...core.logger import get_logger

logger = get_logger("workbench_dedup", "app.log")

_SPACE = re.compile(r"\s+")


def link_key(link: str) -> str:
    """링크를 비교용으로 다듬는다. http/https·끝 슬래시·대소문자 차이 무시."""
    text = (link or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^(www|m)\.", "", text)
    return text.rstrip("/")


def title_key(source: str, title: str) -> str:
    """출처 안에서 제목이 같으면 같은 글로 본다.

    출처를 함께 보는 이유: 지식iN 질문과 블로그 글이 제목만 같을 수 있고,
    그 둘은 열어 보면 다른 글이다.
    """
    text = _SPACE.sub(" ", (title or "")).strip().lower()
    return f"{(source or '').strip()}|{text}" if text else ""


def keys_of(item: Dict[str, Any]) -> Tuple[str, str]:
    """이 글감의 링크 열쇠와 제목 열쇠."""
    return (link_key(item.get("link", "")),
            title_key(item.get("source", ""), item.get("title", "")))


def unique(items: Iterable[Dict[str, Any]],
           seen_links: Optional[Set[str]] = None,
           seen_titles: Optional[Set[str]] = None,
           label: str = "") -> List[Dict[str, Any]]:
    """같은 글을 한 번만 남긴다. 받은 순서를 지킨다.

    Args:
        items: 검색 결과
        seen_links / seen_titles: 앞 페이지에서 이미 본 열쇠(넘기면 이어서 본다)
        label: 로그에 남길 이름

    Returns:
        새로 나온 것만
    """
    links = seen_links if seen_links is not None else set()
    titles = seen_titles if seen_titles is not None else set()
    out: List[Dict[str, Any]] = []
    dropped = 0
    for item in items or []:
        lk, tk = keys_of(item)
        if (lk and lk in links) or (tk and tk in titles):
            dropped += 1
            continue
        if lk:
            links.add(lk)
        if tk:
            titles.add(tk)
        out.append(item)
    if dropped:
        logger.info("[WB_DEDUP] %s 겹친 결과 %d건 제외", label or "검색", dropped)
    return out
