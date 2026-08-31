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

DEFAULT_INTERVAL_MINUTES = 360
DEFAULT_TITLES_PER_KEYWORD = 3
DEFAULT_COLLECT_LIMIT = 100
DEFAULT_MEASURE_LIMIT = 50


@dataclass
class KeywordModuleSettings:
    """모듈 settings 를 읽어 쓸 수 있는 값으로 만든다."""

    enabled: bool = True
    seeds: List[str] = field(default_factory=list)
    modifiers: List[str] = field(default_factory=lambda: list(DEFAULT_MODIFIERS))
    use_blog_categories: bool = True
    # 지난 회차 채택 키워드를 다음 시드로 쓴다. 이게 없으면 카테고리만
    # 반복해 소재가 고갈된다.
    recurse_adopted: bool = True

    seed_limit: int = DEFAULT_SEED_LIMIT
    collect_limit: int = DEFAULT_COLLECT_LIMIT
    measure_limit: int = DEFAULT_MEASURE_LIMIT

    min_volume: int = 100
    min_saturation: float = 0.2

    make_titles: bool = True
    titles_per_keyword: int = DEFAULT_TITLES_PER_KEYWORD

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
            recurse_adopted=bool(kw.get("recurse_adopted", True)),
            seed_limit=_int("seed_limit", DEFAULT_SEED_LIMIT),
            collect_limit=_int("collect_limit", DEFAULT_COLLECT_LIMIT),
            measure_limit=_int("measure_limit", DEFAULT_MEASURE_LIMIT),
            min_volume=_int("min_volume", 100),
            min_saturation=max(0.0, sat),
            make_titles=bool(kw.get("make_titles", True)),
            titles_per_keyword=max(1, min(10, _int(
                "titles_per_keyword", DEFAULT_TITLES_PER_KEYWORD))),
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
            "recurse_adopted": self.recurse_adopted,
            "seed_limit": self.seed_limit,
            "collect_limit": self.collect_limit,
            "measure_limit": self.measure_limit,
            "min_volume": self.min_volume,
            "min_saturation": self.min_saturation,
            "make_titles": self.make_titles,
            "titles_per_keyword": self.titles_per_keyword,
            "min_inventory": self.min_inventory,
            "interval_minutes": self.interval_minutes,
        }
