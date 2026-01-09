"""
설정 API 라우터

Features:
- 사용자 설정 조회/저장
- AI 서비스 API 키 관리
- Google Blogger 시간당 발행 제한 설정
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.user_settings import UserSettings

logger = get_logger("settings", "settings.log")

router = APIRouter(prefix="/settings", tags=["설정"])


# ============================================================
# Pydantic Schemas
# ============================================================

class SettingsResponse(BaseModel):
    """설정 응답 스키마"""
    id: Optional[int] = None
    user_id: int
    openai_api_key: Optional[str] = None
    claude_api_key: Optional[str] = None
    default_ai_model: str = "gpt-4"
    blogger_hourly_limit: int = 2
    has_openai_key: bool = False
    has_claude_key: bool = False

    class Config:
        from_attributes = True


class SettingsUpdateRequest(BaseModel):
    """설정 업데이트 요청 스키마"""
    openai_api_key: Optional[str] = Field(None, max_length=255)
    claude_api_key: Optional[str] = Field(None, max_length=255)
    default_ai_model: Optional[str] = Field(None, max_length=50)
    blogger_hourly_limit: Optional[int] = Field(None, ge=1, le=4)


class PasswordChangeRequest(BaseModel):
    """비밀번호 변경 요청 스키마"""
    current_password: str
    new_password: str = Field(..., min_length=8)


# ============================================================
# API Endpoints
# ============================================================

@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db_session)):
    """
    현재 사용자 설정 조회

    현재는 user_id=1 (단일 사용자) 가정
    """
    try:
        # 현재 단일 사용자 환경 (user_id=1)
        user_id = 1

        # AsyncSession 쿼리 방식
        query = select(UserSettings).where(UserSettings.user_id == user_id)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            # 설정이 없으면 기본값으로 생성 시도
            try:
                settings = UserSettings(
                    user_id=user_id,
                    default_ai_model="gpt-4",
                    blogger_hourly_limit=2
                )
                db.add(settings)
                await db.commit()
                await db.refresh(settings)
                logger.info(f"[SETTINGS] 기본 설정 생성: user_id={user_id}")
            except Exception as create_error:
                logger.error(f"[SETTINGS] 설정 생성 실패: {str(create_error)}")
                await db.rollback()
                # 생성 실패 시 기본값 반환
                return {
                    "id": None,
                    "user_id": user_id,
                    "openai_api_key": None,
                    "claude_api_key": None,
                    "default_ai_model": "gpt-4",
                    "blogger_hourly_limit": 2,
                    "has_openai_key": False,
                    "has_claude_key": False
                }

        return {
            "id": settings.id,
            "user_id": settings.user_id,
            "openai_api_key": settings.masked_openai_key,
            "claude_api_key": settings.masked_claude_key,
            "default_ai_model": settings.default_ai_model,
            "blogger_hourly_limit": settings.blogger_hourly_limit,
            "has_openai_key": settings.has_openai_key,
            "has_claude_key": settings.has_claude_key
        }

    except Exception as e:
        logger.error(f"[SETTINGS] 조회 에러: {str(e)}", exc_info=True)
        # 에러 시에도 기본값 반환 (500 에러 방지)
        return {
            "id": None,
            "user_id": 1,
            "openai_api_key": None,
            "claude_api_key": None,
            "default_ai_model": "gpt-4",
            "blogger_hourly_limit": 2,
            "has_openai_key": False,
            "has_claude_key": False
        }


@router.put("")
async def update_settings(
    request: SettingsUpdateRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    설정 업데이트

    - API 키는 빈 문자열이면 기존 값 유지
    - None이면 기존 값 삭제
    """
    try:
        user_id = 1  # 단일 사용자 환경

        # AsyncSession 쿼리 방식
        query = select(UserSettings).where(UserSettings.user_id == user_id)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            settings = UserSettings(user_id=user_id)
            db.add(settings)

        # OpenAI API 키 업데이트
        if request.openai_api_key is not None:
            if request.openai_api_key == "":
                pass  # 빈 문자열이면 기존 값 유지
            else:
                settings.openai_api_key = request.openai_api_key
                logger.info(f"[SETTINGS] OpenAI API 키 업데이트: user_id={user_id}")

        # Claude API 키 업데이트
        if request.claude_api_key is not None:
            if request.claude_api_key == "":
                pass  # 빈 문자열이면 기존 값 유지
            else:
                settings.claude_api_key = request.claude_api_key
                logger.info(f"[SETTINGS] Claude API 키 업데이트: user_id={user_id}")

        # AI 모델 업데이트
        if request.default_ai_model:
            settings.default_ai_model = request.default_ai_model

        # Blogger 시간당 발행 제한 업데이트
        if request.blogger_hourly_limit is not None:
            settings.blogger_hourly_limit = request.blogger_hourly_limit
            logger.info(
                f"[SETTINGS] Blogger 발행 제한 변경: "
                f"user_id={user_id}, limit={request.blogger_hourly_limit}"
            )

        await db.commit()
        await db.refresh(settings)

        return {
            "success": True,
            "message": "설정이 저장되었습니다",
            "data": settings.to_dict()
        }

    except Exception as e:
        await db.rollback()
        logger.error(f"[SETTINGS] 업데이트 에러: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"설정 저장 중 오류가 발생했습니다: {str(e)}",
            "data": None
        }


@router.post("/password")
async def change_password(
    request: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    비밀번호 변경

    TODO: 실제 비밀번호 검증 및 변경 로직 구현
    """
    try:
        # 현재는 미구현 - 추후 구현
        logger.info("[SETTINGS] 비밀번호 변경 요청 (미구현)")

        return {
            "success": False,
            "message": "비밀번호 변경 기능은 준비 중입니다"
        }

    except Exception as e:
        logger.error(f"[SETTINGS] 비밀번호 변경 에러: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="비밀번호 변경 중 오류가 발생했습니다"
        )


@router.get("/blogger-limit")
async def get_blogger_limit(db: AsyncSession = Depends(get_db_session)):
    """
    현재 Blogger 시간당 발행 제한값 조회

    슬롯 검증 시 사용
    """
    try:
        user_id = 1

        # AsyncSession 쿼리 방식
        query = select(UserSettings).where(UserSettings.user_id == user_id)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        limit = settings.blogger_hourly_limit if settings else 2

        return {"blogger_hourly_limit": limit}

    except Exception as e:
        logger.error(f"[SETTINGS] Blogger 제한 조회 에러: {str(e)}")
        return {"blogger_hourly_limit": 2}  # 기본값 반환
