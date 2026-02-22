"""
Growth Profile API 엔드포인트

프리셋 조회 및 스테이지 미리보기 제공.
프론트엔드에서 Growth Profile 설정 UI에 필요한 데이터를 제공한다.
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Body
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.core.database import get_db_session
from app.routers.auth import get_current_user
from app.models.flow_blog import FlowBlog
from app.models.blog import Blog
from app.services.generation.growth_profile_defaults import (
    DEFAULT_PROFILES,
    get_default_profile,
    get_available_profiles,
)
from app.services.generation.growth_profile_resolver import GrowthProfileResolver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/growth-profile", tags=["growth-profile"])


@router.get("/presets")
async def list_presets(
    _user=Depends(get_current_user),
):
    """
    기본 프로파일 목록 반환

    Growth Profile 설정 UI에서 프리셋 선택용으로 사용.

    Returns:
        profiles: 프리셋 목록 (key, name, description, stages_count, warmup_enabled)
    """
    profiles = get_available_profiles()
    # warmup_enabled 필드 추가
    enriched = []
    for p in profiles:
        warmup = DEFAULT_PROFILES[p["key"]].get("warmup", {})
        enriched.append({
            **p,
            "warmup_enabled": warmup.get("enabled", False),
        })
    return {"profiles": enriched}


@router.get("/presets/{preset_key}")
async def get_preset(
    preset_key: str,
    _user=Depends(get_current_user),
):
    """
    특정 프리셋의 전체 settings 반환

    Args:
        preset_key: aggressive / balanced / conservative

    Returns:
        프리셋의 전체 settings dict (schedule_matrix, stages, warmup 등)

    Raises:
        HTTPException(404): 존재하지 않는 프리셋 키
    """
    try:
        profile = get_default_profile(preset_key)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"프리셋 '{preset_key}'을(를) 찾을 수 없습니다. "
                   f"사용 가능: {list(DEFAULT_PROFILES.keys())}",
        )
    return profile


def _format_module_info(
    params, label: str, active_hours: int
) -> Optional[str]:
    """ModuleIntervalParams를 사람이 읽을 수 있는 문자열로 변환

    Args:
        params: ModuleIntervalParams 인스턴스
        label: 모듈 라벨 (예: "생성", "발행")
        active_hours: 오늘 활성 시간 수

    Returns:
        포맷된 문자열 또는 비활성 시 None
    """
    if not params.enabled:
        return None
    if params.interval_mode == "auto" and params.daily_count:
        return f"하루 {params.daily_count}회"
    elif params.interval_mode == "manual" and params.interval_minutes:
        return f"{params.interval_minutes}분 간격"
    return label


@router.post("/preview")
async def preview_stages(
    settings: dict = Body(..., embed=False),
    flow_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    _user=Depends(get_current_user),
):
    """
    블로그별 스테이지 매핑 미리보기

    프론트엔드에서 프리셋 선택 시 각 블로그가 어느 스테이지에
    해당하는지 실시간 미리보기를 제공한다.

    Args:
        settings: Growth Profile settings dict (Body)
        flow_id: Flow ID (Query, optional)

    Returns:
        blogs: 블로그별 스테이지 매핑 정보 배열
    """
    if flow_id is None:
        return {"blogs": []}

    # Flow에 연결된 블로그 조회 (FlowBlog JOIN Blog)
    stmt = (
        select(Blog)
        .join(FlowBlog, FlowBlog.blog_id == Blog.id)
        .where(FlowBlog.flow_id == flow_id)
    )
    result = await db.execute(stmt)
    blogs = result.scalars().all()

    if not blogs:
        return {"blogs": []}

    # blog_post_counts 구성
    blog_post_counts = {
        blog.id: blog.total_post_count or 0
        for blog in blogs
    }

    # GrowthProfileResolver로 실행 컨텍스트 빌드
    try:
        context = GrowthProfileResolver.build_execution_context(
            flow_id=flow_id,
            gp_settings=settings,
            blog_post_counts=blog_post_counts,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # schedule_matrix에서 활성 시간 계산
    schedule_matrix = settings.get("schedule_matrix")
    active_hours = GrowthProfileResolver.count_active_hours(schedule_matrix)

    # 블로그별 스테이지 정보 구성
    preview_list = []
    for blog in blogs:
        stage = context.get_stage_for_blog(blog.id)
        if stage is None:
            continue

        preview_list.append({
            "blog_id": blog.id,
            "blog_name": blog.blog_name,
            "post_count": blog.total_post_count or 0,
            "stage_name": stage.stage_name,
            "stage_label": stage.stage_label,
            "generate": _format_module_info(
                stage.generate, "생성", active_hours
            ),
            "publish": _format_module_info(
                stage.publish, "발행", active_hours
            ),
            "republish": _format_module_info(
                stage.republish, "재발행", active_hours
            ),
        })

    return {"blogs": preview_list}


@router.get("/stats")
async def get_gp_stats(
    db: AsyncSession = Depends(get_db_session),
    _user=Depends(get_current_user),
):
    """
    Growth Profile 통계 반환

    대시보드 위젯에 표시할 GP 관련 통계를 반환한다.
    - 단계별 블로그 분포
    - 스테이지 전환 임박 블로그
    - 재고 현황

    Returns:
        stage_distribution: 단계별 블로그 수
        transition_alerts: 전환 임박 블로그 목록
        total_gp_modules: GP 모듈 수
    """
    from app.models.module import Module
    from app.models.module_type import ModuleType
    from app.models.blog import Blog
    from app.models.flow_module import FlowModule
    from app.models.crawled_post import CrawledPost

    try:
        # GP 모듈 조회
        stmt = (
            select(Module)
            .join(ModuleType, Module.module_type_id == ModuleType.id)
            .where(ModuleType.code == "growth_profile")
        )
        result = await db.execute(stmt)
        gp_modules = result.scalars().all()

        if not gp_modules:
            return {
                "total_gp_modules": 0,
                "stage_distribution": {},
                "transition_alerts": [],
                "inventory": [],
                "schedule_matrix": None,
            }

        # 각 GP 모듈이 포함된 Flow의 블로그들 수집
        stage_counts: dict[str, int] = {}
        transition_alerts: list[dict] = []
        inventory_list: list[dict] = []

        for gp_module in gp_modules:
            settings = gp_module.settings or {}
            stages = settings.get("stages", [])
            if not stages:
                continue

            # 이 모듈이 포함된 Flow들 찾기
            stmt = (
                select(FlowModule.flow_id)
                .where(FlowModule.module_id == gp_module.id)
            )
            result = await db.execute(stmt)
            flow_ids = [row[0] for row in result.all()]

            if not flow_ids:
                continue

            # Flow에 연결된 블로그들
            stmt = (
                select(Blog)
                .join(FlowBlog, FlowBlog.blog_id == Blog.id)
                .where(FlowBlog.flow_id.in_(flow_ids))
            )
            result = await db.execute(stmt)
            blogs = result.scalars().all()

            for blog in blogs:
                post_count = blog.total_post_count or 0
                current_stage = _resolve_current_stage(
                    stages, post_count
                )
                if not current_stage:
                    continue

                stage_label = current_stage.get(
                    "label", current_stage.get("name", "알 수 없음")
                )
                stage_counts[stage_label] = (
                    stage_counts.get(stage_label, 0) + 1
                )

                # 전환 임박 체크 (max까지 5 이하 남음)
                _check_transition_alert(
                    stages, current_stage, blog,
                    post_count, transition_alerts,
                )

                # 재고 수집 (generate 활성화 시)
                gen_cfg = current_stage.get("generate", {})
                min_inv = gen_cfg.get("min_inventory", 0)
                if gen_cfg.get("enabled") and min_inv > 0:
                    inv_stmt = (
                        select(func.count(CrawledPost.id))
                        .where(
                            CrawledPost.blog_id == blog.id,
                            CrawledPost.source == "generated",
                            CrawledPost.published_at.is_(None),
                        )
                    )
                    inv_result = await db.execute(inv_stmt)
                    inv_count = inv_result.scalar() or 0
                    inventory_list.append({
                        "blog_name": blog.blog_name,
                        "inventory_count": inv_count,
                        "min_inventory": min_inv,
                        "stage_label": stage_label,
                    })

        # schedule_matrix 추출 (첫 GP 모듈)
        schedule_matrix = None
        if gp_modules:
            first_settings = gp_modules[0].settings or {}
            schedule_matrix = first_settings.get("schedule_matrix")

        return {
            "total_gp_modules": len(gp_modules),
            "stage_distribution": stage_counts,
            "transition_alerts": transition_alerts[:5],
            "inventory": inventory_list,
            "schedule_matrix": schedule_matrix,
        }
    except Exception as e:
        logger.error(f"[GP_STATS] 에러: {str(e)}")
        return {
            "total_gp_modules": 0,
            "stage_distribution": {},
            "transition_alerts": [],
            "inventory": [],
            "schedule_matrix": None,
        }


def _resolve_current_stage(
    stages: list[dict], post_count: int
) -> Optional[dict]:
    """블로그 글 수에 해당하는 현재 스테이지를 반환

    Args:
        stages: GP 설정의 stages 리스트
        post_count: 블로그 총 글 수

    Returns:
        매칭된 stage dict 또는 None
    """
    for stage in stages:
        s_min = stage.get("post_count_min", 0)
        s_max = stage.get("post_count_max")
        if s_max is None:
            if post_count >= s_min:
                return stage
        elif s_min <= post_count <= s_max:
            return stage
    return None


def _check_transition_alert(
    stages: list[dict],
    current_stage: dict,
    blog,
    post_count: int,
    alerts: list[dict],
) -> None:
    """전환 임박 블로그를 alerts 리스트에 추가

    Args:
        stages: GP 설정의 stages 리스트
        current_stage: 현재 스테이지 dict
        blog: Blog 모델 인스턴스
        post_count: 블로그 총 글 수
        alerts: 알림을 추가할 리스트
    """
    s_max = current_stage.get("post_count_max")
    if s_max is None or (s_max - post_count) > 5:
        return

    stage_idx = stages.index(current_stage)
    if stage_idx + 1 >= len(stages):
        return

    next_label = stages[stage_idx + 1].get("label", "다음 단계")
    alerts.append({
        "blog_name": blog.blog_name or blog.name,
        "current_count": post_count,
        "threshold": s_max,
        "next_stage": next_label,
    })
