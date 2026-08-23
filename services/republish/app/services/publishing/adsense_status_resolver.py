"""블로그의 애드센스 상태 판정 (실제 사이트 목록 1차 기준).

**판정 우선순위 (사용자 확정 2026-08-23)**
1. 애드센스 사이트 목록의 상태가 최우선이다. blogauto 내부 설정(필수페이지·니치
   강제 등)은 그다음이다. 과거에 승인받은 블로그는 blogauto 설정을 하지 않았어도
   승인으로 분류돼야 한다.
2. 서브도메인은 애드센스가 **부모 도메인 상태를 따른다**(2023-03 정책). 목록에
   없다고 미신청으로 보면 안 된다.

| 사이트 state | 표시 |
|---|---|
| READY(준비됨) | **승인** — 다른 설정과 무관하게 최우선 |
| GETTING_READY / REQUIRES_REVIEW(준비 중) | blogauto 설정에 따라 준비중 / 심사중 |
| NEEDS_ATTENTION(주의 필요) | **확인 필요**(별도 표시) |
| 목록에 없음(상위 도메인까지 탐색 후에도) | 미신청 |
"""
from typing import Any, Dict, Iterable, Optional, Tuple

from ...core.logger import get_logger
from ..generation.sibling_blogs import extract_host

logger = get_logger("adsense_status_resolver", "app.log")

# blogauto 표시 상태
ST_NONE = "none"            # 미신청
ST_PREPARING = "preparing"  # 준비중
ST_APPLIED = "applied"      # 심사중
ST_APPROVED = "approved"    # 승인
ST_ATTENTION = "attention"  # 확인 필요

DISPLAY_STATUSES = (ST_NONE, ST_PREPARING, ST_APPLIED, ST_APPROVED, ST_ATTENTION)

# 애드센스 원문 state
STATE_READY = "READY"
STATE_GETTING_READY = "GETTING_READY"
STATE_REQUIRES_REVIEW = "REQUIRES_REVIEW"
STATE_NEEDS_ATTENTION = "NEEDS_ATTENTION"


def _normalize(domain: Optional[str]) -> str:
    """도메인 비교용 정규화(스킴·www·끝 슬래시·대소문자 제거)."""
    return extract_host(domain)


def find_site_for_host(
    host: str, sites_by_domain: Dict[str, Any]
) -> Tuple[Optional[Any], bool]:
    """호스트에 해당하는 사이트를 찾는다. 없으면 상위 도메인으로 올라간다.

    Returns:
        (사이트, 상속여부) — 상속여부 True면 부모 도메인에서 물려받은 상태다.
    """
    if not host:
        return None, False

    if host in sites_by_domain:
        return sites_by_domain[host], False

    parts = host.split(".")
    for i in range(1, len(parts) - 1):
        parent = ".".join(parts[i:])
        if parent in sites_by_domain:
            return sites_by_domain[parent], True
    return None, False


def resolve_display_status(
    blog: Any,
    sites_by_domain: Dict[str, Any],
) -> Dict[str, Any]:
    """블로그 하나의 표시 상태를 판정한다.

    Args:
        blog: Blog (url, adsense_status, required_pages_status 사용)
        sites_by_domain: {정규화된 도메인: 사이트 객체(state 보유)}

    Returns:
        {"status", "state", "source", "inherited_from"}
        - source: "adsense"(사이트 목록 기준) | "local"(내부 설정 기준)
    """
    host = _normalize(getattr(blog, "url", None))
    site, inherited = find_site_for_host(host, sites_by_domain)

    if site is None:
        # 사이트 목록에 없다 = 아직 신청하지 않음
        return {
            "status": ST_NONE, "state": None,
            "source": "adsense", "inherited_from": None,
        }

    state = (getattr(site, "state", None) or "").upper()
    parent = getattr(site, "domain", None) if inherited else None

    if state == STATE_READY:
        # 최우선 — 내부 설정과 무관하게 승인
        return {
            "status": ST_APPROVED, "state": state,
            "source": "adsense", "inherited_from": parent,
        }

    if state == STATE_NEEDS_ATTENTION:
        return {
            "status": ST_ATTENTION, "state": state,
            "source": "adsense", "inherited_from": parent,
        }

    if state in (STATE_GETTING_READY, STATE_REQUIRES_REVIEW):
        # 준비 중 — 내부 설정으로 준비중/심사중을 가른다
        local = (getattr(blog, "adsense_status", None) or ST_NONE)
        status = ST_APPLIED if local == ST_APPLIED else ST_PREPARING
        return {
            "status": status, "state": state,
            "source": "local", "inherited_from": parent,
        }

    # 알 수 없는 state — 내부 값을 그대로 쓰되 원문을 남긴다
    logger.warning("[ADSENSE_STATUS] 알 수 없는 state=%s | domain=%s", state, host)
    local = (getattr(blog, "adsense_status", None) or ST_NONE)
    return {
        "status": local if local in DISPLAY_STATUSES else ST_NONE,
        "state": state, "source": "local", "inherited_from": parent,
    }


def build_sites_index(sites: Iterable[Any]) -> Dict[str, Any]:
    """사이트 목록을 도메인 인덱스로 만든다(여러 계정 병합).

    같은 도메인이 여러 계정에 있으면 **더 진전된 상태**를 채택한다
    (승인 > 검토중 > 준비중 > 주의필요). 한 도메인이 두 계정에 걸쳐 있을 때
    승인된 쪽을 놓치지 않기 위함이다.
    """
    rank = {
        STATE_READY: 4,
        STATE_REQUIRES_REVIEW: 3,
        STATE_GETTING_READY: 2,
        STATE_NEEDS_ATTENTION: 1,
    }
    index: Dict[str, Any] = {}
    for site in sites:
        domain = _normalize(getattr(site, "domain", None))
        if not domain:
            continue
        prev = index.get(domain)
        if prev is None:
            index[domain] = site
            continue
        if rank.get((getattr(site, "state", "") or "").upper(), 0) > \
           rank.get((getattr(prev, "state", "") or "").upper(), 0):
            index[domain] = site
    return index
