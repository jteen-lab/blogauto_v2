"""
그룹 서비스 (Facade)

분할된 서비스들을 통합하여 기존 API 호환성 유지:
- GroupCoreService: CRUD 작업
- GroupBlogService: 블로그 관리
- GroupSlotService: 슬롯 계산
"""

from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, ProfileGroup, GroupProfileLink, BlogGroupLink, Blog
from ..schemas.blogger_slot import AddBlogResult
from ..core.logger import get_logger
from .group_core_service import GroupCoreService
from .group_blog_service import GroupBlogService
from .group_slot_service import GroupSlotService

logger = get_logger("group_service", "app.log")


class GroupService:
    """그룹 관리 서비스 (Facade)"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._core = GroupCoreService(db)
        self._blog = GroupBlogService(db)
        self._slot = GroupSlotService(db)

    async def get_user_groups(self, user: User) -> List[ProfileGroup]:
        return await self._core.get_user_groups(user)

    async def get_group_by_id(
        self, user: User, group_id: int
    ) -> Optional[ProfileGroup]:
        return await self._core.get_group_by_id(user, group_id)

    async def create_group(self, user: User, data: Dict[str, Any]) -> ProfileGroup:
        blog_ids = data.get("blog_ids", [])

        group = await self._core.create_group_base(user, data.copy())

        blog_results = {"success_count": 0, "failed_blogs": [], "warnings": []}
        if blog_ids:
            await self.db.refresh(group, ["profile_links"])
            blog_results = await self._blog.add_blogs_with_validation(
                user, group, blog_ids
            )

        await self.db.commit()
        await self.db.refresh(group)
        await self.db.refresh(group, ["profile_links", "blog_links"])

        profile_ids = data.get("profile_ids", [])
        total_requested = len(blog_ids)
        success_count = blog_results["success_count"]
        failed_count = len(blog_results["failed_blogs"])

        log_message = f"[GROUP] 생성 완료 | user={user.id} | group={group.id} | profiles={len(profile_ids)} | blogs={success_count}/{total_requested} 성공"
        if blog_results["warnings"]:
            log_message += f" | 경고: {'; '.join(blog_results['warnings'])}"
        if blog_results["failed_blogs"]:
            log_message += f" | 실패: {failed_count}개"

        logger.info(log_message)

        for failed in blog_results["failed_blogs"]:
            logger.warning(f"[GROUP] 블로그 추가 실패: {failed}")

        return group

    async def update_group(
        self, user: User, group_id: int, data: Dict[str, Any]
    ) -> ProfileGroup:
        group = await self.get_group_by_id(user, group_id)
        if not group:
            raise ValueError(f"그룹을 찾을 수 없습니다: {group_id}")

        profile_ids = data.get("profile_ids", None)
        blog_ids = data.get("blog_ids", None)

        await self._core.update_group_base(user, group_id, data.copy())

        blog_results = {"success_count": 0, "failed_blogs": [], "warnings": []}
        if blog_ids is not None:
            await self._blog.release_existing_blogger_slots(group_id)
            await self.db.execute(
                delete(BlogGroupLink).where(BlogGroupLink.group_id == group_id)
            )
            await self.db.commit()

            if blog_ids:
                await self.db.refresh(group, ["profile_links"])
                blog_results = await self._blog.add_blogs_with_validation(
                    user, group, blog_ids
                )

        await self.db.commit()
        await self.db.refresh(group)

        blog_log = "변경없음"
        if blog_ids is not None:
            total_requested = len(blog_ids)
            success_count = blog_results["success_count"]
            failed_count = len(blog_results["failed_blogs"])
            blog_log = f"{success_count}/{total_requested} 성공"

            if blog_results["warnings"]:
                blog_log += f" (경고: {len(blog_results['warnings'])}개)"
            if failed_count > 0:
                blog_log += f" (실패: {failed_count}개)"

        logger.info(
            f"[GROUP] 수정 완료 | group={group_id} | profiles={len(profile_ids) if profile_ids else '변경없음'} | blogs={blog_log}"
        )

        for failed in blog_results["failed_blogs"]:
            logger.warning(f"[GROUP] 블로그 수정 실패: {failed}")

        return group

    async def delete_group(self, user: User, group_id: int) -> bool:
        return await self._core.delete_group(user, group_id)

    async def assign_blogs(
        self, user: User, group_id: int, blog_ids: List[int]
    ) -> ProfileGroup:
        return await self._core.assign_blogs_direct(user, group_id, blog_ids)

    async def copy_group(
        self, user: User, group_id: int, new_name: str
    ) -> ProfileGroup:
        return await self._core.copy_group(user, group_id, new_name)

    async def add_blog_with_slot_validation(
        self, user: User, group_id: int, blog_id: int
    ) -> AddBlogResult:
        group = await self.get_group_by_id(user, group_id)
        if not group:
            return AddBlogResult(
                success=False, message=f"그룹을 찾을 수 없습니다: {group_id}"
            )
        return await self._blog.add_blog_with_slot_validation(user, group, blog_id)

    async def remove_blog_with_slot_release(
        self, user: User, group_id: int, blog_id: int
    ) -> bool:
        group = await self.get_group_by_id(user, group_id)
        if not group:
            raise ValueError(f"그룹을 찾을 수 없습니다: {group_id}")
        return await self._blog.remove_blog_with_slot_release(user, group_id, blog_id)
