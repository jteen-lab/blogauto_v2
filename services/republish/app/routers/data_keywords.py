"""
키워드 데이터 관리 API

Features:
- 수집 키워드 통계(정본 keyword_candidates)
- CollectedKeyword 조회
- 대량 등록 (bulk)
- 엑셀 업로드
- 페이지네이션, 검색
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from pydantic import BaseModel
from datetime import datetime
import io

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.keyword import CollectedKeyword, KeywordCategory
from ..models.keyword_candidate import KeywordCandidate
from ..models.category import Topic, SubTopic
from ..models.user import User
from ..routers.auth import get_current_user

router = APIRouter(prefix="/data/keywords", tags=["data-keywords"])
logger = get_logger("data_keywords", "app.log")


# Pydantic Schemas


class BulkKeywordCreate(BaseModel):
    """대량 키워드 등록"""
    keywords: List[str]


class BulkKeywordDelete(BaseModel):
    """대량 키워드 삭제"""
    ids: List[int]



class KeywordListResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    size: int
    has_next: bool


class CollectedKeywordResponse(BaseModel):
    id: int
    keyword: str
    seed_keyword_id: int
    seed_keyword: Optional[str] = None
    search_volume: Optional[int] = None
    competition: Optional[float] = None
    is_processed: bool
    process_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class CollectedListResponse(BaseModel):
    items: List[CollectedKeywordResponse]
    total: int
    page: int
    size: int
    has_next: bool


# API Endpoints
@router.get("/collected", response_model=CollectedListResponse)
async def list_collected_keywords(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    seed_keyword_id: Optional[int] = Query(None),
    is_processed: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """수집된 키워드 목록 조회"""
    query = select(CollectedKeyword)

    if search:
        query = query.where(CollectedKeyword.keyword.ilike(f"%{search}%"))
    if seed_keyword_id:
        query = query.where(CollectedKeyword.seed_keyword_id == seed_keyword_id)
    if is_processed is not None:
        query = query.where(CollectedKeyword.is_processed == is_processed)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(CollectedKeyword.created_at.desc())
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    keywords = result.scalars().all()

    items = []
    for kw in keywords:
        item = CollectedKeywordResponse.model_validate(kw)
        seed = None   # 시드 테이블 폐기 — 정본으로 일원화됨
        item.seed_keyword = seed.keyword if seed else None
        items.append(item)

    return CollectedListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        has_next=(page * size) < total
    )


@router.get("/stats")
async def get_keyword_stats(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """키워드 통계 — 정본(keyword_candidates) 기준.

    시드 테이블을 걷어내면서 집계 대상도 옮겼다. 키를 `seed` 로 둔 것은
    화면이 그 이름을 쓰고 있어서다(탭 카운트).
    """
    total = (await db.execute(
        select(func.count()).select_from(KeywordCandidate)
        .where(KeywordCandidate.user_id == current_user.id)
    )).scalar() or 0

    active = (await db.execute(
        select(func.count()).select_from(KeywordCandidate).where(
            KeywordCandidate.user_id == current_user.id,
            KeywordCandidate.is_active.is_(True))
    )).scalar() or 0

    collected_total = (await db.execute(
        select(func.count()).select_from(CollectedKeyword)
    )).scalar() or 0

    collected_processed = (await db.execute(
        select(func.count()).select_from(CollectedKeyword)
        .where(CollectedKeyword.is_processed == True)  # noqa: E712
    )).scalar() or 0

    return {
        "seed": {"total": total, "active": active},
        "collected": {"total": collected_total,
                      "processed": collected_processed},
    }


class CollectRequest(BaseModel):
    """키워드 수집 요청"""
    sources: Optional[List[str]] = None  # ['google_trends', 'naver_datalab', 'naver_ads']


@router.post("/collect")
async def collect_keywords(
    request: CollectRequest = CollectRequest(),
    db: AsyncSession = Depends(get_db_session)
):
    """
    API에서 트렌딩 키워드 자동 수집

    각 소스에서 실시간 인기/트렌딩 키워드를 수집하여
    CollectedKeyword 테이블에 저장합니다.

    Args:
        sources: 수집할 소스 목록
            - google_trends: 구글 트렌드 (인증 불필요)
            - naver_datalab: 네이버 데이터랩 (API 키 필요)
            - naver_ads: 네이버 광고 도구 (API 키 필요)

    Returns:
        소스별 수집 결과
    """
    from ..models.user_settings import UserSettings
    from ..services.keyword_collector_service import KeywordCollectorService

    try:
        # 사용자 설정 조회
        query = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            settings = UserSettings(user_id=1)
            db.add(settings)
            await db.commit()

        # 수집 서비스 실행
        collector = KeywordCollectorService(db, settings)
        collect_result = await collector.collect_all(request.sources)

        logger.info(
            f"[COLLECT] 완료: "
            f"total_collected={collect_result.get('total_collected', 0)}, "
            f"total_saved={collect_result.get('total_saved', 0)}"
        )

        return collect_result

    except Exception as e:
        logger.error(f"[COLLECT] 에러: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collect/{source}")
async def collect_keywords_from_source(
    source: str,
    db: AsyncSession = Depends(get_db_session)
):
    """
    특정 소스에서만 키워드 수집

    Args:
        source: 수집 소스 (google_trends, naver_datalab, naver_ads)

    Returns:
        수집 결과
    """
    from ..models.user_settings import UserSettings
    from ..services.keyword_collector_service import KeywordCollectorService

    valid_sources = ['google_trends', 'naver_datalab', 'naver_ads']
    if source not in valid_sources:
        raise HTTPException(
            status_code=400,
            detail=f"유효하지 않은 소스입니다. 사용 가능: {valid_sources}"
        )

    try:
        query = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            settings = UserSettings(user_id=1)
            db.add(settings)
            await db.commit()

        collector = KeywordCollectorService(db, settings)

        if source == 'google_trends':
            collect_result = await collector.collect_from_google_trends()
        elif source == 'naver_datalab':
            collect_result = await collector.collect_from_naver_datalab()
        elif source == 'naver_ads':
            collect_result = await collector.collect_from_naver_ads()

        logger.info(
            f"[COLLECT:{source}] 완료: "
            f"collected={collect_result.get('collected', 0)}, "
            f"saved={collect_result.get('saved', 0)}"
        )

        return collect_result

    except Exception as e:
        logger.error(f"[COLLECT:{source}] 에러: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 키워드 추출 (제목에서 키워드 추출)
# ============================================================

class ExtractKeywordsRequest(BaseModel):
    """키워드 추출 요청"""
    title_limit: int = 100  # 분석할 제목 수
    keyword_limit: int = 50  # 추출할 키워드 수
    method: str = "all"  # konlpy, tfidf, ngram, all
    title_status: str = "new"  # 처리할 제목 상태


@router.post("/extract")
async def extract_keywords_from_titles(
    request: ExtractKeywordsRequest = ExtractKeywordsRequest(),
    db: AsyncSession = Depends(get_db_session)
):
    """
    임시 제목에서 키워드 추출

    TempTitle 테이블에서 지정 수량의 제목을 선정하여
    키워드를 추출하고 정본(keyword_candidates)에 저장합니다.

    추출 방법:
    - konlpy: KoNLPy 형태소 분석 (명사 추출)
    - tfidf: TF-IDF 기반 핵심 키워드
    - ngram: N-gram 빈도 분석
    - all: 모든 방법 통합 (기본값)

    Args:
        title_limit: 분석할 제목 수 (기본 100)
        keyword_limit: 추출할 키워드 수 (기본 50)
        method: 추출 방법 (기본 all)
        title_status: 처리할 제목 상태 (기본 new)

    Returns:
        추출 및 저장 결과
    """
    from ..services.keyword_extractor_service import KeywordExtractorService

    try:
        extractor = KeywordExtractorService(db)

        result = await extractor.extract_and_save_keywords(
            title_limit=request.title_limit,
            keyword_limit=request.keyword_limit,
            method=request.method,
            title_status=request.title_status
        )

        logger.info(
            f"[EXTRACT] 완료: "
            f"titles={result.get('titles_processed', 0)}, "
            f"extracted={result.get('keywords_extracted', 0)}, "
            f"saved={result.get('keywords_saved', 0)}"
        )

        return result

    except Exception as e:
        logger.error(f"[EXTRACT] 에러: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extract/stats")
async def get_extraction_stats(
    db: AsyncSession = Depends(get_db_session)
):
    """
    키워드 추출 통계 조회

    Returns:
        - extracted_keywords: 추출된 키워드 수
        - available_titles: 처리 가능한 제목 수
        - konlpy_available: KoNLPy 사용 가능 여부
    """
    from ..services.keyword_extractor_service import KeywordExtractorService

    try:
        extractor = KeywordExtractorService(db)
        return await extractor.get_extraction_stats()

    except Exception as e:
        logger.error(f"[EXTRACT_STATS] 에러: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


