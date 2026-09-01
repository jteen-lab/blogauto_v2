"""네이버 노출 준비 상태 점검표.

네이버는 사이트 등록·사이트맵 제출에 **API 가 없다.** 수동 1회 작업이고,
웹페이지 수집 요청도 수동(하루 50건)이다. 자동으로 알릴 수 있는 유일한 길은
IndexNow 다.

그래서 "자동으로 다 해 준다" 가 불가능하다. 대신 **무엇이 되어 있고 무엇이
안 되어 있는지**를 한 화면에 모아 준다. 자동으로 확인할 수 있는 것은 확인하고
(로봇 차단·소유확인 메타·사이트맵·RSS·IndexNow 키), 확인이 불가능한 것은
사람이 체크하도록 남긴다.

주의: 소유 확인은 HTML 파일·DNS 로도 가능하다. **메타 태그가 없다고 미등록인
것은 아니다.** 화면에도 그렇게 적는다.

계획서: docs/plans/keyword_module_redesign_plan.md §5-3
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from ...core.logger import get_logger
from . import config as sv_config
from . import naver_check, sitemap_service

logger = get_logger("naver_readiness", "app.log")

TIMEOUT = 10.0

# 워드프레스 기본 RSS 경로. 네이버는 RSS 로 더 빨리 수집한다.
RSS_PATHS = ("/feed", "/rss", "/feed/")

# 점검 항목 코드
CHECK_ROBOTS = "robots_yeti"
CHECK_OWNER = "owner_meta"
CHECK_SITEMAP = "sitemap"
CHECK_RSS = "rss"
CHECK_INDEXNOW = "indexnow"


async def find_rss(blog: Any) -> Optional[str]:
    """RSS 주소를 찾는다. 없으면 None.

    사이트맵과 별개로 제출해야 한다 — 네이버는 RSS 쪽을 더 빨리 본다.
    """
    base = getattr(blog, "url", None)
    if not base:
        return None
    async with httpx.AsyncClient(timeout=TIMEOUT,
                                 follow_redirects=True) as client:
        for path in RSS_PATHS:
            url = urljoin(base if base.endswith("/") else base + "/",
                          path.lstrip("/"))
            try:
                response = await client.get(url)
            except Exception:  # noqa: BLE001
                continue
            body = (response.text or "")[:600].lower()
            if response.status_code == 200 and ("<rss" in body
                                                or "<feed" in body):
                return url
    return None


def _item(code: str, label: str, state: str, detail: str,
          manual: bool = False) -> Dict[str, Any]:
    """점검 항목 하나. state 는 ok | warn | fail | unknown."""
    return {"code": code, "label": label, "state": state,
            "detail": detail, "manual": manual}


def _robots_item(result: naver_check.NaverCheckResult) -> Dict[str, Any]:
    if not result.ok:
        return _item(CHECK_ROBOTS, "네이버 크롤러(Yeti) 허용", "unknown",
                     result.error or "robots.txt 를 읽지 못했습니다")
    if result.yeti_blocked:
        return _item(CHECK_ROBOTS, "네이버 크롤러(Yeti) 허용", "fail",
                     f"robots.txt 가 Yeti 를 막고 있습니다"
                     f"({result.yeti_rule_source or '규칙 확인 필요'})")
    return _item(CHECK_ROBOTS, "네이버 크롤러(Yeti) 허용", "ok",
                 "robots.txt 가 막고 있지 않습니다")


def _owner_item(result: naver_check.NaverCheckResult) -> Dict[str, Any]:
    if result.verification_meta:
        return _item(CHECK_OWNER, "서치어드바이저 소유 확인", "ok",
                     "소유 확인 메타 태그가 있습니다")
    # 메타가 없다고 미등록은 아니다. HTML 파일·DNS 로도 확인할 수 있다.
    return _item(CHECK_OWNER, "서치어드바이저 소유 확인", "unknown",
                 "메타 태그가 없습니다. 파일·DNS 방식일 수 있으니 "
                 "서치어드바이저에서 직접 확인하세요", manual=True)


async def check(blog: Any) -> Dict[str, Any]:
    """블로그 하나의 네이버 준비 상태.

    Args:
        blog: 대상 블로그

    Returns:
        {"ready": bool, "items": [...], "notes": [...]}
    """
    result = await naver_check.check_blog(blog)
    items: List[Dict[str, Any]] = [_robots_item(result), _owner_item(result)]

    snapshot = await sitemap_service.fetch_sitemap_urls(blog)
    if snapshot.ok and snapshot.urls:
        items.append(_item(CHECK_SITEMAP, "사이트맵", "ok",
                           f"{snapshot.source_url} · URL {len(snapshot.urls)}개"))
    else:
        items.append(_item(CHECK_SITEMAP, "사이트맵", "fail",
                           snapshot.error or "사이트맵을 찾지 못했습니다"))

    rss = await find_rss(blog)
    items.append(
        _item(CHECK_RSS, "RSS 제출용 주소", "ok", rss) if rss
        else _item(CHECK_RSS, "RSS 제출용 주소", "warn",
                   "RSS 를 찾지 못했습니다. 네이버는 RSS 쪽을 더 빨리 봅니다")
    )

    if sv_config.indexnow_supported(blog):
        items.append(_item(CHECK_INDEXNOW, "IndexNow 자동 통보", "ok",
                           "이 플랫폼은 키 파일을 올릴 수 있습니다"))
    else:
        items.append(_item(CHECK_INDEXNOW, "IndexNow 자동 통보", "fail",
                           "블로거는 키 파일을 호스트 루트에 올릴 수 없어 "
                           "네이버 자동 통보가 불가능합니다"))

    notes = [
        "사이트 등록·사이트맵/RSS 제출은 네이버에 API 가 없어 수동 1회 작업입니다.",
        "등록 후 노출까지 통상 2주가 걸립니다.",
        "외부 사이트는 '블로그 탭'이 아니라 '웹사이트 탭'에 노출됩니다.",
    ]
    ready = not any(i["state"] == "fail" for i in items)
    logger.info("[NAVER_READINESS] blog=%s | ready=%s | 항목 %d",
                getattr(blog, "id", None), ready, len(items))
    return {"ready": ready, "items": items, "notes": notes}
