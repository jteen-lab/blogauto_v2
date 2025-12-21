"""
플랫폼별 제한 관리 서비스

Features:
- 플랫폼별 최소 간격 및 일일 한도 관리
- Blogger 보수적 접근 (WordPress 대비 2-3배)
- 프로파일 검증 및 경고 메시지 반환
- 일일 쿼터 추적 및 제한
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from ..models.blog import Blog, BlogPlatform
from ..models.publish_log import PublishLog
from ..core.logger import get_logger

logger = get_logger("platform_limiter", "republish.log")

# 플랫폼별 제한 설정
PLATFORM_LIMITS = {
    "wordpress": {
        "min_interval_minutes": 5,
        "max_daily_posts": 100,
        "recommended_interval": 10,
        "rate_limit_per_minute": 10,
        "warning_threshold_percent": 80,
        "hard_stop_percent": 90,
    },
    "blogger": {
        "min_interval_minutes": 15,      # 보수적
        "max_daily_posts": 50,           # 쿼터의 50% (안전)
        "recommended_interval": 30,      # 권장
        "rate_limit_per_minute": 5,
        "account_daily_limit": 100,      # 계정 전체
        "warning_threshold_percent": 60,  # 경고 시작
        "hard_stop_percent": 80,         # 강제 중지
    }
}


class PlatformLimiter:
    """플랫폼별 제한 관리"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_profile(
        self,
        profile: Dict[str, Any],
        platform: str
    ) -> List[str]:
        """
        프로파일 검증 - 경고 메시지 반환

        Args:
            profile: 프로파일 설정 딕셔너리
            platform: 플랫폼명 (wordpress/blogger)

        Returns:
            경고 메시지 리스트
        """
        warnings = []
        limits = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS["wordpress"])

        # 간격 모드별 검증
        if profile.get("interval_mode") == "manual":
            interval = profile.get("manual_interval_minutes", 60)
        else:
            daily_count = profile.get("auto_daily_count", 1)
            interval = max(5, int(1440 / daily_count)) if daily_count > 0 else 60

        # 최소 간격 검증
        min_interval = limits["min_interval_minutes"]
        if interval < min_interval:
            warnings.append(
                f"{platform.title()} 플랫폼 최소 간격은 {min_interval}분입니다. "
                f"현재 설정: {interval}분"
            )

        # 권장 간격 대비 검증
        recommended = limits["recommended_interval"]
        if interval < recommended:
            warnings.append(
                f"{platform.title()} 플랫폼 권장 간격은 {recommended}분입니다. "
                f"현재 설정이 빠를 수 있습니다: {interval}분"
            )

        # Blogger 특별 경고
        if platform == "blogger":
            if interval < 30:
                warnings.append(
                    "⚠️ Blogger는 엄격한 API 제한이 있습니다. "
                    "30분 이상 간격을 권장합니다."
                )

            if profile.get("auto_daily_count", 1) > 20:
                warnings.append(
                    "⚠️ Blogger 일일 20회 이상은 계정 제재 위험이 있습니다."
                )

        return warnings

    async def check_daily_quota(self, blog_id: int, platform: str) -> Tuple[bool, str]:
        """
        일일 쿼터 확인

        Args:
            blog_id: 블로그 ID
            platform: 플랫폼명

        Returns:
            (가능여부, 메시지)
        """
        limits = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS["wordpress"])
        max_daily = limits["max_daily_posts"]

        # 오늘 발행 횟수 조회
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        query = select(func.count(PublishLog.id)).where(
            and_(
                PublishLog.blog_id == blog_id,
                PublishLog.platform == platform,
                PublishLog.status == "success",
                PublishLog.created_at >= today_start,
                PublishLog.created_at < today_end
            )
        )

        result = await self.db.execute(query)
        today_count = result.scalar() or 0

        # 사용률 계산
        usage_percent = (today_count / max_daily) * 100

        # 제한 확인
        warning_threshold = limits["warning_threshold_percent"]
        hard_stop_threshold = limits["hard_stop_percent"]

        if usage_percent >= hard_stop_threshold:
            return False, (
                f"{platform.title()} 일일 한도 {hard_stop_threshold}% 도달 "
                f"({today_count}/{max_daily}). 발행이 차단됩니다."
            )

        if usage_percent >= warning_threshold:
            return True, (
                f"⚠️ {platform.title()} 일일 한도 {usage_percent:.1f}% 사용 중 "
                f"({today_count}/{max_daily}). 주의가 필요합니다."
            )

        return True, f"일일 쿼터 OK: {today_count}/{max_daily} ({usage_percent:.1f}%)"

    async def can_publish(self, blog_id: int, platform: str) -> Tuple[bool, str]:
        """
        발행 가능 여부 종합 확인

        Args:
            blog_id: 블로그 ID
            platform: 플랫폼명

        Returns:
            (가능여부, 메시지)
        """
        # 일일 쿼터 확인
        quota_ok, quota_msg = await self.check_daily_quota(blog_id, platform)

        if not quota_ok:
            logger.warning(f"[LIMIT] Blog {blog_id}: {quota_msg}")
            return False, quota_msg

        # 경고가 있어도 발행은 가능
        if quota_msg.startswith("⚠️"):
            logger.warning(f"[LIMIT] Blog {blog_id}: {quota_msg}")

        return True, quota_msg

    async def get_platform_stats(self, blog_id: int, platform: str) -> Dict[str, Any]:
        """
        플랫폼별 통계 조회

        Args:
            blog_id: 블로그 ID
            platform: 플랫폼명

        Returns:
            통계 딕셔너리
        """
        limits = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS["wordpress"])

        # 오늘 통계
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # 성공/실패 카운트
        success_query = select(func.count(PublishLog.id)).where(
            and_(
                PublishLog.blog_id == blog_id,
                PublishLog.platform == platform,
                PublishLog.status == "success",
                PublishLog.created_at >= today_start,
                PublishLog.created_at < today_end
            )
        )

        failed_query = select(func.count(PublishLog.id)).where(
            and_(
                PublishLog.blog_id == blog_id,
                PublishLog.platform == platform,
                PublishLog.status == "failed",
                PublishLog.created_at >= today_start,
                PublishLog.created_at < today_end
            )
        )

        success_result = await self.db.execute(success_query)
        failed_result = await self.db.execute(failed_query)

        success_count = success_result.scalar() or 0
        failed_count = failed_result.scalar() or 0
        total_count = success_count + failed_count

        # 사용률 계산
        max_daily = limits["max_daily_posts"]
        usage_percent = (success_count / max_daily) * 100

        # 성공률 계산
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0

        return {
            "platform": platform,
            "today_success": success_count,
            "today_failed": failed_count,
            "today_total": total_count,
            "daily_limit": max_daily,
            "usage_percent": round(usage_percent, 1),
            "success_rate": round(success_rate, 1),
            "min_interval": limits["min_interval_minutes"],
            "recommended_interval": limits["recommended_interval"],
            "warning_threshold": limits["warning_threshold_percent"],
            "hard_stop_threshold": limits["hard_stop_percent"],
        }