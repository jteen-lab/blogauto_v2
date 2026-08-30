"""블로그 애드센스 승인 지원 설정 API.

Sprint 1(F1 필수 페이지, F2 저자 프로필) + Sprint 2(F5 발행 케이던스)를
제공한다. 필수 페이지 생성 트리거/상태 조회, 저자 프로필(author_profile)
저장/조회, 승인 전 저속 모드 발행 상한 저장/조회를 담당한다.

설계 문서: docs/flowcharts/adsense_sprint1_p1.md, adsense_sprint2_f5.md
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
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


ADSENSE_STATUS_VALUES = {"none", "preparing", "applied", "approved"}


class PublishCadenceRequest(BaseModel):
    """애드센스 계정 상태 저장 요청 (F5).

    일일 발행 상한(publish_daily_cap)은 성장 프로파일 프리셋으로 이전되어
    제거됨. adsense_status는 계정 신청 상태 추적(F9 준비도)에만 쓰인다.
    """

    adsense_status: str = "none"


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
    """저자 프로필 저장 (name/bio/expertise).

    기존 author_profile을 **병합**해 프로비저닝 키(contact_form_id 등)를 보존한다.
    옛 Google Forms URL은 저장하지 않고 폐기(Tally 자동 생성으로 대체) —
    저장이 옛 구글폼 URL을 다시 주입하지 못하게 한다.
    """
    blog = await get_blog_or_404(blog_id, current_user, db)
    profile = dict(blog.author_profile or {})
    profile["name"] = request.name or ""
    profile["bio"] = request.bio or ""
    profile["expertise"] = request.expertise or ""
    profile["contact_email"] = request.contact_email or ""

    form_url = (request.contact_form_url or "").strip()
    if "docs.google.com/forms" in form_url:
        # 옛 구글폼 URL·식별자 폐기 → 다음 필수페이지 생성 시 Tally로 재생성
        form_url = ""
        profile.pop("contact_form_id", None)
    profile["contact_form_url"] = form_url

    blog.author_profile = profile
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


@router.get("/publish-cadence", summary="발행 케이던스 설정 조회 (F5)")
async def get_publish_cadence(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """애드센스 계정 신청 상태를 조회한다.

    애드센스가 보고한 원문 상태도 함께 돌려준다. 애드센스 API 는 '신청했는지'
    를 알려주지 않고 준비 중(GETTING_READY)까지만 말해 준다. 그래서 '심사 중'
    표시는 사용자가 직접 기록해야 하는데, 화면에 그 사정이 안 보이면 왜 어떤
    블로그만 '준비 중'에 머무는지 알 수 없다.
    """
    from ..services.publishing.adsense_account_service import (
        AdsenseAccountService,
    )
    from ..services.publishing.adsense_status_resolver import (
        resolve_display_status,
    )

    blog = await get_blog_or_404(blog_id, current_user, db)

    remote = {"state": None, "display": None, "inherited_from": None}
    try:
        index = await AdsenseAccountService(db).sites_index(current_user.id)
        if index:
            verdict = resolve_display_status(blog, index)
            remote = {
                "state": verdict.get("state"),
                "display": verdict.get("status"),
                "inherited_from": verdict.get("inherited_from"),
            }
    except Exception as e:  # 부가 정보 — 실패해도 설정 화면은 열려야 한다
        logger.warning(
            "애드센스 원문 상태 조회 실패 | blog_id=%s | %s", blog_id, e,
        )

    return {
        "adsense_status": blog.adsense_status,
        "remote": remote,
    }


@router.post("/publish-cadence", summary="발행 케이던스 설정 저장 (F5)")
async def save_publish_cadence(
    blog_id: int,
    request: PublishCadenceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """애드센스 계정 신청 상태를 저장한다.

    발행량 제어는 성장 프로파일 프리셋으로 이전됨. adsense_status는 F9 준비도
    감사·계정 상태 추적에만 쓰인다.
    """
    if request.adsense_status not in ADSENSE_STATUS_VALUES:
        raise HTTPException(
            status_code=422,
            detail=f"adsense_status는 {sorted(ADSENSE_STATUS_VALUES)} 중 하나여야 합니다",
        )
    blog = await get_blog_or_404(blog_id, current_user, db)
    blog.adsense_status = request.adsense_status
    await db.commit()
    logger.info(
        "애드센스 상태 저장 | blog_id=%s | adsense_status=%s",
        blog_id, blog.adsense_status,
    )
    return {
        "success": True,
        "adsense_status": blog.adsense_status,
    }


# F4 니치 강제 설정은 프롬프트 모듈 settings(niche_enabled/niche_topic_ids)로
# 이전됨(2026-08-16). 블로그 단위 /niche 엔드포인트는 제거.
# 순서도: docs/flowcharts/adsense_module_ui_migration.md
