"""키워드 관리(실험실) 라우터.

기존 수집을 대체할지 판단하기 위한 별도 화면이다. 여기서 만든 데이터는
`keyword_candidates` 에만 들어가며 운영 파이프라인에 영향을 주지 않는다.

순서도: docs/flowcharts/keyword_lab.md
"""
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models import User
from ..models.blog import Blog
from ..models.keyword_candidate import KeywordCandidate
from ..models.user_settings import UserSettings
from ..routers.auth import get_current_user
from ..services.keyword_lab.service import KeywordLabService

logger = get_logger("keyword_lab_router", "app.log")

router = APIRouter(prefix="/api/v1/keyword-lab", tags=["키워드 관리"])
page_router = APIRouter(tags=["페이지"])
templates = Jinja2Templates(directory="app/templates")


async def _settings(db: AsyncSession, user: User) -> UserSettings:
    row = (await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(400, "사용자 설정이 없습니다. 설정에서 API 키를 먼저 등록하세요")
    return row


def _service(db: AsyncSession, settings: UserSettings, user: User):
    return KeywordLabService(db, settings, user.id)


@page_router.get("/keyword-lab", response_class=HTMLResponse)
async def keyword_lab_page(request: Request):
    """키워드 관리 화면."""
    return templates.TemplateResponse(
        "keyword_lab/index.html", {"request": request})


@router.get("/status", summary="API 키 설정 상태")
async def api_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """키가 없으면 화면이 먼저 알려 준다. 눌러 보고 실패하는 것보다 낫다."""
    s = (await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )).scalar_one_or_none()
    return {
        "naver_ads": bool(s and s.naver_ads_api_key and s.naver_ads_secret_key
                          and s.naver_ads_customer_id),
        "naver_search": bool(s and s.naver_search_client_id
                             and s.naver_search_client_secret),
    }


@router.get("/modules", summary="키워드 모듈 목록")
async def list_modules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """수동 실행 대상으로 고를 키워드 모듈들."""
    from ..models.module import Module, ModuleType

    rows = (await db.execute(
        select(Module, ModuleType)
        .join(ModuleType, ModuleType.id == Module.module_type_id)
        .where(Module.user_id == current_user.id,
               ModuleType.code == "keyword",
               Module.is_deleted.is_(False))
        .order_by(Module.name)
    )).all()
    return {"modules": [{
        "id": m.id, "name": m.name,
        "settings": (m.settings or {}).get("keyword") or {},
        "blogs": ((m.settings or {}).get("blogs") or []),
    } for m, _ in rows]}


@router.post("/run", summary="모듈 한 회차 수동 실행")
async def run_module(
    module_id: Optional[int] = Body(None),
    blog_id: Optional[int] = Body(None),
    steps: Optional[List[str]] = Body(None),
    force: bool = Body(True),
    settings_override: Optional[dict] = Body(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """자동 실행과 **같은 실행기**를 부른다.

    다른 코드를 타면 화면에서는 되는데 자동에서만 안 되는 일이 생긴다.
    수동이므로 재고가 충분해도 돌린다(force 기본 true).
    """
    from ..models.module import Module
    from ..services.keyword_lab.runner import KeywordModuleRunner

    settings = settings_override
    if module_id and settings is None:
        module = (await db.execute(
            select(Module).where(Module.id == module_id,
                                 Module.user_id == current_user.id)
        )).scalar_one_or_none()
        if not module:
            raise HTTPException(404, "모듈을 찾을 수 없습니다")
        settings = module.settings or {}
        if blog_id is None:
            blogs = (settings.get("blogs") or [])
            blog_id = blogs[0] if blogs else None

    runner = KeywordModuleRunner(db, current_user.id)
    result = await runner.run(settings, blog_id=blog_id,
                              force=force, steps=steps)
    if not result.get("success"):
        raise HTTPException(400, result.get("error") or "실행 실패")
    return result


@router.post("/test-connection", summary="네이버 API 연결 테스트")
async def test_connection(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """실제로 호출해 본다.

    키가 '채워져 있는지' 만 보면 잘못된 값도 통과한다. 실제로 고객 ID 가
    한 글자('e')로 저장돼 있었는데 status 는 정상으로 보였다.
    """
    from ..services.naver_ads_service import NaverAdsService
    from ..services.naver_search_service import NaverSearchService

    settings = await _settings(db, current_user)

    ads = {"configured": False, "ok": False, "error": None}
    svc = NaverAdsService(settings)
    ads["configured"] = svc.is_configured()
    if ads["configured"]:
        r = await svc.get_keyword_stats(["테스트"], include_related=False)
        ads["ok"] = bool(r.get("success"))
        ads["error"] = None if ads["ok"] else r.get("error")
    else:
        ads["error"] = "검색광고 API 키가 설정에 없습니다"

    search = {"configured": False, "ok": False, "error": None}
    ssvc = NaverSearchService(settings)
    search["configured"] = ssvc.is_configured()
    if search["configured"]:
        r = await ssvc.search_blog("테스트", display=1)
        search["ok"] = bool(r.get("success"))
        search["error"] = None if search["ok"] else r.get("error")
    else:
        search["error"] = "검색 API 키가 설정에 없습니다"

    return {"naver_ads": ads, "naver_search": search}


@router.get("/candidates", summary="후보 목록")
async def list_candidates(
    blog_id: Optional[int] = Query(None),
    verdict: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(300, le=1000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    stmt = select(KeywordCandidate).where(
        KeywordCandidate.user_id == current_user.id)
    if blog_id:
        stmt = stmt.where(KeywordCandidate.blog_id == blog_id)
    if verdict:
        stmt = stmt.where(KeywordCandidate.verdict == verdict)
    if q:
        stmt = stmt.where(KeywordCandidate.keyword.ilike(f"%{q}%"))
    stmt = stmt.order_by(
        KeywordCandidate.search_volume.desc().nullslast()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    # 니치 이름을 붙인다. id 만 주면 화면에서 정렬도 검색도 할 수 없다.
    from ..models.category import SubTopic, Topic

    topic_ids = {r.topic_id for r in rows if r.topic_id} or {0}
    sub_ids = {r.subtopic_id for r in rows if r.subtopic_id} or {0}
    topics = dict((await db.execute(
        select(Topic.id, Topic.name).where(Topic.id.in_(topic_ids))
    )).all())
    subs = dict((await db.execute(
        select(SubTopic.id, SubTopic.name).where(SubTopic.id.in_(sub_ids))
    )).all())

    def _niche(row) -> str:
        sub = subs.get(row.subtopic_id)
        top = topics.get(row.topic_id)
        if sub and top:
            return f"{top} > {sub}"
        return sub or top or "미분류"

    counts = dict((await db.execute(
        select(KeywordCandidate.verdict, func.count(KeywordCandidate.id))
        .where(KeywordCandidate.user_id == current_user.id)
        .group_by(KeywordCandidate.verdict)
    )).all())

    return {
        "candidates": [{
            "id": r.id, "keyword": r.keyword,
            # 니치 = 이 키워드가 분류된 블로그오토 카테고리.
            # 입력한 시드가 아니다 — 시드를 그대로 물려주면 '마라탕' 으로
            # 모은 것이 전부 '음식 효능' 이 되어 카테고리별로 못 넘긴다.
            "niche": _niche(r),
            "seed": r.seed,
            "topic_id": r.topic_id, "subtopic_id": r.subtopic_id,
            "blog_id": r.blog_id,
            "search_volume": r.search_volume,
            "search_volume_pc": r.search_volume_pc,
            "search_volume_mobile": r.search_volume_mobile,
            "competition": r.competition,
            "doc_count": r.doc_count, "saturation": r.saturation,
            "verdict": r.verdict, "verdict_reason": r.verdict_reason,
            "risk_label": r.risk_label,
            "measured_at": r.measured_at.isoformat() if r.measured_at else None,
        } for r in rows],
        "counts": counts,
        "total": sum(counts.values()),
    }


@router.get("/seeds/{blog_id}", summary="블로그의 시드 미리보기")
async def preview_seeds(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """어떤 시드로 조회할지 실행 전에 보여 준다."""
    blog = (await db.execute(
        select(Blog).where(Blog.id == blog_id, Blog.user_id == current_user.id)
    )).scalar_one_or_none()
    if not blog:
        raise HTTPException(404, "블로그를 찾을 수 없습니다")
    settings = await _settings(db, current_user)
    seeds = await _service(db, settings, current_user).seeds_for_blog(blog_id)
    return {"blog_name": blog.name, "seeds": [s["seed"] for s in seeds]}


@router.post("/collect", summary="연관키워드·검색량 수집")
async def collect(
    blog_id: Optional[int] = Body(None),
    seeds: Optional[List[str]] = Body(None),
    limit: int = Body(200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    settings = await _settings(db, current_user)
    result = await _service(db, settings, current_user).collect(
        blog_id=blog_id, seeds=seeds, limit=min(limit, 500))
    if not result.get("success"):
        raise HTTPException(400, result.get("error") or "수집 실패")
    return result


@router.post("/measure", summary="문서수 측정·판정")
async def measure(
    blog_id: Optional[int] = Body(None),
    limit: int = Body(50),
    min_volume: Optional[int] = Body(None),
    min_saturation: Optional[float] = Body(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """끊어서 여러 번 부를 수 있다. 이미 잰 것은 다시 재지 않는다."""
    settings = await _settings(db, current_user)
    result = await _service(db, settings, current_user).measure(
        limit=min(limit, 100), blog_id=blog_id,
        min_volume=min_volume, min_saturation=min_saturation)
    if not result.get("success"):
        raise HTTPException(400, result.get("error") or "측정 실패")
    return result


@router.post("/rejudge", summary="기준만 바꿔 재판정")
async def rejudge(
    min_volume: Optional[int] = Body(None),
    min_saturation: Optional[float] = Body(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    settings = await _settings(db, current_user)
    return await _service(db, settings, current_user).rejudge(
        min_volume, min_saturation)


@router.delete("/candidates", summary="후보 삭제")
async def delete_candidates(
    ids: Optional[List[int]] = Body(None, embed=True),
    blog_id: Optional[int] = Body(None, embed=True),
    all_of_user: bool = Body(False, embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """실험 데이터라 지우고 다시 하는 일이 잦다."""
    stmt = sa_delete(KeywordCandidate).where(
        KeywordCandidate.user_id == current_user.id)
    if ids:
        stmt = stmt.where(KeywordCandidate.id.in_(ids))
    elif blog_id:
        stmt = stmt.where(KeywordCandidate.blog_id == blog_id)
    elif not all_of_user:
        raise HTTPException(422, "대상이 비어 있습니다")
    result = await db.execute(stmt)
    await db.commit()
    return {"success": True, "deleted": result.rowcount or 0}
