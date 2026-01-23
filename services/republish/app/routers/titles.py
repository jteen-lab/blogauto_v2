"""
정식 제목 API (MainTitle)

Features:
- MainTitle CRUD
- 페이지네이션, 검색, 필터링
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.title import MainTitle, TitleGroup
from ..models.keyword import KeywordCategory
from ..models.category import Topic, SubTopic
from ..models.user import User
from ..routers.auth import get_current_user
from ..schemas.title import (
    MainTitleCreate,
    MainTitleUpdate,
    MainTitleResponse,
    MainTitleListResponse,
    MainTitleWithGroup,
    TitleGroupResponse,
)

router = APIRouter(prefix="/titles", tags=["titles"])
logger = get_logger("titles", "app.log")


@router.get("", response_model=MainTitleListResponse)
async def list_main_titles(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="제목 검색"),
    category_id: Optional[int] = Query(None, description="카테고리 필터"),
    status: Optional[str] = Query(None, description="상태 필터"),
    group_id: Optional[int] = Query(None, description="그룹 필터"),
    representatives_only: bool = Query(False, description="대표 제목만"),
    ungrouped_only: bool = Query(False, description="미그룹 제목만"),
    hide_group_members: bool = Query(False, description="그룹 멤버 숨김 (대표+미그룹만 표시)"),
    sort_field: Optional[str] = Query("created_at", description="정렬 필드"),
    sort_dir: Optional[str] = Query("desc", description="정렬 방향"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    정식 제목 목록 조회

    - search: 제목 검색
    - category_id: 카테고리 필터
    - status: 상태 필터 (available/matched/used/archived)
    - group_id: 특정 그룹의 제목만
    - representatives_only: 대표 제목만 조회
    - ungrouped_only: 그룹에 속하지 않은 제목만
    - hide_group_members: 그룹 멤버 숨김 (대표 제목 또는 미그룹 제목만 표시)
    """
    from sqlalchemy import or_

    query = select(MainTitle)

    # 필터 적용
    if search:
        query = query.where(MainTitle.title.ilike(f"%{search}%"))
    if category_id:
        query = query.where(MainTitle.category_id == category_id)
    if status:
        query = query.where(MainTitle.status == status)
    if group_id:
        query = query.where(MainTitle.group_id == group_id)
    if representatives_only:
        query = query.where(MainTitle.is_group_representative == True)
    if ungrouped_only:
        query = query.where(MainTitle.group_id == None)
    # 그룹 멤버 숨김: 대표 제목이거나 그룹에 속하지 않은 제목만 표시
    # 단, 멤버가 1개인 그룹의 유일한 멤버는 표시 (활성 그룹 = 2개 이상)
    if hide_group_members:
        # 멤버가 2개 이상인 활성 그룹 ID 조회
        active_group_ids_subq = (
            select(TitleGroup.id)
            .where(TitleGroup.member_count >= 2)
            .scalar_subquery()
        )
        # 대표 OR 미그룹 OR (그룹 멤버이지만 활성 그룹이 아닌 경우)
        query = query.where(
            or_(
                MainTitle.is_group_representative == True,
                MainTitle.group_id == None,
                ~MainTitle.group_id.in_(select(TitleGroup.id).where(TitleGroup.member_count >= 2))
            )
        )

    # 전체 개수
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 정렬
    sort_columns = {
        "title": MainTitle.title,
        "status": MainTitle.status,
        "created_at": MainTitle.created_at,
        "updated_at": MainTitle.updated_at,
        "use_count": MainTitle.use_count,
    }
    sort_column = sort_columns.get(sort_field, MainTitle.created_at)
    if sort_dir == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # 페이지네이션
    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    titles = result.scalars().all()

    # 응답 구성 - Topic, SubTopic 테이블에서 카테고리명 조회 (배치 쿼리)
    topic_ids = list(set(t.topic_id for t in titles if t.topic_id))
    subtopic_ids = list(set(t.subtopic_id for t in titles if t.subtopic_id))
    group_ids = list(set(t.group_id for t in titles if t.group_id))

    # Topic 배치 조회
    topics_map = {}
    if topic_ids:
        topics_query = select(Topic).where(Topic.id.in_(topic_ids))
        topics_result = await db.execute(topics_query)
        topics_map = {t.id: t for t in topics_result.scalars().all()}

    # SubTopic 배치 조회
    subtopics_map = {}
    if subtopic_ids:
        subtopics_query = select(SubTopic).where(SubTopic.id.in_(subtopic_ids))
        subtopics_result = await db.execute(subtopics_query)
        subtopics_map = {s.id: s for s in subtopics_result.scalars().all()}

    # 그룹 배치 조회
    groups_map = {}
    if group_ids:
        groups_query = select(TitleGroup).where(TitleGroup.id.in_(group_ids))
        groups_result = await db.execute(groups_query)
        groups_map = {g.id: g for g in groups_result.scalars().all()}

    items = []
    for t in titles:
        item = MainTitleResponse.model_validate(t)
        # Topic 이름 설정
        if t.topic_id and t.topic_id in topics_map:
            topic = topics_map[t.topic_id]
            item.topic_name = topic.name
            item.category_name = topic.name
        # SubTopic 이름 설정
        if t.subtopic_id and t.subtopic_id in subtopics_map:
            subtopic = subtopics_map[t.subtopic_id]
            item.subtopic_name = subtopic.name
        # category_path: "주제 - 하위 주제" 형식
        if item.topic_name and item.subtopic_name:
            item.category_path = f"{item.topic_name} - {item.subtopic_name}"
        elif item.topic_name:
            item.category_path = item.topic_name
        # 그룹 정보 설정
        if t.group_id and t.group_id in groups_map:
            group = groups_map[t.group_id]
            item.group_name = group.name
            item.group_member_count = group.member_count
        items.append(item)

    return MainTitleListResponse(
        items=items, total=total, page=page, size=size, has_next=(page * size) < total
    )


@router.get("/{title_id}", response_model=MainTitleWithGroup)
async def get_main_title(
    title_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """정식 제목 상세 조회"""
    title = await db.get(MainTitle, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="제목을 찾을 수 없습니다")

    response = MainTitleWithGroup.model_validate(title)
    # Topic 이름 설정
    if title.topic_id:
        topic = await db.get(Topic, title.topic_id)
        if topic:
            response.topic_name = topic.name
            response.category_name = topic.name
    # SubTopic 이름 설정
    if title.subtopic_id:
        subtopic = await db.get(SubTopic, title.subtopic_id)
        if subtopic:
            response.subtopic_name = subtopic.name
    # category_path: "주제 - 하위 주제" 형식
    if response.topic_name and response.subtopic_name:
        response.category_path = f"{response.topic_name} - {response.subtopic_name}"
    elif response.topic_name:
        response.category_path = response.topic_name
    # 그룹 정보 설정
    if title.group_id:
        grp = await db.get(TitleGroup, title.group_id)
        if grp:
            response.group_name = grp.name
            response.group = TitleGroupResponse.model_validate(grp)

    return response


@router.post("", response_model=MainTitleResponse)
async def create_main_title(
    data: MainTitleCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """정식 제목 수동 생성"""
    title = MainTitle(
        title=data.title,
        category_id=data.category_id,
        topic_id=data.topic_id,
        subtopic_id=data.subtopic_id,
        status=data.status,
        source=data.source,
        source_temp_title_id=data.source_temp_title_id,
        source_url=data.source_url,
        location_info=data.location_info,
        keywords=data.keywords,
    )
    db.add(title)
    await db.commit()
    await db.refresh(title)

    logger.info(f"[CREATE_TITLE] 제목 생성: {title.id} - {title.title[:30]}")
    return MainTitleResponse.model_validate(title)


@router.put("/{title_id}", response_model=MainTitleResponse)
async def update_main_title(
    title_id: int,
    data: MainTitleUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """정식 제목 수정"""
    title = await db.get(MainTitle, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="제목을 찾을 수 없습니다")

    if data.title is not None:
        title.title = data.title
    if data.category_id is not None:
        title.category_id = data.category_id
    if data.group_id is not None:
        title.group_id = data.group_id
    if data.is_group_representative is not None:
        title.is_group_representative = data.is_group_representative
    if data.status is not None:
        title.status = data.status

    await db.commit()
    await db.refresh(title)

    return MainTitleResponse.model_validate(title)


@router.delete("/{title_id}")
async def delete_main_title(
    title_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """정식 제목 삭제"""
    title = await db.get(MainTitle, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="제목을 찾을 수 없습니다")

    # 이 제목을 representative_title_id로 참조하는 그룹이 있으면 참조 해제
    ref_groups_query = select(TitleGroup).where(TitleGroup.representative_title_id == title_id)
    ref_groups_result = await db.execute(ref_groups_query)
    ref_groups = ref_groups_result.scalars().all()
    for group in ref_groups:
        group.representative_title_id = None
        group.member_count = max(0, (group.member_count or 1) - 1)
        # 멤버가 없는 그룹은 삭제
        if group.member_count <= 0:
            await db.delete(group)

    # 그룹 멤버인 경우 카운트 업데이트
    if title.group_id:
        group = await db.get(TitleGroup, title.group_id)
        if group:
            group.member_count = max(0, (group.member_count or 1) - 1)

    await db.delete(title)
    await db.commit()

    return {"message": "삭제되었습니다"}
