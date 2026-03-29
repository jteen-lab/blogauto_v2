"""
발행 포스트 동기화 서비스

블로그 플랫폼의 실제 발행 포스트와 DB의 CrawledPost를 비교하여
블로그에서 삭제된 포스트를 자동으로 정리합니다.
"""
import json
import logging
from pathlib import Path
from typing import Optional, Set
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.blog import Blog
from ..models.crawled_post import CrawledPost
from ..models.title import MainTitle
from ..models.generation_history import GenerationHistory
from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """동기화 결과"""
    success: bool
    platform_post_count: int = 0
    db_published_count: int = 0
    deleted_posts: int = 0
    deleted_images: int = 0
    reset_titles: int = 0
    error: Optional[str] = None


class PostSyncService:
    """
    발행 포스트 동기화 서비스

    블로그 플랫폼에서 현재 발행된 포스트 URL 목록을 가져와
    DB의 발행완료 CrawledPost와 비교합니다.
    블로그에서 삭제된 포스트는 DB에서도 정리합니다.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_published_posts(
        self,
        blog: Blog,
        platform_urls: Set[str],
    ) -> SyncResult:
        """
        플랫폼의 발행 포스트와 DB를 동기화

        Args:
            blog: 대상 블로그
            platform_urls: 플랫폼에서 가져온 현재 발행 포스트 URL 목록

        Returns:
            SyncResult: 동기화 결과
        """
        try:
            # 1. DB에서 이 블로그의 발행완료 CrawledPost 조회
            result = await self.db.execute(
                select(CrawledPost).where(
                    CrawledPost.blog_id == blog.id,
                    CrawledPost.published_at.isnot(None),
                )
            )
            db_published = list(result.scalars().all())

            # 2. 블로그에서 삭제된 포스트 식별
            orphaned_posts = self._find_orphaned_posts(
                db_published, platform_urls
            )

            if not orphaned_posts:
                logger.info(
                    f"[SYNC] 삭제된 포스트 없음 | blog_id={blog.id} | "
                    f"플랫폼={len(platform_urls)}개 | DB={len(db_published)}개"
                )
                return SyncResult(
                    success=True,
                    platform_post_count=len(platform_urls),
                    db_published_count=len(db_published),
                )

            # 3. 삭제된 포스트 정리
            deleted_images = 0
            reset_title_ids: set[int] = set()

            for post in orphaned_posts:
                deleted_images += self._delete_image_file(post.image_url)
                deleted_images += await self._cleanup_generation_images(
                    post.generation_history_id
                )

                if post.matched_main_title_id:
                    reset_title_ids.add(post.matched_main_title_id)

                await self.db.delete(post)

            await self.db.flush()

            # 4. 연결된 MainTitle 상태 리셋
            reset_count = await self._reset_orphaned_titles(reset_title_ids)

            await self.db.commit()

            logger.info(
                f"[SYNC] 동기화 완료 | blog_id={blog.id} | "
                f"삭제={len(orphaned_posts)}개 | 이미지={deleted_images}개 | "
                f"리셋={reset_count}개"
            )

            return SyncResult(
                success=True,
                platform_post_count=len(platform_urls),
                db_published_count=len(db_published),
                deleted_posts=len(orphaned_posts),
                deleted_images=deleted_images,
                reset_titles=reset_count,
            )

        except Exception as e:
            logger.error(f"[SYNC] 동기화 실패 | blog_id={blog.id} | {e}")
            return SyncResult(success=False, error=str(e))

    @staticmethod
    def _find_orphaned_posts(
        db_published: list[CrawledPost],
        platform_urls: Set[str],
    ) -> list[CrawledPost]:
        """
        플랫폼에서 삭제된 포스트 식별

        Args:
            db_published: DB의 발행완료 CrawledPost 목록
            platform_urls: 플랫폼의 현재 URL 목록 (정규화됨)

        Returns:
            플랫폼에서 삭제된 CrawledPost 목록
        """
        orphaned = []
        for post in db_published:
            post_url = (post.url or "").rstrip("/")
            if not post_url:
                continue

            if post_url not in platform_urls:
                orphaned.append(post)

        return orphaned

    async def _cleanup_generation_images(
        self,
        generation_history_id: int | None,
    ) -> int:
        """GenerationHistory의 이미지 파일 삭제"""
        if not generation_history_id:
            return 0

        deleted = 0
        gh_result = await self.db.execute(
            select(GenerationHistory)
            .where(GenerationHistory.id == generation_history_id)
        )
        gen_history = gh_result.scalar_one_or_none()
        if gen_history:
            deleted += self._delete_image_file(gen_history.image_url)
            deleted += self._delete_section_images(
                gen_history.section_images
            )
        return deleted

    async def _reset_orphaned_titles(
        self,
        title_ids: set[int],
    ) -> int:
        """
        다른 발행 포스트가 없는 MainTitle 상태 리셋

        생성(source="generated")되어 발행된 포스트만 확인합니다.
        크롤링 포스트(source="crawled")는 유사도 매칭으로
        matched_main_title_id가 설정되므로 제외해야 합니다.

        Args:
            title_ids: 리셋 대상 MainTitle ID 집합

        Returns:
            리셋된 제목 수
        """
        reset_count = 0
        for title_id in title_ids:
            remaining = await self.db.execute(
                select(CrawledPost.id).where(
                    CrawledPost.matched_main_title_id == title_id,
                    CrawledPost.published_at.isnot(None),
                    CrawledPost.source == "generated",
                )
            )
            if remaining.scalar_one_or_none() is None:
                title = await self.db.get(MainTitle, title_id)
                if title and title.status != "available":
                    logger.info(
                        f"[SYNC] 제목 리셋: id={title_id} | "
                        f"'{title.status}' → 'available'"
                    )
                    title.status = "available"
                    title.use_count = 0
                    title.last_used_at = None
                    reset_count += 1
        return reset_count

    @staticmethod
    def _delete_image_file(image_url: str | None) -> int:
        """
        이미지 URL에서 파일 삭제

        Args:
            image_url: 이미지 URL 경로

        Returns:
            삭제된 파일 수 (0 또는 1)
        """
        if not image_url:
            return 0
        try:
            filename = image_url.split("/")[-1]
            path = Path(settings.image_storage_dir) / filename
            if path.exists():
                path.unlink()
                logger.info(f"[SYNC] 이미지 삭제: {path}")
                return 1
        except Exception as e:
            logger.warning(f"[SYNC] 이미지 삭제 실패: {e}")
        return 0

    @staticmethod
    def _delete_section_images(section_images_json: str | None) -> int:
        """
        섹션 이미지 JSON에서 파일들 삭제

        Args:
            section_images_json: 섹션 이미지 JSON 문자열

        Returns:
            삭제된 파일 수
        """
        if not section_images_json:
            return 0
        deleted = 0
        try:
            items = json.loads(section_images_json)
            if not isinstance(items, list):
                return 0
            for item in items:
                url = item.get("image_url") if isinstance(item, dict) else None
                if url:
                    deleted += PostSyncService._delete_image_file(url)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"[SYNC] 섹션 이미지 삭제 실패: {e}")
        return deleted
