"""
제목 데이터 관리 API

Features:
- TempTitle CRUD
- 상태 관리 (new, filtered, categorized, moved)
- 카테고리 분류
- 대량 등록 (bulk)
- 엑셀 업로드
- 페이지네이션, 검색
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import load_only
from pydantic import BaseModel, Field
from datetime import datetime
import io
import re

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.title import TempTitle, MainTitle
from ..services.title_dedup import title_exists
from ..models.keyword import KeywordCategory, CollectedKeyword
from ..models.category import Topic, SubTopic
from ..models.user import User
from ..routers.auth import get_current_user

router = APIRouter(prefix="/data/titles", tags=["data-titles"])
logger = get_logger("data_titles", "app.log")


# Pydantic Schemas
class TempTitleResponse(BaseModel):
    id: int
    title: str
    source_keyword_id: Optional[int] = None
    source_keyword: Optional[str] = None
    source_blog_url: str
    source_post_url: str
    collection_stage: str
    status: str
    filter_reason: Optional[str] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    category_confidence: Optional[float] = None
    # 카테고리 관리 연동 (Topic > SubTopic)
    topic_id: Optional[int] = None
    topic_name: Optional[str] = None
    subtopic_id: Optional[int] = None
    subtopic_name: Optional[str] = None
    category_path: Optional[str] = None  # "주제/하위 주제" 형식
    similarity_score: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TempTitleListResponse(BaseModel):
    items: List[TempTitleResponse]
    total: int
    page: int
    size: int
    has_next: bool


class TempTitleUpdate(BaseModel):
    title: Optional[str] = None  # ★ 제목 수정 가능
    status: Optional[str] = None
    category_id: Optional[int] = None
    filter_reason: Optional[str] = None


class TitlePromoteRequest(BaseModel):
    title_ids: List[int]


class TitleCategoryRequest(BaseModel):
    title_ids: List[int]
    category_id: int


class BulkTitleCreate(BaseModel):
    """대량 제목 등록"""
    titles: List[str]


class BulkTitleDelete(BaseModel):
    """대량 제목 삭제"""
    ids: List[int]


# API Endpoints

@router.get("/temp/topic-distribution")
async def get_topic_distribution(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """임시 제목의 topic_id 분포 확인 (디버깅용)"""
    from sqlalchemy import text

    # topic_id별 개수 조회
    result = await db.execute(
        text("""
            SELECT topic_id, COUNT(*) as cnt
            FROM temp_titles
            GROUP BY topic_id
            ORDER BY cnt DESC
        """)
    )
    rows = result.fetchall()

    distribution = []
    for row in rows:
        distribution.append({
            "topic_id": row[0],
            "count": row[1]
        })

    return {
        "distribution": distribution,
        "message": "topic_id가 NULL인 경우 카테고리 재분류가 필요합니다"
    }


@router.get("/temp", response_model=TempTitleListResponse)
async def list_temp_titles(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    topic_id: Optional[int] = Query(None, description="카테고리 관리 주제 ID"),
    subtopic_id: Optional[int] = Query(None, description="카테고리 관리 하위 주제 ID"),
    collection_stage: Optional[str] = Query(None),
    sort_field: Optional[str] = Query("created_at", description="정렬 필드"),
    sort_dir: Optional[str] = Query("desc", description="정렬 방향 (asc/desc)"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """임시 제목 목록 조회"""
    # 디버깅 로그
    logger.info(
        f"[TEMP_TITLES] 조회 요청 - search={search}, status={status}, "
        f"topic_id={topic_id} (type={type(topic_id).__name__}), subtopic_id={subtopic_id}, page={page}"
    )

    query = select(TempTitle)

    # 필터 적용
    if search:
        query = query.where(TempTitle.title.ilike(f"%{search}%"))
    if status:
        query = query.where(TempTitle.status == status)
    if category_id:
        query = query.where(TempTitle.category_id == category_id)
    # 카테고리 관리 기반 필터 (Topic/SubTopic)
    if topic_id is not None:
        logger.info(f"[TEMP_TITLES] topic_id 필터 적용: {topic_id} (type={type(topic_id).__name__})")
        query = query.where(TempTitle.topic_id == topic_id)
    if subtopic_id:
        query = query.where(TempTitle.subtopic_id == subtopic_id)
    if collection_stage:
        query = query.where(TempTitle.collection_stage == collection_stage)

    # 전체 개수
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 디버깅: topic_id 필터 결과 로깅
    if topic_id:
        logger.info(f"[TEMP_TITLES] topic_id={topic_id} 필터 결과: {total}건")

    # 정렬 적용
    sort_columns = {
        "title": TempTitle.title,
        "status": TempTitle.status,
        "collection_stage": TempTitle.collection_stage,
        "created_at": TempTitle.created_at,
        "category_path": TempTitle.topic_id,  # 카테고리 정렬 (topic_id 기준)
    }
    sort_column = sort_columns.get(sort_field, TempTitle.created_at)
    if sort_dir == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # 페이지네이션
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    titles = result.scalars().all()

    # 관계 데이터 조회 (KeywordCategory + Topic/SubTopic)
    items = []
    for t in titles:
        item = TempTitleResponse.model_validate(t)
        if t.source_keyword_id:
            kw = await db.get(CollectedKeyword, t.source_keyword_id)
            item.source_keyword = kw.keyword if kw else None
        # KeywordCategory 조회
        if t.category_id:
            cat = await db.get(KeywordCategory, t.category_id)
            item.category_name = cat.name if cat else None
        # Topic/SubTopic 조회 (카테고리 관리 연동)
        if t.topic_id:
            topic = await db.get(Topic, t.topic_id)
            if topic:
                item.topic_id = topic.id
                item.topic_name = topic.name
        if t.subtopic_id:
            subtopic = await db.get(SubTopic, t.subtopic_id)
            if subtopic:
                item.subtopic_id = subtopic.id
                item.subtopic_name = subtopic.name
        # category_path 구성 (주제 - 하위 주제)
        if item.topic_name and item.subtopic_name:
            item.category_path = f"{item.topic_name} - {item.subtopic_name}"
        elif item.topic_name:
            item.category_path = item.topic_name
        items.append(item)

    return TempTitleListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        has_next=(page * size) < total
    )


@router.post("/temp/bulk-delete")
async def delete_temp_titles_bulk(
    data: BulkTitleDelete,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """임시 제목 일괄 삭제"""
    deleted_count = 0

    for title_id in data.ids:
        title = await db.get(TempTitle, title_id)
        if title:
            await db.delete(title)
            deleted_count += 1

    await db.commit()
    logger.info(f"[BULK_DELETE_TITLE] 삭제: {deleted_count}개")

    return {"deleted": deleted_count, "message": f"{deleted_count}개 제목이 삭제되었습니다"}


@router.delete("/temp/delete-all")
async def delete_all_temp_titles(
    status: Optional[str] = Query(None, description="특정 상태만 삭제 (예: new, filtered)"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """임시 제목 전체 삭제"""
    query = select(func.count()).select_from(TempTitle)
    if status:
        query = query.where(TempTitle.status == status)

    total_before = (await db.execute(query)).scalar() or 0

    # 삭제 실행
    from sqlalchemy import delete
    delete_query = delete(TempTitle)
    if status:
        delete_query = delete_query.where(TempTitle.status == status)

    await db.execute(delete_query)
    await db.commit()

    logger.info(f"[DELETE_ALL_TITLE] 전체 삭제: {total_before}개, status={status or 'all'}")

    return {
        "deleted": total_before,
        "status": status or "all",
        "message": f"{total_before}개 제목이 삭제되었습니다"
    }


@router.get("/temp/{title_id}", response_model=TempTitleResponse)
async def get_temp_title(
    title_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """임시 제목 상세 조회"""
    title = await db.get(TempTitle, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="제목을 찾을 수 없습니다")

    item = TempTitleResponse.model_validate(title)
    if title.category_id:
        cat = await db.get(KeywordCategory, title.category_id)
        item.category_name = cat.name if cat else None

    return item


@router.put("/temp/{title_id}", response_model=TempTitleResponse)
async def update_temp_title(
    title_id: int,
    data: TempTitleUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """임시 제목 수정"""
    title_obj = await db.get(TempTitle, title_id)
    if not title_obj:
        raise HTTPException(status_code=404, detail="제목을 찾을 수 없습니다")

    # ★ 제목 텍스트 수정
    if data.title is not None:
        title_obj.title = data.title.strip()
    if data.status is not None:
        title_obj.status = data.status
    if data.category_id is not None:
        title_obj.category_id = data.category_id
    if data.filter_reason is not None:
        title_obj.filter_reason = data.filter_reason

    await db.commit()
    await db.refresh(title_obj)

    return TempTitleResponse.model_validate(title_obj)


@router.delete("/temp/{title_id}")
async def delete_temp_title(
    title_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """임시 제목 삭제"""
    title = await db.get(TempTitle, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="제목을 찾을 수 없습니다")

    await db.delete(title)
    await db.commit()

    return {"message": "삭제되었습니다"}


@router.post("/temp/promote")
async def promote_titles(
    data: TitlePromoteRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    임시 제목을 정식 제목으로 승격

    데이터 이동 모듈과 동일한 방식 사용:
    - topic_id와 subtopic_id가 모두 있는 제목만 승격
    - 카테고리 정보(topic_id, subtopic_id) 유지
    - 유사도 기반 자동 그룹화 (임계값은 시스템 설정 similarity_threshold, 기본 75)
    """
    from ..services.title_transfer_service import move_temp_to_main
    from ..services.system_settings_service import SystemSettingsService
    from sqlalchemy import select

    # 유사도 임계값: 시스템 설정에서 조회(데이터 모듈과 동일 소스로 통일).
    # 미설정 시 기본 75.
    threshold = await SystemSettingsService.get_float(
        "similarity_threshold", db, 75.0
    )

    try:
        # Data Module 방식: topic_id와 subtopic_id가 모두 있는 제목만 필터링
        query = select(TempTitle.id).where(
            TempTitle.id.in_(data.title_ids),
            TempTitle.topic_id.isnot(None),
            TempTitle.subtopic_id.isnot(None)
        )
        filter_result = await db.execute(query)
        valid_title_ids = [row[0] for row in filter_result.all()]

        # 필터링된 제목 수 계산
        skipped_count = len(data.title_ids) - len(valid_title_ids)

        if not valid_title_ids:
            return {
                "promoted": 0,
                "grouped": 0,
                "duplicates": 0,
                "skipped": skipped_count,
                "message": f"카테고리가 지정되지 않은 제목은 승격할 수 없습니다 ({skipped_count}개 스킵)"
            }

        result = await move_temp_to_main(
            db=db,
            temp_title_ids=valid_title_ids,
            auto_group=True,
            threshold=threshold,  # 시스템 설정 기반(기본 75)
        )

        message = f"{result['moved']}개 제목이 승격되었습니다"
        if skipped_count > 0:
            message += f" (카테고리 미지정 {skipped_count}개 스킵)"

        return {
            "promoted": result["moved"],
            "grouped": result.get("grouped", 0),
            "duplicates": result.get("duplicates", 0),
            "skipped": skipped_count,
            "message": message
        }
    except Exception as e:
        logger.error(f"[PROMOTE] 승격 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/temp/categorize")
async def categorize_titles(
    data: TitleCategoryRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """제목에 카테고리 일괄 적용"""
    # 카테고리 존재 확인
    category = await db.get(KeywordCategory, data.category_id)
    if not category:
        raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다")

    updated = 0
    for title_id in data.title_ids:
        title = await db.get(TempTitle, title_id)
        if not title:
            continue
        title.category_id = data.category_id
        title.status = "categorized"
        updated += 1

    await db.commit()

    return {"updated": updated, "message": f"{updated}개 제목에 카테고리가 적용되었습니다"}


@router.post("/temp/filter")
async def filter_titles(
    data: TitlePromoteRequest,
    reason: str = Query(..., description="필터링 사유"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """제목 일괄 필터링 (차단)"""
    filtered = 0
    for title_id in data.title_ids:
        title = await db.get(TempTitle, title_id)
        if not title:
            continue
        title.mark_filtered(reason)
        filtered += 1

    await db.commit()

    return {"filtered": filtered, "message": f"{filtered}개 제목이 필터링되었습니다"}


@router.get("/stats")
async def get_title_stats(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """제목 통계 조회"""
    temp_total = (await db.execute(
        select(func.count()).select_from(TempTitle)
    )).scalar() or 0

    temp_new = (await db.execute(
        select(func.count()).select_from(TempTitle).where(TempTitle.status == "new")
    )).scalar() or 0

    temp_categorized = (await db.execute(
        select(func.count()).select_from(TempTitle).where(TempTitle.status == "categorized")
    )).scalar() or 0

    temp_filtered = (await db.execute(
        select(func.count()).select_from(TempTitle).where(TempTitle.status == "filtered")
    )).scalar() or 0

    main_total = (await db.execute(
        select(func.count()).select_from(MainTitle)
    )).scalar() or 0

    main_available = (await db.execute(
        select(func.count()).select_from(MainTitle).where(MainTitle.status == "available")
    )).scalar() or 0

    return {
        "temp": {
            "total": temp_total,
            "new": temp_new,
            "categorized": temp_categorized,
            "filtered": temp_filtered
        },
        "main": {
            "total": main_total,
            "available": main_available
        }
    }


@router.post("/temp/bulk")
async def create_temp_titles_bulk(
    data: BulkTitleCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """임시 제목 대량 등록"""
    created_count = 0
    skipped_count = 0
    short_count = 0  # 10자 이하로 필터링된 개수

    for title_text in data.titles:
        title_text = title_text.strip()
        if not title_text:
            continue

        # 띄어쓰기 포함 10자 이하 제목은 수집하지 않음
        if len(title_text) <= 10:
            short_count += 1
            continue

        # 중복 체크 (임시+정식 모두, 대소문자 무시)
        if await title_exists(db, title_text):
            skipped_count += 1
            continue

        title = TempTitle(
            title=title_text,
            source_blog_url="",
            source_post_url="",
            collection_stage="manual_input",
            status="new"
        )
        db.add(title)
        created_count += 1

    await db.commit()
    logger.info(
        f"[BULK_TITLE] 등록: {created_count}개, 중복 스킵: {skipped_count}개, "
        f"10자 이하 스킵: {short_count}개"
    )

    return {"created": created_count, "skipped": skipped_count, "short_filtered": short_count}


@router.post("/upload")
async def upload_titles_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """엑셀/CSV 파일로 제목 대량 등록"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일명이 없습니다")

    ext = file.filename.lower().split('.')[-1]
    if ext not in ['xlsx', 'xls', 'csv']:
        raise HTTPException(status_code=400, detail="지원하지 않는 파일 형식입니다 (.xlsx, .xls, .csv만 가능)")

    content = await file.read()
    titles = []

    try:
        if ext == 'csv':
            # CSV 파일 처리
            text = content.decode('utf-8-sig')
            lines = text.strip().split('\n')
            # 첫 번째 줄은 헤더로 스킵
            for line in lines[1:]:
                parts = line.strip().split(',')
                if parts and parts[0].strip():
                    titles.append(parts[0].strip().strip('"'))
        else:
            # Excel 파일 처리
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
                ws = wb.active
                # 첫 번째 행은 헤더로 스킵
                for row in list(ws.iter_rows(min_row=2, max_col=1, values_only=True)):
                    if row[0]:
                        titles.append(str(row[0]).strip())
                wb.close()
            except ImportError:
                raise HTTPException(
                    status_code=400,
                    detail="Excel 파일 처리를 위한 openpyxl 라이브러리가 설치되지 않았습니다. CSV 파일을 사용해주세요."
                )
    except Exception as e:
        logger.error(f"[UPLOAD_ERROR] 파일 파싱 실패: {e}")
        raise HTTPException(status_code=400, detail=f"파일 파싱 실패: {str(e)}")

    if not titles:
        raise HTTPException(status_code=400, detail="유효한 제목이 없습니다")

    # 대량 등록
    created_count = 0
    skipped_count = 0
    short_count = 0  # 10자 이하로 필터링된 개수

    for title_text in titles:
        if not title_text:
            continue

        # 띄어쓰기 포함 10자 이하 제목은 수집하지 않음
        if len(title_text) <= 10:
            short_count += 1
            continue

        # 중복 체크 (임시+정식 모두, 대소문자 무시)
        if await title_exists(db, title_text):
            skipped_count += 1
            continue

        title = TempTitle(
            title=title_text,
            source_blog_url="",
            source_post_url="",
            collection_stage="excel_upload",
            status="new"
        )
        db.add(title)
        created_count += 1

    await db.commit()
    logger.info(
        f"[EXCEL_UPLOAD] 등록: {created_count}개, 중복 스킵: {skipped_count}개, "
        f"10자 이하 스킵: {short_count}개"
    )

    return {"created": created_count, "skipped": skipped_count, "short_filtered": short_count}


@router.post("/temp/remove-duplicates")
async def remove_duplicate_titles(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    중복 제목 수동 제거

    대소문자 무시하여 중복된 제목 중 가장 오래된 것만 남기고 삭제합니다.
    """
    # 1. 모든 제목 조회
    result = await db.execute(
        select(TempTitle).order_by(TempTitle.created_at.asc())
    )
    all_titles = result.scalars().all()

    # 2. 대소문자 무시하여 중복 찾기 (가장 오래된 것 유지)
    seen = {}  # {lowercase_title: first_id}
    duplicates_to_delete = []

    for title in all_titles:
        key = title.title.strip().lower()
        if key in seen:
            # 중복 발견 - 나중에 추가된 것 삭제 대상
            duplicates_to_delete.append(title.id)
        else:
            seen[key] = title.id

    # 3. 중복 삭제
    deleted_count = 0
    for title_id in duplicates_to_delete:
        title = await db.get(TempTitle, title_id)
        if title:
            await db.delete(title)
            deleted_count += 1

    await db.commit()

    logger.info(f"[DEDUP_TITLE] 수동 중복 제거: {deleted_count}개 삭제됨")

    return {
        "deleted": deleted_count,
        "total_before": len(all_titles),
        "total_after": len(all_titles) - deleted_count,
        "message": f"{deleted_count}개 중복 제목이 삭제되었습니다"
    }


@router.post("/temp/reclassify")
async def reclassify_uncategorized_titles(
    force_all: bool = Query(False, description="True면 전체 재분류, False면 미분류만"),
    target: str = Query("temp", description="대상: temp(임시제목) 또는 main(정식제목)"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    제목 카테고리 재분류.

    Args:
        force_all: True면 이미 분류된 제목도 포함하여 전체 재분류.
        target: "temp"이면 임시제목, "main"이면 정식제목 대상.
    """
    from ..services.category_matcher_service import CategoryMatcherService

    if target not in ("temp", "main"):
        raise HTTPException(status_code=400, detail="target은 temp 또는 main이어야 합니다")

    model = MainTitle if target == "main" else TempTitle
    target_label = "정식제목" if target == "main" else "임시제목"

    try:
        base_query = select(model.id, model.title)

        if force_all:
            result = await db.execute(base_query)
            mode_str = f"{target_label} 전체 재분류"
        else:
            result = await db.execute(
                base_query.where(model.topic_id == None)
            )
            mode_str = f"{target_label} 미분류 재분류"

        titles_data = result.all()

        if not titles_data:
            return {
                "success": True,
                "total": 0,
                "matched": 0,
                "message": "재분류할 제목이 없습니다"
            }

        matcher = CategoryMatcherService(db, user_id=current_user.id)
        await matcher._load_keywords(force_reload=True)

        matched_count = 0
        for title_id, title_text in titles_data:
            topic_id, subtopic_id, matched_keyword_id = \
                await matcher.match_and_apply_to_title(title_text)

            if topic_id:
                update_values: dict = {
                    "topic_id": topic_id,
                    "subtopic_id": subtopic_id,
                }
                if target == "temp":
                    update_values["matched_keyword_id"] = matched_keyword_id

                await db.execute(
                    update(model)
                    .where(model.id == title_id)
                    .values(**update_values)
                )
                matched_count += 1

        await db.commit()

        logger.info(
            f"[RECLASSIFY_TITLE] {mode_str} 완료: "
            f"전체 {len(titles_data)}개 중 {matched_count}개 매칭"
        )

        return {
            "success": True,
            "total": len(titles_data),
            "matched": matched_count,
            "mode": "all" if force_all else "uncategorized",
            "target": target,
            "message": f"{target_label} {len(titles_data)}개 중 {matched_count}개가 분류되었습니다"
        }

    except Exception as e:
        logger.error(f"[RECLASSIFY_TITLE] 에러: {str(e)}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 제목 일괄 단어 치환
# ============================================================

class BulkReplaceRequest(BaseModel):
    """제목 일괄 치환 요청"""
    target: str = Field(..., pattern="^(temp|main)$")
    find_text: str = Field(..., min_length=1, max_length=200)
    replace_text: str = Field("", max_length=200)
    case_sensitive: bool = False
    mode: str = Field(..., pattern="^(preview|apply)$")
    title_ids: Optional[List[int]] = None


def _build_replace_previews(
    titles,
    find_text: str,
    replace_text: str,
    case_sensitive: bool,
    existing_titles: set,
) -> tuple:
    """치환 미리보기 목록을 계산한다 (순수 함수, preview/apply 공용).

    Args:
        titles: 대상 제목 객체 목록(.id, .title 보유).
        find_text: 찾을 단어.
        replace_text: 바꿀 단어(빈 문자열이면 삭제).
        case_sensitive: 대소문자 구분 여부.
        existing_titles: 결과가 이 집합에 있으면 중복으로 스킵한다.
            처리 중 생성된 결과도 누적해 같은 배치 내 중복도 막는다.
            빈 집합이면 중복 스킵 없이 모두 치환(임시제목용).

    Returns:
        (previews, duplicates, empty_count) 튜플.
        previews: [{"id", "original", "replaced"}] 목록.
    """
    pattern = re.escape(find_text)
    flags = 0 if case_sensitive else re.IGNORECASE
    previews: list = []
    duplicates = 0
    empty_count = 0
    seen = set(existing_titles)
    for t in titles:
        new_text = re.sub(pattern, replace_text, t.title, flags=flags)
        new_text = re.sub(r'\s+', ' ', new_text.strip())

        if len(new_text) < 2:
            empty_count += 1
            continue
        if new_text == t.title:
            continue
        if new_text in seen:
            duplicates += 1
            continue

        previews.append({
            "id": t.id, "original": t.title, "replaced": new_text,
        })
        seen.add(new_text)
    return previews, duplicates, empty_count


@router.post("/bulk-replace")
async def bulk_replace_titles(
    request: BulkReplaceRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """제목 일괄 단어 치환 (미리보기/적용)."""
    try:
        model = TempTitle if request.target == "temp" else MainTitle
        title_field = TempTitle.title if request.target == "temp" else MainTitle.title

        query = select(model).where(title_field.ilike(f"%{request.find_text}%"))
        if request.title_ids:
            query = query.where(model.id.in_(request.title_ids))

        result = await db.execute(query)
        titles = result.scalars().all()

        # 중복 비교 집합: mode가 아니라 target 기준으로 결정한다.
        # - main(정식제목): uq_main_title_topic 유니크 제약이 있어 중복 생성 시
        #   IntegrityError → 전체 제목을 미리 로드해 중복 결과를 스킵.
        # - temp(임시제목): title 유니크 제약 없음(중복 허용) → 빈 집합으로 두어
        #   결과가 기존 제목과 같아도 자유롭게 치환(이후 dedup 처리).
        # preview/apply 모두 동일 집합을 사용해 두 모드 결과를 일치시킨다.
        existing_titles: set = set()
        if request.target == "main":
            all_result = await db.execute(select(title_field))
            existing_titles = {r[0] for r in all_result.fetchall()}

        previews, duplicates, empty_count = _build_replace_previews(
            titles,
            request.find_text,
            request.replace_text,
            request.case_sensitive,
            existing_titles,
        )

        if request.mode == "preview":
            return {
                "mode": "preview",
                "total_affected": len(previews),
                "previews": previews[:50],
                "duplicates_warning": duplicates,
                "empty_warning": empty_count,
            }

        updated = 0
        for p in previews:
            obj = await db.get(model, p["id"])
            if obj:
                obj.title = p["replaced"]
                updated += 1

        await db.commit()
        logger.info(f"[BULK_REPLACE] {request.target} 치환 완료: {updated}건")

        return {
            "mode": "apply",
            "updated": updated,
            "skipped_duplicates": duplicates,
            "skipped_empty": empty_count,
            "message": f"{updated}개 제목이 변경되었습니다",
        }

    except Exception as e:
        logger.error(f"[BULK_REPLACE] 에러: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
