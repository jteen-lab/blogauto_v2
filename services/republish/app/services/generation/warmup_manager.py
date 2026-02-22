"""
워밍업 관리 서비스

신규 블로그(발행 이력 0건)의 발행 수를 점진적으로 증가시켜
블로그 플랫폼의 기계적 발행 탐지를 방지합니다.

적용 범위: 발행(publish)에만 적용
- 생성(generate): 영향 없음 (내부 동작)
- 재발행(republish): 대상 아님 (신규 블로그에 재발행할 글 없음)

워밍업 대상 기준:
- 발행 이력 0건인 블로그 = 워밍업 대상
- 첫 발행일로부터 warmup_days 경과 = 워밍업 종료
"""
import logging
import math
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional

import pytz
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.crawled_post import CrawledPost

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")


@dataclass
class WarmupStatus:
    """워밍업 상태 판단 결과.

    Attributes:
        is_active: 워밍업 활성 여부
        days_elapsed: 첫 발행 이후 경과일 (미발행: -1)
        daily_max: 오늘 허용 발행 수
        today_published: 오늘 이미 발행한 수
        can_publish: 추가 발행 가능 여부
        effective_interval: 워밍업 기반 간격(분), 비활성이면 None
    """

    is_active: bool
    days_elapsed: int
    daily_max: int
    today_published: int
    can_publish: bool
    effective_interval: Optional[int]


class WarmupManager:
    """워밍업 판단 서비스.

    신규 블로그의 발행 수를 점진적으로 증가시켜
    블로그 플랫폼의 기계적 발행 탐지를 방지합니다.

    Args:
        db: SQLAlchemy 비동기 세션
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def check_warmup(
        self,
        blog_id: int,
        warmup_settings: dict,
        active_hours: int,
    ) -> WarmupStatus:
        """워밍업 상태를 판단합니다.

        Args:
            blog_id: 블로그 ID
            warmup_settings: 워밍업 설정 딕셔너리
                - enabled: bool (워밍업 활성 여부)
                - warmup_days: int (워밍업 기간, 일)
                - initial_daily_posts: int (초기 일일 발행 수)
                - max_daily_posts: int (최대 일일 발행 수)
                - ramp_rate: float (일별 증가율)
            active_hours: 일일 활동 시간 (시)

        Returns:
            WarmupStatus: 워밍업 상태 판단 결과
        """
        # 워밍업 비활성 시 즉시 반환
        if not warmup_settings.get("enabled", False):
            logger.debug("[WARMUP] blog_id=%d: 워밍업 비활성", blog_id)
            return WarmupStatus(
                is_active=False,
                days_elapsed=0,
                daily_max=0,
                today_published=0,
                can_publish=True,
                effective_interval=None,
            )

        # 설정값 추출
        warmup_days: int = warmup_settings.get("warmup_days", 14)
        initial_daily_posts: int = warmup_settings.get("initial_daily_posts", 1)
        max_daily_posts: int = warmup_settings.get("max_daily_posts", 3)
        ramp_rate: float = warmup_settings.get("ramp_rate", 0.5)

        # 첫 발행일 조회
        first_publish_date = await self._get_first_publish_date(blog_id)

        # 발행 이력 없음 → 워밍업 대상 (days_elapsed = -1)
        if first_publish_date is None:
            daily_max = self._calculate_daily_max(
                days_elapsed=-1,
                initial_daily_posts=initial_daily_posts,
                max_daily_posts=max_daily_posts,
                ramp_rate=ramp_rate,
            )
            today_published = await self._count_today_publishes(blog_id)
            effective_interval = max(
                1, math.floor((active_hours * 60) / daily_max)
            )
            logger.info(
                "[WARMUP] blog_id=%d: 미발행 블로그, "
                "daily_max=%d, today_published=%d",
                blog_id, daily_max, today_published,
            )
            return WarmupStatus(
                is_active=True,
                days_elapsed=-1,
                daily_max=daily_max,
                today_published=today_published,
                can_publish=today_published < daily_max,
                effective_interval=effective_interval,
            )

        # 경과일 계산
        today_kst = datetime.now(KST).date()
        first_date = first_publish_date.astimezone(KST).date()
        days_elapsed = (today_kst - first_date).days

        # 워밍업 기간 종료
        if days_elapsed >= warmup_days:
            logger.info(
                "[WARMUP] blog_id=%d: 워밍업 종료 (경과일=%d >= 기간=%d)",
                blog_id, days_elapsed, warmup_days,
            )
            return WarmupStatus(
                is_active=False,
                days_elapsed=days_elapsed,
                daily_max=0,
                today_published=0,
                can_publish=True,
                effective_interval=None,
            )

        # 워밍업 진행 중
        daily_max = self._calculate_daily_max(
            days_elapsed=days_elapsed,
            initial_daily_posts=initial_daily_posts,
            max_daily_posts=max_daily_posts,
            ramp_rate=ramp_rate,
        )
        today_published = await self._count_today_publishes(blog_id)
        effective_interval = max(
            1, math.floor((active_hours * 60) / daily_max)
        )
        logger.info(
            "[WARMUP] blog_id=%d: 워밍업 중 (경과일=%d, "
            "daily_max=%d, today=%d/%d)",
            blog_id, days_elapsed, daily_max,
            today_published, daily_max,
        )
        return WarmupStatus(
            is_active=True,
            days_elapsed=days_elapsed,
            daily_max=daily_max,
            today_published=today_published,
            can_publish=today_published < daily_max,
            effective_interval=effective_interval,
        )

    async def _get_first_publish_date(
        self, blog_id: int
    ) -> Optional[datetime]:
        """블로그의 첫 발행 일시를 조회합니다.

        CrawledPost.published_at 기준으로 가장 이른 발행 일시를 반환합니다.

        Args:
            blog_id: 블로그 ID

        Returns:
            첫 발행 일시, 발행 이력이 없으면 None
        """
        stmt = (
            select(func.min(CrawledPost.published_at))
            .where(CrawledPost.blog_id == blog_id)
            .where(CrawledPost.published_at.is_not(None))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _count_today_publishes(self, blog_id: int) -> int:
        """오늘(KST) 발행한 포스트 수를 조회합니다.

        Args:
            blog_id: 블로그 ID

        Returns:
            오늘 발행한 포스트 수
        """
        today_start_kst = datetime.now(KST).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        stmt = (
            select(func.count(CrawledPost.id))
            .where(CrawledPost.blog_id == blog_id)
            .where(CrawledPost.published_at >= today_start_kst)
            .where(CrawledPost.published_at.is_not(None))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one() or 0

    @staticmethod
    def _calculate_daily_max(
        days_elapsed: int,
        initial_daily_posts: int,
        max_daily_posts: int,
        ramp_rate: float,
    ) -> int:
        """ramp_rate 기반 일일 허용 발행 수를 계산합니다.

        공식: min(initial + floor(days_elapsed * ramp_rate), max_daily_posts)
        days_elapsed가 음수면 0으로 처리하여 initial 값을 반환합니다.

        Args:
            days_elapsed: 첫 발행 이후 경과일 (음수면 0 처리)
            initial_daily_posts: 초기 일일 발행 수
            max_daily_posts: 최대 일일 발행 수
            ramp_rate: 일별 증가율

        Returns:
            일일 허용 발행 수 (최소 1)
        """
        effective_days = max(days_elapsed, 0)
        calculated = initial_daily_posts + math.floor(
            effective_days * ramp_rate
        )
        result = min(calculated, max_daily_posts)
        # 최소 1 보장
        return max(result, 1)
