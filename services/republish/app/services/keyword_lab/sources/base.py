"""수집 소스 공통 타입.

소스마다 주는 것이 다르다. 자동완성은 키워드만 주고 검색량이 없다.
검색광고는 검색량을 준다. 구글 키워드플래너는 **구간값**을 준다
(활성 캠페인이 없으면 "1천~1만" 식으로만 나온다). 서치콘솔은 우리 글이
실제로 노출된 쿼리를 준다 — 추정이 아니라 실측이다.

그래서 공통 형태에 `volume_is_range` 를 둔다. 구간값을 절대 기준
(하한·상한)으로 쓰면 안 되기 때문이다.

계획서: docs/plans/keyword_module_redesign_plan.md §4
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 소스 코드
SRC_NAVER_ADS = "naver_ads"
SRC_NAVER_SUGGEST = "naver_suggest"
SRC_GOOGLE_SUGGEST = "google_suggest"
SRC_GOOGLE_PLANNER = "google_planner"
SRC_GOOGLE_TRENDS = "google_trends"
SRC_GSC = "gsc"
# 발견(시드 없이 지금 뜨는 말) — 확장과 입력이 다르다
SRC_GOOGLE_TRENDING = "google_trending"
SRC_NAVER_DATALAB = "naver_datalab"

ALL_SOURCES = (
    SRC_NAVER_ADS, SRC_NAVER_SUGGEST, SRC_GOOGLE_SUGGEST,
    SRC_GOOGLE_PLANNER, SRC_GOOGLE_TRENDS, SRC_GSC,
    SRC_GOOGLE_TRENDING, SRC_NAVER_DATALAB,
)

# 소스 → 어느 엔진의 지표인지
SOURCE_ENGINE = {
    SRC_NAVER_ADS: "naver",
    SRC_NAVER_SUGGEST: "naver",
    SRC_GOOGLE_SUGGEST: "google",
    SRC_GOOGLE_PLANNER: "google",
    SRC_GOOGLE_TRENDS: "google",
    SRC_GSC: "google",
    SRC_GOOGLE_TRENDING: "google",
    SRC_NAVER_DATALAB: "naver",
}

# 사람이 읽을 이름
SOURCE_LABEL = {
    SRC_NAVER_ADS: "네이버 검색광고",
    SRC_NAVER_SUGGEST: "네이버 자동완성",
    SRC_GOOGLE_SUGGEST: "구글 자동완성",
    SRC_GOOGLE_PLANNER: "구글 키워드플래너",
    SRC_GOOGLE_TRENDS: "구글 트렌드",
    SRC_GSC: "서치콘솔 실측 쿼리",
    SRC_GOOGLE_TRENDING: "구글 실시간 인기(발견)",
    SRC_NAVER_DATALAB: "네이버 데이터랩(트렌드 검증)",
}

# 키워드 길이 상한. 문장이 통째로 들어오면 키워드가 아니다.
MAX_KEYWORD_LEN = 60


@dataclass
class KeywordIdea:
    """소스가 돌려주는 키워드 하나."""

    keyword: str
    source: str
    engine: str = "naver"
    search_volume: Optional[int] = None
    search_volume_pc: Optional[int] = None
    search_volume_mobile: Optional[int] = None
    competition: Optional[str] = None
    # 구간값이면 True. 절대 기준으로 쓰지 말 것.
    volume_is_range: bool = False
    # 어느 시드에서 나왔는지(추적용)
    seed: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_metric_values(self) -> Dict[str, Any]:
        """KeywordMetric 컬럼 값으로."""
        return {
            "search_volume": self.search_volume,
            "search_volume_pc": self.search_volume_pc,
            "search_volume_mobile": self.search_volume_mobile,
            "competition": self.competition,
            "volume_is_range": 1 if self.volume_is_range else 0,
        }


def normalize(keyword: str) -> str:
    """키워드를 다듬는다.

    앞뒤 공백·따옴표를 걷어내고 연속 공백을 하나로 줄인다. 네이버 검색광고는
    **공백이 든 키워드를 거부**하지만(400, 11001) 그 정리는 보내는 쪽에서
    한다. 여기서 공백을 없애면 자동완성·서치콘솔의 구절형 키워드가 망가진다.
    """
    text = re.sub(r"\s+", " ", (keyword or "").strip(" \"'“”‘’"))
    return text if 1 < len(text) <= MAX_KEYWORD_LEN else ""


def dedupe(ideas: List[KeywordIdea]) -> List[KeywordIdea]:
    """같은 키워드는 **검색량을 아는 쪽**을 남긴다.

    자동완성은 키워드만 주고 검색광고는 검색량을 준다. 둘 다 같은 키워드를
    물어오면 지표가 있는 쪽이 쓸모 있다.
    """
    best: Dict[str, KeywordIdea] = {}
    for idea in ideas:
        key = idea.keyword.lower()
        current = best.get(key)
        if current is None:
            best[key] = idea
            continue
        if current.search_volume is None and idea.search_volume is not None:
            best[key] = idea
    return list(best.values())
