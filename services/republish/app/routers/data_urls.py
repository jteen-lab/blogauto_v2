"""
수집된 URL 데이터 관리 API

Features:
- CollectedUrl CRUD
- 상태 관리 (처리 완료, 미처리, 비활성)
- 통계 조회 (Phase 1/2 현황)
- 일괄 처리 (재수집 대상 전환, 삭제)
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from pydantic import BaseModel

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.collected_url import CollectedUrl
from ..models.user import User
from ..routers.auth import get_current_user

router = APIRouter(prefix="/data/urls", tags=["data-urls"])
logger = get_logger("data_urls", "app.log")


# Pydantic Schemas
class CollectedUrlResponse(BaseModel):
    """수집된 URL 응답"""
    id: int
    url: str
    domain: str
    platform: str
    search_keyword: Optional[str] = None
    search_title: Optional[str] = None
    is_processed: bool
    process_count: int
    last_processed_at: Optional[datetime] = None
    titles_collected: int
    is_active: bool
    error_count: int
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CollectedUrlListResponse(BaseModel):
    """URL 목록 응답"""
    items: List[CollectedUrlResponse]
    total: int
    page: int
    size: int
    has_next: bool


class UrlStatsResponse(BaseModel):
    """URL 통계 응답"""
    total: int
    processed: int
    pending: int
    inactive: int
    platforms: dict
    # Phase 1/2 통계
    phase1_today: int  # 오늘 수집된 URL
    phase2_today: int  # 오늘 처리된 URL


class BulkUrlDelete(BaseModel):
    """대량 URL 삭제"""
    ids: List[int]


class BulkUrlReset(BaseModel):
    """대량 URL 재수집 대상 전환"""
    ids: List[int]


class BulkUrlAdd(BaseModel):
    """대량 URL 추가"""
    urls: List[str]


# API Endpoints
@router.get("", response_model=CollectedUrlListResponse)
async def list_collected_urls(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="도메인/키워드 검색"),
    platform: Optional[str] = Query(None, description="플랫폼 필터"),
    status: Optional[str] = Query(None, description="상태 필터 (pending/processed/inactive)"),
    sort_field: Optional[str] = Query("created_at", description="정렬 필드"),
    sort_dir: Optional[str] = Query("desc", description="정렬 방향 (asc/desc)"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """수집된 URL 목록 조회"""
    query = select(CollectedUrl)

    # 검색 필터
    if search:
        query = query.where(
            (CollectedUrl.domain.ilike(f"%{search}%")) |
            (CollectedUrl.search_keyword.ilike(f"%{search}%")) |
            (CollectedUrl.search_title.ilike(f"%{search}%"))
        )

    # 플랫폼 필터
    if platform:
        query = query.where(CollectedUrl.platform == platform)

    # 상태 필터
    if status == "pending":
        query = query.where(
            CollectedUrl.is_processed == False,
            CollectedUrl.is_active == True
        )
    elif status == "processed":
        query = query.where(CollectedUrl.is_processed == True)
    elif status == "inactive":
        query = query.where(CollectedUrl.is_active == False)

    # 전체 개수
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 정렬
    sort_columns = {
        "domain": CollectedUrl.domain,
        "platform": CollectedUrl.platform,
        "is_processed": CollectedUrl.is_processed,
        "titles_collected": CollectedUrl.titles_collected,
        "created_at": CollectedUrl.created_at,
        "last_processed_at": CollectedUrl.last_processed_at,
    }
    sort_column = sort_columns.get(sort_field, CollectedUrl.created_at)
    if sort_dir == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # 페이지네이션
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    urls = result.scalars().all()

    items = [CollectedUrlResponse.model_validate(u) for u in urls]

    return CollectedUrlListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        has_next=(page * size) < total
    )


@router.get("/stats", response_model=UrlStatsResponse)
async def get_url_stats(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """URL 수집 통계 조회 (Phase 1/2 현황 포함)"""
    from datetime import date

    today = date.today()

    # 전체 URL 수
    total = (await db.execute(
        select(func.count()).select_from(CollectedUrl)
    )).scalar() or 0

    # 처리 완료 URL 수
    processed = (await db.execute(
        select(func.count()).select_from(CollectedUrl)
        .where(CollectedUrl.is_processed == True)
    )).scalar() or 0

    # 미처리 URL 수 (활성 상태)
    pending = (await db.execute(
        select(func.count()).select_from(CollectedUrl)
        .where(CollectedUrl.is_processed == False)
        .where(CollectedUrl.is_active == True)
    )).scalar() or 0

    # 비활성화된 URL 수
    inactive = (await db.execute(
        select(func.count()).select_from(CollectedUrl)
        .where(CollectedUrl.is_active == False)
    )).scalar() or 0

    # 플랫폼별 통계
    platform_result = await db.execute(
        select(CollectedUrl.platform, func.count())
        .group_by(CollectedUrl.platform)
    )
    platforms = {row[0]: row[1] for row in platform_result.fetchall()}

    # Phase 1: 오늘 수집된 URL 수
    phase1_today = (await db.execute(
        select(func.count()).select_from(CollectedUrl)
        .where(func.date(CollectedUrl.created_at) == today)
    )).scalar() or 0

    # Phase 2: 오늘 처리된 URL 수
    phase2_today = (await db.execute(
        select(func.count()).select_from(CollectedUrl)
        .where(CollectedUrl.is_processed == True)
        .where(func.date(CollectedUrl.last_processed_at) == today)
    )).scalar() or 0

    return UrlStatsResponse(
        total=total,
        processed=processed,
        pending=pending,
        inactive=inactive,
        platforms=platforms,
        phase1_today=phase1_today,
        phase2_today=phase2_today
    )


# ============ 일괄 처리 API (동적 라우트 전에 배치) ============

@router.post("/bulk-add")
async def add_urls_bulk(
    data: BulkUrlAdd,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """URL 대량 추가"""
    from urllib.parse import urlparse
    import re

    created_count = 0
    duplicate_count = 0
    invalid_count = 0

    for url_str in data.urls:
        url_str = url_str.strip()
        if not url_str:
            continue

        # URL 형식 검증 (http/https로 시작하지 않으면 https 추가)
        if not url_str.startswith(('http://', 'https://')):
            url_str = 'https://' + url_str

        try:
            parsed = urlparse(url_str)
            if not parsed.netloc:
                invalid_count += 1
                continue

            domain = parsed.netloc.lower()

            # 플랫폼 자동 감지
            platform = "other"
            if "tistory.com" in domain:
                platform = "tistory"
            elif "blog.naver.com" in domain or "m.blog.naver.com" in domain:
                platform = "naver_blog"
            elif any(wp in domain for wp in ["wordpress.com", "wp.com"]):
                platform = "wordpress"
            elif re.search(r'\bwp\b|wordpress', domain, re.I):
                platform = "wordpress"

            # 중복 체크 (url + source_module_id IS NULL 조합)
            # alembic 042에서 UNIQUE 제약이 (domain) → (url, source_module_id)로 변경됨.
            # 수동 적재(bulk-add)는 모듈 귀속이 없으므로 source_module_id=NULL로 저장하고,
            # NULL끼리는 NULLS DISTINCT 라 애플리케이션 레벨에서 명시 중복 차단.
            existing = await db.execute(
                select(CollectedUrl)
                .where(CollectedUrl.url == url_str)
                .where(CollectedUrl.source_module_id.is_(None))
            )
            if existing.scalars().first():
                logger.debug(f"[BULK_ADD_URL] 중복 URL 스킵: {url_str}")
                duplicate_count += 1
                continue

            # URL 추가 (source_module_id=None: 수동 적재 경로)
            new_url = CollectedUrl(
                url=url_str,
                domain=domain,
                platform=platform,
                source_module_id=None,
                is_processed=False,
                is_active=True
            )
            db.add(new_url)
            created_count += 1

        except Exception as e:
            logger.warning(f"[BULK_ADD_URL] 파싱 오류: {url_str} - {e}")
            invalid_count += 1

    await db.commit()
    logger.info(f"[BULK_ADD_URL] 추가: {created_count}개, 중복: {duplicate_count}개, 오류: {invalid_count}개")

    return {
        "created": created_count,
        "duplicates": duplicate_count,
        "invalid": invalid_count,
        "message": f"{created_count}개 URL이 추가되었습니다 (중복: {duplicate_count}개, 오류: {invalid_count}개)"
    }


@router.post("/bulk-delete")
async def delete_urls_bulk(
    data: BulkUrlDelete,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """URL 일괄 삭제"""
    deleted_count = 0

    for url_id in data.ids:
        url = await db.get(CollectedUrl, url_id)
        if url:
            await db.delete(url)
            deleted_count += 1

    await db.commit()
    logger.info(f"[BULK_DELETE_URL] 삭제: {deleted_count}개")

    return {"deleted": deleted_count, "message": f"{deleted_count}개 URL이 삭제되었습니다"}


@router.post("/bulk-reset")
async def reset_urls_bulk(
    data: BulkUrlReset,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """URL 일괄 재수집 대상 전환"""
    reset_count = 0

    for url_id in data.ids:
        url = await db.get(CollectedUrl, url_id)
        if url:
            url.reset_for_recollect()
            reset_count += 1

    await db.commit()
    logger.info(f"[BULK_RESET_URL] 재수집 대상 전환: {reset_count}개")

    return {"reset": reset_count, "message": f"{reset_count}개 URL이 재수집 대상으로 전환되었습니다"}


@router.delete("/delete-all")
async def delete_all_urls(
    status: Optional[str] = Query(None, description="특정 상태만 삭제 (pending/processed/inactive)"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """URL 전체 삭제"""
    query = select(func.count()).select_from(CollectedUrl)

    if status == "pending":
        query = query.where(
            CollectedUrl.is_processed == False,
            CollectedUrl.is_active == True
        )
    elif status == "processed":
        query = query.where(CollectedUrl.is_processed == True)
    elif status == "inactive":
        query = query.where(CollectedUrl.is_active == False)

    total_before = (await db.execute(query)).scalar() or 0

    # 삭제 실행
    delete_query = delete(CollectedUrl)
    if status == "pending":
        delete_query = delete_query.where(
            CollectedUrl.is_processed == False,
            CollectedUrl.is_active == True
        )
    elif status == "processed":
        delete_query = delete_query.where(CollectedUrl.is_processed == True)
    elif status == "inactive":
        delete_query = delete_query.where(CollectedUrl.is_active == False)

    await db.execute(delete_query)
    await db.commit()

    logger.info(f"[DELETE_ALL_URL] 전체 삭제: {total_before}개, status={status or 'all'}")

    return {
        "deleted": total_before,
        "status": status or "all",
        "message": f"{total_before}개 URL이 삭제되었습니다"
    }


@router.post("/reset-old")
async def reset_old_processed_urls(
    days: int = Query(7, ge=1, le=30, description="N일 이전에 처리된 URL만 대상"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """오래된 처리 완료 URL을 재수집 대상으로 전환"""
    from datetime import timedelta

    cutoff_date = datetime.now() - timedelta(days=days)

    result = await db.execute(
        update(CollectedUrl)
        .where(CollectedUrl.is_processed == True)
        .where(CollectedUrl.last_processed_at < cutoff_date)
        .values(is_processed=False, error_count=0, last_error=None)
    )

    await db.commit()
    count = result.rowcount

    logger.info(f"[RESET_OLD_URL] {days}일 이전 처리된 URL {count}개 재수집 대상 전환")

    return {
        "reset": count,
        "days": days,
        "message": f"{count}개 URL이 재수집 대상으로 전환되었습니다"
    }


# ============ 개별 URL 처리 API (동적 라우트) ============

@router.get("/{url_id}", response_model=CollectedUrlResponse)
async def get_collected_url(
    url_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """수집된 URL 상세 조회"""
    url = await db.get(CollectedUrl, url_id)
    if not url:
        raise HTTPException(status_code=404, detail="URL을 찾을 수 없습니다")

    return CollectedUrlResponse.model_validate(url)


@router.delete("/{url_id}")
async def delete_collected_url(
    url_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """수집된 URL 삭제"""
    url = await db.get(CollectedUrl, url_id)
    if not url:
        raise HTTPException(status_code=404, detail="URL을 찾을 수 없습니다")

    await db.delete(url)
    await db.commit()

    logger.info(f"[DELETE_URL] URL 삭제: {url.domain}")
    return {"message": "삭제되었습니다"}


@router.post("/{url_id}/reset")
async def reset_url_for_recollect(
    url_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """URL을 재수집 대상으로 전환"""
    url = await db.get(CollectedUrl, url_id)
    if not url:
        raise HTTPException(status_code=404, detail="URL을 찾을 수 없습니다")

    url.reset_for_recollect()
    await db.commit()

    logger.info(f"[RESET_URL] URL 재수집 대상 전환: {url.domain}")
    return {"message": "재수집 대상으로 전환되었습니다"}


@router.post("/{url_id}/activate")
async def activate_url(
    url_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """비활성화된 URL 활성화"""
    url = await db.get(CollectedUrl, url_id)
    if not url:
        raise HTTPException(status_code=404, detail="URL을 찾을 수 없습니다")

    url.is_active = True
    url.error_count = 0
    url.last_error = None
    await db.commit()

    logger.info(f"[ACTIVATE_URL] URL 활성화: {url.domain}")
    return {"message": "활성화되었습니다"}
