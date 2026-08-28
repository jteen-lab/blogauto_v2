"""검색 노출 3종 API — S1 IndexNow · S2 사이트맵 · S6 색인 점검.

계획서: docs/plans/search_visibility_plan.md §4.1
순서도: docs/flowcharts/search_visibility.md
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.search_visibility import SearchVisibilityUrl
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.blog_settings_service import get_blog_or_404
from ..services.search_visibility import backfill as sv_backfill
from ..services.search_visibility import (
    discover_service, indexnow_service, naver_check, runner,
)
from ..services.search_visibility.config import (
    generate_indexnow_key, indexnow_supported, key_file_url, load_config,
)

logger = get_logger("search_visibility_api", "app.log")

router = APIRouter(
    prefix="/blogs/{blog_id}/search-visibility", tags=["검색 노출"],
)


class ConfigRequest(BaseModel):
    """검색 노출 설정 저장 요청."""

    indexnow_enabled: Optional[bool] = None
    sitemap_check_enabled: Optional[bool] = None
    sitemap_url: Optional[str] = None
    index_check_enabled: Optional[bool] = None
    index_check_daily_cap: Optional[int] = None
    discover_enabled: Optional[bool] = None
    discover_min_image_width: Optional[int] = None
    discover_block_on_fail: Optional[bool] = None
    naver_check_enabled: Optional[bool] = None
    naver_check_daily_cap: Optional[int] = None


def _save_config(blog: Any, config: Dict[str, Any]) -> None:
    """설정 JSON을 블로그에 반영한다(JSON 컬럼 변경 통지 포함)."""
    blog.search_index_config = config
    flag_modified(blog, "search_index_config")


def _config_view(blog: Any) -> Dict[str, Any]:
    """화면에 내려줄 설정 + 안내 정보."""
    config = load_config(blog)
    supported = indexnow_supported(blog)
    key = config.get("indexnow_key")
    return {
        **config,
        "indexnow_supported": supported,
        "indexnow_unsupported_reason": (
            None if supported
            else "블로거는 호스트 루트에 키 파일을 올릴 수 없어 IndexNow를 쓸 수 없습니다"
        ),
        "key_file_url": key_file_url(blog, key) if key else None,
        "key_file_content": key,
    }


@router.get("")
async def get_status(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """설정 + 집계 현황 조회."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    summary = await runner.blog_summary(db, blog_id)
    return {"config": _config_view(blog), "summary": summary}


@router.put("/config")
async def save_config(
    blog_id: int,
    request: ConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """설정 저장. IndexNow는 키 검증 전에는 켤 수 없다."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    config = load_config(blog)

    for field, value in request.model_dump(exclude_unset=True).items():
        if value is not None:
            config[field] = value

    if config.get("indexnow_enabled"):
        if not indexnow_supported(blog):
            raise HTTPException(
                status_code=422,
                detail="이 플랫폼은 IndexNow 키 파일을 올릴 수 없어 사용할 수 없습니다",
            )
        if not config.get("indexnow_key_verified"):
            raise HTTPException(
                status_code=422,
                detail="키 파일 검증을 먼저 통과해야 IndexNow를 켤 수 있습니다",
            )

    _save_config(blog, config)
    await db.commit()
    return {"config": _config_view(blog)}


@router.post("/indexnow/key")
async def issue_key(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """IndexNow 키를 새로 발급한다(기존 키는 무효가 된다)."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    if not indexnow_supported(blog):
        raise HTTPException(
            status_code=422, detail="이 플랫폼에서는 IndexNow를 쓸 수 없습니다",
        )

    config = load_config(blog)
    config["indexnow_key"] = generate_indexnow_key()
    config["indexnow_key_verified"] = False
    config["indexnow_key_error"] = None
    config["indexnow_key_checked_at"] = None
    config["indexnow_enabled"] = False
    _save_config(blog, config)
    await db.commit()
    return {"config": _config_view(blog)}


@router.post("/indexnow/verify")
async def verify_key(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """호스트 루트의 키 파일을 실제로 받아 검증한다."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    config = load_config(blog)
    key = config.get("indexnow_key")
    if not key:
        raise HTTPException(status_code=422, detail="먼저 키를 발급하세요")

    ok, error = await indexnow_service.verify_key(blog, key)
    config["indexnow_key_verified"] = ok
    config["indexnow_key_error"] = error
    config["indexnow_key_checked_at"] = datetime.now().isoformat()
    _save_config(blog, config)
    await db.commit()
    return {"verified": ok, "error": error, "config": _config_view(blog)}


@router.post("/check/sitemap")
async def check_sitemap(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """사이트맵 신선도 점검을 즉시 1회 실행한다(S2)."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    result = await runner.run_sitemap_check(db, blog)
    await db.commit()
    return result


@router.post("/check/index")
async def check_index(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """색인 상태 점검을 즉시 1회 실행한다(S6)."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    result = await runner.run_index_check(db, blog)
    await db.commit()
    return result


@router.post("/backfill")
async def backfill(
    blog_id: int,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """기존 발행 글을 원장에 채운다(색인율 기준선 확보용)."""
    await get_blog_or_404(blog_id, current_user, db)
    result = await sv_backfill.backfill_blog(db, blog_id, limit)
    await db.commit()
    return result


@router.post("/check/naver-index")
async def check_naver_index(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """네이버 색인(검색 노출) 점검을 즉시 1회 실행한다(S6-N)."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    result = await runner.run_naver_index_check(db, blog)
    await db.commit()
    return result


@router.post("/check/naver")
async def check_naver(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """네이버 노출 전제조건 점검(NEO) — Yeti robots + 소유확인 메타."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    result = await naver_check.check_blog(blog)
    return {
        "ok": result.ok,
        "robots_found": result.robots_found,
        "yeti_blocked": result.yeti_blocked,
        "yeti_rule_source": result.yeti_rule_source,
        "verification_meta": result.verification_meta,
        "error": result.error,
    }


@router.post("/check/discover")
async def check_discover(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """디스커버 준비도 점검(X5) — 템플릿 원본 + 발행 실물 신호."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    stmt = (
        select(SearchVisibilityUrl.url)
        .where(SearchVisibilityUrl.blog_id == blog_id)
        .order_by(SearchVisibilityUrl.published_at.desc())
        .limit(1)
    )
    published_url = (await db.execute(stmt)).scalar_one_or_none()

    result = await discover_service.check_blog(blog, published_url)
    return result.to_dict()


@router.get("/urls")
async def list_urls(
    blog_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, List[Dict[str, Any]]]:
    """최근 발행 URL의 노출 상태 목록."""
    await get_blog_or_404(blog_id, current_user, db)
    stmt = (
        select(SearchVisibilityUrl)
        .where(SearchVisibilityUrl.blog_id == blog_id)
        .order_by(SearchVisibilityUrl.published_at.desc())
        .limit(min(limit, 200))
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "urls": [
            {
                "id": row.id,
                "url": row.url,
                "title": row.title,
                "published_at": (
                    row.published_at.isoformat() if row.published_at else None
                ),
                "indexnow_status": row.indexnow_status,
                "indexnow_status_code": row.indexnow_status_code,
                "indexnow_error": row.indexnow_error,
                "sitemap_state": row.sitemap_state,
                "sitemap_miss_streak": row.sitemap_miss_streak,
                "index_state": row.index_state,
                "index_detail": row.index_detail,
                "naver_index_state": row.naver_index_state,
                "naver_detail": row.naver_detail,
            }
            for row in rows
        ],
    }
