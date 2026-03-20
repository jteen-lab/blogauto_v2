"""
생성 콘텐츠 조회/삭제 API 라우터

생성된 글의 HTML 콘텐츠를 조회, 복사, 삭제하는 API.
설계 문서: generation_content_storage_plan.md - Phase 2
"""
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db_session
from ..core.config import settings
from ..models.user import User
from ..models.crawled_post import CrawledPost
from ..models.generation_history import GenerationHistory
from ..models.blog import Blog
from ..models.title import MainTitle
from ..routers.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/generation/content",
    tags=["Generation Content"],
)


# ============================================================
# 응답 모델
# ============================================================

class ContentResponse(BaseModel):
    """콘텐츠 조회 응답"""
    success: bool
    crawled_post_id: int
    title: str
    blog_id: int
    blog_name: Optional[str] = None
    content_html: Optional[str] = None
    image_url: Optional[str] = None
    source: str
    is_published: bool
    created_at: Optional[str] = None


class ContentListItem(BaseModel):
    """콘텐츠 목록 아이템"""
    crawled_post_id: int
    title: str
    blog_id: int
    blog_name: Optional[str] = None
    has_content: bool
    has_image: bool
    image_url: Optional[str] = None
    source: str
    is_published: bool
    created_at: Optional[str] = None
    content_length: Optional[int] = None


class ContentListResponse(BaseModel):
    """콘텐츠 목록 응답"""
    success: bool
    items: list[ContentListItem]
    total: int


# ============================================================
# API 엔드포인트
# ============================================================

@router.get("/list")
async def list_generated_content(
    blog_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ContentListResponse:
    """
    생성된 콘텐츠 목록 조회

    Args:
        blog_id: 블로그 ID 필터 (선택)
        page: 페이지 번호
        page_size: 페이지 크기
    """
    query = (
        select(CrawledPost)
        .where(CrawledPost.source == "generated")
        .order_by(desc(CrawledPost.created_at))
    )

    if blog_id:
        query = query.where(CrawledPost.blog_id == blog_id)

    # 전체 개수 조회
    count_query = (
        select(func.count())
        .select_from(CrawledPost)
        .where(CrawledPost.source == "generated")
    )
    if blog_id:
        count_query = count_query.where(CrawledPost.blog_id == blog_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 페이지네이션
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    posts = result.scalars().all()

    # 블로그 이름 조회
    blog_ids = list({p.blog_id for p in posts})
    blog_names = {}
    if blog_ids:
        blog_result = await db.execute(
            select(Blog.id, Blog.name).where(Blog.id.in_(blog_ids))
        )
        blog_names = {row.id: row.name for row in blog_result.fetchall()}

    items = []
    for post in posts:
        items.append(ContentListItem(
            crawled_post_id=post.id,
            title=post.title,
            blog_id=post.blog_id,
            blog_name=blog_names.get(post.blog_id),
            has_content=bool(post.content_html),
            has_image=bool(post.image_url),
            image_url=post.image_url,
            source=post.source,
            is_published=post.is_published,
            created_at=post.created_at.isoformat() if post.created_at else None,
            content_length=len(post.content_html) if post.content_html else None,
        ))

    return ContentListResponse(success=True, items=items, total=total)


@router.get("/{crawled_post_id}")
async def get_content(
    crawled_post_id: int,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ContentResponse:
    """
    생성된 콘텐츠 상세 조회

    Args:
        crawled_post_id: CrawledPost ID
    """
    result = await db.execute(
        select(CrawledPost).where(CrawledPost.id == crawled_post_id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다")

    # 블로그 이름 조회
    blog_result = await db.execute(
        select(Blog.name).where(Blog.id == post.blog_id)
    )
    blog_name = blog_result.scalar_one_or_none()

    return ContentResponse(
        success=True,
        crawled_post_id=post.id,
        title=post.title,
        blog_id=post.blog_id,
        blog_name=blog_name,
        content_html=post.content_html,
        image_url=post.image_url,
        source=post.source,
        is_published=post.is_published,
        created_at=post.created_at.isoformat() if post.created_at else None,
    )


@router.get("/{crawled_post_id}/html")
async def get_content_html(
    crawled_post_id: int,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """
    HTML 문자열만 반환 (클립보드 복사용)

    Args:
        crawled_post_id: CrawledPost ID
    """
    result = await db.execute(
        select(CrawledPost.content_html, CrawledPost.title)
        .where(CrawledPost.id == crawled_post_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다")

    return {
        "success": True,
        "title": row.title,
        "html": row.content_html or "",
    }


@router.delete("/{crawled_post_id}")
async def delete_content(
    crawled_post_id: int,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """
    생성된 콘텐츠 삭제

    CrawledPost 삭제 + 연결된 이미지 파일 삭제.
    이미 발행된 콘텐츠는 삭제 불가.

    Args:
        crawled_post_id: CrawledPost ID
    """
    result = await db.execute(
        select(CrawledPost).where(CrawledPost.id == crawled_post_id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다")

    if post.is_published:
        raise HTTPException(
            status_code=400,
            detail="이미 발행된 콘텐츠는 삭제할 수 없습니다"
        )

    # 삭제 전 연결 정보 저장
    post_title = post.title
    linked_main_title_id = post.matched_main_title_id

    # 이미지 파일 삭제
    deleted_image = False
    if post.image_url:
        try:
            image_filename = post.image_url.split("/")[-1]
            image_path = Path(settings.image_storage_dir) / image_filename
            if image_path.exists():
                image_path.unlink()
                deleted_image = True
                logger.info(f"[CONTENT] 이미지 삭제: {image_path}")
        except Exception as e:
            logger.warning(f"[CONTENT] 이미지 삭제 실패: {e}")

    # CrawledPost 삭제
    await db.delete(post)
    await db.flush()

    # MainTitle 상태 복원: 다른 매칭 CrawledPost가 없으면 "available"로
    restored_main_title = False
    if linked_main_title_id:
        remaining = await db.execute(
            select(func.count())
            .select_from(CrawledPost)
            .where(
                CrawledPost.matched_main_title_id == linked_main_title_id,
                CrawledPost.match_status == "matched",
            )
        )
        remaining_count = remaining.scalar() or 0

        if remaining_count == 0:
            mt_result = await db.execute(
                select(MainTitle).where(MainTitle.id == linked_main_title_id)
            )
            main_title = mt_result.scalar_one_or_none()
            if main_title and main_title.status == "used":
                main_title.status = "available"
                restored_main_title = True
                logger.info(
                    f"[CONTENT] MainTitle 상태 복원: "
                    f"id={linked_main_title_id} used→available"
                )

    await db.commit()

    logger.info(
        f"[CONTENT] 콘텐츠 삭제 완료: id={crawled_post_id}, "
        f"title={post_title}"
    )

    return {
        "success": True,
        "message": f"콘텐츠가 삭제되었습니다: {post_title}",
        "deleted_image": deleted_image,
        "restored_main_title": restored_main_title,
    }
