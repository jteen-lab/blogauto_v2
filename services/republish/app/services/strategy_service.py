"""
발행 비중 전략 서비스

Features:
- 블로그별 발행 비중 전략 관리
- 자동/수동 비중 조절
- 누적 포스트 수 기반 자동 비중 변경
- 신규 발행 우선 정책 적용
"""

from typing import Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from ..models.blog_publish_strategy import BlogPublishStrategy
from ..models.blog import Blog
from ..models.user import User
from ..models.post import Post
from ..models.publish_log import PublishLog
from ..core.logger import get_logger

logger = get_logger("strategy_service", "republish.log")


class StrategyService:
    """발행 비중 전략 서비스"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ===========================================
    # 전략 CRUD
    # ===========================================

    async def get_or_create_strategy(
        self,
        user: User,
        blog_id: int
    ) -> BlogPublishStrategy:
        """전략 조회 또는 생성 (블로그당 1개)"""
        # 권한 확인
        blog_query = select(Blog).where(
            and_(Blog.id == blog_id, Blog.user_id == user.id)
        )
        blog_result = await self.db.execute(blog_query)
        blog = blog_result.scalar_one_or_none()

        if not blog:
            raise ValueError(f"블로그를 찾을 수 없습니다: {blog_id}")

        # 기존 전략 조회
        strategy_query = select(BlogPublishStrategy).where(
            BlogPublishStrategy.blog_id == blog_id
        )
        result = await self.db.execute(strategy_query)
        strategy = result.scalar_one_or_none()

        if strategy:
            return strategy

        # 새 전략 생성
        try:
            strategy = BlogPublishStrategy(blog_id=blog_id)
            self.db.add(strategy)
            await self.db.commit()
            await self.db.refresh(strategy)

            logger.info(f"발행 전략 생성 성공 | 블로그ID={blog_id} | 사용자={user.id}")
            return strategy

        except Exception as e:
            await self.db.rollback()
            logger.error(f"발행 전략 생성 실패 | 블로그ID={blog_id} | 사용자={user.id} | 오류={e}")
            raise

    async def update_strategy(
        self,
        user: User,
        blog_id: int,
        update_data: Dict[str, Any]
    ) -> BlogPublishStrategy:
        """전략 수정"""
        try:
            strategy = await self.get_or_create_strategy(user, blog_id)

            # 업데이트
            for key, value in update_data.items():
                if hasattr(strategy, key):
                    setattr(strategy, key, value)

            # 수동 모드에서 비중 합계 검증
            if strategy.strategy_mode == "manual":
                total = strategy.publish_weight + strategy.republish_weight
                if total != 100:
                    raise ValueError(f"비중 합계는 100이어야 합니다. 현재: {total}")

            await self.db.commit()
            await self.db.refresh(strategy)

            logger.info(f"발행 전략 수정 성공 | 블로그ID={blog_id} | 사용자={user.id}")
            return strategy

        except Exception as e:
            await self.db.rollback()
            logger.error(f"발행 전략 수정 실패 | 블로그ID={blog_id} | 사용자={user.id} | 오류={e}")
            raise

    # ===========================================
    # 비중 계산 및 결정
    # ===========================================

    async def calculate_weights(
        self,
        user: User,
        blog_id: int
    ) -> Dict[str, Any]:
        """현재 비중 계산"""
        try:
            strategy = await self.get_or_create_strategy(user, blog_id)

            # 블로그 총 포스트 수 조회
            post_count_query = select(func.count(Post.id)).where(
                and_(
                    Post.blog_id == blog_id,
                    Post.is_deleted == False,
                    Post.status.in_(["published", "republished"])
                )
            )
            post_count_result = await self.db.execute(post_count_query)
            total_posts = post_count_result.scalar() or 0

            # 비중 계산
            weights = strategy.get_weights_by_post_count(total_posts)

            # 오늘 신규 발행 수 조회
            today_publish_count = await self._get_today_publish_count(blog_id)

            # 재발행 보류 여부
            should_skip_republish = strategy.should_skip_republish_today(today_publish_count)

            result = {
                "strategy_mode": strategy.strategy_mode,
                "total_posts": total_posts,
                "today_publish_count": today_publish_count,
                "publish_weight": weights["publish"],
                "republish_weight": weights["republish"],
                "should_skip_republish": should_skip_republish,
                "skip_reason": (
                    f"오늘 신규 발행 {today_publish_count}회 >= 기준 {strategy.min_daily_publish_for_skip}회"
                    if should_skip_republish else None
                )
            }

            logger.info(
                f"[STRATEGY] Blog {blog_id}: publish={weights['publish']}%, "
                f"republish={weights['republish']}% "
                f"({strategy.strategy_mode}: {total_posts} posts)"
            )

            return result

        except Exception as e:
            logger.error(f"비중 계산 실패 | 블로그ID={blog_id} | 사용자={user.id} | 오류={e}")
            raise

    async def should_publish_or_republish(
        self,
        user: User,
        blog_id: int
    ) -> Tuple[str, str]:
        """발행 vs 재발행 결정"""
        try:
            weights_data = await self.calculate_weights(user, blog_id)

            # 재발행 보류 체크
            if weights_data["should_skip_republish"]:
                logger.info(
                    f"[STRATEGY] Blog {blog_id}: republish skipped - {weights_data['skip_reason']}"
                )
                return "publish", weights_data["skip_reason"]

            # 가중치 기반 랜덤 선택
            import random
            rand = random.randint(1, 100)

            publish_weight = weights_data["publish_weight"]

            if rand <= publish_weight:
                return "publish", f"가중치 결정: {rand} <= {publish_weight}% (신규 발행)"
            else:
                return "republish", f"가중치 결정: {rand} > {publish_weight}% (재발행)"

        except Exception as e:
            logger.error(f"발행 유형 결정 실패 | 블로그ID={blog_id} | 사용자={user.id} | 오류={e}")
            # 기본값: 신규 발행
            return "publish", "오류로 인한 기본값"

    async def _get_today_publish_count(self, blog_id: int) -> int:
        """오늘 신규 발행 수 조회"""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        query = select(func.count(PublishLog.id)).where(
            and_(
                PublishLog.blog_id == blog_id,
                PublishLog.action == "publish",  # 신규 발행만
                PublishLog.status == "success",
                PublishLog.created_at >= today_start,
                PublishLog.created_at < today_end
            )
        )

        result = await self.db.execute(query)
        return result.scalar() or 0

    # ===========================================
    # 통계 및 분석
    # ===========================================

    async def get_strategy_stats(
        self,
        user: User,
        blog_id: int,
        days: int = 7
    ) -> Dict[str, Any]:
        """전략 통계 조회"""
        try:
            strategy = await self.get_or_create_strategy(user, blog_id)

            # 기간 설정
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # 발행 통계
            publish_query = select(func.count(PublishLog.id)).where(
                and_(
                    PublishLog.blog_id == blog_id,
                    PublishLog.action == "publish",
                    PublishLog.status == "success",
                    PublishLog.created_at >= start_date
                )
            )

            republish_query = select(func.count(PublishLog.id)).where(
                and_(
                    PublishLog.blog_id == blog_id,
                    PublishLog.action == "republish",
                    PublishLog.status == "success",
                    PublishLog.created_at >= start_date
                )
            )

            publish_result = await self.db.execute(publish_query)
            republish_result = await self.db.execute(republish_query)

            publish_count = publish_result.scalar() or 0
            republish_count = republish_result.scalar() or 0
            total_count = publish_count + republish_count

            # 실제 비중 계산
            actual_publish_percent = (
                (publish_count / total_count * 100) if total_count > 0 else 0
            )
            actual_republish_percent = (
                (republish_count / total_count * 100) if total_count > 0 else 0
            )

            # 현재 전략 비중
            weights_data = await self.calculate_weights(user, blog_id)

            return {
                "period_days": days,
                "strategy_mode": strategy.strategy_mode,
                "target_publish_weight": weights_data["publish_weight"],
                "target_republish_weight": weights_data["republish_weight"],
                "actual_publish_count": publish_count,
                "actual_republish_count": republish_count,
                "actual_total_count": total_count,
                "actual_publish_percent": round(actual_publish_percent, 1),
                "actual_republish_percent": round(actual_republish_percent, 1),
                "variance_publish": round(
                    actual_publish_percent - weights_data["publish_weight"], 1
                ),
                "variance_republish": round(
                    actual_republish_percent - weights_data["republish_weight"], 1
                )
            }

        except Exception as e:
            logger.error(f"전략 통계 조회 실패 | 블로그ID={blog_id} | 사용자={user.id} | 오류={e}")
            raise