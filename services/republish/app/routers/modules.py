"""
모듈 라우터

Features:
- 모듈 CRUD 작업
- 타입별 필터링
- 페이지네이션 지원
- 블로그-카테고리 매핑 조회 및 강제 연동
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..models import User
from ..models.module import Module
from ..models.module_type import ModuleType
from ..models.category import BlogCategory, Topic, SubTopic
from ..services.module_service import ModuleService
from ..schemas.module import (
    ModuleCreateRequest,
    ModuleUpdateRequest,
    ModuleDetailResponse,
    ModuleListResponse
)
from ..routers.auth import get_current_user
from ..core.logger import get_logger

logger = get_logger("modules_router", "app.log")

router = APIRouter(prefix="/modules", tags=["modules"])


@router.get(
    "",
    response_model=ModuleListResponse,
    summary="모듈 목록 조회",
    description="사용자의 모듈 목록을 조회합니다. 타입별 필터링과 페이지네이션을 지원합니다."
)
async def get_modules(
    module_type_code: Optional[str] = Query(None, description="모듈 타입 코드 필터"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ModuleListResponse:
    """모듈 목록 조회"""
    service = ModuleService(db)
    return await service.get_modules(current_user, module_type_code, page, size)


# ──────────────────────────────────────────────────────
# 블로그-카테고리 양방향 연동 API (경로 우선순위: /{module_id}보다 먼저)
# ──────────────────────────────────────────────────────

@router.get(
    "/used-blog-categories",
    summary="사용 중인 블로그-카테고리 매핑 조회",
    description="다른 프롬프트 모듈에서 사용 중인 (blog, category) 매핑을 반환합니다.",
)
async def get_used_blog_categories(
    exclude_module_id: Optional[int] = Query(
        None, description="제외할 모듈 ID (현재 편집 중인 모듈)",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Phase 1-1: 사용 중인 블로그-카테고리 매핑 조회"""
    modules = await _get_prompt_modules(db, current_user.id, exclude_module_id)

    raw_mappings = []
    for mod in modules:
        settings = mod.settings or {}
        bcm = settings.get("blog_category_map")
        if not bcm:
            bcm = _build_legacy_map(settings)
        for m in bcm:
            raw_mappings.append({**m, "module_id": mod.id, "module_name": mod.name})

    # 이름 해석
    names = await _resolve_category_names(db, raw_mappings)
    result = []
    for m in raw_mappings:
        result.append({
            "blog_id": m["blog_id"],
            "topic_id": m.get("topic_id"),
            "subtopic_id": m.get("subtopic_id"),
            "topic_name": names.get(("topic", m.get("topic_id")), ""),
            "subtopic_name": names.get(("subtopic", m.get("subtopic_id")), ""),
            "module_id": m["module_id"],
            "module_name": m["module_name"],
        })
    return {"mappings": result}


@router.post(
    "",
    response_model=ModuleDetailResponse,
    status_code=201,
    summary="모듈 생성",
    description="새로운 모듈을 생성합니다."
)
async def create_module(
    request: ModuleCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ModuleDetailResponse:
    """모듈 생성 (Phase 1-4: blog_category_map 자동 생성)"""
    if request.settings and isinstance(request.settings, dict):
        s = request.settings
        if "categories" in s and "blogs" in s and "blog_category_map" not in s:
            s["blog_category_map"] = _build_legacy_map(s)

    service = ModuleService(db)
    module = await service.create_module(current_user, request)

    return ModuleDetailResponse.model_validate(module)


@router.get(
    "/{module_id}",
    response_model=ModuleDetailResponse,
    summary="모듈 상세 조회",
    description="특정 모듈의 상세 정보를 조회합니다."
)
async def get_module(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ModuleDetailResponse:
    """모듈 상세 조회"""
    service = ModuleService(db)
    module = await service.get_module(current_user, module_id)

    if not module:
        raise HTTPException(
            status_code=404,
            detail="모듈을 찾을 수 없습니다"
        )

    return ModuleDetailResponse.model_validate(module)


@router.put(
    "/{module_id}",
    response_model=ModuleDetailResponse,
    summary="모듈 수정",
    description="기존 모듈의 정보를 수정합니다."
)
async def update_module(
    module_id: int,
    request: ModuleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ModuleDetailResponse:
    """모듈 수정 (Phase 1-4: blog_category_map 자동 생성)"""
    # settings에 blog_category_map이 없으면 자동 생성
    if request.settings and isinstance(request.settings, dict):
        s = request.settings
        if "categories" in s and "blogs" in s and "blog_category_map" not in s:
            s["blog_category_map"] = _build_legacy_map(s)
            logger.info(
                f"[UPDATE_MODULE] blog_category_map 자동 생성: "
                f"{len(s['blog_category_map'])}개 매핑"
            )

    service = ModuleService(db)
    module = await service.update_module(current_user, module_id, request)

    if not module:
        raise HTTPException(
            status_code=404,
            detail="모듈을 찾을 수 없습니다"
        )

    return ModuleDetailResponse.model_validate(module)


@router.post(
    "/{module_id}/copy",
    response_model=ModuleDetailResponse,
    status_code=201,
    summary="모듈 복사",
    description="기존 모듈을 복사하여 새로운 모듈을 생성합니다."
)
async def copy_module(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ModuleDetailResponse:
    """모듈 복사"""
    service = ModuleService(db)
    module = await service.copy_module(current_user, module_id)

    if not module:
        raise HTTPException(
            status_code=404,
            detail="복사할 모듈을 찾을 수 없습니다"
        )

    return ModuleDetailResponse.model_validate(module)


@router.delete(
    "/{module_id}",
    status_code=204,
    summary="모듈 삭제",
    description="모듈을 삭제합니다. 플로우에서 사용 중인 모듈은 force=true로 강제 삭제할 수 있습니다."
)
async def delete_module(
    module_id: int,
    force: bool = Query(False, description="플로우 연결을 해제하고 강제 삭제"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """모듈 삭제

    Args:
        module_id: 삭제할 모듈 ID
        force: True이면 플로우 연결 해제 후 강제 삭제
    """
    service = ModuleService(db)
    success = await service.delete_module(current_user, module_id, force=force)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="모듈을 찾을 수 없습니다"
        )


# ──────────────────────────────────────────────────────
# 내부 헬퍼 함수
# ──────────────────────────────────────────────────────

async def _get_prompt_modules(
    db: AsyncSession, user_id: int, exclude_id: Optional[int] = None,
) -> list:
    """현재 사용자의 프롬프트 모듈 목록 조회 (내부 헬퍼)"""
    stmt = (
        select(Module)
        .join(ModuleType, Module.module_type_id == ModuleType.id)
        .where(ModuleType.code == "prompt", Module.user_id == user_id)
    )
    if exclude_id:
        stmt = stmt.where(Module.id != exclude_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _build_legacy_map(settings: dict) -> list:
    """blog_category_map이 없는 레거시 모듈용 매핑 추론"""
    categories = settings.get("categories", [])
    blogs = settings.get("blogs", [])
    if not categories or not blogs:
        return []
    mapping = []
    for blog_id in blogs:
        for cat in categories:
            mapping.append({
                "blog_id": blog_id,
                "topic_id": cat.get("topic_id"),
                "subtopic_id": cat.get("subtopic_id"),
            })
    return mapping


def _topics_conflict(
    topic_a: int, sub_a, topic_b: int, sub_b,
) -> bool:
    """범위 기반 충돌 판정: 전체 토픽(subtopic_id=None) ↔ 개별 서브토픽 포함"""
    if topic_a != topic_b:
        return False
    if sub_a is None and sub_b is None:
        return True
    if sub_a is None or sub_b is None:
        return True
    return sub_a == sub_b


async def _resolve_category_names(
    db: AsyncSession, mappings: list,
) -> dict:
    """topic_id/subtopic_id → 이름 매핑 캐시 생성"""
    topic_ids = {m["topic_id"] for m in mappings if m.get("topic_id")}
    sub_ids = {m["subtopic_id"] for m in mappings if m.get("subtopic_id")}

    names: dict = {}
    if topic_ids:
        res = await db.execute(select(Topic).where(Topic.id.in_(topic_ids)))
        for t in res.scalars().all():
            names[("topic", t.id)] = t.name
    if sub_ids:
        res = await db.execute(select(SubTopic).where(SubTopic.id.in_(sub_ids)))
        for s in res.scalars().all():
            names[("subtopic", s.id)] = s.name
    return names


# ──────────────────────────────────────────────────────
# 강제 연동 API
# ──────────────────────────────────────────────────────

async def _remove_conflicts_from_sources(
    db: AsyncSession, user_id: int, exclude_module_id: Optional[int],
    blog_id: int, target_cats: list,
) -> list:
    """소스 모듈들에서 충돌 매핑 제거 + 전체 토픽 분해 (공통 로직)"""
    all_subtopics_cache: dict = {}
    other_modules = await _get_prompt_modules(db, user_id, exclude_module_id)
    affected = []

    for mod in other_modules:
        settings = mod.settings or {}
        bcm = settings.get("blog_category_map")
        if not bcm:
            bcm = _build_legacy_map(settings)

        removed = []
        new_bcm = []
        explode_entries = []

        for m in bcm:
            m_blog = m["blog_id"]
            m_topic = m.get("topic_id")
            m_sub = m.get("subtopic_id")

            is_conflict = (
                m_blog == blog_id
                and any(
                    _topics_conflict(m_topic, m_sub, t, s)
                    for t, s in target_cats
                )
            )

            if is_conflict:
                removed.append(m)
                if m_sub is None:
                    taken_subs = {
                        s for t, s in target_cats
                        if t == m_topic and s is not None
                    }
                    if taken_subs:
                        if m_topic not in all_subtopics_cache:
                            res = await db.execute(
                                select(SubTopic.id).where(
                                    SubTopic.topic_id == m_topic
                                )
                            )
                            all_subtopics_cache[m_topic] = [
                                r[0] for r in res.fetchall()
                            ]
                        for sub_id in all_subtopics_cache[m_topic]:
                            if sub_id not in taken_subs:
                                explode_entries.append({
                                    "blog_id": m_blog,
                                    "topic_id": m_topic,
                                    "subtopic_id": sub_id,
                                })
            else:
                new_bcm.append(m)

        if removed:
            new_bcm.extend(explode_entries)
            new_settings = {**settings, "blog_category_map": new_bcm}
            remaining_blog_ids = list({m["blog_id"] for m in new_bcm})
            new_settings["blogs"] = remaining_blog_ids
            mod.settings = new_settings
            await db.flush()
            affected.append({
                "module_id": mod.id,
                "module_name": mod.name,
                "removed_mappings": removed,
                "exploded_entries": explode_entries,
                "remaining_blogs": remaining_blog_ids,
            })

    return affected


@router.post(
    "/release-categories",
    summary="카테고리 매핑 해제",
    description="다른 모듈에서 사용 중인 매핑을 해제합니다 (신규 모듈용).",
)
async def release_categories(
    body: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """소스 모듈에서 충돌 매핑 제거 (현재 모듈 ID 불필요)"""
    blog_id = body.get("blog_id")
    categories = body.get("categories", [])
    exclude_module_id = body.get("exclude_module_id")
    if not blog_id or not categories:
        raise HTTPException(400, "blog_id와 categories는 필수입니다")

    target_cats = [
        (c.get("topic_id"), c.get("subtopic_id"))
        for c in categories
    ]
    affected = await _remove_conflicts_from_sources(
        db, current_user.id, exclude_module_id, blog_id, target_cats,
    )
    await db.commit()
    return {"success": True, "affected_modules": affected}


@router.post(
    "/{module_id}/force-link",
    summary="강제 연동",
    description="다른 모듈에서 사용 중인 (blog, category) 매핑을 이 모듈로 이동합니다.",
)
async def force_link(
    module_id: int,
    body: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Phase 1-3: 강제 연동 - 충돌 매핑을 현재 모듈로 이동"""
    blog_id = body.get("blog_id")
    categories = body.get("categories", [])
    if not blog_id or not categories:
        raise HTTPException(400, "blog_id와 categories는 필수입니다")

    service = ModuleService(db)
    current_module = await service.get_module(current_user, module_id)
    if not current_module:
        raise HTTPException(404, "모듈을 찾을 수 없습니다")

    target_cats = [
        (c.get("topic_id"), c.get("subtopic_id"))
        for c in categories
    ]

    # 소스 모듈에서 충돌 제거
    affected = await _remove_conflicts_from_sources(
        db, current_user.id, module_id, blog_id, target_cats,
    )

    # 현재 모듈에 매핑 추가
    cur_settings = current_module.settings or {}
    cur_bcm = cur_settings.get("blog_category_map", [])
    existing_keys = {
        (m["blog_id"], m.get("topic_id"), m.get("subtopic_id"))
        for m in cur_bcm
    }
    for t, s in target_cats:
        key = (blog_id, t, s)
        if key not in existing_keys:
            cur_bcm.append({
                "blog_id": blog_id,
                "topic_id": t,
                "subtopic_id": s,
            })
    cur_settings["blog_category_map"] = cur_bcm
    cur_blogs = set(cur_settings.get("blogs", []))
    cur_blogs.add(blog_id)
    cur_settings["blogs"] = list(cur_blogs)
    current_module.settings = cur_settings
    await db.commit()

    return {"success": True, "affected_modules": affected}