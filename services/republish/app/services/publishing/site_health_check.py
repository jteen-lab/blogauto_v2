"""블로그 등록·연결 테스트 시 검색 노출 기본 조건을 점검한다.

레시피노트의 robots.txt 가 수작남 사이트맵을 가리키고 있었는데 몇 주 뒤에야
발견했다. 등록 시점에 드러났으면 허비하지 않았다.

막지 않고 **알리기만** 한다. 이 조건들은 발행 자체를 못 하게 할 사유가 아니다.

진단: docs/plans/search_visibility_all_blogs.md
순서도: docs/flowcharts/index_feedback_and_quality_gate.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from ...core.logger import get_logger

logger = get_logger("site_health_check", "app.log")

TIMEOUT = 15.0


@dataclass
class SiteHealth:
    """검색 노출 기본 조건 점검 결과."""

    checked: bool = False
    issues: List[Dict[str, str]] = field(default_factory=list)

    def add(self, code: str, message: str) -> None:
        self.issues.append({"code": code, "message": message})

    def to_dict(self) -> Dict[str, Any]:
        return {"checked": self.checked, "issues": self.issues}


def _host(url: Optional[str]) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def check_sitemap_host(robots_txt: str, blog_host: str) -> Optional[str]:
    """robots.txt 의 Sitemap 이 자기 도메인을 가리키는지.

    남의 사이트맵을 가리키면 구글이 이 사이트의 목록을 찾지 못한다.
    """
    if not blog_host:
        return None
    lines = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots_txt or "")
    if not lines:
        return "robots.txt 에 사이트맵 선언이 없습니다"
    for sm in lines:
        if _host(sm) == blog_host:
            return None
    return (
        f"robots.txt 의 사이트맵이 다른 도메인을 가리킵니다 "
        f"({_host(lines[0]) or lines[0]}). 자기 사이트맵으로 고쳐야 "
        f"검색엔진이 글 목록을 찾습니다"
    )


def check_noindex(html: str) -> Optional[str]:
    """meta robots 에 noindex 가 걸려 있는지."""
    for tag in re.findall(r"(?is)<meta[^>]+name=['\"]robots['\"][^>]*>", html or ""):
        if re.search(r"(?i)noindex", tag):
            return "meta robots 에 noindex 가 있어 검색에 노출되지 않습니다"
    return None


def check_naver_verification(html: str) -> Optional[str]:
    """네이버 소유확인 태그가 있는지(없으면 네이버 수집 요청 자체가 안 된다)."""
    if re.search(r"(?i)naver-site-verification", html or ""):
        return None
    return (
        "네이버 소유확인 태그가 없습니다. 서치어드바이저에 등록해야 "
        "네이버 수집 요청을 할 수 있습니다"
    )


async def check_site(url: str) -> SiteHealth:
    """사이트를 실제로 받아 점검한다. 실패해도 예외를 올리지 않는다."""
    health = SiteHealth()
    base = (url or "").rstrip("/")
    if not base:
        return health

    host = _host(base)
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT, follow_redirects=True,
        ) as client:
            robots = ""
            try:
                r = await client.get(f"{base}/robots.txt")
                if r.status_code == 200:
                    robots = r.text
            except Exception as e:  # noqa: BLE001
                logger.debug("[SITE_HEALTH] robots.txt 조회 실패 | %s", e)

            html = ""
            try:
                r = await client.get(base + "/")
                if r.status_code == 200:
                    html = r.text
            except Exception as e:  # noqa: BLE001
                logger.debug("[SITE_HEALTH] 홈 조회 실패 | %s", e)
    except Exception as e:  # noqa: BLE001
        logger.warning("[SITE_HEALTH] 점검 실패 | %s | %s", url, e)
        return health

    health.checked = True
    for code, msg in (
        ("sitemap_host", check_sitemap_host(robots, host) if robots else
         "robots.txt 를 읽지 못했습니다"),
        ("noindex", check_noindex(html)),
        ("naver_verification", check_naver_verification(html)),
    ):
        if msg:
            health.add(code, msg)

    if health.issues:
        logger.info(
            "[SITE_HEALTH] %s | 확인 필요 %d건: %s",
            host, len(health.issues),
            " / ".join(i["code"] for i in health.issues),
        )
    return health
