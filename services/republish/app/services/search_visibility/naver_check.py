"""네이버 노출 기술 점검 (NEO 레인).

우리에게 네이버 쪽 기술 점검이 없었다. 외부 스킬 검토에서 가져온 항목이다
(docs/plans/external_skill_review_seo.md §4-(2)).

점검 항목
    1. robots.txt 가 네이버 크롤러 `Yeti` 를 막지 않는가
    2. 네이버 서치어드바이저 소유 확인 메타 태그가 있는가(정황)

주의: 소유 확인은 HTML 파일·DNS 로도 가능하므로 **메타 태그 부재가 미등록의
증거는 아니다.** 화면에도 그렇게 표시한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from ...core.logger import get_logger
from .config import blog_host

logger = get_logger("naver_check", "app.log")

TIMEOUT = 15.0
NAVER_BOT = "yeti"
# 본문 앞부분만 본다 — 검증 메타는 <head> 에 있다.
HEAD_BYTES = 60000

VERIFY_RE = re.compile(r"naver-site-verification", re.I)
GROUP_RE = re.compile(r"user-agent\s*:\s*(?P<agent>[^\r\n]+)", re.I)


@dataclass
class NaverCheckResult:
    """네이버 점검 1회 결과."""

    ok: bool
    robots_found: bool = False
    yeti_blocked: Optional[bool] = None
    yeti_rule_source: Optional[str] = None
    verification_meta: Optional[bool] = None
    error: Optional[str] = None


def _blocks_root(block_lines: list[str]) -> bool:
    """User-agent 그룹의 규칙이 사이트 전체를 막는지 판정한다."""
    for line in block_lines:
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "disallow" and value == "/":
            return True
    return False


def _yeti_verdict(robots: str) -> tuple[Optional[bool], Optional[str]]:
    """Yeti 가 차단되는지와 그 근거가 된 그룹을 돌려준다."""
    groups: dict[str, list[str]] = {}
    current: list[str] = []
    for raw in robots.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = GROUP_RE.match(line)
        if match:
            current = groups.setdefault(match.group("agent").strip().lower(), [])
            continue
        if current is not None:
            current.append(line)

    if NAVER_BOT in groups:
        return _blocks_root(groups[NAVER_BOT]), "Yeti"
    if "*" in groups:
        return _blocks_root(groups["*"]), "*"
    return False, None


async def check_blog(blog: Any) -> NaverCheckResult:
    """블로그의 네이버 노출 전제조건을 점검한다."""
    host = blog_host(blog)
    if not host:
        return NaverCheckResult(ok=False, error="블로그 URL에서 호스트를 확인할 수 없습니다")

    result = NaverCheckResult(ok=True)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            robots = await client.get(f"https://{host}/robots.txt")
            if robots.status_code == 200 and robots.text.strip():
                result.robots_found = True
                blocked, source = _yeti_verdict(robots.text)
                result.yeti_blocked = blocked
                result.yeti_rule_source = source

            home = await client.get(f"https://{host}/")
            if home.status_code == 200:
                result.verification_meta = bool(
                    VERIFY_RE.search(home.text[:HEAD_BYTES]),
                )
    except Exception as exc:  # noqa: BLE001 — 점검 실패가 다른 기능을 막지 않는다
        logger.warning("[NAVER_CHECK] 실패 | host=%s | %s", host, exc)
        return NaverCheckResult(ok=False, error=f"점검 실패: {exc}")

    return result
