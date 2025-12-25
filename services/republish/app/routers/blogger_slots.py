"""
Blogger 슬롯 관리 API 라우터

Features:
- 슬롯 현황 조회
- 가용 슬롯 확인
- 슬롯 예약 검증
- 대체 슬롯 추천
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any

from ..core.database import get_db_session
from .auth import get_current_user
from ..models import User
from ..services.blogger_slot_service import BloggerGlobalSlotManager
from ..services.google_credential_service import GoogleCredentialService
from ..schemas.blogger_slot import (
    BloggerSlotResponse,
    SlotInfo,
    SlotSuggestion,
    ValidationResult,
    ScheduleInfo
)
from ..core.logger import get_logger

logger = get_logger("blogger_slots_api", "app.log")

router = APIRouter(prefix="/blogger-slots", tags=["blogger-slots"])


@router.get("/{credential_id}", response_model=List[BloggerSlotResponse])
async def get_all_slots(
    credential_id: int,
    day_of_week: Optional[int] = Query(None, description="요일 필터 (0=월요일)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Google 계정의 모든 예약된 슬롯 조회"""
    logger.info(f"[GET_ALL_SLOTS] credential_id={credential_id}, user_id={current_user.id}")

    # 계정 소유권 확인
    credential_service = GoogleCredentialService(db)
    credential = await credential_service.get_by_id(credential_id, current_user.id)
    if not credential:
        raise HTTPException(status_code=404, detail="Google 계정을 찾을 수 없습니다")

    try:
        slot_manager = BloggerGlobalSlotManager(db, credential_id)
        slots = await slot_manager.get_all_reserved_slots(day_of_week)

        return [
            BloggerSlotResponse(
                id=slot.id,
                google_credential_id=slot.google_credential_id,
                day_of_week=slot.day_of_week,
                hour=slot.hour,
                minute=slot.minute,
                time_str=slot.time_str,
                day_name_kr=slot.day_name_kr,
                day_name_en=slot.day_name_en,
                assignment_type=slot.assignment_type,
                assignment_id=slot.assignment_id,
                blog_id=slot.blog_id,
                group_id=slot.group_id,
                profile_id=slot.profile_id,
                is_weekend=slot.is_weekend,
                is_business_hour=slot.is_business_hour,
                created_at=slot.created_at
            )
            for slot in slots
        ]

    except Exception as e:
        logger.error(f"[GET_ALL_SLOTS] 오류: {e}")
        raise HTTPException(status_code=500, detail=f"슬롯 조회 실패: {str(e)}")


@router.get("/{credential_id}/day/{day_of_week}", response_model=Dict[int, List[SlotInfo]])
async def get_day_slots(
    credential_id: int,
    day_of_week: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """특정 요일의 시간대별 슬롯 현황"""
    if not 0 <= day_of_week <= 6:
        raise HTTPException(status_code=400, detail="요일은 0(월요일)~6(일요일) 범위여야 합니다")

    logger.info(f"[GET_DAY_SLOTS] credential_id={credential_id}, day={day_of_week}")

    # 계정 소유권 확인
    credential_service = GoogleCredentialService(db)
    credential = await credential_service.get_by_id(credential_id, current_user.id)
    if not credential:
        raise HTTPException(status_code=404, detail="Google 계정을 찾을 수 없습니다")

    try:
        slot_manager = BloggerGlobalSlotManager(db, credential_id)
        hour_slots = await slot_manager.get_slot_status_by_hour(day_of_week)

        return hour_slots

    except Exception as e:
        logger.error(f"[GET_DAY_SLOTS] 오류: {e}")
        raise HTTPException(status_code=500, detail=f"일별 슬롯 조회 실패: {str(e)}")


@router.get("/{credential_id}/available", response_model=List[int])
async def get_available_slots(
    credential_id: int,
    day: int = Query(..., description="요일 (0=월요일)"),
    hour: int = Query(..., description="시간 (0-23)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """특정 시간의 가용 슬롯 분(minute) 목록"""
    if not 0 <= day <= 6:
        raise HTTPException(status_code=400, detail="요일은 0~6 범위여야 합니다")
    if not 0 <= hour <= 23:
        raise HTTPException(status_code=400, detail="시간은 0~23 범위여야 합니다")

    logger.info(f"[GET_AVAILABLE] credential_id={credential_id}, day={day}, hour={hour}")

    # 계정 소유권 확인
    credential_service = GoogleCredentialService(db)
    credential = await credential_service.get_by_id(credential_id, current_user.id)
    if not credential:
        raise HTTPException(status_code=404, detail="Google 계정을 찾을 수 없습니다")

    try:
        slot_manager = BloggerGlobalSlotManager(db, credential_id)
        available_minutes = await slot_manager.get_available_slots(day, hour)

        return available_minutes

    except Exception as e:
        logger.error(f"[GET_AVAILABLE] 오류: {e}")
        raise HTTPException(status_code=500, detail=f"가용 슬롯 조회 실패: {str(e)}")


@router.post("/{credential_id}/validate", response_model=ValidationResult)
async def validate_schedules(
    credential_id: int,
    request_data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """스케줄 목록 슬롯 예약 가능 여부 검증 (dry-run)"""
    logger.info(f"[VALIDATE_SCHEDULES] credential_id={credential_id}")

    # 계정 소유권 확인
    credential_service = GoogleCredentialService(db)
    credential = await credential_service.get_by_id(credential_id, current_user.id)
    if not credential:
        raise HTTPException(status_code=404, detail="Google 계정을 찾을 수 없습니다")

    # 요청 데이터 검증
    blog_id = request_data.get("blog_id")
    schedules_data = request_data.get("schedules", [])

    if not blog_id:
        raise HTTPException(status_code=400, detail="blog_id가 필요합니다")
    if not schedules_data:
        raise HTTPException(status_code=400, detail="schedules가 필요합니다")

    try:
        # 스케줄 데이터 변환
        schedules = []
        for schedule_data in schedules_data:
            schedule = ScheduleInfo(
                profile_id=schedule_data["profile_id"],
                profile_name=schedule_data["profile_name"],
                day_of_week=schedule_data["day_of_week"],
                hour=schedule_data["hour"],
                minute=schedule_data.get("minute", 0)
            )
            schedules.append(schedule)

        slot_manager = BloggerGlobalSlotManager(db, credential_id)
        validation_result = await slot_manager.validate_blog_schedules(blog_id, schedules)

        return validation_result

    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"필수 필드 누락: {str(e)}")
    except Exception as e:
        logger.error(f"[VALIDATE_SCHEDULES] 오류: {e}")
        raise HTTPException(status_code=500, detail=f"스케줄 검증 실패: {str(e)}")


@router.get("/{credential_id}/suggest", response_model=List[SlotSuggestion])
async def suggest_alternative_slots(
    credential_id: int,
    day: int = Query(..., description="요일 (0=월요일)"),
    hours: str = Query(..., description="선호 시간대 (예: 9,10,11)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """대체 슬롯 추천"""
    if not 0 <= day <= 6:
        raise HTTPException(status_code=400, detail="요일은 0~6 범위여야 합니다")

    # 시간대 파싱
    try:
        preferred_hours = [int(h.strip()) for h in hours.split(",")]
        if not all(0 <= h <= 23 for h in preferred_hours):
            raise ValueError("시간은 0~23 범위여야 합니다")
    except ValueError:
        raise HTTPException(status_code=400, detail="시간대 형식이 올바르지 않습니다 (예: 9,10,11)")

    logger.info(f"[SUGGEST_SLOTS] credential_id={credential_id}, day={day}, hours={preferred_hours}")

    # 계정 소유권 확인
    credential_service = GoogleCredentialService(db)
    credential = await credential_service.get_by_id(credential_id, current_user.id)
    if not credential:
        raise HTTPException(status_code=404, detail="Google 계정을 찾을 수 없습니다")

    try:
        slot_manager = BloggerGlobalSlotManager(db, credential_id)
        suggestions = await slot_manager.suggest_alternative_slots(day, preferred_hours)

        return suggestions

    except Exception as e:
        logger.error(f"[SUGGEST_SLOTS] 오류: {e}")
        raise HTTPException(status_code=500, detail=f"슬롯 추천 실패: {str(e)}")