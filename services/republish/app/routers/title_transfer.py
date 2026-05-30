"""
제목 이동 API

Features:
- 임시 제목 → 정식 제목 이동 (자동 그룹화 포함)
- 정식 제목 → 임시 제목 롤백
- 카테고리 분류된 제목 자동 이동
- 이동 통계 조회
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.title import MainTitle, TitleGroup, TempTitle
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.title_transfer_service import (
    move_temp_to_main,
    move_main_to_temp,
    auto_transfer_categorized_titles,
)

# shared 서비스에서 기본값 가져오기
import sys
import os

# Docker 환경과 로컬 환경 모두 지원
_shared_paths = ['/app/shared', '/home/jteen/blogauto_v2/shared']
for _path in _shared_paths:
    if os.path.exists(_path) and _path not in sys.path:
        sys.path.insert(0, _path)
        break

from services.similarity_service import DEFAULT_SIMILARITY_THRESHOLD

router = APIRouter(prefix="/titles/transfer", tags=["title-transfer"])
logger = get_logger("title_transfer_api", "app.log")


# ===== 요청/응답 스키마 =====

class MoveToMainRequest(BaseModel):
    """임시 → 정식 이동 요청"""
    temp_title_ids: List[int] = Field(..., description="이동할 임시 제목 ID 목록")
    auto_group: bool = Field(True, description="자동 그룹화 여부")
    similarity_threshold: float = Field(
        DEFAULT_SIMILARITY_THRESHOLD,
        ge=0, le=100,
        description="유사도 임계값 (0-100)"
    )


class MoveToTempRequest(BaseModel):
    """정식 → 임시 이동 요청"""
    title_ids: List[int] = Field(..., description="이동할 정식 제목 ID 목록")


class AutoTransferRequest(BaseModel):
    """자동 이동 요청"""
    similarity_threshold: float = Field(
        DEFAULT_SIMILARITY_THRESHOLD,
        ge=0, le=100,
        description="유사도 임계값 (0-100)"
    )


class TransferResponse(BaseModel):
    """이동 결과 응답"""
    success: bool
    moved: int
    grouped: int = 0
    duplicates: int = 0
    total: int = 0
    errors: List[str] = []
    message: str


class TransferStatsResponse(BaseModel):
    """이동 통계 응답"""
    temp_titles: dict
    main_titles: dict
    groups: dict


# ===== API 엔드포인트 =====

@router.post("/to-main", response_model=None)
async def transfer_to_main(
    data: MoveToMainRequest,
    async_mode: bool = False,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    임시 제목 → 정식 제목 이동

    선택한 임시 제목들을 정식 제목으로 이동합니다.
    auto_group=true이면 유사도 매칭으로 자동 그룹화합니다.

    Phase 3: async_mode=true 면 Celery 워커 디스패치 + task_id 반환.
    """
    # Phase 3: 비동기 디스패치 (대량 전환의 중복체크·유사도 부하를 워커로)
    if async_mode:
        from ..core.celery_match_tasks import task_transfer_temp_to_main
        task = task_transfer_temp_to_main.delay(
            data.temp_title_ids,
            data.auto_group,
            data.similarity_threshold,
        )
        return {
            "async": True,
            "task_id": task.id,
            "state": "queued",
            "poll_url": f"/api/v1/tasks/{task.id}",
        }

    try:
        result = await move_temp_to_main(
            db=db,
            temp_title_ids=data.temp_title_ids,
            auto_group=data.auto_group,
            threshold=data.similarity_threshold
        )

        return TransferResponse(
            success=True,
            moved=result["moved"],
            grouped=result.get("grouped", 0),
            duplicates=result.get("duplicates", 0),
            errors=result.get("errors", []),
            message=f"{result['moved']}개 제목이 정식 제목으로 이동되었습니다."
        )
    except Exception as e:
        logger.error(f"[TRANSFER] 임시→정식 이동 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/to-temp", response_model=TransferResponse)
async def transfer_to_temp(
    data: MoveToTempRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    정식 제목 → 임시 제목 이동

    선택한 정식 제목들을 임시 제목으로 되돌립니다.
    대표 제목인 경우 그룹 내 다른 제목이 대표가 됩니다.
    """
    try:
        result = await move_main_to_temp(
            db=db,
            title_ids=data.title_ids
        )

        return TransferResponse(
            success=True,
            moved=result["moved"],
            errors=result.get("errors", []),
            message=f"{result['moved']}개 제목이 임시 제목으로 이동되었습니다."
        )
    except Exception as e:
        logger.error(f"[TRANSFER] 정식→임시 이동 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto", response_model=TransferResponse)
async def auto_transfer(
    data: AutoTransferRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    카테고리가 있는 임시 제목 자동 이동

    카테고리가 분류된 모든 임시 제목을 정식 제목으로 이동합니다.
    수집 모듈 완료 후 자동으로 호출될 수 있습니다.
    """
    try:
        result = await auto_transfer_categorized_titles(
            db=db,
            threshold=data.similarity_threshold
        )

        return TransferResponse(
            success=True,
            total=result.get("total", 0),
            moved=result["moved"],
            grouped=result.get("grouped", 0),
            duplicates=result.get("duplicates", 0),
            errors=result.get("errors", []),
            message=f"총 {result.get('total', 0)}개 중 {result['moved']}개가 이동되었습니다."
        )
    except Exception as e:
        logger.error(f"[TRANSFER] 자동 이동 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=TransferStatsResponse)
async def get_transfer_stats(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    이동 통계 조회

    - 임시 제목 수 (전체/카테고리 있음/없음)
    - 정식 제목 수 (전체/그룹화된 것)
    - 그룹 수
    """
    # 임시 제목 통계
    temp_total = (await db.execute(
        select(func.count()).select_from(TempTitle)
    )).scalar() or 0

    temp_with_category = (await db.execute(
        select(func.count()).select_from(TempTitle).where(TempTitle.category_id != None)
    )).scalar() or 0

    temp_new = (await db.execute(
        select(func.count()).select_from(TempTitle).where(TempTitle.status == "new")
    )).scalar() or 0

    temp_categorized = (await db.execute(
        select(func.count()).select_from(TempTitle).where(TempTitle.status == "categorized")
    )).scalar() or 0

    # 정식 제목 통계
    main_total = (await db.execute(
        select(func.count()).select_from(MainTitle)
    )).scalar() or 0

    main_grouped = (await db.execute(
        select(func.count()).select_from(MainTitle).where(MainTitle.group_id != None)
    )).scalar() or 0

    main_available = (await db.execute(
        select(func.count()).select_from(MainTitle).where(MainTitle.status == "available")
    )).scalar() or 0

    # 그룹 통계
    groups_total = (await db.execute(
        select(func.count()).select_from(TitleGroup)
    )).scalar() or 0

    groups_active = (await db.execute(
        select(func.count()).select_from(TitleGroup).where(TitleGroup.is_active == True)
    )).scalar() or 0

    return TransferStatsResponse(
        temp_titles={
            "total": temp_total,
            "with_category": temp_with_category,
            "without_category": temp_total - temp_with_category,
            "new": temp_new,
            "categorized": temp_categorized,
            "ready_to_move": temp_new + temp_categorized,
        },
        main_titles={
            "total": main_total,
            "grouped": main_grouped,
            "ungrouped": main_total - main_grouped,
            "available": main_available,
        },
        groups={
            "total": groups_total,
            "active": groups_active,
        }
    )
