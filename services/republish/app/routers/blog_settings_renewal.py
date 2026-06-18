"""블로그 재발행 리뉴얼 설정 API (P1).

리뉴얼 정책(블로그 기본 주기 + 카테고리별 주기 + 제목 모드 + 본문/이미지
삭제 유예)을 Blog.renewal_config(JSON)에 저장/조회한다. 카테고리 주기는
그 블로그가 선택한 서브카테고리(blog_categories)만 대상으로 한다.
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.user import User
from ..models.category import SubTopic, Topic, BlogCategory
from ..routers.auth import get_current_user
from ..services.blog_settings_service import get_blog_or_404

logger = get_logger("blog_settings_renewal", "app.log")

router = APIRouter(prefix="/blogs/{blog_id}/settings", tags=["블로그 설정"])

TITLE_MODES = ("keep", "recombine")


class RenewalSettingsRequest(BaseModel):
    """리뉴얼 설정 저장 요청."""

    enabled: bool = False
    default_period_months: int = Field(6, ge=1, le=120)
    title_mode: str = Field("keep", pattern="^(keep|recombine)$")
    delete_grace_days: int = Field(7, ge=0, le=365)
    # {subtopic_id(문자열): 개월수}
    category_periods: Dict[str, int] = Field(default_factory=dict)


def _normalize_config(req: RenewalSettingsRequest) -> dict:
    """요청을 renewal_config 저장 형태로 정규화(주기 1~120개월 클램프)."""
    cats: Dict[str, int] = {}
    for key, value in (req.category_periods or {}).items():
        try:
            months = int(value)
        except (TypeError, ValueError):
            continue
        if months < 1:
            continue
        cats[str(key)] = min(months, 120)
    return {
        "enabled": bool(req.enabled),
        "default_period_months": req.default_period_months,
        "title_mode": req.title_mode if req.title_mode in TITLE_MODES else "keep",
        "delete_grace_days": req.delete_grace_days,
        "category_periods": cats,
    }


async def _blog_subcategories(
    db: AsyncSession, blog_id: int,
) -> List[dict]:
    """블로그가 선택한 활성 서브카테고리 목록(id/이름/주제명)."""
    rows = await db.execute(
        select(SubTopic.id, SubTopic.name, Topic.name)
        .join(BlogCategory, BlogCategory.subtopic_id == SubTopic.id)
        .join(Topic, SubTopic.topic_id == Topic.id)
        .where(
            BlogCategory.blog_id == blog_id,
            BlogCategory.is_active.is_(True),
            BlogCategory.subtopic_id.isnot(None),
        )
        .distinct()
        .order_by(Topic.name, SubTopic.name)
    )
    return [
        {
            "subtopic_id": sid,
            "subtopic_name": sname,
            "topic_name": tname,
        }
        for sid, sname, tname in rows.all()
    ]


@router.get("/renewal", summary="재발행 리뉴얼 설정 조회")
async def get_renewal_settings(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """리뉴얼 설정 + 그 블로그가 선택한 서브카테고리 목록 반환."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    cfg = dict(blog.renewal_config or {})
    return {
        "renewal_config": {
            "enabled": cfg.get("enabled", False),
            "default_period_months": cfg.get("default_period_months", 6),
            "title_mode": cfg.get("title_mode", "keep"),
            "delete_grace_days": cfg.get("delete_grace_days", 7),
            "category_periods": cfg.get("category_periods", {}),
        },
        "categories": await _blog_subcategories(db, blog_id),
    }


@router.post("/renewal", summary="재발행 리뉴얼 설정 저장")
async def save_renewal_settings(
    blog_id: int,
    request: RenewalSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """리뉴얼 설정 저장(blog.renewal_config)."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    blog.renewal_config = _normalize_config(request)
    flag_modified(blog, "renewal_config")
    await db.commit()
    logger.info(
        "재발행 리뉴얼 설정 저장 | blog_id=%s | 기본주기=%s개월 | "
        "title_mode=%s | 카테고리주기=%d개",
        blog_id,
        blog.renewal_config["default_period_months"],
        blog.renewal_config["title_mode"],
        len(blog.renewal_config["category_periods"]),
    )
    return {
        "success": True,
        "message": "리뉴얼 설정이 저장되었습니다",
        "renewal_config": blog.renewal_config,
    }


@router.post("/renewal/preview", summary="리뉴얼 미리보기(원본 vs 재생성)")
async def preview_renewal(
    blog_id: int,
    post_id: Optional[int] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """설정 시 결과 확인용. dry-run으로 원본/재생성 본문을 함께 반환.

    post_id 미지정 시 그 블로그의 가장 오래된 리뉴얼 가능 글로 자동 선택한다.
    실제 라이브 글/DB는 변경하지 않으며, 생성 호출이 발생해 수십 초 걸린다.
    """
    from ..models.crawled_post import CrawledPost
    from ..services.renewal.renewal_service import RenewalService

    blog = await get_blog_or_404(blog_id, current_user, db)

    if post_id:
        post = await db.get(CrawledPost, post_id)
    else:
        post = (
            await db.execute(
                select(CrawledPost)
                .where(
                    CrawledPost.blog_id == blog_id,
                    CrawledPost.source == "generated",
                    CrawledPost.published_at.isnot(None),
                    CrawledPost.platform_post_id.isnot(None),
                    CrawledPost.generation_history_id.isnot(None),
                )
                .order_by(CrawledPost.published_at.asc())
                .limit(1)
            )
        ).scalars().first()
    if not post or post.blog_id != blog_id:
        return {"success": False, "error": "미리보기할 글이 없습니다"}

    res = await RenewalService(db, blog.user_id).renew_post(
        blog, post, dry_run=True, include_content=True,
    )
    res["post_id"] = post.id
    return res
