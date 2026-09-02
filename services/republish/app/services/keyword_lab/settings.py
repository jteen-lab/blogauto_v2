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

# 한 회차에 수행할 단계. 골라서 끄면 **개별 모듈**이 된다
# (수집만 하는 모듈 / 측정만 하는 모듈 …). 한 모듈이 전부 할 수도 있다.
WORK_STEPS = ("collect", "measure", "classify", "rejudge")
DEFAULT_STEPS = ["collect", "measure", "classify"]

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


def _steps(value: Any, legacy_rejudge: Any = None) -> List[str]:
    """이 모듈이 맡을 단계 목록.

    모르는 값은 버린다. 전부 꺼 버리면 회차가 아무 일도 안 하므로 기본값을
    돌려준다 — 실수로 비운 모듈이 조용히 노는 것을 막는다.

    옛 설정 `rejudge_on_run` 은 단계 목록으로 흡수한다.
    """
    if isinstance(value, str):
        value = [x.strip() for x in value.split(",")]
    picked = [x for x in (value or []) if x in WORK_STEPS]
    if not picked:
        # steps 를 안 정한 옛 모듈. 기본 단계를 준다.
        picked = list(DEFAULT_STEPS)
    if legacy_rejudge and "rejudge" not in picked:
        picked.append("rejudge")
    # 실행 순서를 고정한다. 측정 전에 분류해도 결과가 달라지지 않지만
    # 로그가 뒤죽박죽이면 무엇이 언제 돌았는지 읽을 수 없다.
    return [s for s in WORK_STEPS if s in picked]


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
    # 이 모듈이 맡을 단계. 하나만 켜면 그 단계 전용 모듈이 된다.
    steps: List[str] = field(default_factory=lambda: list(DEFAULT_STEPS))
    seeds: List[str] = field(default_factory=list)
    modifiers: List[str] = field(default_factory=lambda: list(DEFAULT_MODIFIERS))
    use_blog_categories: bool = True
    # 검색광고 외에 켤 소스(자동완성·플래너·트렌드·서치콘솔)
    sources: List[str] = field(default_factory=lambda: list(DEFAULT_SOURCES))
    # 발견 결과에 니치 필터를 건다. 끄면 무관한 트렌드어가 그대로 들어온다.
    discovery_niche_filter: bool = True
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

    # 제목은 '제목 생성/수집' 모듈이 맡는다(계획서 S5). 수집 모듈이
    # 제목까지 만들면 중간 결과를 걸러낼 자리가 없고 실패가 한 덩어리로
    # 묻힌다. 옛 모듈 호환을 위해 설정은 남기되 **기본은 꺼 둔다.**
    make_titles: bool = False
    titles_per_keyword: int = DEFAULT_TITLES_PER_KEYWORD

    # 제목을 만들 AI. 블로그가 없으면(=시드만으로 도는 테스트) 블로그의
    # ai_config 를 쓸 수 없어 제공자가 비고, AI 서비스는 폴백을 하지 않아
    # 조용히 전부 실패한다. 그래서 모듈이 스스로 갖는다.
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None

    # 검증 모드. 켜면 제목을 **데이터 관리(임시제목·정식제목)에 저장하지
    # 않고** 결과만 돌려준다. 수집 품질을 먼저 확인하고, 쓸 만해지면 끈다.
    # 기본 켜짐 — 검증 없이 재고를 오염시키는 쪽이 되돌리기 어렵다.
    dry_run: bool = True

    # 클러스터 생산 — 키워드 1개 = 제목 1개는 대량 발행에 맞지 않는다.
    # 묶음 하나에서 대표 글 1편 + 곁가지 글 N편을 만든다.
    cluster_enabled: bool = True
    cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD
    cluster_min_size: int = DEFAULT_CLUSTER_MIN_SIZE
    cluster_max_size: int = DEFAULT_CLUSTER_MAX_SIZE
    # 0이면 묶음 크기 + 1(대표 글)로 자동 결정한다.
    titles_per_cluster: int = 0

    # 기준값이 바뀌면 이미 쌓인 후보도 다시 판정한다. API 를 부르지 않지만
    # 전체 행을 훑으므로 매 회차 돌릴 필요는 없다 — 기본은 꺼 둔다.
    rejudge_on_run: bool = False

    # 성과 되먹임 — 내보낸 뒤 실제로 노출됐는지 회수해 시드 순서에 반영한다.
    feedback_enabled: bool = True
    feedback_days: int = 28

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
            steps=_steps(kw.get("steps"), kw.get("rejudge_on_run")),
            seeds=[x for x in _list("seeds", []) if x],
            modifiers=_list("modifiers", DEFAULT_MODIFIERS),
            use_blog_categories=bool(kw.get("use_blog_categories", True)),
            sources=_sources(kw.get("sources")),
            discovery_niche_filter=bool(
                kw.get("discovery_niche_filter", True)),
            enrich_limit=_int("enrich_limit", DEFAULT_ENRICH_LIMIT),
            recurse_adopted=bool(kw.get("recurse_adopted", True)),
            seed_limit=_int("seed_limit", DEFAULT_SEED_LIMIT),
            collect_limit=_int("collect_limit", DEFAULT_COLLECT_LIMIT),
            measure_limit=_int("measure_limit", DEFAULT_MEASURE_LIMIT),
            min_volume=_int("min_volume", 100),
            max_volume=_int("max_volume", 100_000),
            min_saturation=max(0.0, sat),
            pub_window_days=max(1, _int("pub_window_days", 30)),
            make_titles=bool(kw.get("make_titles", False)),
            dry_run=bool(kw.get("dry_run", True)),
            ai_provider=(kw.get("ai_provider") or None),
            ai_model=(kw.get("ai_model") or None),
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
            rejudge_on_run=bool(kw.get("rejudge_on_run", False)),
            feedback_enabled=bool(kw.get("feedback_enabled", True)),
            feedback_days=max(1, _int("feedback_days", 28)),
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
            "steps": self.steps,
            "seeds": self.seeds,
            "modifiers": self.modifiers,
            "use_blog_categories": self.use_blog_categories,
            "sources": self.sources,
            "discovery_niche_filter": self.discovery_niche_filter,
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
            "dry_run": self.dry_run,
            "ai_provider": self.ai_provider,
            "ai_model": self.ai_model,
            "titles_per_keyword": self.titles_per_keyword,
            "cluster_enabled": self.cluster_enabled,
            "cluster_threshold": self.cluster_threshold,
            "cluster_min_size": self.cluster_min_size,
            "cluster_max_size": self.cluster_max_size,
            "titles_per_cluster": self.titles_per_cluster,
            "rejudge_on_run": self.rejudge_on_run,
            "feedback_enabled": self.feedback_enabled,
            "feedback_days": self.feedback_days,
            "min_inventory": self.min_inventory,
            "interval_minutes": self.interval_minutes,
        }
