"""
AI API 키 관리 API 라우터

Features:
- API 키 CRUD 엔드포인트
- 우선순위 관리
- 상태 관리
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..services.ai_key_manager import AIKeyManager
from ..schemas.ai_api_key import (
    AIProvider,
    AIApiKeyCreate,
    AIApiKeyUpdate,
    AIApiKeyPriorityUpdate,
    AIApiKeyResponse,
    AIApiKeyListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai-keys", tags=["AI API Keys"])


@router.get("/deepseek/peak-hours")
async def deepseek_peak_hours() -> dict:
    """딥시크 피크 시간대(KST) — 성장 프로파일 화면이 받아 쓴다.

    피크 정의를 클라이언트에 또 적으면 요금제가 바뀔 때 한쪽만 고쳐진다.
    서버 상수(deepseek_pricing)를 그대로 내려보낸다.
    """
    from ..services.ai.deepseek_pricing import (
        PEAK_MULTIPLIER,
        PEAK_WEEKDAYS,
        peak_hours_kst,
    )

    return {
        "hours_kst": peak_hours_kst(),
        "weekdays": list(PEAK_WEEKDAYS),
        "multiplier": PEAK_MULTIPLIER,
        "note": "피크 시간은 비피크의 2배 요금입니다 (월~금 기준)",
    }


def get_key_manager(db: AsyncSession = Depends(get_db_session)) -> AIKeyManager:
    """AIKeyManager 의존성 주입"""
    return AIKeyManager(db, user_id=1)


@router.get("", response_model=AIApiKeyListResponse)
async def list_keys(
    provider: Optional[AIProvider] = None,
    manager: AIKeyManager = Depends(get_key_manager),
):
    """
    API 키 목록 조회

    Args:
        provider: 특정 제공자만 조회 (선택)

    Returns:
        API 키 목록
    """
    keys = await manager.get_keys_by_provider(provider)
    stats = await manager.get_key_stats()

    return AIApiKeyListResponse(
        keys=[AIApiKeyResponse(**key.to_dict()) for key in keys],
        total=len(keys),
        by_provider=stats.get("by_provider", {}),
    )


@router.post("", response_model=AIApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    data: AIApiKeyCreate,
    manager: AIKeyManager = Depends(get_key_manager),
):
    """
    새 API 키 등록

    Args:
        data: 키 생성 데이터

    Returns:
        생성된 API 키 정보
    """
    key = await manager.create_key(data)
    return AIApiKeyResponse(**key.to_dict())


@router.get("/{key_id}", response_model=AIApiKeyResponse)
async def get_key(
    key_id: int,
    manager: AIKeyManager = Depends(get_key_manager),
):
    """
    특정 API 키 조회

    Args:
        key_id: 키 ID

    Returns:
        API 키 정보
    """
    key = await manager.get_key(key_id)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API 키를 찾을 수 없습니다: id={key_id}"
        )
    return AIApiKeyResponse(**key.to_dict())


@router.put("/{key_id}", response_model=AIApiKeyResponse)
async def update_key(
    key_id: int,
    data: AIApiKeyUpdate,
    manager: AIKeyManager = Depends(get_key_manager),
):
    """
    API 키 정보 수정

    Args:
        key_id: 키 ID
        data: 수정할 데이터

    Returns:
        수정된 API 키 정보
    """
    key = await manager.update_key(key_id, data)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API 키를 찾을 수 없습니다: id={key_id}"
        )
    return AIApiKeyResponse(**key.to_dict())


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(
    key_id: int,
    manager: AIKeyManager = Depends(get_key_manager),
):
    """
    API 키 삭제

    Args:
        key_id: 키 ID
    """
    success = await manager.delete_key(key_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API 키를 찾을 수 없습니다: id={key_id}"
        )


@router.post("/{key_id}/reset-status", response_model=AIApiKeyResponse)
async def reset_key_status(
    key_id: int,
    manager: AIKeyManager = Depends(get_key_manager),
):
    """
    API 키 상태 초기화 (오류/Rate limit → 활성)

    Args:
        key_id: 키 ID

    Returns:
        수정된 API 키 정보
    """
    key = await manager.get_key(key_id)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API 키를 찾을 수 없습니다: id={key_id}"
        )

    await manager.reset_key_status(key_id)
    await manager.db.refresh(key)
    return AIApiKeyResponse(**key.to_dict())


@router.put("/priorities/batch", response_model=dict)
async def update_priorities(
    data: AIApiKeyPriorityUpdate,
    manager: AIKeyManager = Depends(get_key_manager),
):
    """
    우선순위 일괄 변경

    Args:
        data: 우선순위 변경 목록

    Returns:
        변경된 키 개수
    """
    count = await manager.update_priorities(data)
    return {"updated_count": count}


@router.get("/stats/summary", response_model=dict)
async def get_stats(
    manager: AIKeyManager = Depends(get_key_manager),
):
    """
    API 키 통계 조회

    Returns:
        키 통계 정보
    """
    return await manager.get_key_stats()


@router.post("/maintenance/reset-rate-limits", response_model=dict)
async def reset_rate_limits(
    manager: AIKeyManager = Depends(get_key_manager),
):
    """
    쿨다운 시간이 지난 Rate limit 키들을 활성 상태로 복구

    Returns:
        복구된 키 개수
    """
    count = await manager.reset_rate_limited_keys()
    return {"reset_count": count}
