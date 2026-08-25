"""검색 노출 3종 — S1 IndexNow · S2 사이트맵 신선도 · S6 색인 점검.

계획서: docs/plans/search_visibility_plan.md §4.1
순서도: docs/flowcharts/search_visibility.md
"""
from .config import (
    DEFAULT_SEARCH_INDEX_CONFIG,
    generate_indexnow_key,
    indexnow_supported,
    load_config,
    merge_config,
)

__all__ = [
    "DEFAULT_SEARCH_INDEX_CONFIG",
    "generate_indexnow_key",
    "indexnow_supported",
    "load_config",
    "merge_config",
]
