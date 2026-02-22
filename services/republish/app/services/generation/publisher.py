"""
발행 오케스트레이터

InventoryManager에서 발행 대상 포스트를 조회하고,
워밍업 제약을 확인한 후, 플랫폼 API로 발행합니다.
발행 완료 후 재고 상태를 반환합니다.

설계 문서: growth_stage_strategy_plan.md - Phase D
"""
import logging
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.blog import Blog
from .inventory_manager import InventoryManager
from .warmup_manager import WarmupStatus

logger = logging.getLogger(__name__)


class Publisher:
    """
    발행 오케스트레이터

    InventoryManager에서 발행 대상 포스트를 조회하고,
    워밍업 제약을 확인한 후, 플랫폼 API로 발행합니다.
    발행 완료 후 재고 상태를 반환합니다.

    NOTE: 실제 플랫폼 API 호출은 flows_execute.py의
    _execute_republish_for_blog 패턴을 참조합니다.
    Publisher는 재고 관리와 상태 업데이트만 담당하고,
    플랫폼별 발행 로직은 호출자(flows_execute.py)가 처리합니다.

    Args:
        db: SQLAlchemy 비동기 세션
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.inventory_mgr = InventoryManager(db)

    async def publish_for_blog(
        self,
        blog: Blog,
        warmup_status: WarmupStatus,
    ) -> Dict[str, Any]:
        """
        블로그에 생성된 글 1건을 발행 처리합니다.

        실제 플랫폼 API 호출은 포함하지 않습니다.
        발행 대상 조회 -> 워밍업 한도 체크 -> 재고 업데이트만 수행하고,
        호출자가 반환된 post 정보로 플랫폼 발행을 진행합니다.

        Args:
            blog: 발행 대상 블로그
            warmup_status: 워밍업 상태 (WarmupManager.check_warmup() 결과)

        Returns:
            dict: {
                "success": bool,
                "skipped": bool (optional),
                "message": str,
                "post_id": int (optional, 발행 대상 CrawledPost ID),
                "post_title": str (optional),
                "crawled_post": CrawledPost (optional, 발행 대상 객체),
                "inventory": int (optional, 남은 재고),
                "needs_generation": bool (optional),
            }
        """
        # 1. 워밍업 일일 한도 체크
        if warmup_status.is_active and not warmup_status.can_publish:
            logger.info(
                "[PUBLISHER] 워밍업 일일 한도 초과 | blog=%s | "
                "published=%d/%d",
                blog.name, warmup_status.today_published,
                warmup_status.daily_max,
            )
            return {
                "success": True,
                "skipped": True,
                "message": (
                    f"워밍업 일일 한도 초과 "
                    f"({warmup_status.today_published}/{warmup_status.daily_max})"
                ),
            }

        # 2. 발행 대상 포스트 조회
        post = await self.inventory_mgr.get_post_for_publish(blog.id)
        if post is None:
            logger.info(
                "[PUBLISHER] 발행할 글 없음 (재고 0) | blog=%s",
                blog.name,
            )
            return {
                "success": True,
                "skipped": True,
                "message": "발행할 글 없음 (재고 0)",
            }

        # 3. 발행 대상 정보 반환 (플랫폼 API 호출은 호출자가 진행)
        # 호출자가 플랫폼 발행 성공 후 complete_publish()를 호출해야 함
        logger.info(
            "[PUBLISHER] 발행 대상 준비 | blog=%s | post_id=%d | "
            "title='%s'",
            blog.name, post.id, post.title[:30],
        )
        return {
            "success": True,
            "post_id": post.id,
            "post_title": post.title,
            "crawled_post": post,
            "message": f"발행 대상: {post.title[:30]}",
        }

    async def complete_publish(
        self,
        blog_id: int,
        crawled_post_id: int,
        published_url: str = None,
    ) -> Dict[str, Any]:
        """
        발행 완료 처리 (플랫폼 API 성공 후 호출).

        CrawledPost를 발행 완료로 표시하고,
        재고를 확인하여 생성 필요 여부를 반환합니다.

        Args:
            blog_id: 블로그 ID
            crawled_post_id: 발행된 CrawledPost ID
            published_url: 발행된 URL (선택)

        Returns:
            dict: {"inventory": int, "needs_generation": bool}
        """
        publish_result = await self.inventory_mgr.on_publish_complete(
            blog_id=blog_id,
            crawled_post_id=crawled_post_id,
        )
        logger.info(
            "[PUBLISHER] 발행 완료 처리 | blog_id=%d | post_id=%d | "
            "재고=%d | 생성필요=%s",
            blog_id, crawled_post_id,
            publish_result.inventory_check.current_inventory,
            publish_result.inventory_check.needs_generation,
        )
        return {
            "inventory": publish_result.inventory_check.current_inventory,
            "needs_generation": publish_result.inventory_check.needs_generation,
        }
