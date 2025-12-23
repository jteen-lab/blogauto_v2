"""
그룹 서비스
"""
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import User, ProfileGroup, GroupProfileLink, BlogGroupLink, PublishProfile, Blog
from ..core.logger import get_logger

logger = get_logger("group_service", "app.log")


class GroupService:
    """그룹 관리 서비스"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_user_groups(self, user: User) -> List[ProfileGroup]:
        """사용자의 그룹 목록 조회"""
        query = select(ProfileGroup).where(
            ProfileGroup.user_id == user.id
        ).options(
            selectinload(ProfileGroup.profile_links),
            selectinload(ProfileGroup.blog_links)
        ).order_by(ProfileGroup.created_at.desc())
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def get_group_by_id(self, user: User, group_id: int) -> Optional[ProfileGroup]:
        """그룹 상세 조회"""
        query = select(ProfileGroup).where(
            and_(
                ProfileGroup.id == group_id,
                ProfileGroup.user_id == user.id
            )
        ).options(
            selectinload(ProfileGroup.profile_links).selectinload(GroupProfileLink.profile),
            selectinload(ProfileGroup.blog_links).selectinload(BlogGroupLink.blog)
        )
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def create_group(self, user: User, data: Dict[str, Any]) -> ProfileGroup:
        """그룹 생성"""
        profile_ids = data.pop("profile_ids", [])
        blog_ids = data.pop("blog_ids", [])

        group = ProfileGroup(user_id=user.id, **data)
        self.db.add(group)
        await self.db.flush()

        # 프로파일 연결
        for pid in profile_ids:
            link = GroupProfileLink(group_id=group.id, profile_id=pid)
            self.db.add(link)

        # 블로그 연결
        for bid in blog_ids:
            link = BlogGroupLink(group_id=group.id, blog_id=bid)
            self.db.add(link)

        await self.db.commit()
        await self.db.refresh(group)

        # 관계 데이터 로딩
        await self.db.refresh(group, ['profile_links', 'blog_links'])

        logger.info(f"[GROUP] 생성 완료 | user={user.id} | group={group.id} | profiles={len(profile_ids)} | blogs={len(blog_ids)}")
        return group
    
    async def update_group(self, user: User, group_id: int, data: Dict[str, Any]) -> ProfileGroup:
        """그룹 수정"""
        group = await self.get_group_by_id(user, group_id)
        if not group:
            raise ValueError(f"그룹을 찾을 수 없습니다: {group_id}")

        profile_ids = data.pop("profile_ids", None)
        blog_ids = data.pop("blog_ids", None)

        # 기본 정보 업데이트
        for key, value in data.items():
            if value is not None and hasattr(group, key):
                setattr(group, key, value)

        # 프로파일 연결 업데이트
        if profile_ids is not None:
            await self.db.execute(
                delete(GroupProfileLink).where(GroupProfileLink.group_id == group_id)
            )
            for pid in profile_ids:
                link = GroupProfileLink(group_id=group_id, profile_id=pid)
                self.db.add(link)

        # 블로그 연결 업데이트
        if blog_ids is not None:
            await self.db.execute(
                delete(BlogGroupLink).where(BlogGroupLink.group_id == group_id)
            )
            for bid in blog_ids:
                link = BlogGroupLink(group_id=group_id, blog_id=bid)
                self.db.add(link)

        await self.db.commit()
        await self.db.refresh(group)

        logger.info(f"[GROUP] 수정 완료 | group={group_id} | profiles={len(profile_ids) if profile_ids else '변경없음'} | blogs={len(blog_ids) if blog_ids else '변경없음'}")
        return group
    
    async def delete_group(self, user: User, group_id: int) -> bool:
        """그룹 삭제"""
        group = await self.get_group_by_id(user, group_id)
        if not group:
            raise ValueError(f"그룹을 찾을 수 없습니다: {group_id}")
        
        await self.db.delete(group)
        await self.db.commit()
        
        logger.info(f"[GROUP] 삭제 완료 | group={group_id}")
        return True
    
    async def assign_blogs(self, user: User, group_id: int, blog_ids: List[int]) -> ProfileGroup:
        """그룹에 블로그 할당"""
        group = await self.get_group_by_id(user, group_id)
        if not group:
            raise ValueError(f"그룹을 찾을 수 없습니다: {group_id}")
        
        # 기존 연결 삭제
        await self.db.execute(
            delete(BlogGroupLink).where(BlogGroupLink.group_id == group_id)
        )
        
        # 새 연결 생성
        for bid in blog_ids:
            link = BlogGroupLink(group_id=group_id, blog_id=bid)
            self.db.add(link)
        
        await self.db.commit()
        await self.db.refresh(group)
        
        logger.info(f"[GROUP] 블로그 할당 | group={group_id} | blogs={blog_ids}")
        return group
    
    async def copy_group(self, user: User, group_id: int, new_name: str) -> ProfileGroup:
        """그룹 복사"""
        original = await self.get_group_by_id(user, group_id)
        if not original:
            raise ValueError(f"그룹을 찾을 수 없습니다: {group_id}")
        
        # 새 그룹 생성
        new_group = ProfileGroup(
            user_id=user.id,
            name=new_name,
            description=original.description,
            is_active=original.is_active
        )
        self.db.add(new_group)
        await self.db.flush()
        
        # 프로파일 연결 복사
        for link in original.profile_links:
            new_link = GroupProfileLink(group_id=new_group.id, profile_id=link.profile_id)
            self.db.add(new_link)
        
        await self.db.commit()
        await self.db.refresh(new_group)
        
        logger.info(f"[GROUP] 복사 완료 | original={group_id} | new={new_group.id}")
        return new_group
