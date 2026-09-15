"""고른 질문의 본문을 가져온다.

검색 API 는 요약 130자만 준다. 질문자가 쓴 상황(품목·지역·날짜)이
거기서 잘린다. 페이지를 열면 질문과 답변이 따로 뽑힌다.

**고른 것만 가져온다.** 한 페이지가 34만 자라 목록을 통째로 긁으면
화면이 멈추고 차단 위험도 생긴다.

순서도: docs/flowcharts/question_body.md
"""
import asyncio
import logging
import re
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 12
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")

#: 한 번에 받을 수 있는 최대 개수. 더 고르면 앞에서 자른다.
MAX_LINKS = 5

#: 질문 본문 선택자
Q_SELECTORS = (".questionDetail", ".c-heading__content")

#: 답변 본문 선택자
A_SELECTORS = ("#content .se-main-container", ".c-heading-answer__content")

#: 잘라 쓸 길이. 답변이 길어 프롬프트를 잡아먹으면 안 된다.
Q_MAX = 1500
A_MAX = 1200


def _text(node: Any) -> str:
    """태그를 걷어낸 글."""
    return re.sub(r"\s+", " ", node.get_text(" ")).strip()


def _pick(soup: Any, selectors: tuple, limit: int) -> str:
    """선택자를 차례로 시도해 처음 걸리는 것을 쓴다."""
    for sel in selectors:
        found = soup.select(sel)
        if not found:
            continue
        joined = " ".join(_text(n) for n in found if _text(n))
        if joined:
            return joined[:limit]
    return ""


async def _fetch_one(client: httpx.AsyncClient, link: str) -> Dict[str, Any]:
    """한 건. 실패해도 예외를 올리지 않는다 — 제목만으로도 글은 쓴다."""
    out = {"link": link, "question": "", "answer": "", "error": ""}
    try:
        from bs4 import BeautifulSoup

        resp = await client.get(link, headers={"User-Agent": UA})
        if resp.status_code != 200:
            out["error"] = f"HTTP {resp.status_code}"
            return out
        soup = BeautifulSoup(resp.text, "html.parser")
        out["question"] = _pick(soup, Q_SELECTORS, Q_MAX)
        out["answer"] = _pick(soup, A_SELECTORS, A_MAX)
        if not out["question"] and not out["answer"]:
            out["error"] = "본문을 찾지 못했습니다"
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)[:80]
        logger.warning("[QUESTION_BODY] 실패 | %s | %s", link[:60], e)
    return out


async def fetch_bodies(links: List[str]) -> List[Dict[str, Any]]:
    """고른 질문들의 본문. 순서는 준 것과 같다.

    Args:
        links: 질문 페이지 주소 목록

    Returns:
        [{"link", "question", "answer", "error"}, ...]
    """
    picked = [l.strip() for l in (links or []) if (l or "").strip()][:MAX_LINKS]
    if not picked:
        return []
    async with httpx.AsyncClient(timeout=TIMEOUT,
                                 follow_redirects=True) as client:
        got = await asyncio.gather(
            *[_fetch_one(client, l) for l in picked],
            return_exceptions=True)
    out: List[Dict[str, Any]] = []
    for link, item in zip(picked, got):
        if isinstance(item, dict):
            out.append(item)
        else:
            out.append({"link": link, "question": "", "answer": "",
                        "error": "조회 실패"})
    ok = len([o for o in out if o.get("question") or o.get("answer")])
    logger.info("[QUESTION_BODY] %d건 요청 · %d건 성공", len(picked), ok)
    return out
