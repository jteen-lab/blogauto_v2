"""블로그 애드센스 승인 지원 설정 API (Sprint 1: F1 필수 페이지, F2 저자 프로필).

필수 페이지(개인정보처리방침/이용약관/소개/문의) 생성 트리거/상태 조회와
저자 프로필(author_profile) 저장/조회를 제공한다.

설계 문서: docs/flowcharts/adsense_sprint1_p1.md
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.blog_settings_service import get_blog_or_404
from ..services.publishing.adsense_readiness_service import AdsenseReadinessService
from ..services.publishing.required_pages_service import RequiredPagesService

logger = get_logger("blog_settings_adsense", "app.log")

router = APIRouter(prefix="/blogs/{blog_id}/settings", tags=["블로그 설정"])


class AuthorProfileRequest(BaseModel):
    """저자 프로필 저장 요청."""

    name: Optional[str] = None
    bio: Optional[str] = None
    expertise: Optional[str] = None
    contact_email: Optional[str] = None
    contact_form_url: Optional[str] = None


@router.get("/required-pages", summary="필수 페이지 생성 상태 조회")
async def get_required_pages_status(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """필수 페이지(개인정보처리방침/이용약관/소개/문의) 발행 상태 조회."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    return {
        "status": blog.required_pages_status,
        "page_ids": blog.required_page_ids or {},
    }


@router.post("/required-pages/generate", summary="필수 페이지 4종 생성/갱신")
async def generate_required_pages(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """개인정보처리방침/이용약관/소개/문의 페이지를 생성하거나 갱신한다.

    아직 생성되지 않은 페이지는 신규 생성하고, 이미 생성된 페이지는 저자
    프로필/연락처 등 최신 정보를 반영해 원격 콘텐츠를 덮어쓴다. 재호출해도
    안전하다.
    """
    blog = await get_blog_or_404(blog_id, current_user, db)
    contact_email = (blog.author_profile or {}).get("contact_email") or current_user.email
    outcome = await RequiredPagesService(db).generate_all(blog, contact_email)
    logger.info(
        "필수 페이지 생성/갱신 요청 | blog_id=%s | success=%s | status=%s",
        blog_id, outcome.get("success"), outcome.get("status"),
    )
    return outcome


@router.delete("/required-pages", summary="필수 페이지 4종 삭제")
async def delete_required_pages(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """생성된 필수 페이지 4종을 원격 플랫폼에서 삭제하고 상태를 초기화한다."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    outcome = await RequiredPagesService(db).delete_all(blog)
    logger.info(
        "필수 페이지 삭제 요청 | blog_id=%s | success=%s | status=%s",
        blog_id, outcome.get("success"), outcome.get("status"),
    )
    return outcome


@router.get("/author-profile", summary="저자 프로필 조회")
async def get_author_profile(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """저자성(E-E-A-T) 신호용 저자 프로필 조회."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    return {"author_profile": blog.author_profile or {}}


@router.post("/author-profile", summary="저자 프로필 저장")
async def save_author_profile(
    blog_id: int,
    request: AuthorProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """저자 프로필 저장 (name/bio/expertise). 소개 페이지 생성 시 반영된다."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    blog.author_profile = {
        "name": request.name or "",
        "bio": request.bio or "",
        "expertise": request.expertise or "",
        "contact_email": request.contact_email or "",
        "contact_form_url": request.contact_form_url or "",
    }
    flag_modified(blog, "author_profile")
    await db.commit()
    logger.info("저자 프로필 저장 | blog_id=%s", blog_id)
    return {"success": True, "author_profile": blog.author_profile}


@router.get("/adsense-readiness", summary="애드센스 준비도 감사(F9)")
async def get_adsense_readiness(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """필수 페이지/저자 프로필/연락 채널/발행량 등 이미 저장된 신호를 모아
    승인 실험(A/B 버킷) 라벨링과 재신청 전 자가진단에 바로 쓸 수 있는
    요약을 반환한다. thin content 비율 등 정량 지표는 이번 스코프 밖.
    """
    blog = await get_blog_or_404(blog_id, current_user, db)
    return await AdsenseReadinessService(db).audit(blog)
