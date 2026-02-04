"""
참조자료 수집 API 라우터

Features:
- 참조자료 수집 시작 (백그라운드 태스크)
- 수집 상태/결과 조회, 삭제, 재시도
"""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.database import get_db_session
from ..models.collected_reference import CollectedReference, CrawlLog
from ..models.user import User
from ..models.user_settings import UserSettings
from ..routers.auth import get_current_user
from ..schemas.reference_collection import (
    CollectRequest, CollectResponse, StatusResponse,
    ReferenceResult, ReferenceListItem, CrawlLogItem, DocumentSummary
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/references", tags=["Reference Collection"])


async def run_collection_task(reference_id: int, search_query: str, user_id: int):
    """백그라운드 수집 태스크"""
    from ..core.database import db_manager
    from ..services.reference_search_service import ReferenceSearchService
    from ..services.reference_crawling_service import ReferenceCrawlingService
    from ..services.reference_summary_service import ReferenceSummaryService

    async with db_manager.get_session() as db:
        try:
            ref = await db.get(CollectedReference, reference_id)
            if not ref:
                return
            ref.status = "collecting"
            await db.commit()

            # 사용자 설정 조회
            user_settings = (await db.execute(
                select(UserSettings).where(UserSettings.user_id == user_id)
            )).scalar_one_or_none()

            if not user_settings:
                ref.status, ref.error_message = "failed", "사용자 설정을 찾을 수 없습니다"
                await db.commit()
                return

            # 검색
            search_results = await ReferenceSearchService(user_settings).search_webdoc(search_query, 30)
            ref.total_searched = len(search_results)
            await db.commit()

            if not search_results:
                ref.status, ref.error_message, ref.completed_at = "failed", "검색 결과 없음", datetime.now()
                await db.commit()
                return

            # 크롤링
            crawl_result = await ReferenceCrawlingService(db).crawl_documents(
                [r.link for r in search_results], reference_id
            )
            ref.total_crawled, ref.total_failed = crawl_result.total_success, crawl_result.total_failed
            await db.commit()

            if not crawl_result.documents:
                ref.status, ref.error_message, ref.completed_at = "failed", "크롤링 실패", datetime.now()
                await db.commit()
                return

            # 요약
            summaries = await ReferenceSummaryService(db, user_id).summarize_documents(crawl_result.documents)
            ref.selected_references = [
                {"url": s.url, "title": s.title, "summary": s.summary,
                 "original_length": s.original_length, "is_ai_summary": s.is_ai_summary,
                 "selected_at": datetime.now().isoformat()}
                for s in summaries
            ]
            ref.status, ref.completed_at = "completed", datetime.now()
            await db.commit()
            logger.info(f"[REF_COLLECT] 완료 | id={reference_id} | crawled={ref.total_crawled}")

        except Exception as e:
            logger.error(f"[REF_COLLECT] 실패 | id={reference_id} | error={e}")
            ref = await db.get(CollectedReference, reference_id)
            if ref:
                ref.status, ref.error_message, ref.completed_at = "failed", str(e)[:500], datetime.now()
                await db.commit()


@router.post("/collect", response_model=CollectResponse, status_code=status.HTTP_201_CREATED)
async def start_collection(
    data: CollectRequest, background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session), current_user: User = Depends(get_current_user),
):
    """참조자료 수집 시작"""
    reference = CollectedReference(title_id=data.title_id, search_query=data.search_query, status="pending")
    db.add(reference)
    await db.commit()
    await db.refresh(reference)

    logger.info(f"[REF_COLLECT] 시작 | id={reference.id} | query={data.search_query}")
    background_tasks.add_task(run_collection_task, reference.id, data.search_query, current_user.id)

    return CollectResponse(reference_id=reference.id, status="collecting", message="참조자료 수집이 시작되었습니다")


@router.get("/{reference_id}/status", response_model=StatusResponse)
async def get_collection_status(
    reference_id: int, db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """수집 진행 상태 조회"""
    ref = await db.get(CollectedReference, reference_id)
    if not ref:
        raise HTTPException(status_code=404, detail="수집 기록을 찾을 수 없습니다")

    return StatusResponse(
        reference_id=ref.id, status=ref.status,
        progress={"searched": ref.total_searched, "crawled": ref.total_crawled, "failed": ref.total_failed},
        created_at=ref.created_at, completed_at=ref.completed_at
    )


@router.get("/{reference_id}", response_model=ReferenceResult)
async def get_collection_result(
    reference_id: int, db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """수집 결과 조회"""
    ref = await db.get(CollectedReference, reference_id)
    if not ref:
        raise HTTPException(status_code=404, detail="수집 기록을 찾을 수 없습니다")

    logs = (await db.execute(
        select(CrawlLog).where(CrawlLog.reference_id == reference_id).order_by(CrawlLog.crawled_at.desc())
    )).scalars().all()

    selected = [
        DocumentSummary(
            url=r.get("url", ""), title=r.get("title"), original_length=r.get("original_length", 0),
            summary=r.get("summary", ""), summary_length=len(r.get("summary", "")),
            is_ai_summary=r.get("is_ai_summary", False)
        ) for r in (ref.selected_references or [])
    ]

    return ReferenceResult(
        reference_id=ref.id, search_query=ref.search_query, status=ref.status,
        total_searched=ref.total_searched, total_crawled=ref.total_crawled, total_failed=ref.total_failed,
        selected_references=selected, crawl_logs=[CrawlLogItem.model_validate(log) for log in logs],
        created_at=ref.created_at, completed_at=ref.completed_at
    )


@router.get("", response_model=list[ReferenceListItem])
async def list_collections(
    page: int = 1, size: int = 20, status: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session), current_user: User = Depends(get_current_user),
):
    """수집 목록 조회"""
    query = select(CollectedReference).order_by(CollectedReference.created_at.desc())
    if status:
        query = query.where(CollectedReference.status == status)
    refs = (await db.execute(query.offset((page - 1) * size).limit(size))).scalars().all()

    return [
        ReferenceListItem(
            id=r.id, search_query=r.search_query, status=r.status, total_crawled=r.total_crawled,
            selected_count=len(r.selected_references or []), created_at=r.created_at,
            completed_at=r.completed_at, title_id=r.title_id
        ) for r in refs
    ]


@router.delete("/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    reference_id: int, db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """수집 결과 삭제"""
    ref = await db.get(CollectedReference, reference_id)
    if not ref:
        raise HTTPException(status_code=404, detail="수집 기록을 찾을 수 없습니다")
    await db.delete(ref)
    await db.commit()
    logger.info(f"[REF_COLLECT] 삭제 | id={reference_id}")


@router.post("/{reference_id}/retry", response_model=CollectResponse)
async def retry_collection(
    reference_id: int, background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session), current_user: User = Depends(get_current_user),
):
    """수집 재시도"""
    ref = await db.get(CollectedReference, reference_id)
    if not ref:
        raise HTTPException(status_code=404, detail="수집 기록을 찾을 수 없습니다")
    if ref.status not in ("failed", "completed"):
        raise HTTPException(status_code=400, detail="실패/완료 상태에서만 재시도 가능")

    ref.status, ref.total_searched, ref.total_crawled, ref.total_failed = "pending", 0, 0, 0
    ref.selected_references, ref.error_message, ref.completed_at = None, None, None
    await db.commit()

    logger.info(f"[REF_COLLECT] 재시도 | id={reference_id}")
    background_tasks.add_task(run_collection_task, ref.id, ref.search_query, current_user.id)

    return CollectResponse(reference_id=ref.id, status="collecting", message="참조자료 수집을 재시도합니다")
