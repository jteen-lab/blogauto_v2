"""
재고 관리 서비스 (발행-생성 인터페이스)

발행 모듈과 생성 모듈 사이의 연결 고리.
발행 후 CrawledPost 상태를 업데이트하고,
재고 수준을 확인하여 생성 필요 여부를 판단합니다.

워크플로우:
1. get_post_for_publish() → 발행 대상 글 조회 (FIFO)
2. mark_as_published() → 발행 완료 처리 (published_at 설정)
3. on_publish_complete() → 재고 확인 콜백 (InventoryCheckResult 반환)

설계 문서: generation_module_workplan.md - Phase 6
"""
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.crawled_post import CrawledPost
from .inventory_trigger import InventoryTrigger, InventoryCheckResult

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """발행 후 재고 확인 결과"""
    blog_id: int
    crawled_post_id: Optional[int]
    published_at: datetime
    inventory_check: InventoryCheckResult


class InventoryManager:
    """
    크롤링 포스트 재고 관리

    발행 모듈과 생성 모듈 사이의 인터페이스.
    생성된 글의 발행 상태를 관리하고,
    발행 후 재고를 확인하여 생성 필요 여부를 알려줍니다.

    생성 트리거 자체는 수행하지 않습니다.
    반환된 InventoryCheckResult를 보고 호출자가 판단합니다.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.inventory_trigger = InventoryTrigger(db)

    async def get_post_for_publish(
        self,
        blog_id: int,
        generation_history_id: Optional[int] = None,
    ) -> Optional[CrawledPost]:
        """
        발행할 포스트 1개 가져오기 (FIFO)

        source='generated'이고 아직 발행되지 않은
        가장 오래된 글을 반환합니다.

        Args:
            blog_id: 블로그 ID
            generation_history_id: 특정 생성 이력의 글 조회 (선택)

        Returns:
            발행 가능한 CrawledPost 또는 None
        """
        conditions = [
            CrawledPost.blog_id == blog_id,
            CrawledPost.source == "generated",
            CrawledPost.published_at.is_(None),
        ]

        if generation_history_id:
            conditions.append(
                CrawledPost.generation_history_id == generation_history_id
            )

        query = (
            select(CrawledPost)
            .where(*conditions)
            .order_by(CrawledPost.created_at.asc())
            .limit(1)
        )

        result = await self.db.execute(query)
        post = result.scalar_one_or_none()

        if post:
            logger.info(
                f"[INVENTORY_MGR] 발행 대상 조회 | "
                f"blog_id={blog_id} | post_id={post.id} | "
                f"title='{post.title[:30]}'"
            )
        else:
            logger.info(
                f"[INVENTORY_MGR] 발행 대상 없음 | "
                f"blog_id={blog_id}"
            )

        return post

    async def mark_as_published(
        self,
        crawled_post_id: int,
        published_url: Optional[str] = None,
        platform_post_id: Optional[str] = None,
    ) -> CrawledPost:
        """
        발행 완료 처리 (재고 -1 효과)

        CrawledPost의 published_at을 설정하여
        재고 카운팅에서 제외되도록 합니다.

        Args:
            crawled_post_id: 발행 완료된 CrawledPost ID
            published_url: 발행된 URL (선택)
            platform_post_id: 플랫폼 포스트 ID (선택)

        Returns:
            업데이트된 CrawledPost

        Raises:
            ValueError: CrawledPost를 찾을 수 없을 때
        """
        post = await self.db.get(CrawledPost, crawled_post_id)
        if not post:
            raise ValueError(
                f"CrawledPost를 찾을 수 없습니다: id={crawled_post_id}"
            )

        post.mark_published(published_url, platform_post_id=platform_post_id)
        await self.db.flush()

        logger.info(
            f"[INVENTORY_MGR] 발행 완료 처리 | "
            f"post_id={post.id} | blog_id={post.blog_id} | "
            f"title='{post.title[:30]}'"
        )

        return post

    async def on_publish_complete(
        self,
        blog_id: int,
        crawled_post_id: Optional[int] = None,
        module_settings: Optional[dict] = None,
    ) -> PublishResult:
        """
        발행 완료 후 콜백

        발행 모듈이 발행 성공 후 호출합니다.
        CrawledPost를 발행 처리하고 현재 재고 상태를 반환합니다.

        생성 자체는 수행하지 않습니다.
        반환된 InventoryCheckResult.needs_generation을 보고
        호출자가 생성 트리거 여부를 결정합니다.

        Args:
            blog_id: 블로그 ID
            crawled_post_id: 발행된 CrawledPost ID (선택)
            module_settings: 모듈 설정 (재고 임계값 커스텀용)

        Returns:
            PublishResult: 발행 처리 + 재고 확인 결과
        """
        now = datetime.now()

        # 1. CrawledPost 발행 처리 (ID가 주어진 경우)
        if crawled_post_id:
            await self.mark_as_published(crawled_post_id)

        # 2. 재고 확인
        inventory_check = await self.inventory_trigger.check_inventory(
            blog_id, module_settings=module_settings
        )

        logger.info(
            f"[INVENTORY_MGR] 발행 후 재고 확인 | "
            f"blog_id={blog_id} | "
            f"재고={inventory_check.current_inventory} | "
            f"기준={inventory_check.threshold} | "
            f"생성필요={'예' if inventory_check.needs_generation else '아니오'}"
        )

        return PublishResult(
            blog_id=blog_id,
            crawled_post_id=crawled_post_id,
            published_at=now,
            inventory_check=inventory_check,
        )

    async def get_inventory_status(
        self,
        blog_id: int,
        module_settings: Optional[dict] = None,
    ) -> InventoryCheckResult:
        """
        현재 재고 상태 조회 (발행 처리 없이)

        대시보드, 모니터링 등에서 사용합니다.

        Args:
            blog_id: 블로그 ID
            module_settings: 모듈 설정

        Returns:
            InventoryCheckResult
        """
        return await self.inventory_trigger.check_inventory(
            blog_id, module_settings=module_settings
        )
