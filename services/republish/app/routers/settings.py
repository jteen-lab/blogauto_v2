"""
설정 API 라우터

Features:
- 사용자 설정 조회/저장
- AI 서비스 API 키 관리
- 네이버 검색광고 API 관리
- Google Blogger 시간당 발행 제한 설정
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.user import User
from ..models.user_settings import UserSettings
from ..routers.auth import get_current_user
from ..services.naver_ads_service import NaverAdsService
from ..services.naver_search_service import NaverSearchService
from ..services.google_trends_service import GoogleTrendsService
from ..services.naver_datalab_service import NaverDatalabService
from ..services.google_keyword_planner_service import GoogleKeywordPlannerService

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
    gemini_api_key: Optional[str] = None
    default_ai_model: str = "gpt-4"
    blogger_hourly_limit: int = 2
    has_openai_key: bool = False
    has_claude_key: bool = False
    has_gemini_key: bool = False
    # 네이버 검색광고 API
    naver_ads_api_key: Optional[str] = None
    naver_ads_secret_key: Optional[str] = None
    naver_ads_customer_id: Optional[str] = None
    has_naver_ads_api: bool = False

    class Config:
        from_attributes = True


class SettingsUpdateRequest(BaseModel):
    """설정 업데이트 요청 스키마

    API 키 처리 규칙:
    - None: 기존 값 유지
    - 빈 문자열(""): 키 삭제 (null로 설정)
    - 새 값: 키 업데이트
    - 마스킹된 값(****포함): 기존 값 유지
    """
    openai_api_key: Optional[str] = Field(None, max_length=255)
    claude_api_key: Optional[str] = Field(None, max_length=255)
    gemini_api_key: Optional[str] = Field(None, max_length=255)
    default_ai_model: Optional[str] = Field(None, max_length=50)
    blogger_hourly_limit: Optional[int] = Field(None, ge=1, le=4)
    # Google Blogger OAuth
    blogger_client_id: Optional[str] = Field(None, max_length=255)
    blogger_client_secret: Optional[str] = Field(None, max_length=255)
    # 네이버 검색광고 API
    naver_ads_api_key: Optional[str] = Field(None, max_length=255)
    naver_ads_secret_key: Optional[str] = Field(None, max_length=255)
    naver_ads_customer_id: Optional[str] = Field(None, max_length=50)
    # 네이버 검색 API
    naver_search_client_id: Optional[str] = Field(None, max_length=255)
    naver_search_client_secret: Optional[str] = Field(None, max_length=255)
    # 네이버 데이터랩 API
    naver_datalab_client_id: Optional[str] = Field(None, max_length=255)
    naver_datalab_client_secret: Optional[str] = Field(None, max_length=255)
    # Google Keyword Planner API
    google_ads_developer_token: Optional[str] = Field(None, max_length=255)
    google_ads_client_id: Optional[str] = Field(None, max_length=255)
    google_ads_client_secret: Optional[str] = Field(None, max_length=255)
    google_ads_refresh_token: Optional[str] = Field(None, max_length=512)
    google_ads_customer_id: Optional[str] = Field(None, max_length=50)


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
            "gemini_api_key": settings.masked_gemini_key,
            "default_ai_model": settings.default_ai_model,
            "blogger_hourly_limit": settings.blogger_hourly_limit,
            # Google Blogger OAuth
            "blogger_client_id": settings.masked_blogger_client_id,
            "blogger_client_secret": settings.masked_blogger_client_secret,
            "has_blogger_oauth": settings.has_blogger_oauth,
            "has_openai_key": settings.has_openai_key,
            "has_claude_key": settings.has_claude_key,
            "has_gemini_key": settings.has_gemini_key,
            # 네이버 검색광고 API
            "naver_ads_api_key": settings.masked_naver_ads_api_key,
            "naver_ads_secret_key": settings.masked_naver_ads_secret_key,
            "naver_ads_customer_id": settings.naver_ads_customer_id,
            "has_naver_ads_api": settings.has_naver_ads_api,
            # 네이버 검색 API
            "naver_search_client_id": settings.masked_naver_search_client_id,
            "naver_search_client_secret": settings.masked_naver_search_client_secret,
            "has_naver_search_api": settings.has_naver_search_api,
            # 네이버 데이터랩 API
            "naver_datalab_client_id": settings.masked_naver_datalab_client_id,
            "naver_datalab_client_secret": settings.masked_naver_datalab_client_secret,
            "has_naver_datalab_api": settings.has_naver_datalab_api,
            # Google Keyword Planner API
            "google_ads_developer_token": settings.masked_google_ads_developer_token,
            "google_ads_client_id": settings.masked_google_ads_client_id,
            "google_ads_client_secret": settings.masked_google_ads_client_secret,
            "google_ads_refresh_token": settings.masked_google_ads_refresh_token,
            "google_ads_customer_id": settings.google_ads_customer_id,
            "has_google_keyword_planner_api": settings.has_google_keyword_planner_api
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

    API 키 처리 규칙:
    - None (payload에 없음): 기존 값 유지
    - 빈 문자열(""): 키 삭제 (null로 설정)
    - 마스킹된 값(****포함): 기존 값 유지
    - 새 값: 키 업데이트
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

        # 마스킹된 키인지 확인하는 헬퍼 함수
        def is_masked_key(key: Optional[str]) -> bool:
            return key is not None and "****" in key

        # OpenAI API 키 업데이트
        if request.openai_api_key is not None:
            logger.debug(f"[SETTINGS] OpenAI 키 요청값: '{request.openai_api_key}' (길이: {len(request.openai_api_key)})")
            if is_masked_key(request.openai_api_key):
                logger.debug(f"[SETTINGS] OpenAI 키: 마스킹된 값 - 기존 값 유지")
            elif request.openai_api_key == "":
                settings.openai_api_key = None  # 빈 문자열이면 키 삭제
                logger.info(f"[SETTINGS] OpenAI API 키 삭제: user_id={user_id}")
            else:
                settings.openai_api_key = request.openai_api_key
                logger.info(f"[SETTINGS] OpenAI API 키 업데이트: user_id={user_id}")

        # Claude API 키 업데이트
        if request.claude_api_key is not None:
            logger.debug(f"[SETTINGS] Claude 키 요청값: '{request.claude_api_key}' (길이: {len(request.claude_api_key)})")
            if is_masked_key(request.claude_api_key):
                logger.debug(f"[SETTINGS] Claude 키: 마스킹된 값 - 기존 값 유지")
            elif request.claude_api_key == "":
                settings.claude_api_key = None  # 빈 문자열이면 키 삭제
                logger.info(f"[SETTINGS] Claude API 키 삭제: user_id={user_id}")
            else:
                settings.claude_api_key = request.claude_api_key
                logger.info(f"[SETTINGS] Claude API 키 업데이트: user_id={user_id}")

        # Gemini API 키 업데이트
        if request.gemini_api_key is not None:
            logger.debug(f"[SETTINGS] Gemini 키 요청값: '{request.gemini_api_key}' (길이: {len(request.gemini_api_key)})")
            if is_masked_key(request.gemini_api_key):
                logger.debug(f"[SETTINGS] Gemini 키: 마스킹된 값 - 기존 값 유지")
            elif request.gemini_api_key == "":
                settings.gemini_api_key = None  # 빈 문자열이면 키 삭제
                logger.info(f"[SETTINGS] Gemini API 키 삭제: user_id={user_id}")
            else:
                settings.gemini_api_key = request.gemini_api_key
                logger.info(f"[SETTINGS] Gemini API 키 업데이트: user_id={user_id}")

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

        # 네이버 검색광고 API 키 업데이트
        if request.naver_ads_api_key is not None and request.naver_ads_api_key != "":
            settings.naver_ads_api_key = request.naver_ads_api_key
            logger.info(f"[SETTINGS] 네이버 검색광고 API 키 업데이트: user_id={user_id}")

        if request.naver_ads_secret_key is not None and request.naver_ads_secret_key != "":
            settings.naver_ads_secret_key = request.naver_ads_secret_key
            logger.info(f"[SETTINGS] 네이버 검색광고 Secret 키 업데이트: user_id={user_id}")

        if request.naver_ads_customer_id is not None:
            settings.naver_ads_customer_id = request.naver_ads_customer_id
            logger.info(f"[SETTINGS] 네이버 검색광고 고객 ID 업데이트: user_id={user_id}")

        # 네이버 검색 API 키 업데이트
        if request.naver_search_client_id is not None and request.naver_search_client_id != "":
            settings.naver_search_client_id = request.naver_search_client_id
            logger.info(f"[SETTINGS] 네이버 검색 Client ID 업데이트: user_id={user_id}")

        if request.naver_search_client_secret is not None and request.naver_search_client_secret != "":
            settings.naver_search_client_secret = request.naver_search_client_secret
            logger.info(f"[SETTINGS] 네이버 검색 Client Secret 업데이트: user_id={user_id}")

        # 네이버 데이터랩 API 키 업데이트
        if request.naver_datalab_client_id is not None and request.naver_datalab_client_id != "":
            settings.naver_datalab_client_id = request.naver_datalab_client_id
            logger.info(f"[SETTINGS] 네이버 데이터랩 Client ID 업데이트: user_id={user_id}")

        if request.naver_datalab_client_secret is not None and request.naver_datalab_client_secret != "":
            settings.naver_datalab_client_secret = request.naver_datalab_client_secret
            logger.info(f"[SETTINGS] 네이버 데이터랩 Client Secret 업데이트: user_id={user_id}")

        # Google Blogger OAuth 업데이트
        if request.blogger_client_id is not None and request.blogger_client_id != "":
            if "****" not in request.blogger_client_id:
                settings.blogger_client_id = request.blogger_client_id
                logger.info(f"[SETTINGS] Blogger Client ID 업데이트: user_id={user_id}")
        elif request.blogger_client_id == "":
            settings.blogger_client_id = None

        if request.blogger_client_secret is not None and request.blogger_client_secret != "":
            if "****" not in request.blogger_client_secret:
                settings.blogger_client_secret = request.blogger_client_secret
                logger.info(f"[SETTINGS] Blogger Client Secret 업데이트: user_id={user_id}")
        elif request.blogger_client_secret == "":
            settings.blogger_client_secret = None

        # Google Keyword Planner API 키 업데이트
        if request.google_ads_developer_token is not None and request.google_ads_developer_token != "":
            settings.google_ads_developer_token = request.google_ads_developer_token
            logger.info(f"[SETTINGS] Google Ads Developer Token 업데이트: user_id={user_id}")

        if request.google_ads_client_id is not None and request.google_ads_client_id != "":
            settings.google_ads_client_id = request.google_ads_client_id
            logger.info(f"[SETTINGS] Google Ads Client ID 업데이트: user_id={user_id}")

        if request.google_ads_client_secret is not None and request.google_ads_client_secret != "":
            settings.google_ads_client_secret = request.google_ads_client_secret
            logger.info(f"[SETTINGS] Google Ads Client Secret 업데이트: user_id={user_id}")

        if request.google_ads_refresh_token is not None and request.google_ads_refresh_token != "":
            settings.google_ads_refresh_token = request.google_ads_refresh_token
            logger.info(f"[SETTINGS] Google Ads Refresh Token 업데이트: user_id={user_id}")

        if request.google_ads_customer_id is not None:
            settings.google_ads_customer_id = request.google_ads_customer_id
            logger.info(f"[SETTINGS] Google Ads Customer ID 업데이트: user_id={user_id}")

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


# ============================================================
# F10: 문의 폼 전용 구글 계정(A) 자격
# ============================================================

class FormsAccountRequest(BaseModel):
    """문의 폼 전용 계정 refresh token 저장 요청."""

    refresh_token: str = Field(..., min_length=10)
    email: Optional[str] = None


@router.get("/forms-account")
async def get_forms_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """문의 폼 전용 계정 설정 상태 조회(토큰 값은 노출하지 않음)."""
    from ..services.system_settings_service import SystemSettingsService
    from ..services.publishing.google_forms_service import (
        SETTING_FORMS_REFRESH_TOKEN, SETTING_FORMS_EMAIL,
    )
    token = await SystemSettingsService.get(SETTING_FORMS_REFRESH_TOKEN, db)
    email = await SystemSettingsService.get(SETTING_FORMS_EMAIL, db)
    return {"configured": bool(token), "email": email or ""}


@router.post("/forms-account")
async def save_forms_account(
    request: FormsAccountRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """문의 폼 전용 계정의 refresh token을 암호화 저장한다(F10).

    OAuth Playground 등에서 계정 A로 Forms 스코프 인증 후 발급받은 refresh
    token을 붙여넣는다. blogauto가 이 토큰으로 Forms API를 호출한다.
    """
    from ..core.encryption import encrypt_api_key
    from ..services.system_settings_service import SystemSettingsService
    from ..services.publishing.google_forms_service import (
        SETTING_FORMS_REFRESH_TOKEN, SETTING_FORMS_EMAIL,
    )
    await SystemSettingsService.set(
        SETTING_FORMS_REFRESH_TOKEN, encrypt_api_key(request.refresh_token.strip()), db,
    )
    if request.email:
        await SystemSettingsService.set(SETTING_FORMS_EMAIL, request.email.strip(), db)
    await db.commit()
    logger.info("[SETTINGS] 문의 폼 전용 계정 저장 | email=%s", request.email or "")
    return {"success": True, "configured": True, "email": request.email or ""}


# ============================================================
# 네이버 검색 API (블로그 검색)
# ============================================================

naver_search_router = APIRouter(prefix="/naver-search", tags=["네이버 검색"])


@naver_search_router.post("/test")
async def test_naver_search_connection(db: AsyncSession = Depends(get_db_session)):
    """
    네이버 검색 API 연결 테스트

    저장된 API 키로 테스트 요청을 보내 연결 상태 확인
    """
    try:
        # AsyncSession으로 설정 조회
        query = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            return {
                "success": False,
                "error": "설정을 찾을 수 없습니다"
            }

        # 서비스 인스턴스 생성
        service = NaverSearchService(settings)

        if not service.is_configured():
            return {
                "success": False,
                "error": "API 키가 설정되지 않았습니다"
            }

        # 비동기 테스트 실행
        test_result = await service.test_connection()

        logger.info(
            f"[NAVER_SEARCH] 연결 테스트: "
            f"success={test_result.get('success')}"
        )

        return test_result

    except Exception as e:
        logger.error(f"[NAVER_SEARCH] 연결 테스트 에러: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


@naver_search_router.post("/blog")
async def search_blog(
    query: str,
    display: int = 10,
    start: int = 1,
    sort: str = "sim",
    db: AsyncSession = Depends(get_db_session)
):
    """
    블로그 검색

    Args:
        query: 검색어
        display: 결과 개수 (1~100)
        start: 시작 위치 (1~1000)
        sort: 정렬 (sim: 정확도, date: 날짜)

    Returns:
        검색 결과 목록
    """
    try:
        query_stmt = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query_stmt)
        settings = result.scalar_one_or_none()

        if not settings:
            return {"success": False, "error": "설정을 찾을 수 없습니다"}

        service = NaverSearchService(settings)

        if not service.is_configured():
            return {"success": False, "error": "API 키가 설정되지 않았습니다"}

        search_result = await service.search_blog(query, display, start, sort)

        logger.info(
            f"[NAVER_SEARCH] 블로그 검색: query={query}, "
            f"results={search_result.get('display', 0)}"
        )

        return search_result

    except Exception as e:
        logger.error(f"[NAVER_SEARCH] 블로그 검색 에러: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e)}


# ============================================================
# 네이버 검색광고 API
# ============================================================

naver_ads_router = APIRouter(prefix="/naver-ads", tags=["네이버 검색광고"])


@naver_ads_router.post("/test")
async def test_naver_ads_connection(db: AsyncSession = Depends(get_db_session)):
    """
    네이버 검색광고 API 연결 테스트

    저장된 API 키로 테스트 요청을 보내 연결 상태 확인
    """
    try:
        # AsyncSession으로 설정 조회
        query = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            return {
                "success": False,
                "error": "설정을 찾을 수 없습니다"
            }

        # 서비스 인스턴스 생성 (설정 객체 전달)
        service = NaverAdsService(settings)

        if not service.is_configured():
            return {
                "success": False,
                "error": "API 키가 설정되지 않았습니다"
            }

        # 비동기 테스트 실행
        test_result = await service.test_connection()

        logger.info(
            f"[NAVER_ADS] 연결 테스트: "
            f"success={test_result.get('success')}"
        )

        return test_result

    except Exception as e:
        logger.error(f"[NAVER_ADS] 연결 테스트 에러: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


@naver_ads_router.post("/keywords")
async def get_keyword_stats(
    keywords: list[str],
    db: AsyncSession = Depends(get_db_session)
):
    """
    키워드 검색량 조회

    Args:
        keywords: 조회할 키워드 목록 (최대 5개)

    Returns:
        키워드별 검색량 및 연관 키워드
    """
    try:
        # AsyncSession으로 설정 조회
        query = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            return {
                "success": False,
                "error": "설정을 찾을 수 없습니다"
            }

        service = NaverAdsService(settings)

        if not service.is_configured():
            return {
                "success": False,
                "error": "API 키가 설정되지 않았습니다"
            }

        keyword_result = await service.get_keyword_stats(keywords)

        logger.info(
            f"[NAVER_ADS] 키워드 조회: "
            f"keywords={keywords}, result_count={len(keyword_result.get('keywords', []))}"
        )

        return keyword_result

    except Exception as e:
        logger.error(f"[NAVER_ADS] 키워드 조회 에러: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================
# 구글 트렌드 API
# ============================================================

google_trends_router = APIRouter(prefix="/google-trends", tags=["구글 트렌드"])


@google_trends_router.post("/test")
async def test_google_trends_connection():
    """
    구글 트렌드 API 연결 테스트

    pytrends는 인증이 필요 없어 바로 테스트 가능
    """
    try:
        service = GoogleTrendsService()
        test_result = await service.test_connection()

        logger.info(
            f"[GOOGLE_TRENDS] 연결 테스트: "
            f"success={test_result.get('success')}"
        )

        return test_result

    except Exception as e:
        logger.error(f"[GOOGLE_TRENDS] 연결 테스트 에러: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


@google_trends_router.post("/trending")
async def get_trending_searches(country: str = "south_korea"):
    """
    실시간 인기 검색어 조회

    Args:
        country: 국가 코드 (south_korea, united_states 등)

    Returns:
        인기 검색어 목록
    """
    try:
        service = GoogleTrendsService()
        result = await service.get_trending_searches(country=country)

        logger.info(
            f"[GOOGLE_TRENDS] 인기 검색어 조회: "
            f"country={country}, count={len(result.get('trending', []))}"
        )

        return result

    except Exception as e:
        logger.error(f"[GOOGLE_TRENDS] 인기 검색어 조회 에러: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


class GoogleTrendsRelatedRequest(BaseModel):
    """구글 트렌드 연관 검색어 요청"""
    keywords: list[str]
    timeframe: str = "today 12-m"
    geo: str = "KR"


@google_trends_router.post("/related")
async def get_related_queries(request: GoogleTrendsRelatedRequest):
    """
    연관 검색어 조회

    Args:
        keywords: 검색 키워드 목록 (최대 5개)
        timeframe: 기간
        geo: 지역 코드

    Returns:
        연관 검색어 및 급상승 검색어
    """
    try:
        service = GoogleTrendsService()
        result = await service.get_related_queries(
            keywords=request.keywords,
            timeframe=request.timeframe,
            geo=request.geo
        )

        logger.info(
            f"[GOOGLE_TRENDS] 연관 검색어 조회: "
            f"keywords={request.keywords}, count={len(result.get('keywords', []))}"
        )

        return result

    except Exception as e:
        logger.error(f"[GOOGLE_TRENDS] 연관 검색어 조회 에러: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================
# 네이버 데이터랩 API
# ============================================================

naver_datalab_router = APIRouter(prefix="/naver-datalab", tags=["네이버 데이터랩"])


@naver_datalab_router.post("/test")
async def test_naver_datalab_connection(db: AsyncSession = Depends(get_db_session)):
    """
    네이버 데이터랩 API 연결 테스트

    저장된 API 키로 테스트 요청을 보내 연결 상태 확인
    """
    try:
        # AsyncSession으로 설정 조회
        query = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            return {
                "success": False,
                "error": "설정을 찾을 수 없습니다"
            }

        # 서비스 인스턴스 생성 (설정 객체 전달)
        service = NaverDatalabService(settings)

        if not service.is_configured():
            return {
                "success": False,
                "error": "API 키가 설정되지 않았습니다"
            }

        # 비동기 테스트 실행
        test_result = await service.test_connection()

        logger.info(
            f"[NAVER_DATALAB] 연결 테스트: "
            f"success={test_result.get('success')}"
        )

        return test_result

    except Exception as e:
        logger.error(f"[NAVER_DATALAB] 연결 테스트 에러: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


class NaverDatalabTrendRequest(BaseModel):
    """네이버 데이터랩 트렌드 요청"""
    keywords: list[str]
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    time_unit: str = "month"


@naver_datalab_router.post("/trend")
async def get_search_trend(
    request: NaverDatalabTrendRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    검색어 트렌드 조회

    Args:
        keywords: 조회할 키워드 목록 (최대 5개)
        start_date: 시작일 (YYYY-MM-DD)
        end_date: 종료일 (YYYY-MM-DD)
        time_unit: 구간 단위 (date, week, month)

    Returns:
        검색어별 트렌드 데이터
    """
    try:
        # AsyncSession으로 설정 조회
        query = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            return {
                "success": False,
                "error": "설정을 찾을 수 없습니다"
            }

        service = NaverDatalabService(settings)

        if not service.is_configured():
            return {
                "success": False,
                "error": "API 키가 설정되지 않았습니다"
            }

        trend_result = await service.get_search_trend(
            keywords=request.keywords,
            start_date=request.start_date,
            end_date=request.end_date,
            time_unit=request.time_unit
        )

        logger.info(
            f"[NAVER_DATALAB] 트렌드 조회: "
            f"keywords={request.keywords}, result_count={len(trend_result.get('trends', []))}"
        )

        return trend_result

    except Exception as e:
        logger.error(f"[NAVER_DATALAB] 트렌드 조회 에러: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================
# Google Keyword Planner API
# ============================================================

google_keyword_planner_router = APIRouter(
    prefix="/google-keyword-planner",
    tags=["구글 키워드 플래너"]
)


@google_keyword_planner_router.post("/test")
async def test_google_keyword_planner_connection(
    db: AsyncSession = Depends(get_db_session)
):
    """
    Google Keyword Planner API 연결 테스트

    저장된 API 키로 테스트 요청을 보내 연결 상태 확인
    """
    try:
        # AsyncSession으로 설정 조회
        query = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            return {
                "success": False,
                "error": "설정을 찾을 수 없습니다"
            }

        # 서비스 인스턴스 생성
        service = GoogleKeywordPlannerService(settings)

        if not service.is_configured():
            return {
                "success": False,
                "error": "API 키가 설정되지 않았습니다"
            }

        # 연결 테스트 실행
        test_result = await service.test_connection()

        logger.info(
            f"[GOOGLE_PLANNER] 연결 테스트: "
            f"success={test_result.get('success')}"
        )

        return test_result

    except Exception as e:
        logger.error(f"[GOOGLE_PLANNER] 연결 테스트 에러: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


class GoogleKeywordPlannerRequest(BaseModel):
    """구글 키워드 플래너 요청"""
    keywords: list[str]
    language_id: str = "1012"  # 한국어
    location_ids: list[str] = ["2410"]  # 한국


@google_keyword_planner_router.post("/keywords")
async def get_keyword_ideas(
    request: GoogleKeywordPlannerRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    키워드 아이디어 조회

    Args:
        keywords: 시드 키워드 목록
        language_id: 언어 ID (기본: 1012=한국어)
        location_ids: 지역 ID 목록 (기본: 2410=한국)

    Returns:
        키워드 아이디어 및 검색량 데이터
    """
    try:
        # AsyncSession으로 설정 조회
        query = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            return {
                "success": False,
                "error": "설정을 찾을 수 없습니다"
            }

        service = GoogleKeywordPlannerService(settings)

        if not service.is_configured():
            return {
                "success": False,
                "error": "API 키가 설정되지 않았습니다"
            }

        keyword_result = await service.get_keyword_ideas(
            keywords=request.keywords,
            language_id=request.language_id,
            location_ids=request.location_ids
        )

        logger.info(
            f"[GOOGLE_PLANNER] 키워드 조회: "
            f"keywords={request.keywords}, "
            f"result_count={len(keyword_result.get('keywords', []))}"
        )

        return keyword_result

    except Exception as e:
        logger.error(f"[GOOGLE_PLANNER] 키워드 조회 에러: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================
# API 상태 확인 엔드포인트 (수집 모듈용)
# ============================================================

@router.get("/api-status")
async def get_api_status(db: AsyncSession = Depends(get_db_session)):
    """
    모든 API 설정 상태 조회

    수집 모듈에서 각 데이터 소스의 활성화 여부를 확인하는 데 사용
    """
    try:
        # AsyncSession으로 설정 조회
        query = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            return {
                "naver_ads": False,
                "naver_datalab": False,
                "google_trends": True,  # 인증 불필요
                "google_planner": False,
                "naver_news": False,
                "google_news": True  # 인증 불필요 (RSS)
            }

        return {
            "naver_ads": settings.has_naver_ads_api,
            "naver_datalab": settings.has_naver_datalab_api,
            "google_trends": True,  # pytrends는 인증 불필요
            "google_planner": settings.has_google_keyword_planner_api,
            "naver_news": settings.has_naver_search_api,  # 네이버 검색 API 사용
            "google_news": True  # RSS는 인증 불필요
        }

    except Exception as e:
        logger.error(f"[SETTINGS] API 상태 조회 에러: {str(e)}", exc_info=True)
        return {
            "naver_ads": False,
            "naver_datalab": False,
            "google_trends": True,
            "google_planner": False,
            "naver_news": False,
            "google_news": True
        }


# ============================================================
# 시스템 설정 API (Celery, Rate Limit)
# ============================================================

system_settings_router = APIRouter(prefix="/system-settings", tags=["시스템 설정"])


@system_settings_router.get("")
async def get_system_settings(
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
):
    """시스템 설정 ���체 조회."""
    from ..services.system_settings_service import SystemSettingsService
    return await SystemSettingsService.get_all(db)


@system_settings_router.put("")
async def update_system_settings(
    updates: dict,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
):
    """시스템 설정 업데이트."""
    from ..services.system_settings_service import SystemSettingsService
    try:
        await SystemSettingsService.set_many(updates, db)
        return {"success": True, "message": "시스템 설정이 저장되었습니다"}
    except Exception as e:
        logger.error(f"[SETTINGS] 시스템 설정 저장 에러: {e}")
        return {"success": False, "message": str(e)}
