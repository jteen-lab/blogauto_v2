"""키워드 모듈 설정 — 모듈 settings 를 해석한다.

수동 화면과 스케줄러가 **같은 설정 모양**을 쓴다. 다르면 화면에서 되던
것이 자동에서 안 되는 일이 생긴다.

순서도: docs/flowcharts/keyword_module.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 수식어. 시드 하나로 후보를 여러 개 만든다. API 호출은 늘지 않는다 —
# 검색광고는 한 번에 5개를 받으므로 결합한 것을 묶어 보낸다.
# 공백은 붙여 쓴다: 네이버가 공백 든 키워드를 거부한다(400, 11001).
DEFAULT_MODIFIERS = ["방법", "추천", "후기", "비교", "초보"]

# 한 회차에 쓸 시드 수. 검색광고 일일 호출 제한이 있어 한 번에 다
# 돌리지 않는다. 10개면 결합 포함 API 2~12회.
DEFAULT_SEED_LIMIT = 10

# 재고가 이보다 많으면 돌지 않는다. 매번 도는 것은 API 낭비다.
DEFAULT_MIN_INVENTORY = 30

# 켤 수 있는 수집 소스. 기본은 검색광고만 — 나머지는 사용자가 켠다.
# 한 소스만 쓰면 그 소스의 한계가 결과의 한계가 된다.
DEFAULT_SOURCES = ["naver_ads"]

# 검색량 없는 후보를 한 회차에 몇 개까지 보강할지(네이버 검색광고 호출).
DEFAULT_ENRICH_LIMIT = 100

DEFAULT_INTERVAL_MINUTES = 360
DEFAULT_TITLES_PER_KEYWORD = 3

# 클러스터 기본값. 업계 권장은 묶음당 키워드 8~10개다.
DEFAULT_CLUSTER_THRESHOLD = 0.34
DEFAULT_CLUSTER_MIN_SIZE = 3
DEFAULT_CLUSTER_MAX_SIZE = 12
DEFAULT_COLLECT_LIMIT = 100
DEFAULT_MEASURE_LIMIT = 50


def _ratio(value: Any, default: float) -> float:
    """0~1 비율값. 잘못된 값은 기본값으로 돌린다."""
    try:
        number = float(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return default if not 0 < number <= 1 else number


def _sources(value: Any) -> List[str]:
    """켤 소스 목록. 모르는 코드는 버리고, 검색광고는 항상 포함한다.

    검색광고를 빼면 검색량을 아는 소스가 사라져 후보가 전부 pending 이 된다.
    """
    from .sources.base import ALL_SOURCES, SRC_NAVER_ADS

    if isinstance(value, str):
        value = [x.strip() for x in value.split(",")]
    picked = [x for x in (value or []) if x in ALL_SOURCES]
    if SRC_NAVER_ADS not in picked:
        picked.insert(0, SRC_NAVER_ADS)
    return picked


@dataclass
class KeywordModuleSettings:
    """모듈 settings 를 읽어 쓸 수 있는 값으로 만든다."""

    enabled: bool = True
    seeds: List[str] = field(default_factory=list)
    modifiers: List[str] = field(default_factory=lambda: list(DEFAULT_MODIFIERS))
    use_blog_categories: bool = True
    # 검색광고 외에 켤 소스(자동완성·플래너·트렌드·서치콘솔)
    sources: List[str] = field(default_factory=lambda: list(DEFAULT_SOURCES))
    enrich_limit: int = DEFAULT_ENRICH_LIMIT
    # 지난 회차 채택 키워드를 다음 시드로 쓴다. 이게 없으면 카테고리만
    # 반복해 소재가 고갈된다.
    recurse_adopted: bool = True

    seed_limit: int = DEFAULT_SEED_LIMIT
    collect_limit: int = DEFAULT_COLLECT_LIMIT
    measure_limit: int = DEFAULT_MEASURE_LIMIT

    min_volume: int = 100
    # 상한이 없으면 검색량 50만짜리 대형 키워드가 그대로 채택된다.
    # 신생 블로그가 써도 묻히는 자리다.
    max_volume: int = 100_000
    min_saturation: float = 0.2
    # 공급을 볼 기간(일). 누적 문서수가 아니라 최근 발행량이 경쟁 지표다.
    pub_window_days: int = 30

    make_titles: bool = True
    titles_per_keyword: int = DEFAULT_TITLES_PER_KEYWORD

    # 클러스터 생산 — 키워드 1개 = 제목 1개는 대량 발행에 맞지 않는다.
    # 묶음 하나에서 대표 글 1편 + 곁가지 글 N편을 만든다.
    cluster_enabled: bool = True
    cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD
    cluster_min_size: int = DEFAULT_CLUSTER_MIN_SIZE
    cluster_max_size: int = DEFAULT_CLUSTER_MAX_SIZE
    # 0이면 묶음 크기 + 1(대표 글)로 자동 결정한다.
    titles_per_cluster: int = 0

    # 재고가 이보다 많으면 회차를 건너뛴다.
    min_inventory: int = DEFAULT_MIN_INVENTORY
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES

    @classmethod
    def parse(cls, settings: Optional[dict]) -> "KeywordModuleSettings":
        s = settings or {}
        kw = s.get("keyword") if isinstance(s.get("keyword"), dict) else s
        sched = s.get("schedule") or {}

        def _int(key: str, default: int, source: dict = None) -> int:
            try:
                v = (source or kw).get(key)
                return default if v in (None, "") else max(0, int(v))
            except (TypeError, ValueError):
                return default

        def _list(key: str, default: List[str]) -> List[str]:
            v = kw.get(key)
            if isinstance(v, str):
                v = [x.strip() for x in v.split(",")]
            if not isinstance(v, list):
                return list(default)
            out = [str(x).strip() for x in v if str(x).strip()]
            return out or list(default)

        try:
            sat = float(kw.get("min_saturation", 0.2))
        except (TypeError, ValueError):
            sat = 0.2

        return cls(
            enabled=bool(kw.get("enabled", True)),
            seeds=[x for x in _list("seeds", []) if x],
            modifiers=_list("modifiers", DEFAULT_MODIFIERS),
            use_blog_categories=bool(kw.get("use_blog_categories", True)),
            sources=_sources(kw.get("sources")),
            enrich_limit=_int("enrich_limit", DEFAULT_ENRICH_LIMIT),
            recurse_adopted=bool(kw.get("recurse_adopted", True)),
            seed_limit=_int("seed_limit", DEFAULT_SEED_LIMIT),
            collect_limit=_int("collect_limit", DEFAULT_COLLECT_LIMIT),
            measure_limit=_int("measure_limit", DEFAULT_MEASURE_LIMIT),
            min_volume=_int("min_volume", 100),
            max_volume=_int("max_volume", 100_000),
            min_saturation=max(0.0, sat),
            pub_window_days=max(1, _int("pub_window_days", 30)),
            make_titles=bool(kw.get("make_titles", True)),
            titles_per_keyword=max(1, min(10, _int(
                "titles_per_keyword", DEFAULT_TITLES_PER_KEYWORD))),
            cluster_enabled=bool(kw.get("cluster_enabled", True)),
            cluster_threshold=_ratio(kw.get("cluster_threshold"),
                                     DEFAULT_CLUSTER_THRESHOLD),
            cluster_min_size=max(2, _int("cluster_min_size",
                                         DEFAULT_CLUSTER_MIN_SIZE)),
            cluster_max_size=max(2, _int("cluster_max_size",
                                         DEFAULT_CLUSTER_MAX_SIZE)),
            titles_per_cluster=min(30, _int("titles_per_cluster", 0)),
            min_inventory=_int("min_inventory", DEFAULT_MIN_INVENTORY),
            # 주기는 성장 프로파일이 아니라 모듈 자신이 정한다.
            # GP 는 '얼마나 자주 발행할까' 를 정하고, 키워드 생산은
            # '재고가 부족한가' 로 돈다. 축이 다르다.
            interval_minutes=_int(
                "interval_minutes", DEFAULT_INTERVAL_MINUTES, sched),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "seeds": self.seeds,
            "modifiers": self.modifiers,
            "use_blog_categories": self.use_blog_categories,
            "sources": self.sources,
            "enrich_limit": self.enrich_limit,
            "recurse_adopted": self.recurse_adopted,
            "seed_limit": self.seed_limit,
            "collect_limit": self.collect_limit,
            "measure_limit": self.measure_limit,
            "min_volume": self.min_volume,
            "max_volume": self.max_volume,
            "min_saturation": self.min_saturation,
            "pub_window_days": self.pub_window_days,
            "make_titles": self.make_titles,
            "titles_per_keyword": self.titles_per_keyword,
            "cluster_enabled": self.cluster_enabled,
            "cluster_threshold": self.cluster_threshold,
            "cluster_min_size": self.cluster_min_size,
            "cluster_max_size": self.cluster_max_size,
            "titles_per_cluster": self.titles_per_cluster,
            "min_inventory": self.min_inventory,
            "interval_minutes": self.interval_minutes,
        }
