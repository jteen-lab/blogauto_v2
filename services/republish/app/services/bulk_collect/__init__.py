"""
대량 수집(bulk_collect) 패키지 (Phase B)

기존 단일 파일 `bulk_title_collector_service.py` 를 책임별로 분리한 신규 패키지.
구성 요소:
    - ChunkProcessor: collected_urls 의 pending row 청크 단위 처리
    - DomainLimiter: 도메인별 동시 요청 제한
    - LastmodTracker: BulkCollectProgress 모델 기반 lastmod / 사이클 통계 관리
    - Timebox: 사이클 최대 시간 추적
    - SitemapParser, fetch_title_from_url, clean_title: 사이트맵/제목 파싱 유틸리티

외부 호출자(특히 신규 Celery 태스크 `tasks.bulk_collect_cycle`)는 이 패키지에서
필요한 클래스를 import 한다.
"""

from .chunk_processor import ChunkProcessor, ChunkStats
from .cycle_runner import run_bulk_collect_cycle
from .domain_limiter import DomainLimiter
from .lastmod_tracker import LastmodTracker
from ..title_collect.sitemap import (
    SitemapParser,
    clean_title,
    fetch_title_from_url,
)
from .timebox import Timebox
from .url_ingester import maybe_ingest_input_urls

__all__ = [
    "ChunkProcessor",
    "ChunkStats",
    "DomainLimiter",
    "LastmodTracker",
    "Timebox",
    "SitemapParser",
    "clean_title",
    "fetch_title_from_url",
    "maybe_ingest_input_urls",
    "run_bulk_collect_cycle",
]
