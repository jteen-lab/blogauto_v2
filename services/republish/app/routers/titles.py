"""
정식 제목 API (MainTitle)

Features:
- MainTitle CRUD
- 페이지네이션, 검색, 필터링
"""
from typing import Optional, List, TYPE_CHECKING
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..core.config import settings
from ..models.title import MainTitle, TitleGroup
from ..models.keyword import KeywordCategory
from ..models.category import Topic, SubTopic, BlogCategory
from ..models.crawled_post import CrawledPost
from ..models.generation_history import GenerationHistory
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


async def _cleanup_post_images(
    post: CrawledPost, db: AsyncSession
) -> int:
    """
    CrawledPost에 연결된 이미지 파일(대표/섹션)을 삭제합니다.

    Args:
        post: 삭제 대상 CrawledPost
        db: 비동기 DB 세션

    Returns:
        삭제된 이미지 파일 수
    """
    import json
    from pathlib import Path

    deleted = 0

    def _remove_file(image_url: str | None) -> int:
        if not image_url:
            return 0
        try:
            filename = image_url.split("/")[-1]
            path = Path(settings.image_storage_dir) / filename
            if path.exists():
                path.unlink()
                return 1
        except Exception as e:
            logger.warning(f"[TITLES] 이미지 삭제 실패: {e}")
        return 0

    # 대표 이미지
    deleted += _remove_file(post.image_url)

    # GenerationHistory 연결 이미지
    if post.generation_history_id:
        gh_result = await db.execute(
            select(GenerationHistory)
            .where(GenerationHistory.id == post.generation_history_id)
        )
        gen_history = gh_result.scalar_one_or_none()
        if gen_history:
            deleted += _remove_file(gen_history.image_url)
            # 섹션 이미지
            if gen_history.section_images:
                try:
                    items = json.loads(gen_history.section_images)
                    if isinstance(items, list):
                        for item in items:
                            url = item.get("image_url") if isinstance(item, dict) else None
                            deleted += _remove_file(url)
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"[TITLES] 섹션 이미지 삭제 실패: {e}")

    return deleted


async def _build_blog_category_filter(
    blog_id: int,
    db: AsyncSession,
) -> Optional["ColumnElement"]:
    """
    블로그 카테고리 기반 MainTitle 필터 조건을 생성합니다.

    BlogCategory에서 해당 blog_id의 활성 카테고리를 조회한 뒤,
    subtopic_id가 있으면 subtopic 기준, topic_id만 있으면 topic 기준으로
    MainTitle을 필터링하는 OR 조건을 반환합니다.

    Args:
        blog_id: 블로그 ID
        db: 비동기 DB 세션

    Returns:
        SQLAlchemy WHERE 조건 또는 None (카테고리가 없는 경우)
    """
    # 해당 블로그의 활성 카테고리 조회
    bc_query = select(BlogCategory).where(
        BlogCategory.blog_id == blog_id,
        BlogCategory.is_active == True,
    )
    bc_result = await db.execute(bc_query)
    blog_categories = bc_result.scalars().all()

    if not blog_categories:
        logger.debug(f"[TITLE_FILTER] blog_id={blog_id}: 활성 카테고리 없음, 필터 미적용")
        return None

    # subtopic_id / topic_id 분리 수집
    subtopic_ids: set[int] = set()
    topic_only_ids: set[int] = set()

    for bc in blog_categories:
        if bc.subtopic_id:
            subtopic_ids.add(bc.subtopic_id)
        elif bc.topic_id:
            topic_only_ids.add(bc.topic_id)

    # OR 조건 구성
    conditions: list = []
    if subtopic_ids:
        conditions.append(MainTitle.subtopic_id.in_(list(subtopic_ids)))
    if topic_only_ids:
        conditions.append(MainTitle.topic_id.in_(list(topic_only_ids)))

    if not conditions:
        return None

    logger.debug(
        f"[TITLE_FILTER] blog_id={blog_id}: "
        f"subtopic_ids={subtopic_ids}, topic_only_ids={topic_only_ids}"
    )
    return or_(*conditions)


@router.get("", response_model=MainTitleListResponse)
async def list_main_titles(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    search: Optional[str] = Query(None, description="제목 검색"),
    category_id: Optional[int] = Query(None, description="카테고리 필터"),
    status: Optional[str] = Query(None, description="상태 필터"),
    group_id: Optional[int] = Query(None, description="그룹 필터"),
    representatives_only: bool = Query(False, description="대표 제목만"),
    ungrouped_only: bool = Query(False, description="미그룹 제목만"),
    hide_group_members: bool = Query(False, description="그룹 멤버 숨김 (대표+미그룹만 표시)"),
    blog_id: Optional[int] = Query(None, description="블로그 ID (매칭 필터용)"),
    matching_filter: Optional[str] = Query(None, description="매칭 필터: all/matched/unmatched"),
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
    - blog_id: 블로그 ID (매칭 필터링에 사용)
    - matching_filter: 매칭 필터 (all: 전체, matched: 매칭됨, unmatched: 독립포스트)
    """
    from ..models.crawled_post import CrawledPost

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

    # 블로그 카테고리 기반 필터링: blog_id가 있으면 해당 블로그 카테고리의 제목만 표시
    if blog_id:
        category_filter = await _build_blog_category_filter(blog_id, db)
        if category_filter is not None:
            query = query.where(category_filter)

    # Phase 2-2: 블로그-제목 매칭 필터
    if blog_id and matching_filter and matching_filter != "all":
        # 해당 블로그에서 매칭된 main_title_id들 조회
        matched_title_ids_subq = (
            select(CrawledPost.matched_main_title_id)
            .where(
                CrawledPost.blog_id == blog_id,
                CrawledPost.match_status == "matched",
                CrawledPost.matched_main_title_id.isnot(None)
            )
            .distinct()
            .scalar_subquery()
        )
        if matching_filter == "matched":
            # 매칭된 제목만
            query = query.where(MainTitle.id.in_(matched_title_ids_subq))
        elif matching_filter == "unmatched":
            # 매칭되지 않은 제목만 (독립 포스트)
            query = query.where(~MainTitle.id.in_(matched_title_ids_subq))

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

    # 블로그 선택 시: 발행대기 우선 → 매칭됨 → 미매칭 순으로 정렬.
    # 사용자가 매칭한 글(특히 발행대기)이 1페이지 상단에 보이도록 한다.
    if blog_id:
        pending_subq = select(CrawledPost.matched_main_title_id).where(
            CrawledPost.blog_id == blog_id,
            CrawledPost.match_status == "matched",
            CrawledPost.matched_main_title_id.isnot(None),
            CrawledPost.published_at.is_(None),
        ).distinct().scalar_subquery()
        matched_subq = select(CrawledPost.matched_main_title_id).where(
            CrawledPost.blog_id == blog_id,
            CrawledPost.match_status == "matched",
            CrawledPost.matched_main_title_id.isnot(None),
        ).distinct().scalar_subquery()
        match_priority = case(
            (MainTitle.id.in_(pending_subq), 0),  # 발행대기 최우선
            (MainTitle.id.in_(matched_subq), 1),  # 발행완료/매칭
            else_=2,                              # 미매칭(독립포스트)
        )
        if sort_dir == "asc":
            query = query.order_by(match_priority, sort_column.asc())
        else:
            query = query.order_by(match_priority, sort_column.desc())
    else:
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

    # Phase 2-2: blog_id가 있을 때 매칭된 크롤 포스트 배치 조회
    crawled_posts_map = {}
    if blog_id:
        title_ids = [t.id for t in titles]
        if title_ids:
            crawled_query = select(CrawledPost).where(
                CrawledPost.blog_id == blog_id,
                CrawledPost.matched_main_title_id.in_(title_ids),
                CrawledPost.match_status == "matched"
            )
            crawled_result = await db.execute(crawled_query)
            for cp in crawled_result.scalars().all():
                if cp.matched_main_title_id:
                    crawled_posts_map[cp.matched_main_title_id] = cp

    from ..schemas.title import CrawledPostInfo

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
        # Phase 2-2: 매칭된 크롤 포스트 정보
        if t.id in crawled_posts_map:
            cp = crawled_posts_map[t.id]
            item.matched_crawled_post = CrawledPostInfo(
                id=cp.id,
                title=cp.title,
                url=cp.url,
                match_score=cp.match_score,
                published_at=cp.published_at,
                image_url=cp.image_url,
                has_content=bool(cp.content_html),
            )
        items.append(item)

    return MainTitleListResponse(
        items=items, total=total, page=page, size=size, has_next=(page * size) < total
    )


@router.get("/unified")
async def list_titles_unified(
    blog_id: int = Query(..., description="블로그 ID (필수)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    search: Optional[str] = Query(None, description="제목 검색"),
    sort_field: Optional[str] = Query("created_at"),
    sort_dir: Optional[str] = Query("desc"),
    matching_filter: Optional[str] = Query("all", description="all|matched|unmatched"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """블로그 정식제목 + 미매칭 크롤링 통합 페이지네이션.

    백엔드에서 두 테이블을 합쳐 정렬한 후 페이지 단위로 응답한다.
    대용량(수만~수십만 건) 데이터에서도 안정적으로 동작하도록
    SQL OFFSET/LIMIT 기반 페이지네이션을 사용.

    matching_filter:
        - all: 메인 타이틀(BlogCategory 필터) + 미매칭 크롤링 통합
        - matched: 메인 타이틀 중 이 블로그가 매칭한 것만
        - unmatched: 메인 타이틀 중 매칭 안 된 것만 (미매칭 크롤링 제외)

    Returns:
        items: [{_kind: 'main'|'unmatched', ...}], total, main_total,
               unmatched_total, page, size, has_next
    """
    from ..models.crawled_post import CrawledPost as _CP
    from ..models.blog import Blog as _Blog

    blog = await db.get(_Blog, blog_id)
    if not blog:
        raise HTTPException(status_code=404, detail="블로그를 찾을 수 없습니다")

    # 1) 메인 타이틀 쿼리 빌드 (BlogCategory 필터 + hide_group_members + 매칭 필터)
    main_query = select(MainTitle)
    if search:
        main_query = main_query.where(MainTitle.title.ilike(f"%{search}%"))
    cat_filter = await _build_blog_category_filter(blog_id, db)
    if cat_filter is not None:
        main_query = main_query.where(cat_filter)

    # 이 블로그에 매칭된 MainTitle ID 서브쿼리.
    # 그룹 필터 예외 처리에 사용되므로 그룹 필터보다 먼저 정의한다.
    matched_subq = (
        select(_CP.matched_main_title_id)
        .where(
            _CP.blog_id == blog_id,
            _CP.match_status == "matched",
            _CP.matched_main_title_id.isnot(None),
        )
        .distinct()
        .scalar_subquery()
    )

    # 그룹 필터: 그룹 대표/단독/소그룹 만 표시하여 중복 노출을 줄인다.
    # 단, 이 블로그에 이미 매칭(발행대기/완료) 된 MainTitle 은
    # is_group_representative 가 아니더라도 반드시 노출되어야 한다.
    # (그렇지 않으면 슈마즈처럼 발행대기 글이 목록에서 사라지는 회귀가 발생)
    main_query = main_query.where(
        or_(
            MainTitle.is_group_representative.is_(True),
            MainTitle.group_id.is_(None),
            ~MainTitle.group_id.in_(
                select(TitleGroup.id).where(TitleGroup.member_count >= 2)
            ),
            MainTitle.id.in_(matched_subq),
        )
    )

    if matching_filter == "matched":
        main_query = main_query.where(MainTitle.id.in_(matched_subq))
    elif matching_filter == "unmatched":
        main_query = main_query.where(~MainTitle.id.in_(matched_subq))

    main_count = (
        await db.execute(
            select(func.count()).select_from(main_query.subquery())
        )
    ).scalar() or 0

    # 2) 미매칭 크롤링 쿼리 빌드 (matching_filter='all'에서만 사용)
    unmatched_count = 0
    include_unmatched = matching_filter == "all"
    if include_unmatched:
        unmatched_query = select(_CP).where(
            _CP.blog_id == blog_id,
            _CP.match_status == "unmatched",
        )
        if search:
            unmatched_query = unmatched_query.where(
                _CP.title.ilike(f"%{search}%")
            )
        unmatched_count = (
            await db.execute(
                select(func.count()).select_from(unmatched_query.subquery())
            )
        ).scalar() or 0

    grand_total = main_count + (unmatched_count if include_unmatched else 0)
    if grand_total == 0:
        return {
            "items": [], "total": 0, "main_total": 0, "unmatched_total": 0,
            "page": page, "size": size, "has_next": False,
        }

    # 3) 통합 정렬을 위한 sort 키 매핑
    main_sort_col_map = {
        "title": MainTitle.title,
        "created_at": MainTitle.created_at,
        "updated_at": MainTitle.updated_at,
        "status": MainTitle.status,
        "use_count": MainTitle.use_count,
    }
    unmatched_sort_col_map = {
        "title": _CP.title,
        "created_at": _CP.crawled_at,
        "updated_at": _CP.crawled_at,
        "status": _CP.match_status,
        "use_count": _CP.id,  # fallback
    }
    main_sort = main_sort_col_map.get(sort_field, MainTitle.created_at)
    main_query = main_query.order_by(
        main_sort.asc() if sort_dir == "asc" else main_sort.desc()
    )
    if include_unmatched:
        unm_sort = unmatched_sort_col_map.get(sort_field, _CP.crawled_at)
        unmatched_query = unmatched_query.order_by(
            unm_sort.asc() if sort_dir == "asc" else unm_sort.desc()
        )

    # 4) 통합 페이지네이션 (정확한 통합 정렬을 위해 전체 데이터를 fetch 후
    #    Python 측에서 합쳐 정렬 + 슬라이싱)
    #
    # 이전에는 fetch_limit = page * size 로 잘랐는데, main_count 가
    # fetch_limit 보다 크면 SQL 정렬 후순위 row 가 fetch 누락되어
    # "마지막 페이지까지 가도 일부 항목이 보이지 않는" 문제가 발생했다.
    # 통합 정렬과 일관성을 보장하기 위해 두 쿼리 모두 전체 결과를 가져온다.
    main_rows = (await db.execute(main_query)).scalars().all()
    unmatched_rows = []
    if include_unmatched:
        unmatched_rows = (await db.execute(unmatched_query)).scalars().all()

    # 5) 메인 타이틀 부가 정보 일괄 조회 (Topic/SubTopic/Group/matched_crawled_post)
    topic_ids = list({t.topic_id for t in main_rows if t.topic_id})
    subtopic_ids = list({t.subtopic_id for t in main_rows if t.subtopic_id})
    group_ids = list({t.group_id for t in main_rows if t.group_id})
    topics_map = {}
    if topic_ids:
        r = await db.execute(select(Topic).where(Topic.id.in_(topic_ids)))
        topics_map = {t.id: t for t in r.scalars().all()}
    subtopics_map = {}
    if subtopic_ids:
        r = await db.execute(select(SubTopic).where(SubTopic.id.in_(subtopic_ids)))
        subtopics_map = {s.id: s for s in r.scalars().all()}
    groups_map = {}
    if group_ids:
        r = await db.execute(select(TitleGroup).where(TitleGroup.id.in_(group_ids)))
        groups_map = {g.id: g for g in r.scalars().all()}

    crawled_map = {}
    main_ids = [t.id for t in main_rows]
    if main_ids:
        r = await db.execute(
            select(_CP).where(
                _CP.blog_id == blog_id,
                _CP.matched_main_title_id.in_(main_ids),
                _CP.match_status == "matched",
            )
        )
        for cp in r.scalars().all():
            if cp.matched_main_title_id:
                crawled_map[cp.matched_main_title_id] = cp

    # 6) 메인 행 → dict 변환
    def main_to_dict(t):
        d = {
            "_kind": "main",
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "topic_id": t.topic_id,
            "subtopic_id": t.subtopic_id,
            "group_id": t.group_id,
            "is_group_representative": t.is_group_representative,
            "use_count": t.use_count,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        if t.topic_id and t.topic_id in topics_map:
            d["topic_name"] = topics_map[t.topic_id].name
            d["category_name"] = topics_map[t.topic_id].name
        if t.subtopic_id and t.subtopic_id in subtopics_map:
            d["subtopic_name"] = subtopics_map[t.subtopic_id].name
        if d.get("topic_name") and d.get("subtopic_name"):
            d["category_path"] = f"{d['topic_name']} - {d['subtopic_name']}"
        elif d.get("topic_name"):
            d["category_path"] = d["topic_name"]
        if t.group_id and t.group_id in groups_map:
            g = groups_map[t.group_id]
            d["group_name"] = g.name
            d["group_member_count"] = g.member_count
        if t.id in crawled_map:
            cp = crawled_map[t.id]
            d["matched_crawled_post"] = {
                "id": cp.id,
                "title": cp.title,
                "url": cp.url,
                "match_score": cp.match_score,
                "published_at": (
                    cp.published_at.isoformat() if cp.published_at else None
                ),
                "image_url": cp.image_url,
                "has_content": bool(cp.content_html),
            }
        return d

    def unmatched_to_dict(cp):
        return {
            "_kind": "unmatched",
            "id": cp.id,
            "title": cp.title,
            "url": cp.url,
            "crawled_at": cp.crawled_at.isoformat() if cp.crawled_at else None,
            "match_status": cp.match_status,
        }

    # 7) Python 측 통합 정렬
    # status 정렬은 UI 표시 그룹 (독립포스트/발행대기/발행완료/미매칭) 기준으로
    # 처리한다. 백엔드 MainTitle.status 컬럼과 UI 표시 상태가 다르기 때문에
    # 컬럼만 정렬하면 사용자가 보는 동일 그룹이 흩어지는 문제가 있다.
    # 1차 키: display_status 그룹, 2차 키: title (가나다)
    DISPLAY_STATUS_ORDER = {
        "독립포스트": 0,
        "발행대기": 1,
        "발행완료": 2,
        "미매칭크롤": 3,
    }

    def compute_display_status(row: dict) -> str:
        if row.get("_kind") == "unmatched":
            return "미매칭크롤"
        mcp = row.get("matched_crawled_post")
        if not mcp:
            return "독립포스트"
        return "발행완료" if mcp.get("published_at") else "발행대기"

    def title_key(row: dict) -> str:
        return (row.get("title") or "").lower()

    def sort_key(row: dict):
        if sort_field == "title":
            return title_key(row)
        if sort_field in ("created_at", "updated_at"):
            return (
                row.get(sort_field)
                or row.get("created_at")
                or row.get("crawled_at")
                or ""
            )
        if sort_field == "status":
            # 1차: display_status 그룹, 2차: title 가나다
            return (
                DISPLAY_STATUS_ORDER.get(compute_display_status(row), 99),
                title_key(row),
            )
        if sort_field == "use_count":
            return row.get("use_count") or 0
        return row.get("created_at") or row.get("crawled_at") or ""

    combined = [main_to_dict(t) for t in main_rows]
    if include_unmatched:
        combined.extend(unmatched_to_dict(cp) for cp in unmatched_rows)

    # status 정렬에서 sort_dir 은 그룹 순서 자체를 뒤집는 의도이므로
    # 같은 그룹 내 2차 키(title)는 항상 오름차순(가나다)을 유지하기 위해
    # desc 인 경우에도 안정적인 두 단계 정렬을 사용한다.
    if sort_field == "status" and sort_dir != "asc":
        # 1) 2차 키 (title) 오름차순으로 먼저 안정 정렬
        combined.sort(key=title_key)
        # 2) 1차 키 (display_status) 내림차순 안정 정렬 (그룹만 역순)
        combined.sort(
            key=lambda r: DISPLAY_STATUS_ORDER.get(
                compute_display_status(r), 99
            ),
            reverse=True,
        )
    else:
        combined.sort(key=sort_key, reverse=(sort_dir != "asc"))

    # 8) 페이지 슬라이싱
    start = (page - 1) * size
    page_items = combined[start:start + size]
    has_next = (start + size) < grand_total

    return {
        "items": page_items,
        "total": grand_total,
        "main_total": main_count,
        "unmatched_total": unmatched_count,
        "page": page,
        "size": size,
        "has_next": has_next,
    }


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
    """정식 제목 수동 생성

    Args:
        data: 생성할 제목 데이터
        db: 데이터베이스 세션
        current_user: 인증된 사용자

    Returns:
        생성된 MainTitle 응답

    Raises:
        HTTPException: 동일 (title, topic_id) 조합이 이미 존재할 때 409 Conflict
    """
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
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning(f"[CREATE_TITLE] 중복 제목: '{data.title[:30]}' (topic_id={data.topic_id})")
        raise HTTPException(
            status_code=409,
            detail=f"동일한 제목이 이미 존재합니다 (topic_id={data.topic_id})"
        )
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
    permanent: bool = Query(False, description="True면 DB에서 완전 삭제"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    정식 제목 삭제/초기화

    permanent=False (기본): 연결된 CrawledPost 삭제 + MainTitle status를 available로 리셋
    permanent=True: 연결된 CrawledPost 삭제 + MainTitle도 DB에서 완전 삭제
    """
    title = await db.get(MainTitle, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="제목을 찾을 수 없습니다")

    # 1. 연결된 모든 CrawledPost 조회 (발행 여부 무관)
    posts_result = await db.execute(
        select(CrawledPost).where(
            CrawledPost.matched_main_title_id == title_id,
        )
    )
    linked_posts = list(posts_result.scalars().all())

    # 2. CrawledPost + 이미지 파일 삭제
    deleted_posts = 0
    deleted_images = 0
    for post in linked_posts:
        deleted_images += await _cleanup_post_images(post, db)
        await db.delete(post)
        deleted_posts += 1

    if deleted_posts:
        await db.flush()

    # 3. TitleGroup 참조 정리
    ref_groups_query = select(TitleGroup).where(
        TitleGroup.representative_title_id == title_id
    )
    ref_groups_result = await db.execute(ref_groups_query)
    ref_groups = ref_groups_result.scalars().all()
    for group in ref_groups:
        group.representative_title_id = None
        group.member_count = max(0, (group.member_count or 1) - 1)
        if group.member_count <= 0:
            await db.delete(group)

    if title.group_id:
        group = await db.get(TitleGroup, title.group_id)
        if group:
            group.member_count = max(0, (group.member_count or 1) - 1)

    # 4. MainTitle 처리
    if permanent:
        await db.delete(title)
        action = "삭제"
    else:
        title.status = "available"
        title.use_count = 0
        title.last_used_at = None
        action = "초기화"

    await db.commit()

    logger.info(
        f"[TITLES] 제목 {action}: id={title_id} | "
        f"삭제된 포스트={deleted_posts} | 삭제된 이미지={deleted_images}"
    )

    return {
        "message": f"제목이 {action}되었습니다",
        "deleted_posts": deleted_posts,
        "deleted_images": deleted_images,
    }


# ===== 수동 그룹 관리 API =====

from pydantic import BaseModel, Field


class ManualGroupRequest(BaseModel):
    """수동 그룹 매칭 요청"""
    title_ids: List[int] = Field(..., min_length=2, description="그룹으로 묶을 제목 ID 목록 (최소 2개)")
    group_name: Optional[str] = Field(None, description="그룹명 (미지정 시 첫 제목 사용)")


class RemoveFromGroupRequest(BaseModel):
    """그룹에서 제목 제외 요청"""
    title_ids: List[int] = Field(..., min_length=1, description="그룹에서 제외할 제목 ID 목록")


@router.post("/groups/manual", summary="수동 그룹 매칭")
async def manual_group_titles(
    data: ManualGroupRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    선택한 제목들을 수동으로 활성 그룹으로 묶습니다.

    동작 방식:
    1. 선택한 제목 중 활성 그룹(멤버 2개 이상)의 대표가 있으면 → 해당 그룹에 나머지를 멤버로 추가
    2. 여러 활성 그룹이 선택된 경우 → 첫 번째 그룹에 다른 그룹의 모든 멤버를 병합
    3. 모두 개별 제목인 경우 → 첫 번째 제목이 대표인 새 그룹 생성
    """
    from datetime import datetime

    if len(data.title_ids) < 2:
        raise HTTPException(status_code=400, detail="최소 2개 이상의 제목이 필요합니다")

    # 선택된 제목 조회
    titles_query = select(MainTitle).where(MainTitle.id.in_(data.title_ids))
    titles_result = await db.execute(titles_query)
    selected_titles = list(titles_result.scalars().all())
    selected_titles_map = {t.id: t for t in selected_titles}

    if len(selected_titles) != len(data.title_ids):
        raise HTTPException(status_code=404, detail="일부 제목을 찾을 수 없습니다")

    # 선택된 제목들의 그룹 정보 수집
    selected_group_ids = set(t.group_id for t in selected_titles if t.group_id)

    # 활성 그룹(멤버 2개 이상) 조회
    active_groups = []
    if selected_group_ids:
        groups_query = select(TitleGroup).where(
            TitleGroup.id.in_(selected_group_ids),
            TitleGroup.member_count >= 2
        )
        groups_result = await db.execute(groups_query)
        active_groups = list(groups_result.scalars().all())

    # === 시나리오 판단 ===

    # 시나리오 1 & 2: 활성 그룹이 있는 경우 - 첫 번째 활성 그룹에 병합
    if active_groups:
        from sqlalchemy import update as sql_update

        # 첫 번째 활성 그룹을 타겟으로 선택
        target_group = active_groups[0]
        target_group_id = target_group.id

        # 타겟 그룹의 모든 멤버 조회
        target_members_query = select(MainTitle).where(MainTitle.group_id == target_group_id)
        target_members_result = await db.execute(target_members_query)
        target_members = {t.id: t for t in target_members_result.scalars().all()}

        # 다른 활성 그룹들의 모든 멤버도 타겟 그룹으로 이동
        other_group_ids = [g.id for g in active_groups[1:]]
        other_members = {}
        groups_to_delete_ids = []

        if other_group_ids:
            other_members_query = select(MainTitle).where(MainTitle.group_id.in_(other_group_ids))
            other_members_result = await db.execute(other_members_query)
            other_members = {t.id: t for t in other_members_result.scalars().all()}
            groups_to_delete_ids = other_group_ids

        # 병합할 제목 ID들 (타겟 그룹에 없는 것들)
        title_ids_to_merge = []

        # 선택된 제목 중 타겟 그룹에 없는 것들
        for title in selected_titles:
            if title.id not in target_members:
                title_ids_to_merge.append(title.id)

        # 다른 활성 그룹의 멤버들 (타겟 그룹에 없는 것들)
        for title_id in other_members.keys():
            if title_id not in target_members and title_id not in title_ids_to_merge:
                title_ids_to_merge.append(title_id)

        # 병합 실행 - 직접 UPDATE 쿼리 사용
        merged_count = 0
        if title_ids_to_merge:
            update_stmt = sql_update(MainTitle).where(
                MainTitle.id.in_(title_ids_to_merge)
            ).values(
                group_id=target_group_id,
                is_group_representative=False,
                grouped_at=datetime.utcnow()
            )
            await db.execute(update_stmt)
            merged_count = len(title_ids_to_merge)
            logger.info(f"[MANUAL_GROUP] 병합할 제목 ID: {title_ids_to_merge}")

        # 타겟 그룹 멤버 수 업데이트
        total_members = len(target_members) + merged_count
        target_group.member_count = total_members

        # 삭제할 그룹 처리 - 직접 DELETE 쿼리 사용
        if groups_to_delete_ids:
            from sqlalchemy import delete as sql_delete
            delete_stmt = sql_delete(TitleGroup).where(TitleGroup.id.in_(groups_to_delete_ids))
            await db.execute(delete_stmt)

        await db.commit()

        logger.info(f"[MANUAL_GROUP] 그룹 병합: target_group_id={target_group_id}, merged={merged_count}, deleted_groups={len(groups_to_delete_ids)}")

        return {
            "success": True,
            "group_id": target_group_id,
            "group_name": target_group.name,
            "member_count": total_members,
            "merged_count": merged_count,
            "deleted_groups": len(groups_to_delete_ids),
            "message": f"{merged_count}개 제목이 그룹에 추가되었습니다"
        }

    # 시나리오 3: 모두 개별 제목 (또는 비활성 그룹의 멤버) - 새 그룹 생성
    else:
        from sqlalchemy import update as sql_update, delete as sql_delete

        # 기존 그룹 ID 수집
        old_group_ids = set(t.group_id for t in selected_titles if t.group_id)

        # 기존 그룹들의 멤버 수 업데이트 및 빈 그룹 삭제
        groups_to_delete_ids = []
        if old_group_ids:
            old_groups_query = select(TitleGroup).where(TitleGroup.id.in_(old_group_ids))
            old_groups_result = await db.execute(old_groups_query)
            for old_group in old_groups_result.scalars().all():
                # 이 그룹에서 빠지는 제목 수
                leaving_count = sum(1 for t in selected_titles if t.group_id == old_group.id)
                new_member_count = (old_group.member_count or 0) - leaving_count

                if new_member_count <= 1:
                    # 멤버가 1개 이하면 그룹 삭제, 남은 멤버는 그룹 해제
                    remaining_update = sql_update(MainTitle).where(
                        MainTitle.group_id == old_group.id,
                        ~MainTitle.id.in_(data.title_ids)
                    ).values(group_id=None, is_group_representative=False)
                    await db.execute(remaining_update)
                    groups_to_delete_ids.append(old_group.id)
                else:
                    old_group.member_count = new_member_count
                    # 대표가 빠진 경우 새 대표 설정
                    if old_group.representative_title_id in data.title_ids:
                        new_rep_query = select(MainTitle).where(
                            MainTitle.group_id == old_group.id,
                            ~MainTitle.id.in_(data.title_ids)
                        ).limit(1)
                        new_rep = (await db.execute(new_rep_query)).scalars().first()
                        if new_rep:
                            old_group.representative_title_id = new_rep.id
                            # 새 대표 설정 - UPDATE 쿼리 사용
                            await db.execute(sql_update(MainTitle).where(
                                MainTitle.id == new_rep.id
                            ).values(is_group_representative=True))

        # 새 그룹 생성
        rep_title = selected_titles[0]
        group_name = data.group_name or rep_title.title[:50]
        new_group = TitleGroup(
            name=group_name,
            category_id=rep_title.topic_id,
            member_count=len(selected_titles),
            is_active=True,
        )
        db.add(new_group)
        await db.flush()  # ID 생성

        logger.info(f"[MANUAL_GROUP] 새 그룹 생성됨: group_id={new_group.id}, title_ids={data.title_ids}")

        # 제목들을 새 그룹에 연결 - 직접 UPDATE 쿼리 사용
        # 먼저 모든 제목을 멤버로 설정
        update_all_stmt = sql_update(MainTitle).where(
            MainTitle.id.in_(data.title_ids)
        ).values(
            group_id=new_group.id,
            grouped_at=datetime.utcnow(),
            is_group_representative=False
        )
        await db.execute(update_all_stmt)

        # 첫 번째 제목을 대표로 설정
        rep_title_id = data.title_ids[0]
        update_rep_stmt = sql_update(MainTitle).where(
            MainTitle.id == rep_title_id
        ).values(is_group_representative=True)
        await db.execute(update_rep_stmt)

        # 그룹의 대표 제목 ID 설정
        new_group.representative_title_id = rep_title_id

        # 빈 그룹 삭제
        if groups_to_delete_ids:
            delete_stmt = sql_delete(TitleGroup).where(TitleGroup.id.in_(groups_to_delete_ids))
            await db.execute(delete_stmt)

        await db.commit()

        logger.info(f"[MANUAL_GROUP] 새 그룹 생성 완료: group_id={new_group.id}, count={len(selected_titles)}, rep_id={rep_title_id}")

        return {
            "success": True,
            "group_id": new_group.id,
            "group_name": new_group.name,
            "member_count": len(selected_titles),
            "representative_title_id": rep_title_id,
            "message": f"{len(selected_titles)}개 제목이 새 그룹으로 묶였습니다"
        }


@router.post("/groups/{group_id}/remove", summary="그룹에서 제목 제외")
async def remove_from_group(
    group_id: int,
    data: RemoveFromGroupRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    선택한 제목들을 그룹에서 제외합니다.

    - 제외된 제목은 미그룹 상태가 됩니다.
    - 그룹 멤버가 1개 이하가 되면 그룹이 삭제됩니다.
    """
    # 그룹 조회
    group = await db.get(TitleGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")

    # 제목 조회
    titles_query = select(MainTitle).where(
        MainTitle.id.in_(data.title_ids),
        MainTitle.group_id == group_id
    )
    titles_result = await db.execute(titles_query)
    titles = list(titles_result.scalars().all())

    if not titles:
        raise HTTPException(status_code=404, detail="그룹에 속한 제목을 찾을 수 없습니다")

    removed_count = 0
    removed_rep = False

    for title in titles:
        if title.is_group_representative:
            removed_rep = True
        title.group_id = None
        title.is_group_representative = False
        title.grouped_at = None
        title.similarity_score = None
        removed_count += 1

    # 그룹 멤버 수 업데이트
    remaining_count = (group.member_count or 0) - removed_count
    group.member_count = max(0, remaining_count)

    # 대표 제목이 제외된 경우 새 대표 설정
    if removed_rep:
        new_rep_query = select(MainTitle).where(MainTitle.group_id == group_id).limit(1)
        new_rep = (await db.execute(new_rep_query)).scalars().first()
        if new_rep:
            new_rep.is_group_representative = True
            group.representative_title_id = new_rep.id
        else:
            group.representative_title_id = None

    # 그룹 멤버가 1개 이하면 그룹 삭제
    group_deleted = False
    if remaining_count <= 1:
        # 남은 멤버가 있으면 그룹 해제
        if remaining_count == 1:
            last_member_query = select(MainTitle).where(MainTitle.group_id == group_id)
            last_member = (await db.execute(last_member_query)).scalars().first()
            if last_member:
                last_member.group_id = None
                last_member.is_group_representative = False

        # 그룹 삭제
        await db.delete(group)
        group_deleted = True
        logger.info(f"[REMOVE_GROUP] 그룹 삭제 (멤버 부족): group_id={group_id}")

    await db.commit()

    return {
        "success": True,
        "removed_count": removed_count,
        "remaining_count": max(0, remaining_count - 1) if group_deleted else remaining_count,
        "group_deleted": group_deleted,
        "message": f"{removed_count}개 제목이 그룹에서 제외되었습니다" + (" (그룹 삭제됨)" if group_deleted else "")
    }


class PairMatchRequest(BaseModel):
    """1:1 페어 매칭 요청"""
    crawled_post_id: int = Field(..., description="매칭할 크롤링 포스트 ID")
    blog_id: int = Field(..., description="블로그 ID")


@router.post("/main/{main_title_id}/pair-match", summary="1:1 페어 매칭")
async def pair_match_title(
    main_title_id: int,
    data: PairMatchRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    독립 포스트(MainTitle)와 미매칭 크롤링 포스트를 수동으로 1:1 매칭합니다.

    - 크롤링 포스트의 match_status가 'unmatched'인 경우에만 매칭 가능
    - 매칭 후 크롤링 포스트의 matched_main_title_id에 해당 MainTitle ID가 설정됨
    - match_score는 100.0 (수동 매칭)으로 설정됨
    """
    from ..models.crawled_post import CrawledPost
    from datetime import datetime

    # MainTitle 조회
    main_title = await db.get(MainTitle, main_title_id)
    if not main_title:
        raise HTTPException(status_code=404, detail="정식 제목을 찾을 수 없습니다")

    # CrawledPost 조회
    crawled_post = await db.get(CrawledPost, data.crawled_post_id)
    if not crawled_post:
        raise HTTPException(status_code=404, detail="크롤링 포스트를 찾을 수 없습니다")

    # 블로그 ID 검증
    if crawled_post.blog_id != data.blog_id:
        raise HTTPException(status_code=400, detail="블로그 ID가 일치하지 않습니다")

    # 미매칭 상태 확인
    if crawled_post.match_status != "unmatched":
        raise HTTPException(
            status_code=400,
            detail=f"미매칭 상태의 포스트만 매칭할 수 있습니다 (현재 상태: {crawled_post.match_status})"
        )

    # 수동 매칭 처리
    crawled_post.match_status = "matched"
    crawled_post.matched_main_title_id = main_title_id
    crawled_post.match_score = 100.0  # 수동 매칭은 100% 점수
    crawled_post.updated_at = datetime.now()

    await db.commit()
    await db.refresh(crawled_post)

    logger.info(
        f"[PAIR_MATCH] 수동 매칭 완료 | "
        f"main_title_id={main_title_id} | "
        f"crawled_post_id={data.crawled_post_id} | "
        f"blog_id={data.blog_id}"
    )

    return {
        "success": True,
        "message": "1:1 페어 매칭이 완료되었습니다",
        "main_title_id": main_title_id,
        "main_title": main_title.title,
        "crawled_post_id": data.crawled_post_id,
        "crawled_post_title": crawled_post.title,
    }


@router.post("/main/{main_title_id}/unmatch", summary="매칭 해제")
async def unmatch_title(
    main_title_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    메인 타이틀과 매칭된 크롤링 포스트의 매칭을 해제합니다.

    - 메인 타이틀은 독립포스트로 돌아갑니다.
    - 크롤링 포스트는 미매칭 상태로 돌아갑니다.
    """
    from ..models.crawled_post import CrawledPost
    from sqlalchemy import update as sql_update
    from datetime import datetime

    # MainTitle 조회
    main_title = await db.get(MainTitle, main_title_id)
    if not main_title:
        raise HTTPException(status_code=404, detail="정식 제목을 찾을 수 없습니다")

    # 매칭된 크롤링 포스트 조회
    matched_query = select(CrawledPost).where(
        CrawledPost.matched_main_title_id == main_title_id,
        CrawledPost.match_status == "matched"
    )
    result = await db.execute(matched_query)
    matched_posts = result.scalars().all()

    if not matched_posts:
        raise HTTPException(status_code=404, detail="매칭된 크롤링 포스트가 없습니다")

    # 모든 매칭된 포스트의 매칭 해제
    unmatch_count = 0
    for post in matched_posts:
        post.match_status = "unmatched"
        post.matched_main_title_id = None
        post.match_score = None
        post.updated_at = datetime.now()
        unmatch_count += 1

    await db.commit()

    logger.info(
        f"[UNMATCH] 매칭 해제 완료 | "
        f"main_title_id={main_title_id} | "
        f"unmatched_count={unmatch_count}"
    )

    return {
        "success": True,
        "message": f"매칭이 해제되었습니다. {unmatch_count}개 포스트가 미매칭 상태로 변경되었습니다",
        "main_title_id": main_title_id,
        "unmatched_count": unmatch_count
    }


@router.delete("/groups/{group_id}", summary="그룹 해제")
async def dissolve_group(
    group_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    그룹을 해제하고 모든 멤버를 미그룹 상태로 변경합니다.

    - 그룹이 삭제됩니다.
    - 멤버 제목들은 삭제되지 않고 미그룹 상태가 됩니다.
    """
    # 그룹 조회
    group = await db.get(TitleGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")

    # 그룹 멤버 조회
    members_query = select(MainTitle).where(MainTitle.group_id == group_id)
    members_result = await db.execute(members_query)
    members = list(members_result.scalars().all())

    # 모든 멤버 그룹 해제
    for member in members:
        member.group_id = None
        member.is_group_representative = False
        member.grouped_at = None
        member.similarity_score = None

    # 그룹 삭제
    await db.delete(group)
    await db.commit()

    logger.info(f"[DISSOLVE_GROUP] 그룹 해제: group_id={group_id}, members={len(members)}")

    return {
        "success": True,
        "disbanded_count": len(members),
        "message": f"그룹이 해제되었습니다. {len(members)}개 제목이 미그룹 상태가 되었습니다"
    }
