"""
카테고리 관리 API 엔드포인트

Features:
- 3계층 카테고리 CRUD 작업
- 블로그-카테고리 연결 관리
- 계층적 데이터 조회
- 요청 검증 및 응답
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..core.database import get_db_session
from ..services.category_service import CategoryService
from ..schemas.category import (
    TopicCreateRequest, TopicUpdateRequest, TopicResponse,
    SubTopicCreateRequest, SubTopicUpdateRequest, SubTopicResponse,
    KeywordCreateRequest, KeywordUpdateRequest, KeywordResponse,
    BlogCategoryCreateRequest, BlogCategoryUpdateRequest, BlogCategoryResponse,
    CategoryTreeResponse, CategoryStatsResponse,
    ErrorResponse
)
from ..models.user import User
from ..core.logger import get_logger
from .auth import get_current_user

logger = get_logger("category_router", "category.log")
templates = Jinja2Templates(directory="app/templates")

router = APIRouter(prefix="/categories", tags=["카테고리 관리"])
page_router = APIRouter(tags=["카테고리 페이지"])

# 응답 예시
responses = {
    400: {"model": ErrorResponse, "description": "잘못된 요청"},
    401: {"model": ErrorResponse, "description": "인증 실패"},
    404: {"model": ErrorResponse, "description": "리소스 없음"},
    500: {"model": ErrorResponse, "description": "서버 내부 오류"}
}


# =================================
# Topic (주제) API 엔드포인트
# =================================

@router.post(
    "/topics",
    response_model=TopicResponse,
    status_code=status.HTTP_201_CREATED,
    summary="주제 생성",
    description="새 주제를 생성합니다",
    responses=responses
)
async def create_topic(
    request: TopicCreateRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> TopicResponse:
    """주제 생성"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"주제 생성 API 요청 | 사용자={current_user.id} | IP={client_ip}")

    category_service = CategoryService(db)
    return await category_service.create_topic(current_user, request)


@router.get(
    "/topics",
    response_model=List[TopicResponse],
    summary="주제 목록 조회",
    description="사용자의 주제 목록을 조회합니다",
    responses=responses
)
async def get_topics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> List[TopicResponse]:
    """주제 목록 조회"""
    category_service = CategoryService(db)
    return await category_service.get_user_topics(current_user)


@router.get(
    "/topics/{topic_id}",
    response_model=TopicResponse,
    summary="주제 상세 조회",
    description="특정 주제의 상세 정보를 조회합니다",
    responses=responses
)
async def get_topic(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> TopicResponse:
    """주제 상세 조회"""
    category_service = CategoryService(db)
    return await category_service.get_topic_by_id(current_user, topic_id)


@router.put(
    "/topics/{topic_id}",
    response_model=TopicResponse,
    summary="주제 수정",
    description="주제 정보를 수정합니다",
    responses=responses
)
async def update_topic(
    topic_id: int,
    request: TopicUpdateRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> TopicResponse:
    """주제 수정"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"주제 수정 API 요청 | 주제ID={topic_id} | 사용자={current_user.id} | IP={client_ip}")

    category_service = CategoryService(db)
    return await category_service.update_topic(current_user, topic_id, request)


@router.delete(
    "/topics/{topic_id}",
    summary="주제 삭제",
    description="주제를 삭제합니다 (소프트 삭제)",
    responses={
        **responses,
        200: {"description": "삭제 성공"}
    }
)
async def delete_topic(
    topic_id: int,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> dict:
    """주제 삭제"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"주제 삭제 API 요청 | 주제ID={topic_id} | 사용자={current_user.id} | IP={client_ip}")

    category_service = CategoryService(db)
    return await category_service.delete_topic(current_user, topic_id)


# =================================
# SubTopic (하위 주제) API 엔드포인트
# =================================

@router.post(
    "/subtopics",
    response_model=SubTopicResponse,
    status_code=status.HTTP_201_CREATED,
    summary="하위 주제 생성",
    description="새 하위 주제를 생성합니다",
    responses=responses
)
async def create_subtopic(
    request: SubTopicCreateRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> SubTopicResponse:
    """하위 주제 생성"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"하위 주제 생성 API 요청 | 사용자={current_user.id} | IP={client_ip}")

    category_service = CategoryService(db)
    return await category_service.create_subtopic(current_user, request)


@router.get(
    "/topics/{topic_id}/subtopics",
    response_model=List[SubTopicResponse],
    summary="하위 주제 목록 조회",
    description="특정 주제의 하위 주제 목록을 조회합니다",
    responses=responses
)
async def get_subtopics_by_topic(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> List[SubTopicResponse]:
    """하위 주제 목록 조회"""
    category_service = CategoryService(db)
    return await category_service.get_subtopics_by_topic(current_user, topic_id)


# =================================
# Keyword (키워드) API 엔드포인트
# =================================

@router.post(
    "/keywords",
    response_model=KeywordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="키워드 생성",
    description="새 키워드를 생성합니다",
    responses=responses
)
async def create_keyword(
    request: KeywordCreateRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> KeywordResponse:
    """키워드 생성"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"키워드 생성 API 요청 | 사용자={current_user.id} | IP={client_ip}")

    category_service = CategoryService(db)
    return await category_service.create_keyword(current_user, request)


@router.get(
    "/subtopics/{subtopic_id}/keywords",
    response_model=List[KeywordResponse],
    summary="키워드 목록 조회",
    description="특정 하위 주제의 키워드 목록을 조회합니다",
    responses=responses
)
async def get_keywords_by_subtopic(
    subtopic_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> List[KeywordResponse]:
    """키워드 목록 조회"""
    category_service = CategoryService(db)
    return await category_service.get_keywords_by_subtopic(current_user, subtopic_id)


# =================================
# 계층적 조회 API 엔드포인트
# =================================

@router.get(
    "/tree",
    response_model=List[CategoryTreeResponse],
    summary="카테고리 트리 조회",
    description="계층적 카테고리 구조를 조회합니다",
    responses=responses
)
async def get_category_tree(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> List[CategoryTreeResponse]:
    """카테고리 트리 조회"""
    category_service = CategoryService(db)
    return await category_service.get_category_tree(current_user)


@router.get(
    "/stats",
    response_model=CategoryStatsResponse,
    summary="카테고리 통계 조회",
    description="사용자의 카테고리 통계를 조회합니다",
    responses=responses
)
async def get_category_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> CategoryStatsResponse:
    """카테고리 통계 조회"""
    category_service = CategoryService(db)
    return await category_service.get_category_stats(current_user)


# =================================
# 페이지 라우터 (HTML 응답)
# =================================

@page_router.get("/categories", response_class=HTMLResponse)
async def categories_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """카테고리 관리 페이지"""
    try:
        category_service = CategoryService(db)
        topics = await category_service.get_user_topics(current_user)
        stats = await category_service.get_category_stats(current_user)

        # Pydantic 객체를 딕셔너리로 변환 (JSON 직렬화를 위해)
        topics_dict = [topic.model_dump() for topic in topics]

        return templates.TemplateResponse(
            "categories/manage.html",
            {
                "request": request,
                "user": current_user,
                "topics": topics,  # HTML 렌더링용
                "topics_dict": topics_dict,  # JSON 직렬화용
                "stats": stats
            }
        )
    except Exception as e:
        logger.error(f"카테고리 관리 페이지 오류 | 사용자={current_user.id} | 오류={e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "카테고리 정보를 불러올 수 없습니다"
            }
        )


@page_router.get("/categories/tree", response_class=HTMLResponse)
async def categories_tree_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """카테고리 트리 보기 페이지"""
    try:
        category_service = CategoryService(db)
        tree = await category_service.get_category_tree(current_user)
        stats = await category_service.get_category_stats(current_user)

        return templates.TemplateResponse(
            "categories/tree.html",
            {
                "request": request,
                "user": current_user,
                "tree": tree,
                "stats": stats
            }
        )
    except Exception as e:
        logger.error(f"카테고리 트리 페이지 오류 | 사용자={current_user.id} | 오류={e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "카테고리 트리를 불러올 수 없습니다"
            }
        )


# =================================
# 유틸리티 함수
# =================================

def _get_client_ip(request: Request) -> str:
    """클라이언트 IP 추출"""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"
