"""
키워드 데이터 관리 API

Features:
- SeedKeyword CRUD
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
from ..models.keyword import SeedKeyword, CollectedKeyword, KeywordCategory
from ..models.category import Topic, SubTopic
from ..models.user import User
from ..routers.auth import get_current_user

router = APIRouter(prefix="/data/keywords", tags=["data-keywords"])
logger = get_logger("data_keywords", "app.log")


# Pydantic Schemas
class SeedKeywordResponse(BaseModel):
    id: int
    keyword: str
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    # 카테고리 관리 연동 (Topic > SubTopic)
    topic_id: Optional[int] = None
    topic_name: Optional[str] = None
    subtopic_id: Optional[int] = None
    subtopic_name: Optional[str] = None
    category_path: Optional[str] = None  # "주제/하위 주제" 형식
    source_type: str
    is_active: bool
    use_count: int
    priority: int
    last_used_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SeedKeywordCreate(BaseModel):
    keyword: str
    category_id: Optional[int] = None
    source_type: str = "user_input"
    priority: int = 0


class BulkKeywordCreate(BaseModel):
    """대량 키워드 등록"""
    keywords: List[str]


class BulkKeywordDelete(BaseModel):
    """대량 키워드 삭제"""
    ids: List[int]


class SeedKeywordUpdate(BaseModel):
    keyword: Optional[str] = None
    category_id: Optional[int] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None


class KeywordListResponse(BaseModel):
    items: List[SeedKeywordResponse]
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
@router.get("/seed", response_model=KeywordListResponse)
async def list_seed_keywords(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    sort_field: Optional[str] = Query("created_at", description="정렬 필드"),
    sort_dir: Optional[str] = Query("desc", description="정렬 방향 (asc/desc)"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """시드 키워드 목록 조회"""
    query = select(SeedKeyword)

    # 필터 적용
    if search:
        query = query.where(SeedKeyword.keyword.ilike(f"%{search}%"))
    if source_type:
        query = query.where(SeedKeyword.source_type == source_type)
    if is_active is not None:
        query = query.where(SeedKeyword.is_active == is_active)

    # 전체 개수
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 정렬 적용
    sort_columns = {
        "keyword": SeedKeyword.keyword,
        "source_type": SeedKeyword.source_type,
        "use_count": SeedKeyword.use_count,
        "priority": SeedKeyword.priority,
        "created_at": SeedKeyword.created_at,
        "last_used_at": SeedKeyword.last_used_at,
        "category_path": SeedKeyword.topic_id,  # 카테고리 정렬 (topic_id 기준)
    }
    sort_column = sort_columns.get(sort_field, SeedKeyword.created_at)
    if sort_dir == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # 페이지네이션
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    keywords = result.scalars().all()

    # 카테고리 정보 조회 (KeywordCategory + Topic/SubTopic)
    items = []
    for kw in keywords:
        item = SeedKeywordResponse.model_validate(kw)
        # KeywordCategory 조회
        if kw.category_id:
            cat = await db.get(KeywordCategory, kw.category_id)
            item.category_name = cat.name if cat else None
        # Topic/SubTopic 조회 (카테고리 관리 연동)
        if kw.topic_id:
            topic = await db.get(Topic, kw.topic_id)
            if topic:
                item.topic_id = topic.id
                item.topic_name = topic.name
        if kw.subtopic_id:
            subtopic = await db.get(SubTopic, kw.subtopic_id)
            if subtopic:
                item.subtopic_id = subtopic.id
                item.subtopic_name = subtopic.name
        # category_path 구성 (주제 - 하위 주제)
        if item.topic_name and item.subtopic_name:
            item.category_path = f"{item.topic_name} - {item.subtopic_name}"
        elif item.topic_name:
            item.category_path = item.topic_name
        items.append(item)

    return KeywordListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        has_next=(page * size) < total
    )


@router.post("/seed", response_model=SeedKeywordResponse)
async def create_seed_keyword(
    data: SeedKeywordCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """시드 키워드 생성"""
    # 중복 체크
    existing = await db.execute(
        select(SeedKeyword).where(
            SeedKeyword.keyword == data.keyword,
            SeedKeyword.category_id == data.category_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 존재하는 키워드입니다")

    keyword = SeedKeyword(
        keyword=data.keyword,
        category_id=data.category_id,
        source_type=data.source_type,
        priority=data.priority
    )
    db.add(keyword)
    await db.commit()
    await db.refresh(keyword)

    return SeedKeywordResponse.model_validate(keyword)


@router.post("/seed/bulk-delete")
async def delete_seed_keywords_bulk(
    data: BulkKeywordDelete,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """시드 키워드 일괄 삭제"""
    deleted_count = 0

    for keyword_id in data.ids:
        keyword = await db.get(SeedKeyword, keyword_id)
        if keyword:
            await db.delete(keyword)
            deleted_count += 1

    await db.commit()
    logger.info(f"[BULK_DELETE_KEYWORD] 삭제: {deleted_count}개")

    return {"deleted": deleted_count, "message": f"{deleted_count}개 키워드가 삭제되었습니다"}


@router.delete("/seed/delete-all")
async def delete_all_seed_keywords(
    source_type: Optional[str] = Query(None, description="특정 소스만 삭제 (예: naver_ads, google_trends)"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """시드 키워드 전체 삭제"""
    query = select(func.count()).select_from(SeedKeyword)
    if source_type:
        query = query.where(SeedKeyword.source_type == source_type)

    total_before = (await db.execute(query)).scalar() or 0

    # 삭제 실행
    from sqlalchemy import delete
    delete_query = delete(SeedKeyword)
    if source_type:
        delete_query = delete_query.where(SeedKeyword.source_type == source_type)

    await db.execute(delete_query)
    await db.commit()

    logger.info(f"[DELETE_ALL_KEYWORD] 전체 삭제: {total_before}개, source_type={source_type or 'all'}")

    return {
        "deleted": total_before,
        "source_type": source_type or "all",
        "message": f"{total_before}개 키워드가 삭제되었습니다"
    }


@router.put("/seed/{keyword_id}", response_model=SeedKeywordResponse)
async def update_seed_keyword(
    keyword_id: int,
    data: SeedKeywordUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """시드 키워드 수정"""
    keyword = await db.get(SeedKeyword, keyword_id)
    if not keyword:
        raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다")

    if data.keyword is not None:
        keyword.keyword = data.keyword
    if data.category_id is not None:
        keyword.category_id = data.category_id
    if data.is_active is not None:
        keyword.is_active = data.is_active
    if data.priority is not None:
        keyword.priority = data.priority

    await db.commit()
    await db.refresh(keyword)

    return SeedKeywordResponse.model_validate(keyword)


@router.delete("/seed/{keyword_id}")
async def delete_seed_keyword(
    keyword_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """시드 키워드 삭제"""
    keyword = await db.get(SeedKeyword, keyword_id)
    if not keyword:
        raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다")

    await db.delete(keyword)
    await db.commit()

    return {"message": "삭제되었습니다"}


class MoveToFilterRequest(BaseModel):
    """키워드를 필터로 이동"""
    keyword_ids: List[int]
    target_type: str = "both"  # keyword, title, both


@router.post("/seed/move-to-filter")
async def move_keywords_to_filter(
    data: MoveToFilterRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    선택한 키워드를 필터로 이동 (키워드는 삭제됨)

    키워드를 필터값으로 등록하고 원본 키워드는 삭제합니다.
    """
    from ..models.content_filter import ContentFilter

    moved_count = 0
    skipped_count = 0
    deleted_ids = []

    for keyword_id in data.keyword_ids:
        keyword = await db.get(SeedKeyword, keyword_id)
        if not keyword:
            continue

        keyword_value = keyword.keyword.strip()

        # 중복 필터 체크
        existing = await db.execute(
            select(ContentFilter).where(
                ContentFilter.filter_value == keyword_value,
                ContentFilter.filter_type == "keyword"
            )
        )
        if existing.scalar_one_or_none():
            skipped_count += 1
            # 이미 필터에 있으면 키워드만 삭제
            await db.delete(keyword)
            deleted_ids.append(keyword_id)
            continue

        # 새 필터 생성
        new_filter = ContentFilter(
            name=keyword_value,
            filter_type="keyword",
            filter_value=keyword_value,
            target_type=data.target_type,
            description=f"키워드에서 이동됨 (id={keyword_id})",
            is_system=False,
            is_active=True
        )
        db.add(new_filter)

        # 원본 키워드 삭제
        await db.delete(keyword)
        deleted_ids.append(keyword_id)
        moved_count += 1

    await db.commit()

    logger.info(f"[MOVE_TO_FILTER] 이동: {moved_count}개, 중복 스킵: {skipped_count}개")

    return {
        "moved": moved_count,
        "skipped": skipped_count,
        "deleted_ids": deleted_ids,
        "message": f"{moved_count}개 키워드가 필터로 이동되었습니다"
    }


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
        seed = await db.get(SeedKeyword, kw.seed_keyword_id)
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
    """키워드 통계 조회"""
    seed_total = (await db.execute(
        select(func.count()).select_from(SeedKeyword)
    )).scalar() or 0

    seed_active = (await db.execute(
        select(func.count()).select_from(SeedKeyword).where(SeedKeyword.is_active == True)
    )).scalar() or 0

    collected_total = (await db.execute(
        select(func.count()).select_from(CollectedKeyword)
    )).scalar() or 0

    collected_processed = (await db.execute(
        select(func.count()).select_from(CollectedKeyword).where(CollectedKeyword.is_processed == True)
    )).scalar() or 0

    return {
        "seed": {"total": seed_total, "active": seed_active},
        "collected": {"total": collected_total, "processed": collected_processed}
    }


@router.post("/seed/bulk")
async def create_seed_keywords_bulk(
    data: BulkKeywordCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """시드 키워드 대량 등록"""
    created_count = 0
    skipped_count = 0

    for kw_text in data.keywords:
        kw_text = kw_text.strip()
        if not kw_text:
            continue

        # 중복 체크
        existing = await db.execute(
            select(SeedKeyword).where(SeedKeyword.keyword == kw_text)
        )
        if existing.scalar_one_or_none():
            skipped_count += 1
            continue

        keyword = SeedKeyword(
            keyword=kw_text,
            source_type="user_input"
        )
        db.add(keyword)
        created_count += 1

    await db.commit()
    logger.info(f"[BULK_KEYWORD] 등록: {created_count}개, 중복 스킵: {skipped_count}개")

    return {"created": created_count, "skipped": skipped_count}


@router.post("/upload")
async def upload_keywords_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """엑셀/CSV 파일로 키워드 대량 등록"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일명이 없습니다")

    ext = file.filename.lower().split('.')[-1]
    if ext not in ['xlsx', 'xls', 'csv']:
        raise HTTPException(status_code=400, detail="지원하지 않는 파일 형식입니다 (.xlsx, .xls, .csv만 가능)")

    content = await file.read()
    keywords = []

    try:
        if ext == 'csv':
            # CSV 파일 처리
            text = content.decode('utf-8-sig')
            lines = text.strip().split('\n')
            # 첫 번째 줄은 헤더로 스킵
            for line in lines[1:]:
                parts = line.strip().split(',')
                if parts and parts[0].strip():
                    keywords.append(parts[0].strip().strip('"'))
        else:
            # Excel 파일 처리
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
                ws = wb.active
                # 첫 번째 행은 헤더로 스킵
                for row in list(ws.iter_rows(min_row=2, max_col=1, values_only=True)):
                    if row[0]:
                        keywords.append(str(row[0]).strip())
                wb.close()
            except ImportError:
                raise HTTPException(
                    status_code=400,
                    detail="Excel 파일 처리를 위한 openpyxl 라이브러리가 설치되지 않았습니다. CSV 파일을 사용해주세요."
                )
    except Exception as e:
        logger.error(f"[UPLOAD_ERROR] 파일 파싱 실패: {e}")
        raise HTTPException(status_code=400, detail=f"파일 파싱 실패: {str(e)}")

    if not keywords:
        raise HTTPException(status_code=400, detail="유효한 키워드가 없습니다")

    # 대량 등록
    created_count = 0
    skipped_count = 0

    for kw_text in keywords:
        if not kw_text:
            continue

        existing = await db.execute(
            select(SeedKeyword).where(SeedKeyword.keyword == kw_text)
        )
        if existing.scalar_one_or_none():
            skipped_count += 1
            continue

        keyword = SeedKeyword(
            keyword=kw_text,
            source_type="excel_upload"
        )
        db.add(keyword)
        created_count += 1

    await db.commit()
    logger.info(f"[EXCEL_UPLOAD] 등록: {created_count}개, 중복 스킵: {skipped_count}개")

    return {"created": created_count, "skipped": skipped_count}


# ============================================================
# 자동 키워드 수집
# ============================================================

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
    키워드를 추출하고 SeedKeyword 테이블에 저장합니다.

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


@router.post("/seed/remove-duplicates")
async def remove_duplicate_keywords(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    중복 키워드 수동 제거

    대소문자 무시하여 중복된 키워드 중 최신 것만 남기고 삭제합니다.
    """
    # 1. 모든 키워드 조회
    result = await db.execute(
        select(SeedKeyword).order_by(SeedKeyword.created_at.asc())
    )
    all_keywords = result.scalars().all()

    # 2. 대소문자 무시하여 중복 찾기 (가장 오래된 것 유지)
    seen = {}  # {lowercase_keyword: first_id}
    duplicates_to_delete = []

    for kw in all_keywords:
        key = kw.keyword.strip().lower()
        if key in seen:
            # 중복 발견 - 나중에 추가된 것 삭제 대상
            duplicates_to_delete.append(kw.id)
        else:
            seen[key] = kw.id

    # 3. 중복 삭제
    deleted_count = 0
    for kw_id in duplicates_to_delete:
        keyword = await db.get(SeedKeyword, kw_id)
        if keyword:
            await db.delete(keyword)
            deleted_count += 1

    await db.commit()

    logger.info(f"[DEDUP_KEYWORD] 수동 중복 제거: {deleted_count}개 삭제됨")

    return {
        "deleted": deleted_count,
        "total_before": len(all_keywords),
        "total_after": len(all_keywords) - deleted_count,
        "message": f"{deleted_count}개 중복 키워드가 삭제되었습니다"
    }


@router.post("/seed/reclassify")
async def reclassify_uncategorized_keywords(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    미분류 키워드 카테고리 재분류

    topic_id가 NULL인 키워드들을 대상으로
    카테고리 관리의 키워드와 매칭하여 카테고리를 할당합니다.
    """
    from ..services.category_matcher_service import CategoryMatcherService

    try:
        # 1. 미분류 키워드 조회
        result = await db.execute(
            select(SeedKeyword).where(SeedKeyword.topic_id == None)
        )
        uncategorized = result.scalars().all()

        if not uncategorized:
            return {
                "success": True,
                "total": 0,
                "matched": 0,
                "message": "미분류 키워드가 없습니다"
            }

        # 2. 카테고리 매처 초기화
        matcher = CategoryMatcherService(db)
        await matcher._load_keywords()

        # 3. 각 키워드에 대해 매칭 시도
        matched_count = 0
        for kw in uncategorized:
            topic_id, subtopic_id, matched_keyword_id = \
                await matcher.match_and_apply_to_keyword(kw.keyword)

            if topic_id:
                kw.topic_id = topic_id
                kw.subtopic_id = subtopic_id
                kw.matched_keyword_id = matched_keyword_id
                matched_count += 1

        await db.commit()

        logger.info(
            f"[RECLASSIFY_KEYWORD] 재분류 완료: "
            f"전체 {len(uncategorized)}개 중 {matched_count}개 매칭"
        )

        return {
            "success": True,
            "total": len(uncategorized),
            "matched": matched_count,
            "message": f"{len(uncategorized)}개 중 {matched_count}개 키워드가 분류되었습니다"
        }

    except Exception as e:
        logger.error(f"[RECLASSIFY_KEYWORD] 에러: {str(e)}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
