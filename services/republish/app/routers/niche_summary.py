"""니치 현황 요약 — 어느 니치에 제목이 얼마나 쌓였나.

정식제목 탭의 **네비게이션**이다. 숫자만 보고 "어디를 채워야 하는지"
판단할 수 있어야 수집·생성을 적극적으로 돌리게 된다.

두 값을 함께 본다.

    재고    이 니치에 쓸 수 있는 정식제목 수
    블로그  이 니치를 쓰는 블로그 수

**블로그 0인 니치의 재고는 죽은 재고다.** 아무도 꺼내 쓰지 않는다.
반대로 블로그는 많은데 재고가 적으면 그쪽부터 채워야 한다.

계획서: docs/plans/title_tab_workplan.md §9
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.blog import Blog
from ..models.category import BlogCategory, Keyword, SubTopic, Topic
from ..models.keyword_candidate import KeywordCandidate
from ..models.title import MainTitle
from ..models.user import User
from ..routers.auth import get_current_user

router = APIRouter(prefix="/data/niches", tags=["data-titles"])
logger = get_logger("niche_summary", "app.log")

# 이보다 적으면 "부족" 으로 본다. 블로그 하나가 며칠 쓸 분량이다.
DEFAULT_LOW = 20

# 요약탭에 띄울 카드 수. 슬라이드로 더 볼 수 있지만 무한히 깔면
# 정식제목 목록이 화면 밖으로 밀린다.
DEFAULT_CARDS = 12


class NicheRow(BaseModel):
    """니치 한 줄."""

    topic_id: int
    topic_name: str
    subtopic_id: int
    subtopic_name: str
    titles: int = 0
    blogs: int = 0
    # 카드를 펼쳤을 때 보여 줄 것들
    blog_names: List[str] = []
    # 제목을 만들 재료. 0 이면 생성 버튼을 눌러도 0건이다.
    keywords: int = 0
    # 카테고리 키워드 — 채택 키워드가 없을 때 수집 시드로 쓴다
    seeds: int = 0
    # 쓰는 블로그가 있는데 재고가 적은 곳 — 여기부터 채워야 한다
    is_low: bool = False
    # 재고는 있는데 쓰는 블로그가 없는 곳 — 죽은 재고
    is_orphan: bool = False


class NicheSummaryResponse(BaseModel):
    items: List[NicheRow]
    total_titles: int = 0
    low_count: int = 0
    orphan_count: int = 0
    threshold: int = DEFAULT_LOW
    card_limit: int = DEFAULT_CARDS


@router.get("", response_model=NicheSummaryResponse)
async def niche_summary(
    low_threshold: Optional[int] = Query(None, ge=1, le=1000),
    only_used: bool = Query(
        False, description="블로그가 쓰는 니치만 — 죽은 재고를 숨긴다"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> NicheSummaryResponse:
    """니치별 재고·블로그·키워드.

    삭제된 분류는 뺀다 — 분류 매처가 쓰지 않는 것을 보여 주면 사람이
    그쪽을 채우려 든다.

    부족한 것부터 앞에 온다. 요약탭은 앞에서부터 잘라 쓴다.
    """
    settings = await _settings(db)
    threshold = low_threshold or settings["low_threshold"]

    rows = await _rows(db, current_user.id)
    names = await _blog_names(db)

    items: List[NicheRow] = []
    for row in rows:
        count, blog_count = int(row.titles or 0), int(row.blogs or 0)
        if only_used and not blog_count:
            continue
        items.append(NicheRow(
            topic_id=row.topic_id, topic_name=row.topic_name,
            subtopic_id=row.subtopic_id, subtopic_name=row.subtopic_name,
            titles=count, blogs=blog_count,
            blog_names=names.get(row.subtopic_id, []),
            keywords=int(row.keywords or 0), seeds=int(row.seeds or 0),
            is_low=bool(blog_count and count < threshold),
            is_orphan=bool(count and not blog_count)))

    # 부족한 니치를 앞으로. 그 안에서는 재고가 적은 것부터.
    items.sort(key=lambda r: (not r.is_low, r.titles, r.subtopic_name))

    return NicheSummaryResponse(
        items=items,
        total_titles=sum(r.titles for r in items),
        low_count=sum(1 for r in items if r.is_low),
        orphan_count=sum(1 for r in items if r.is_orphan),
        threshold=threshold,
        card_limit=settings["card_limit"])


class NicheSettings(BaseModel):
    """요약탭 설정 — 화면과 수집이 같은 값을 쓴다."""

    low_threshold: int = DEFAULT_LOW
    card_limit: int = DEFAULT_CARDS


@router.get("/settings", response_model=NicheSettings)
async def get_settings(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> NicheSettings:
    """부족 기준·카드 노출 수."""
    return NicheSettings(**await _settings(db))


@router.put("/settings", response_model=NicheSettings)
async def put_settings(
    payload: NicheSettings,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> NicheSettings:
    """저장. 수집기(niche_demand)도 같은 값을 읽는다."""
    from ..services.system_settings_service import SystemSettingsService

    low = max(1, min(1000, payload.low_threshold))
    cards = max(1, min(100, payload.card_limit))
    await SystemSettingsService.set_many(
        {"niche_low_threshold": str(low), "niche_card_limit": str(cards)}, db)
    logger.info("[NICHE_SUMMARY] 설정 저장 | 기준=%d | 카드=%d", low, cards)
    return NicheSettings(low_threshold=low, card_limit=cards)


async def _settings(db: AsyncSession) -> dict:
    """저장된 설정. 실패해도 화면은 떠야 하므로 기본값으로 떨어진다."""
    from ..services.system_settings_service import SystemSettingsService

    try:
        return {
            "low_threshold": await SystemSettingsService.get_int(
                "niche_low_threshold", DEFAULT_LOW, db),
            "card_limit": await SystemSettingsService.get_int(
                "niche_card_limit", DEFAULT_CARDS, db),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("[NICHE_SUMMARY] 설정 로드 실패 | %s", e)
        return {"low_threshold": DEFAULT_LOW, "card_limit": DEFAULT_CARDS}


async def _blog_names(db: AsyncSession) -> dict:
    """니치별 블로그 이름.

    집계 쿼리에 붙이면 `array_agg` 가 필요한데 그건 PostgreSQL 전용이다.
    니치는 100여 개라 따로 한 번 읽는 편이 낫다.
    """
    rows = (await db.execute(
        select(BlogCategory.subtopic_id, Blog.name)
        .join(Blog, Blog.id == BlogCategory.blog_id)
        .where(BlogCategory.is_active.is_(True),
               BlogCategory.subtopic_id.is_not(None))
        .distinct()
        .order_by(BlogCategory.subtopic_id, Blog.name)
    )).all()
    out: dict = {}
    for sid, name in rows:
        if name:
            out.setdefault(sid, []).append(name)
    return out


async def _rows(db: AsyncSession, user_id: int):
    """니치별 집계 한 방.

    블로그는 이름까지 가져온다 — 카드를 펼쳤을 때 "군타, 굿팁꿀팁" 처럼
    누가 쓰는지 보여야 채울 가치가 있는지 판단이 된다.
    """
    titles = (
        select(MainTitle.subtopic_id.label("sid"),
               func.count(MainTitle.id).label("n"))
        .where(MainTitle.status == "available",
               MainTitle.subtopic_id.is_not(None))
        .group_by(MainTitle.subtopic_id).subquery())
    blogs = (
        select(BlogCategory.subtopic_id.label("sid"),
               func.count(func.distinct(BlogCategory.blog_id)).label("n"))
        .where(BlogCategory.is_active.is_(True),
               BlogCategory.subtopic_id.is_not(None))
        .group_by(BlogCategory.subtopic_id).subquery())
    # 채택됐고 아직 제목을 안 만든 키워드 — 지금 생성에 쓸 수 있는 재료
    kw = (
        select(KeywordCandidate.subtopic_id.label("sid"),
               func.count(KeywordCandidate.id).label("n"))
        .where(KeywordCandidate.user_id == user_id,
               KeywordCandidate.verdict == "adopt",
               KeywordCandidate.titled.is_(False),
               KeywordCandidate.subtopic_id.is_not(None))
        .group_by(KeywordCandidate.subtopic_id).subquery())
    # 카테고리 키워드 — 채택 키워드가 없을 때 수집 시드가 된다
    seeds = (
        select(Keyword.subtopic_id.label("sid"),
               func.count(Keyword.id).label("n"))
        .where(Keyword.is_deleted.is_(False))
        .group_by(Keyword.subtopic_id).subquery())

    return (await db.execute(
        select(Topic.id.label("topic_id"), Topic.name.label("topic_name"),
               SubTopic.id.label("subtopic_id"),
               SubTopic.name.label("subtopic_name"),
               func.coalesce(titles.c.n, 0).label("titles"),
               func.coalesce(blogs.c.n, 0).label("blogs"),
               func.coalesce(kw.c.n, 0).label("keywords"),
               func.coalesce(seeds.c.n, 0).label("seeds"))
        .select_from(SubTopic)
        .join(Topic, Topic.id == SubTopic.topic_id)
        .outerjoin(titles, titles.c.sid == SubTopic.id)
        .outerjoin(blogs, blogs.c.sid == SubTopic.id)
        .outerjoin(kw, kw.c.sid == SubTopic.id)
        .outerjoin(seeds, seeds.c.sid == SubTopic.id)
        .where(SubTopic.is_deleted.is_(False), Topic.is_deleted.is_(False),
               Topic.user_id == user_id)
    )).all()
