"""X1 — 외부 링크 정책 적용.

애드센스 자산에서 CPA/제휴 랜딩으로 링크할 때 지켜야 하는 것:

1. `rel="sponsored nofollow"` — 상업적 링크에 표시가 없으면 구글 링크 스팸 정책 위반.
2. `data-google-vignette="false"` — 전면광고는 아웃바운드 클릭에서도 뜨는데,
   노출을 늘리려고 링크를 배치했다는 인상을 주지 않기 위해 명시적으로 끈다.
   (얻는 것은 기존 수익의 15~35% 증분, 잃는 것은 계정 전체)
3. 글당 외부 링크 개수 상한 — 링크가 많을수록 브리지 페이지로 읽힌다.

내부 링크(같은 호스트)와 이미 표시된 링크는 건드리지 않는다.

설계: docs/plans/external_traffic_strategy.md §6.6
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Set
from urllib.parse import urlparse

from ...core.logger import get_logger

logger = get_logger("external_link", "app.log")

ANCHOR_RE = re.compile(r"<a\b([^>]*)>", re.I)
HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
REL_RE = re.compile(r'rel\s*=\s*["\']([^"\']*)["\']', re.I)
VIGNETTE_RE = re.compile(r"data-google-vignette\s*=", re.I)

REQUIRED_REL = ("sponsored", "nofollow")
# 링크를 세지 않는 스킴
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "#")


@dataclass
class LinkPolicyResult:
    """정책 적용 결과."""

    html: str
    external_count: int = 0
    tagged: int = 0
    over_limit: bool = False


def _host(url: str) -> Optional[str]:
    try:
        return urlparse(url).hostname
    except Exception:  # noqa: BLE001
        return None


def _is_external(href: str, own_hosts: Set[str]) -> bool:
    """자기 호스트가 아닌 http(s) 링크인지 판정한다."""
    lowered = href.strip().lower()
    if any(lowered.startswith(s) for s in SKIP_SCHEMES):
        return False
    if lowered.startswith("/") or not lowered.startswith("http"):
        return False
    host = _host(href)
    return bool(host) and host.lower() not in own_hosts


def _merge_rel(existing: str) -> str:
    """기존 rel 값을 보존하면서 필요한 토큰을 더한다."""
    tokens = [t for t in (existing or "").split() if t]
    for required in REQUIRED_REL:
        if required not in tokens:
            tokens.append(required)
    return " ".join(tokens)


def _own_hosts(blog_url: str) -> Set[str]:
    """블로그 자신의 호스트(www 유무 포함)."""
    host = (_host(blog_url) or "").lower()
    if not host:
        return set()
    bare = host[4:] if host.startswith("www.") else host
    return {bare, f"www.{bare}"}


def apply(html: str, blog_url: str, max_external: int = 0) -> LinkPolicyResult:
    """본문의 외부 링크에 정책을 적용한다.

    Args:
        html: 발행 직전 본문 HTML
        blog_url: 블로그 주소(자기 호스트 판정용)
        max_external: 글당 외부 링크 상한. 0이면 상한 없음(경고만 안 함)

    Returns:
        LinkPolicyResult — 실패해도 원본 HTML 을 담아 돌려준다.
    """
    if not html:
        return LinkPolicyResult(html=html or "")

    own = _own_hosts(blog_url)
    counted: List[str] = []
    tagged = 0

    def _rewrite(match: re.Match) -> str:
        nonlocal tagged
        attrs = match.group(1)
        href_match = HREF_RE.search(attrs)
        if not href_match or not _is_external(href_match.group(1), own):
            return match.group(0)

        counted.append(href_match.group(1))

        rel_match = REL_RE.search(attrs)
        new_attrs = attrs
        merged = _merge_rel(rel_match.group(1) if rel_match else "")
        if rel_match:
            if rel_match.group(1).split() != merged.split():
                new_attrs = REL_RE.sub(f'rel="{merged}"', new_attrs, count=1)
                tagged += 1
        else:
            new_attrs = f'{new_attrs.rstrip()} rel="{merged}"'
            tagged += 1

        if not VIGNETTE_RE.search(new_attrs):
            new_attrs = f'{new_attrs.rstrip()} data-google-vignette="false"'

        return f"<a{new_attrs}>"

    try:
        result = ANCHOR_RE.sub(_rewrite, html)
    except Exception as exc:  # noqa: BLE001 — 발행을 막지 않는다
        logger.warning("[EXT_LINK] 정책 적용 실패(무시): %s", exc)
        return LinkPolicyResult(html=html)

    over = bool(max_external) and len(counted) > max_external
    if over:
        logger.warning(
            "[EXT_LINK] 외부 링크 %d개 — 상한 %d 초과 | %s",
            len(counted), max_external, blog_url,
        )
    if tagged:
        logger.info("[EXT_LINK] rel 표시 %d개 적용 | %s", tagged, blog_url)

    return LinkPolicyResult(
        html=result, external_count=len(counted), tagged=tagged, over_limit=over,
    )
