"""제목 생성/수집 모듈 실행 API.

모듈 폼의 테스트 패널과 데이터 관리 화면이 쓴다. 플로우·오토런과 **같은
실행기**를 부른다 — 다른 코드를 타면 한쪽에서만 나는 버그가 생긴다.

한 회차는 AI 호출이라 오래 걸린다. 요청을 붙잡으면 프록시가 응답 헤더 대기
60초에서 끊으므로 토큰을 주고 폴링하게 한다.

계획서: docs/plans/keyword_pipeline_restructure_review.md §5-2
"""
from __future__ import annotations

import asyncio
import uuid
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models import User
from ..models.blog import Blog
from ..routers.auth import get_current_user
from ..services.in_memory_ttl_cache import cache_get, cache_set

logger = get_logger("title_gen_router", "app.log")

router = APIRouter(prefix="/api/v1/title-gen", tags=["제목 생성/수집"])

TASK_PREFIX = "title_gen_task:"
TASK_TTL = 1800.0


def _task_key(task_id: str) -> str:
    return f"{TASK_PREFIX}{task_id}"


@router.post("/run", summary="한 회차 실행")
async def run_module(
    module_id: Optional[int] = Body(None),
    blog_id: Optional[int] = Body(None),
    steps: Optional[List[str]] = Body(None),
    force: bool = Body(True),
    settings_override: Optional[dict] = Body(None),
    background: bool = Body(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """저장하지 않은 설정으로도 돌릴 수 있다(settings_override).

    수동 실행이므로 재고가 충분해도 돈다(force 기본 true).
    """
    from ..models.module import Module
    from ..services.title_gen.runner import TitleModuleRunner

    settings = settings_override
    if module_id and settings is None:
        module = (await db.execute(
            select(Module).where(Module.id == module_id,
                                 Module.user_id == current_user.id)
        )).scalar_one_or_none()
        if not module:
            raise HTTPException(404, "모듈을 찾을 수 없습니다")
        settings = module.settings or {}

    blog_ids = []
    if blog_id:
        blog = (await db.execute(
            select(Blog).where(Blog.id == blog_id,
                               Blog.user_id == current_user.id)
        )).scalar_one_or_none()
        if not blog:
            raise HTTPException(404, "블로그를 찾을 수 없습니다")
        blog_ids = [blog_id]

    if background:
        task_id = uuid.uuid4().hex
        asyncio.create_task(_run_in_background(
            task_id, current_user.id, settings, blog_ids, force, steps))
        logger.info("[TITLE_GEN] 백그라운드 실행 시작 | %s", task_id)
        return {"status": "running", "task_id": task_id}

    blogs = []
    if blog_ids:
        blogs = [(await db.execute(
            select(Blog).where(Blog.id == blog_ids[0])
        )).scalar_one_or_none()]
    runner = TitleModuleRunner(db, current_user.id)
    result = await runner.run_for_blogs(settings, [b for b in blogs if b],
                                        force=force, steps=steps)
    if not result.get("success"):
        raise HTTPException(400, result.get("error") or "실행 실패")
    return result


async def _run_in_background(task_id: str, user_id: int,
                             settings: Optional[dict], blog_ids: List[int],
                             force: bool, steps: Optional[List[str]]) -> None:
    """요청과 분리해 돈다. 요청 세션은 응답과 함께 닫힌다."""
    from ..core.database import db_manager
    from ..services.title_gen.runner import TitleModuleRunner

    try:
        async with db_manager.get_session() as db:
            blogs = []
            for blog_id in blog_ids:
                row = (await db.execute(
                    select(Blog).where(Blog.id == blog_id)
                )).scalar_one_or_none()
                if row:
                    blogs.append(row)
            runner = TitleModuleRunner(db, user_id)
            result = await runner.run_for_blogs(settings, blogs, force=force,
                                                steps=steps)
        cache_set(_task_key(task_id), {"status": "done", "result": result})
    except Exception as e:  # noqa: BLE001
        logger.error("[TITLE_GEN] 백그라운드 오류 | %s | %s", task_id, e)
        cache_set(_task_key(task_id),
                  {"status": "failed", "error": str(e)[:300]})


@router.get("/run/{task_id}", summary="실행 결과 조회")
async def run_result(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    row = cache_get(_task_key(task_id), TASK_TTL)
    return row if row is not None else {"status": "running"}
