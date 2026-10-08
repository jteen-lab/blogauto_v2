"""참고 자료 중 공식 출처가 0건이면 만들지 않는다(보류) — 모듈 스위치.

취업인포마스터(블로그 17) 애드센스 '가치 없는 콘텐츠' 거절(10/8) 재정비.
자격증·시험 글은 시행 기관 공고가 근거다. 참고 자료가 블로그·카페 글뿐이면
틀린 일정·수수료가 그대로 실린다.

모듈 설정 ``settings.reference.require_official`` 가 true 일 때만 동작한다.
키가 없거나 false 면 아무것도 하지 않는다 — 다른 블로그는 지금과 같다.
건강 글 보류(health_hold)와 같은 방식: 제목은 지우지 않고 hold_count 를 올린다.

순서도: docs/flowcharts/title_topic_gate.md (공식 출처 보류)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, List, Optional
from urllib.parse import urlparse

from ...core.logger import get_logger

logger = get_logger("official_hold", "app.log")

DEFAULT_DOMAINS = (
    ".go.kr", ".or.kr", "q-net.or.kr", "korcham.net", "kuksiwon.or.kr",
    "dataq.or.kr", "kotsa.or.kr", "work24.go.kr",
)
REASON = "공식 출처 필수 모듈인데 참고 자료에 공식 기관 주소 0건"


def switch(settings: Optional[dict]) -> Optional[List[str]]:
    """스위치가 켜져 있으면 공식 도메인 목록, 꺼져 있으면 None."""
    ref = (settings or {}).get("reference") or {}
    if not isinstance(ref, dict) or ref.get("require_official") is not True:
        return None
    domains = ref.get("official_domains") or DEFAULT_DOMAINS
    return [str(d).lower().strip() for d in domains if str(d).strip()]


def _host(url: str) -> str:
    """주소의 호스트(소문자). 깨진 주소는 빈 문자열."""
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""


def is_official(url: str, domains: Iterable[str]) -> bool:
    """호스트가 공식 도메인과 같거나 그 하위 도메인이면 True.

    '.go.kr' 처럼 점으로 시작하면 접미사, 'q-net.or.kr' 이면 같은 호스트
    또는 '*.q-net.or.kr' 만 인정한다('fakeq-net.or.kr' 는 아님).
    """
    host = _host(url)
    if not host:
        return False
    for d in domains:
        if d.startswith("."):
            if host.endswith(d):
                return True
        elif host == d or host.endswith("." + d):
            return True
    return False


def reference_urls(ref_result: Any) -> List[str]:
    """참고 자료 결과에서 실제로 쓴 문서 주소(요약 문서 + 통합 요약 출처)."""
    urls = [getattr(s, "url", "") for s in (getattr(ref_result, "summaries", None) or [])]
    urls += list(getattr(ref_result, "sources", None) or [])
    return [u for u in dict.fromkeys(urls) if u]


def count_official(ref_result: Any, domains: Iterable[str]) -> int:
    """참고 자료 중 공식 도메인 주소 수."""
    domains = list(domains)
    return sum(1 for u in reference_urls(ref_result) if is_official(u, domains))


async def hold_if_no_official(db, settings: Optional[dict], source_title,
                              ref_result, working_title: str,
                              blog_id: int) -> Optional[str]:
    """스위치가 켜졌고 공식 출처가 0건이면 제목에 기록하고 사유를 돌려준다."""
    domains = switch(settings)
    if domains is None:
        return None
    found = count_official(ref_result, domains)
    if found:
        logger.info("[OFFICIAL_HOLD] 통과 blog=%s | 공식 %d건 | '%s'",
                    blog_id, found, (working_title or "")[:40])
        return None
    source_title.hold_count = (source_title.hold_count or 0) + 1
    source_title.last_held_at = datetime.now()
    source_title.hold_reason = REASON
    await db.commit()
    logger.warning("[OFFICIAL_HOLD] 보류 blog=%s | %d회 | '%s' | %s",
                   blog_id, source_title.hold_count,
                   (working_title or "")[:40], REASON)
    return REASON
