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
    # 미리보기에서 실제 블로그 스타일을 재현하기 위한 블로그 설정.
    # (프런트가 style_config로 CSS를 생성해 미리보기 iframe에 주입 — 발행 HTML엔
    #  클래스만 있고 CSS는 블로그 테마에 있으므로, 초기설정 검증용 미리보기에 필요)
    platform: Optional[str] = None
    style_config: Optional[dict] = None
    placeholders: Optional[dict] = None


class ContentListItem(BaseModel):
    """콘텐츠 목록 아이템"""
    crawled_post_id: int
    title: str
    blog_id: int
    blog_name: Optional[str] = None
    platform: Optional[str] = None
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

    # 블로그 이름 + 플랫폼 조회
    blog_ids = list({p.blog_id for p in posts})
    blog_names = {}
    blog_platforms = {}
    if blog_ids:
        blog_result = await db.execute(
            select(Blog.id, Blog.name, Blog.platform).where(Blog.id.in_(blog_ids))
        )
        for row in blog_result.fetchall():
            blog_names[row.id] = row.name
            blog_platforms[row.id] = (
                row.platform.value if hasattr(row.platform, 'value')
                else str(row.platform)
            )

    items = []
    for post in posts:
        items.append(ContentListItem(
            crawled_post_id=post.id,
            title=post.title,
            blog_id=post.blog_id,
            blog_name=blog_names.get(post.blog_id),
            platform=blog_platforms.get(post.blog_id, "blogger"),
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

    # 블로그 이름 + 미리보기 스타일 재현용 설정 조회
    blog_result = await db.execute(
        select(Blog.name, Blog.platform, Blog.style_config, Blog.placeholders)
        .where(Blog.id == post.blog_id)
    )
    blog_row = blog_result.first()
    blog_name = blog_row[0] if blog_row else None

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
        platform=(blog_row[1] if blog_row else None),
        style_config=(blog_row[2] if blog_row else None) or {},
        placeholders=(blog_row[3] if blog_row else None) or {},
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


class BatchDeleteRequest(BaseModel):
    """일괄 삭제 요청 모델"""
    ids: list[int]


async def _delete_single_post(
    post: CrawledPost, db: AsyncSession
) -> int:
    """단일 CrawledPost 삭제 공통 로직.

    이미지 파일 삭제 + CrawledPost DB 레코드 삭제.
    생성(source=generated) CrawledPost 삭제 시 연결된 MainTitle을
    "available"로 리셋하여 재사용 가능하게 합니다.

    Args:
        post: 삭제 대상 CrawledPost (blog eager-loaded)
        db: 비동기 DB 세션

    Returns:
        삭제된 이미지 파일 수
    """
    generation_history_id = post.generation_history_id
    main_title_id = post.matched_main_title_id
    post_source = post.source

    # 대표 이미지 파일 삭제
    deleted_images = _delete_image_file(post.image_url)

    # GenerationHistory 연결된 이미지 삭제
    if generation_history_id:
        gh_result = await db.execute(
            select(GenerationHistory)
            .where(GenerationHistory.id == generation_history_id)
        )
        gen_history = gh_result.scalar_one_or_none()
        if gen_history:
            deleted_images += _delete_image_file(gen_history.image_url)
            deleted_images += _delete_section_images(gen_history.section_images)

    # CrawledPost 삭제
    await db.delete(post)
    await db.flush()

    # 생성 CrawledPost 삭제 시 연결된 MainTitle을 available로 리셋
    if main_title_id and post_source == "generated":
        from ..models.title import MainTitle
        other_cp = await db.execute(
            select(func.count(CrawledPost.id)).where(
                CrawledPost.matched_main_title_id == main_title_id,
                CrawledPost.source == "generated",
            )
        )
        remaining = other_cp.scalar() or 0
        if remaining == 0:
            title = await db.get(MainTitle, main_title_id)
            if title and title.status == "used":
                title.status = "available"
                title.use_count = max(0, (title.use_count or 1) - 1)
                title.last_used_at = None
                logger.info(
                    f"[CONTENT] MainTitle 리셋 | id={main_title_id} "
                    f"| used → available (CrawledPost 삭제)"
                )

    return deleted_images


@router.delete("/{crawled_post_id}")
async def delete_content(
    crawled_post_id: int,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """
    생성된 콘텐츠 삭제

    CrawledPost 삭제 + 연결된 이미지 파일(대표/섹션) 삭제.
    발행 여부와 무관하게 삭제 가능.

    Args:
        crawled_post_id: CrawledPost ID
    """
    result = await db.execute(
        select(CrawledPost)
        .options(selectinload(CrawledPost.blog))
        .where(CrawledPost.id == crawled_post_id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다")

    if post.blog and post.blog.user_id != user.id:
        raise HTTPException(status_code=403, detail="권한이 없습니다")

    post_title = post.title
    deleted_images = await _delete_single_post(post, db)
    await db.commit()

    logger.info(
        f"[CONTENT] 콘텐츠 삭제 완료: id={crawled_post_id}, "
        f"title={post_title}, images={deleted_images}"
    )

    return {
        "success": True,
        "message": f"콘텐츠가 삭제되었습니다: {post_title}",
        "deleted_images": deleted_images,
    }


@router.post("/batch-delete")
async def batch_delete_content(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """
    생성된 콘텐츠 일괄 삭제

    여러 CrawledPost를 한 번에 삭제한다.
    소유권 검증 후 이미지 파일 삭제. MainTitle은 변경하지 않는다.

    Args:
        body: 삭제할 crawled_post_id 목록
    """
    if not body.ids:
        return {"success": True, "deleted_count": 0, "deleted_images": 0}

    result = await db.execute(
        select(CrawledPost)
        .options(selectinload(CrawledPost.blog))
        .where(CrawledPost.id.in_(body.ids))
    )
    posts = result.scalars().all()

    total_images = 0
    deleted_count = 0

    for post in posts:
        if post.blog and post.blog.user_id != user.id:
            logger.warning(f"[CONTENT] 일괄삭제 권한 없음: post_id={post.id}")
            continue

        total_images += await _delete_single_post(post, db)
        deleted_count += 1

    await db.commit()

    logger.info(
        f"[CONTENT] 일괄 삭제 완료: 요청={len(body.ids)}, "
        f"삭제={deleted_count}, 이미지={total_images}"
    )

    return {
        "success": True,
        "deleted_count": deleted_count,
        "deleted_images": total_images,
    }


def _delete_image_file(image_url: str | None) -> int:
    """이미지 URL에서 파일을 삭제하고 삭제 건수를 반환한다."""
    if not image_url:
        return 0
    try:
        filename = image_url.split("/")[-1]
        path = Path(settings.image_storage_dir) / filename
        if path.exists():
            path.unlink()
            logger.info(f"[CONTENT] 이미지 삭제: {path}")
            return 1
    except Exception as e:
        logger.warning(f"[CONTENT] 이미지 삭제 실패: {e}")
    return 0


def _delete_section_images(section_images_json: str | None) -> int:
    """GenerationHistory.section_images JSON에서 이미지 파일들을 삭제한다."""
    if not section_images_json:
        return 0
    import json
    deleted = 0
    try:
        items = json.loads(section_images_json)
        if not isinstance(items, list):
            return 0
        for item in items:
            url = item.get("image_url") if isinstance(item, dict) else None
            deleted += _delete_image_file(url)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"[CONTENT] 섹션 이미지 삭제 실패: {e}")
    return deleted
