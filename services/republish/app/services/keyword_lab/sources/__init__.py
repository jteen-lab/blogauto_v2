"""키워드 수집 소스 모음.

한 소스만 쓰면 그 소스의 한계가 그대로 결과의 한계가 된다. 검색광고
연관키워드만 보면 최신성이 약하고 질문형이 거의 안 잡힌다.

계획서: docs/plans/keyword_module_redesign_plan.md §4
"""
from .base import (
    ALL_SOURCES, SOURCE_ENGINE, SOURCE_LABEL, SRC_GOOGLE_PLANNER,
    SRC_GOOGLE_SUGGEST, SRC_GOOGLE_TRENDS, SRC_GSC, SRC_NAVER_ADS,
    SRC_NAVER_SUGGEST, KeywordIdea, dedupe, normalize,
)

__all__ = [
    "ALL_SOURCES", "SOURCE_ENGINE", "SOURCE_LABEL", "KeywordIdea",
    "SRC_NAVER_ADS", "SRC_NAVER_SUGGEST", "SRC_GOOGLE_SUGGEST",
    "SRC_GOOGLE_PLANNER", "SRC_GOOGLE_TRENDS", "SRC_GSC",
    "dedupe", "normalize",
]
