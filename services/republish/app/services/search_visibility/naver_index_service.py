"""S6-N — 네이버 색인 여부 점검 (웹문서 검색 API).

구글은 GSC URL Inspection 으로 색인을 직접 물어볼 수 있지만 네이버에는 그런 API 가
없다. 대신 **웹문서 검색에 우리 URL 이 나타나는지** 확인해 대신한다.

한계(중요): 검색 결과에 없다고 미색인이 확정되는 것은 아니다.
    - 제목이 일반적이면 다른 문서에 밀린다
    - 색인은 됐지만 순위가 낮아 상위 N 개 밖일 수 있다
    따라서 상태를 indexed/not_indexed 가 아니라 **found/not_found** 로 부른다.
    "네이버에서 이 제목으로 검색했을 때 우리 글이 잡히는가" 라는 질문의 답이다.

네이버 자동화 수단 정리(2026-08 기준)
    - 사이트 등록·사이트맵 제출: API 없음(수동 1회성)
    - 웹페이지 수집 요청: 수동, 하루 50건
    - IndexNow: 유일한 자동 경로(단 블로거는 키 파일을 못 올려 불가)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from ...core.logger import get_logger

logger = get_logger("naver_index", "app.log")

# 제목으로 검색했을 때 몇 위까지 보고 판정할지
SEARCH_DISPLAY = 30
TAG_RE = re.compile(r"<[^>]+>")


def normalize(url: str) -> str:
    """비교용 URL 정규화 — 스킴·www·끝 슬래시 차이를 없앤다."""
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parsed.path or "").rstrip("/")
    return f"{host}{path}"


def clean_title(title: str) -> str:
    """검색 질의로 쓸 제목을 다듬는다.

    네이버 API 는 따옴표 구문 검색을 지원하지 않으므로 특수문자를 걷어내고
    본문 단어만 남긴다.
    """
    plain = TAG_RE.sub("", title or "")
    plain = re.sub(r"[\[\]{}()<>|\"']", " ", plain)
    return re.sub(r"\s+", " ", plain).strip()


@dataclass
class NaverIndexResult:
    """URL 1건의 네이버 검색 확인 결과."""

    found: bool
    rank: Optional[int] = None
    query: str = ""
    result_count: int = 0
    error: Optional[str] = None

    def to_detail(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "rank": self.rank,
            "result_count": self.result_count,
            "error": self.error,
        }


def find_rank(items: List[Dict[str, Any]], target_url: str) -> Optional[int]:
    """검색 결과에서 대상 URL 의 순위를 찾는다(1부터). 없으면 None."""
    target = normalize(target_url)
    if not target:
        return None
    for index, item in enumerate(items, start=1):
        if normalize(item.get("link") or "") == target:
            return index
    return None


async def check_url(
    service: Any, url: str, title: str,
) -> NaverIndexResult:
    """제목으로 웹문서를 검색해 해당 URL 이 잡히는지 확인한다.

    Args:
        service: NaverWebdocService 인스턴스
        url: 확인할 발행 URL
        title: 그 글의 제목(검색 질의로 쓴다)

    Returns:
        NaverIndexResult
    """
    query = clean_title(title)
    if not query:
        return NaverIndexResult(found=False, error="제목이 비어 검색할 수 없습니다")

    try:
        response = await service.search_webdoc(query, display=SEARCH_DISPLAY)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[NAVER_INDEX] 검색 실패 | %s | %s", query[:20], exc)
        return NaverIndexResult(found=False, query=query, error=f"검색 실패: {exc}")

    if not response.get("success", True) and response.get("error"):
        return NaverIndexResult(
            found=False, query=query, error=str(response["error"]),
        )

    items = response.get("items") or []
    rank = find_rank(items, url)
    return NaverIndexResult(
        found=rank is not None, rank=rank, query=query, result_count=len(items),
    )
