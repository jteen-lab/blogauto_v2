"""제목 수집 모듈 설정.

수집은 두 기능으로 나뉜다. 옛 방식은 "키워드로 검색 → 목표 수 채우면 종료"
였고, 도메인 하나에서 목표를 못 채우면 **그 도메인이 그대로 방치**됐다.
어디까지 했는지 적을 자리가 없어서였다(URL 12만 건 중 처리 0.02%).

    ① 제목 수집  — 채택 키워드로 검색 → 제목 + 새 도메인
    ② 도메인 추출 — 이미 저장된 도메인에서 마저 추출

②가 큐를 소진시킨다. ①만 켜면 새 소재를 찾고, ②만 켜면 밀린 것을 비운다.

계획서: docs/plans/title_tab_workplan.md §2-2
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

# 한 회차 기본값. 유입이 처리를 앞지르지 않게 잡은 값이다.
DEFAULT_SEED_LIMIT = 10
DEFAULT_URLS_PER_DOMAIN = 30
DEFAULT_DOMAINS_PER_CYCLE = 5
DEFAULT_MAX_PENDING_DOMAINS = 50

DEFAULT_EXTRACT_DOMAINS = 5
DEFAULT_TITLES_PER_DOMAIN = 30

# 니치 대조 모드. 초기에는 '표시' 가 안전하다 — 분류표가 얇은 상태에서
# 차단부터 켜면 살릴 수 있는 제목까지 막힌다.
NICHE_MARK = "mark"
NICHE_BLOCK = "block"
NICHE_MODES = (NICHE_MARK, NICHE_BLOCK)


def _int(source: dict, key: str, default: int, low: int = 1,
         high: int = 10_000) -> int:
    """범위를 벗어난 값은 기본값으로. 0을 넣어 회차가 멈추는 것을 막는다."""
    try:
        value = source.get(key)
        if value in (None, ""):
            return default
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


@dataclass
class TitleCollectSettings:
    """수집 섹션 설정."""

    enabled: bool = True

    # ① 제목 수집
    search_enabled: bool = True
    seed_limit: int = DEFAULT_SEED_LIMIT
    urls_per_domain: int = DEFAULT_URLS_PER_DOMAIN
    domains_per_cycle: int = DEFAULT_DOMAINS_PER_CYCLE
    # 미완료 도메인이 이보다 많으면 ①을 건너뛴다. 분리만으로는 격차가
    # 다시 벌어지므로 상한을 함께 둔다.
    max_pending_domains: int = DEFAULT_MAX_PENDING_DOMAINS

    # ② 도메인 추출
    extract_enabled: bool = True
    extract_domains: int = DEFAULT_EXTRACT_DOMAINS
    titles_per_domain: int = DEFAULT_TITLES_PER_DOMAIN

    # 저장 시점 니치 대조
    niche_mode: str = NICHE_MARK

    @classmethod
    def parse(cls, settings: Optional[dict]) -> "TitleCollectSettings":
        raw = settings or {}
        source = raw.get("collect") if isinstance(raw.get("collect"), dict) \
            else raw
        mode = str(source.get("niche_mode") or NICHE_MARK).strip()
        return cls(
            enabled=bool(source.get("enabled", True)),
            search_enabled=bool(source.get("search_enabled", True)),
            seed_limit=_int(source, "seed_limit", DEFAULT_SEED_LIMIT, 1, 50),
            urls_per_domain=_int(source, "urls_per_domain",
                                 DEFAULT_URLS_PER_DOMAIN, 1, 200),
            domains_per_cycle=_int(source, "domains_per_cycle",
                                   DEFAULT_DOMAINS_PER_CYCLE, 1, 50),
            max_pending_domains=_int(source, "max_pending_domains",
                                     DEFAULT_MAX_PENDING_DOMAINS, 1, 1000),
            extract_enabled=bool(source.get("extract_enabled", True)),
            extract_domains=_int(source, "extract_domains",
                                 DEFAULT_EXTRACT_DOMAINS, 1, 50),
            titles_per_domain=_int(source, "titles_per_domain",
                                   DEFAULT_TITLES_PER_DOMAIN, 1, 200),
            niche_mode=mode if mode in NICHE_MODES else NICHE_MARK,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "search_enabled": self.search_enabled,
            "seed_limit": self.seed_limit,
            "urls_per_domain": self.urls_per_domain,
            "domains_per_cycle": self.domains_per_cycle,
            "max_pending_domains": self.max_pending_domains,
            "extract_enabled": self.extract_enabled,
            "extract_domains": self.extract_domains,
            "titles_per_domain": self.titles_per_domain,
            "niche_mode": self.niche_mode,
        }
