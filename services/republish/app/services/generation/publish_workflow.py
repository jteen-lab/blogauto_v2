"""발행 전체 워크플로우 (ON/OFF 모드 공통).

발행 대상 선택 → 플랫폼 발행 → 후처리(재고/상태 업데이트)를
하나의 서비스로 통합하여, Celery ON/OFF 모드에서 동일한 결과를 보장합니다.
"""
import logging
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PublishWorkflow:
    """발행 전체 워크플로우.

    Args:
        db: SQLAlchemy 비동기 세션
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute_publish(
        self,
        blog_id: int,
        post_id: int = 0,
    ) -> Dict[str, Any]:
        """발행 전체 워크플로우 실행.

        1. 발행 대상 선택 (post_id=0이면 자동 선택)
        2. 플랫폼별 발행 (WordPress/Blogger)
        3. complete_publish() 호출 (재고/상태 업데이트)

        Args:
            blog_id: 블로그 ID
            post_id: 발행할 포스트 ID (0이면 자동 선택)

        Returns:
            dict: 발행 결과
        """
        from app.models.blog import Blog
        from app.models.crawled_post import CrawledPost
        from app.services.generation.inventory_manager import InventoryManager
        from app.services.generation.publisher import Publisher
        from app.services.publishing.publisher_pipeline import PublisherPipeline

        blog = await self.db.get(Blog, blog_id)
        if not blog:
            return {"success": False, "message": f"Blog({blog_id}) 없음"}

        # 1. 발행 대상 선택
        if post_id == 0:
            inventory_mgr = InventoryManager(self.db)
            post = await inventory_mgr.get_post_for_publish(blog_id)
            if not post:
                return {
                    "success": True,
                    "skipped": True,
                    "message": "발행할 글 없음 (재고 0)",
                }
        else:
            post = await self.db.get(CrawledPost, post_id)
            if not post:
                return {
                    "success": False,
                    "message": f"Post({post_id}) 없음",
                }

        logger.info(
            f"[PUBLISH_WF] 발행 대상 | blog_id={blog_id} | "
            f"post_id={post.id} | title='{post.title[:30]}'"
        )

        # 2. 플랫폼 발행
        credential = None
        if blog.google_credential_id:
            from app.models.google_credential import GoogleCredential
            credential = await self.db.get(
                GoogleCredential, blog.google_credential_id,
            )

        pipeline = PublisherPipeline(self.db)
        pub_result = await pipeline.publish_post(
            blog, post, credential=credential,
        )

        if not pub_result.success:
            logger.warning(
                f"[PUBLISH_WF] 플랫폼 발행 실패 | blog_id={blog_id} | "
                f"error={pub_result.error} | "
                f"retryable={pub_result.retryable}"
            )
            return {
                "success": False,
                "message": pub_result.error or "플랫폼 발행 실패",
                "retryable": pub_result.retryable,
            }

        # 3. 후처리 (재고/상태 업데이트)
        publisher = Publisher(self.db)
        complete_info = await publisher.complete_publish(
            blog_id, post.id,
            published_url=pub_result.published_url,
        )

        logger.info(
            f"[PUBLISH_WF] 발행 완료 | blog_id={blog_id} | "
            f"url={pub_result.published_url} | "
            f"재고={complete_info['inventory']}"
        )

        return {
            "success": True,
            "published_url": pub_result.published_url,
            "platform_post_id": pub_result.platform_post_id,
            "image_uploaded": pub_result.image_uploaded,
            "post_id": post.id,
            "post_title": post.title,
            "inventory": complete_info["inventory"],
            "needs_generation": complete_info["needs_generation"],
        }

    async def execute_republish(
        self,
        blog_id: int,
    ) -> Dict[str, Any]:
        """재발행 전체 워크플로우 실행.

        Args:
            blog_id: 블로그 ID

        Returns:
            dict: 재발행 결과
        """
        from app.models.blog import Blog, BlogPlatform

        blog = await self.db.get(Blog, blog_id)
        if not blog:
            return {"success": False, "message": f"Blog({blog_id}) 없음"}

        # 리뉴얼 게이트: 리뉴얼 사용(enabled) + 주기 도래 글이 있으면 리뉴얼,
        # 없거나 비활성이면 아래 기존 date-bump 재발행으로 진행.
        cfg = blog.renewal_config or {}
        if cfg.get("enabled"):
            # P4 저장 정리: 유예 경과 글 본문/이미지 삭제(메타 보존). 비차단.
            try:
                from app.services.renewal.renewal_cleanup import (
                    cleanup_purged_posts,
                )
                await cleanup_purged_posts(self.db, blog, cfg)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[REPUBLISH] 저장정리 오류(무시) | blog=%s | %s",
                    blog.name, exc,
                )
            due = await self._find_due_renewable_post(blog, cfg)
            if due:
                from app.services.renewal.renewal_service import RenewalService
                # #4 미매칭 글이면 리뉴얼 직전 자동 정식제목 등록 시도
                # (카테고리 주기·제목 재조합이 동작하도록). 실패해도 비차단.
                if not due.matched_main_title_id:
                    try:
                        from app.services.auto_match_service import (
                            AutoMatchService,
                        )
                        await AutoMatchService(self.db).match_single_post(due)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "[REPUBLISH] 단일매칭 오류(무시) | post=%s | %s",
                            due.id, exc,
                        )
                logger.info(
                    "[REPUBLISH] 리뉴얼 대상 | blog=%s | post=%s",
                    blog.name, due.id,
                )
                res = await RenewalService(
                    self.db, blog.user_id,
                ).renew_post(blog, due, dry_run=False)
                if res.get("success"):
                    res["action"] = "renewed"
                    return res
                logger.warning(
                    "[REPUBLISH] 리뉴얼 실패 → date-bump 폴백 | %s",
                    res.get("error"),
                )

        if blog.platform == BlogPlatform.WORDPRESS:
            from app.services.wordpress_service import (
                WordPressRepublishService,
            )
            service = WordPressRepublishService()
            return await service.republish(blog)

        elif blog.platform == BlogPlatform.BLOGGER:
            # 발행과 동일하게 레거시 oauth(blog.oauth_token_encrypted) 또는
            # credential 어느 쪽이든 사용. google_credential_id 없이도 진행하고,
            # 토큰 해석 실패 시에만 republish 내부에서 인증 오류를 반환한다.
            from app.services.blogger_service import (
                BloggerRepublishService,
            )
            from app.models.google_credential import GoogleCredential
            credential = None
            if blog.google_credential_id:
                credential = await self.db.get(
                    GoogleCredential, blog.google_credential_id,
                )
            async with BloggerRepublishService() as svc:
                return await svc.republish(blog, credential)

        return {
            "success": False,
            "message": f"지원하지 않는 플랫폼: {blog.platform}",
        }

    async def _find_due_renewable_post(self, blog, cfg: Dict[str, Any]):
        """리뉴얼 주기가 도래한 가장 오래된 리뉴얼 가능 글을 찾는다.

        나이 기준 = COALESCE(last_renewed_at, published_at)(우리 DB).
        주기 = category_periods[subtopic_id] ?? default_period_months(월).
        도래 글 없으면 None.
        """
        from datetime import datetime, timezone

        from dateutil.relativedelta import relativedelta
        from sqlalchemy import func, select

        from app.models.crawled_post import CrawledPost
        from app.models.title import MainTitle

        default_months = int(cfg.get("default_period_months", 6) or 6)
        cat_periods = cfg.get("category_periods", {}) or {}
        now = datetime.now(timezone.utc)

        age_key = func.coalesce(
            CrawledPost.last_renewed_at, CrawledPost.published_at,
        )
        rows = (await self.db.execute(
            select(CrawledPost)
            .where(
                CrawledPost.blog_id == blog.id,
                CrawledPost.source == "generated",
                CrawledPost.published_at.isnot(None),
                CrawledPost.platform_post_id.isnot(None),
                CrawledPost.generation_history_id.isnot(None),
            )
            .order_by(age_key.asc())
            .limit(50)
        )).scalars().all()

        for post in rows:
            ref = post.last_renewed_at or post.published_at
            if not ref:
                continue
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            period = default_months
            if post.matched_main_title_id and cat_periods:
                mt = await self.db.get(MainTitle, post.matched_main_title_id)
                sub = getattr(mt, "subtopic_id", None) if mt else None
                if sub is not None:
                    period = int(cat_periods.get(str(sub), default_months))
            if ref <= now - relativedelta(months=period):
                return post
        return None
