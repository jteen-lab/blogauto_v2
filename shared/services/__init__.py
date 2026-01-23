"""
BlogAuto V2 공유 서비스 모듈

여러 서비스에서 공통으로 사용하는 기능을 제공합니다.
- LocationService: 지역명 추출 및 비교
- SimilarityService: 유사도 매칭 (지역명 우선 처리)
"""

from .location_service import (
    LocationService,
    extract_location,
    is_same_location,
    remove_location,
    normalize_location,
)

from .similarity_service import (
    SimilarityService,
    calculate_similarity,
    find_best_match,
    batch_group_titles,
    DEFAULT_SIMILARITY_THRESHOLD,
)

__all__ = [
    # Location
    "LocationService",
    "extract_location",
    "is_same_location",
    "remove_location",
    "normalize_location",
    # Similarity
    "SimilarityService",
    "calculate_similarity",
    "find_best_match",
    "batch_group_titles",
    "DEFAULT_SIMILARITY_THRESHOLD",
]
