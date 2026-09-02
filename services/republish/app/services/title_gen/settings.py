"""제목 모듈 설정.

키워드 모듈과 **같은 모양**을 쓴다(모듈 settings dict). 화면과 스케줄러가
같은 해석기를 보게 해야 한쪽에서만 되는 일이 생기지 않는다.

계획서: docs/plans/keyword_pipeline_restructure_review.md §5-2
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

# 한 회차에 처리할 클러스터·키워드 수. 제목 생성은 AI 호출이라 비싸다.
DEFAULT_CLUSTER_LIMIT = 5
DEFAULT_KEYWORD_LIMIT = 20

DEFAULT_INTERVAL_MINUTES = 180

# 재고가 이보다 많으면 돌지 않는다(하한). 실제 목표치는 발행 속도로 정한다.
DEFAULT_MIN_INVENTORY = 30


@dataclass
class TitleModuleSettings:
    """제목 생성/수집 모듈 설정."""

    enabled: bool = True

    # 검증 모드 — 데이터 관리에 저장하지 않고 결과만 본다.
    # 기본 켜짐: 검증 없이 재고를 오염시키는 쪽이 되돌리기 어렵다.
    dry_run: bool = True

    # 제목을 만들 AI. 블로그 없이 도는 테스트에서는 여기서 골라야 한다.
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None

    # 경쟁 제목 각도 — 수집 제목을 재고로 쓰지 않고 "겹치지 말라" 는
    # 신호로만 쓴다. 순수 AI 도 순수 수집도 아닌 혼합이 권고다.
    use_angles: bool = True
    angle_sample: int = 10

    # 클러스터 생산(대표 글 1편 + 곁가지 N편)
    cluster_enabled: bool = True
    cluster_threshold: float = 0.34
    cluster_min_size: int = 3
    cluster_max_size: int = 12
    titles_per_cluster: int = 0      # 0이면 묶음 크기만큼

    # 묶이지 않은 단독 키워드
    titles_per_keyword: int = 3

    cluster_limit: int = DEFAULT_CLUSTER_LIMIT
    keyword_limit: int = DEFAULT_KEYWORD_LIMIT

    min_inventory: int = DEFAULT_MIN_INVENTORY
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES

    @classmethod
    def parse(cls, settings: Optional[dict]) -> "TitleModuleSettings":
        """모듈 settings 를 읽어 쓸 수 있는 값으로 만든다."""
        s = settings or {}
        raw = s.get("title") if isinstance(s.get("title"), dict) else s
        sched = s.get("schedule") or {}

        def _int(key: str, default: int, source: dict = None) -> int:
            try:
                value = (source or raw).get(key)
                return default if value in (None, "") else max(0, int(value))
            except (TypeError, ValueError):
                return default

        def _ratio(key: str, default: float) -> float:
            try:
                value = raw.get(key)
                number = float(value) if value is not None else default
            except (TypeError, ValueError):
                return default
            return default if not 0 < number <= 1 else number

        return cls(
            enabled=bool(raw.get("enabled", True)),
            dry_run=bool(raw.get("dry_run", True)),
            ai_provider=(raw.get("ai_provider") or None),
            ai_model=(raw.get("ai_model") or None),
            use_angles=bool(raw.get("use_angles", True)),
            angle_sample=max(1, min(30, _int("angle_sample", 10))),
            cluster_enabled=bool(raw.get("cluster_enabled", True)),
            cluster_threshold=_ratio("cluster_threshold", 0.34),
            cluster_min_size=max(2, _int("cluster_min_size", 3)),
            cluster_max_size=max(2, _int("cluster_max_size", 12)),
            titles_per_cluster=min(30, _int("titles_per_cluster", 0)),
            titles_per_keyword=max(1, min(10, _int("titles_per_keyword", 3))),
            cluster_limit=max(1, min(50, _int("cluster_limit",
                                              DEFAULT_CLUSTER_LIMIT))),
            keyword_limit=max(1, min(200, _int("keyword_limit",
                                               DEFAULT_KEYWORD_LIMIT))),
            min_inventory=_int("min_inventory", DEFAULT_MIN_INVENTORY),
            interval_minutes=_int("interval_minutes",
                                  DEFAULT_INTERVAL_MINUTES, sched),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "ai_provider": self.ai_provider,
            "ai_model": self.ai_model,
            "use_angles": self.use_angles,
            "angle_sample": self.angle_sample,
            "cluster_enabled": self.cluster_enabled,
            "cluster_threshold": self.cluster_threshold,
            "cluster_min_size": self.cluster_min_size,
            "cluster_max_size": self.cluster_max_size,
            "titles_per_cluster": self.titles_per_cluster,
            "titles_per_keyword": self.titles_per_keyword,
            "cluster_limit": self.cluster_limit,
            "keyword_limit": self.keyword_limit,
            "min_inventory": self.min_inventory,
            "interval_minutes": self.interval_minutes,
        }

    def as_maker_config(self) -> Any:
        """`TitleMaker`·`ClusterBuilder` 가 기대하는 모양으로 바꾼다.

        두 서비스는 키워드 모듈 설정을 받도록 만들어졌다. 필드 이름이 같아
        얇은 어댑터로 충분하다 — 제목 생성 로직을 복사하지 않는다.
        """
        from types import SimpleNamespace

        return SimpleNamespace(
            dry_run=self.dry_run,
            ai_provider=self.ai_provider,
            ai_model=self.ai_model,
            cluster_enabled=self.cluster_enabled,
            cluster_threshold=self.cluster_threshold,
            cluster_min_size=self.cluster_min_size,
            cluster_max_size=self.cluster_max_size,
            titles_per_cluster=self.titles_per_cluster,
            titles_per_keyword=self.titles_per_keyword,
            min_inventory=self.min_inventory,
        )
