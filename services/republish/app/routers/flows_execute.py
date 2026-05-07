"""
플로우 실행 API

플로우를 1회 즉시 실행합니다.
모듈 타입별로 실행 방식이 다릅니다:
- collect: 블로그 없이 독립 실행 (키워드/제목 수집)
- data: 블로그 없이 독립 실행 (제목 이동 등)
- republish: 블로그 필수, 재발행 수행
- publish: 블로그 필수, GP 기반 발행 + 워밍업 (Phase D)
- prompt: 블로그 필수, 재고 기반 글 생성 (Phase 4)
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db_session
from app.services.system_settings_service import SystemSettingsService


async def _use_celery(key: str, db: AsyncSession) -> bool:
    """시스템 설정에서 Celery 플래그 조회."""
    return await SystemSettingsService.get_bool(key, db, default=False)
from app.models.flow import Flow
from app.models.flow_module import FlowModule
from app.models.flow_blog import FlowBlog
from app.models.module import Module
from app.models.blog import Blog, BlogPlatform
from app.models.autorun_log import AutorunLog
from app.routers.auth import get_current_user
from app.models.user import User
from app.services.wordpress_service import WordPressRepublishService
from app.services.blogger_service import BloggerRepublishService
from app.services.naver_ads_service import NaverAdsService
from app.models.user_settings import UserSettings
from app.core.logger import get_logger
from app.services.generation.growth_profile_resolver import GrowthProfileResolver
from app.services.generation.flow_execution_context import FlowExecutionContext
from app.models.flow_execution_state import FlowExecutionState

router = APIRouter(prefix="/api/v1/flows", tags=["flows-execute"])
logger = get_logger("flow_execute", "app.log")

from app.services.generation.title_peek import (
    peek_next_generate_title as _peek_next_generate_title,
    peek_next_publish_post as _peek_next_publish_post,
)

# 모듈 개별 실행 상태 (메모리 기반, 서버 재시작 시 초기화)
# {execution_id: {"status": "running"|"completed"|"failed", "message": str, ...}}
_module_exec_states: Dict[str, dict] = {}


@router.post("/{flow_id}/execute")
async def execute_flow_once(
    flow_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    플로우 1회 즉시 실행 (테스트) - 백그라운드 작업

    장시간 실행되는 수집 작업의 브라우저 타임아웃을 방지하기 위해
    백그라운드 작업으로 실행합니다.

    - 플로우 존재 여부만 확인하고 즉시 응답 반환
    - 실제 작업은 백그라운드에서 실행
    - 결과는 AutorunLog에 기록됨
    """
    execution_id = str(uuid.uuid4())

    logger.info(f"[FLOW_EXECUTE] ========== 백그라운드 실행 요청 ==========")
    logger.info(f"[FLOW_EXECUTE] flow_id={flow_id} | user_id={current_user.id} | execution_id={execution_id}")

    # 1. 플로우 존재 여부만 빠르게 확인 (모듈 개수 확인용)
    result = await db.execute(
        select(Flow)
        .where(Flow.id == flow_id, Flow.user_id == current_user.id)
        .options(
            selectinload(Flow.module_links),
            selectinload(Flow.blog_links)
        )
    )
    flow = result.scalar_one_or_none()

    if not flow:
        logger.warning(f"[FLOW_EXECUTE] 플로우를 찾을 수 없음: {flow_id}")
        raise HTTPException(status_code=404, detail="플로우를 찾을 수 없습니다")

    # 2. 모듈 존재 확인
    module_count = len(flow.module_links)
    blog_count = len(flow.blog_links)

    if module_count == 0:
        logger.warning(f"[FLOW_EXECUTE] 플로우에 모듈이 없음: {flow_id}")
        raise HTTPException(status_code=400, detail="플로우에 모듈이 없습니다")

    # 3. 백그라운드 작업 등록 (asyncio.create_task 사용)
    task = asyncio.create_task(
        _execute_flow_background(
            flow_id=flow_id,
            user_id=current_user.id,
            execution_id=execution_id
        )
    )

    # 태스크 예외 로깅 (fire-and-forget 방식에서 예외가 무시되지 않도록)
    def _handle_task_exception(t):
        try:
            exc = t.exception()
            if exc:
                logger.error(f"[FLOW_BG] 백그라운드 작업 예외 발생: {exc}", exc_info=exc)
        except asyncio.CancelledError:
            pass

    task.add_done_callback(_handle_task_exception)

    logger.info(f"[FLOW_EXECUTE] 백그라운드 작업 등록 완료 | flow={flow.name}")

    # 4. 즉시 응답 반환
    return {
        "success": True,
        "message": "플로우 실행이 시작되었습니다. 결과는 실행 로그에서 확인하세요.",
        "status": "started",
        "execution_id": execution_id,
        "flow_id": flow.id,
        "flow_name": flow.name,
        "module_count": module_count,
        "blog_count": blog_count
    }


async def _execute_flow_background(
    flow_id: int,
    user_id: int,
    execution_id: str
) -> None:
    """
    백그라운드에서 플로우 실행

    - 자체 DB 세션 생성 (요청 세션은 이미 종료됨)
    - 성공/실패 결과를 AutorunLog에 저장
    """
    from app.core.database import db_manager

    started_at = datetime.now()
    logger.info(f"[FLOW_BG] ========== 백그라운드 실행 시작 ==========")
    logger.info(f"[FLOW_BG] flow_id={flow_id} | user_id={user_id} | execution_id={execution_id}")

    try:
        async with db_manager.get_session() as db:
            # 1. 플로우 조회 (모듈, 블로그 포함)
            result = await db.execute(
                select(Flow)
                .where(Flow.id == flow_id, Flow.user_id == user_id)
                .options(
                    selectinload(Flow.module_links)
                    .selectinload(FlowModule.module)
                    .selectinload(Module.module_type),
                    selectinload(Flow.blog_links)
                    .selectinload(FlowBlog.blog)
                    .selectinload(Blog.google_credential)
                )
            )
            flow = result.scalar_one_or_none()

            if not flow:
                logger.error(f"[FLOW_BG] 플로우를 찾을 수 없음: {flow_id}")
                return

            # 2. 모듈과 블로그 확인
            modules = [link.module for link in flow.module_links if link.module]
            blogs = [link.blog for link in flow.blog_links if link.blog]

            if not modules:
                logger.error(f"[FLOW_BG] 플로우에 모듈이 없음: {flow_id}")
                return

            # 3. 모듈을 타입별로 그룹화
            modules_by_type: Dict[str, List[Module]] = {}
            for module in modules:
                type_code = module.module_type.code if module.module_type else "unknown"
                if type_code not in modules_by_type:
                    modules_by_type[type_code] = []
                modules_by_type[type_code].append(module)

            logger.info(f"[FLOW_BG] 플로우: {flow.name} | 모듈: {len(modules)}개 | 블로그: {len(blogs)}개")
            logger.info(f"[FLOW_BG] 모듈 타입별: {', '.join(f'{k}={len(v)}' for k, v in modules_by_type.items())}")

            # ============================================================
            # Step 0: Growth Profile 스케줄러 (핵심 변경)
            # ============================================================
            gp_context = await _build_growth_profile_context(
                modules_by_type, blogs, flow
            )
            if gp_context is None:
                logger.warning(
                    f"[FLOW_BG] GP 컨텍스트 실패로 플로우 중단 | flow_id={flow.id} | "
                    f"GP 미설정, 비활성 시간대, 또는 stages 없음 → 위 로그 확인"
                )
                await _save_autorun_log(
                    db=db, user_id=user_id, flow_id=flow.id,
                    flow_name=flow.name, module_name="Flow 실행",
                    blog_name="-",
                    result={
                        "success": False,
                        "message": "GP 컨텍스트 실패 (GP 미설정/비활성 시간대/stages 없음)",
                    },
                    duration_ms=0, action="flow_init"
                )
                return

            # 4. 결과 집계 변수
            success_count = 0
            fail_count = 0
            total_processed = 0

            # 5. collect 모듈 실행 (블로그 없이 독립 실행)
            if "collect" in modules_by_type:
                for collect_module in modules_by_type["collect"]:
                    module_start_time = datetime.now()
                    logger.info(f"[FLOW_BG] 수집 모듈 실행: {collect_module.name}")

                    try:
                        result = await _execute_collect_module(collect_module, db)
                        duration_ms = int((datetime.now() - module_start_time).total_seconds() * 1000)

                        # AutorunLog 저장
                        await _save_autorun_log(
                            db=db,
                            user_id=user_id,
                            flow_id=flow.id,
                            flow_name=flow.name,
                            module_name=collect_module.name,
                            blog_name="-",
                            result=result,
                            duration_ms=duration_ms,
                            action="collect"
                        )

                        if result.get("success"):
                            success_count += 1
                            logger.info(f"[FLOW_BG] 수집 성공 | module={collect_module.name}")
                        else:
                            fail_count += 1
                            logger.warning(f"[FLOW_BG] 수집 실패 | module={collect_module.name}")

                        total_processed += 1

                    except Exception as e:
                        fail_count += 1
                        total_processed += 1
                        duration_ms = int((datetime.now() - module_start_time).total_seconds() * 1000)
                        logger.error(f"[FLOW_BG] 수집 모듈 오류 | module={collect_module.name} | error={e}")

                        # 에러 시에도 AutorunLog 저장
                        await _save_autorun_log(
                            db=db,
                            user_id=user_id,
                            flow_id=flow.id,
                            flow_name=flow.name,
                            module_name=collect_module.name,
                            blog_name="-",
                            result={"success": False, "message": str(e)},
                            duration_ms=duration_ms,
                            action="collect"
                        )

            # 6. data 모듈 실행 (블로그 없이 독립 실행 - 제목 이동 등)
            if "data" in modules_by_type:
                # 플로우 내 수집 모듈 존재 여부 확인
                has_collect_module = "collect" in modules_by_type

                for data_module in modules_by_type["data"]:
                    module_start_time = datetime.now()
                    logger.info(f"[FLOW_BG] 데이터 모듈 실행: {data_module.name}")

                    # 수집 모듈 연동 모드인데 플로우에 수집 모듈이 없는 경우 경고
                    data_settings = data_module.settings or {}
                    execution_mode = data_settings.get("execution_mode", "collection_link")

                    if execution_mode == "collection_link" and not has_collect_module:
                        logger.warning(
                            f"[FLOW_BG] ⚠️ 데이터 모듈 '{data_module.name}'이 수집 모듈 연동 모드이지만 "
                            f"플로우에 수집 모듈이 없습니다. 스케줄 모드로 전환하거나 수집 모듈을 추가하세요."
                        )
                        # 경고만 하고 실행은 계속 (데이터 모듈 자체는 독립 실행 가능)
                        await _save_autorun_log(
                            db=db,
                            user_id=user_id,
                            flow_id=flow.id,
                            flow_name=flow.name,
                            module_name=data_module.name,
                            blog_name="-",
                            result={
                                "success": False,
                                "message": "수집 모듈 연동 모드이지만 플로우에 수집 모듈이 없습니다. 수집 모듈을 추가하거나 스케줄 모드로 변경하세요."
                            },
                            duration_ms=0,
                            action="data"
                        )
                        fail_count += 1
                        total_processed += 1
                        continue

                    try:
                        result = await _execute_data_module(data_module, db)
                        duration_ms = int((datetime.now() - module_start_time).total_seconds() * 1000)

                        # AutorunLog 저장
                        await _save_autorun_log(
                            db=db,
                            user_id=user_id,
                            flow_id=flow.id,
                            flow_name=flow.name,
                            module_name=data_module.name,
                            blog_name="-",
                            result=result,
                            duration_ms=duration_ms,
                            action="data"
                        )

                        if result.get("success"):
                            success_count += 1
                            logger.info(f"[FLOW_BG] 데이터 모듈 성공 | module={data_module.name}")
                        else:
                            fail_count += 1
                            logger.warning(f"[FLOW_BG] 데이터 모듈 실패 | module={data_module.name}")

                        total_processed += 1

                    except Exception as e:
                        fail_count += 1
                        total_processed += 1
                        duration_ms = int((datetime.now() - module_start_time).total_seconds() * 1000)
                        logger.error(f"[FLOW_BG] 데이터 모듈 오류 | module={data_module.name} | error={e}")

                        # 에러 시에도 AutorunLog 저장
                        await _save_autorun_log(
                            db=db,
                            user_id=user_id,
                            flow_id=flow.id,
                            flow_name=flow.name,
                            module_name=data_module.name,
                            blog_name="-",
                            result={"success": False, "message": str(e)},
                            duration_ms=duration_ms,
                            action="data"
                        )

            # 7. GP 기반 발행 (publish 모듈 불필요 - GP가 직접 실행)
            if gp_context and gp_context.has_growth_profile() and blogs:
                from app.services.generation.publisher import Publisher
                from app.services.generation.warmup_manager import WarmupManager
                from app.services.publishing.publisher_pipeline import PublisherPipeline

                active_hours = _count_active_hours(gp_context.schedule_matrix)
                warmup_settings = (
                    gp_context.growth_profile.get("warmup", {})
                    if gp_context.growth_profile else {}
                )

                warmup_mgr = WarmupManager(db)
                publisher = Publisher(db)
                pipeline = PublisherPipeline(db)

                gp_module_name = "GP 발행"
                for _link in flow.module_links:
                    if _link.module and _link.module.module_type:
                        if _link.module.module_type.code == "growth_profile":
                            gp_module_name = _link.module.name
                            break

                for blog in blogs:
                    stage_params = gp_context.get_stage_for_blog(blog.id)

                    # publish 비활성 → 스킵
                    if not stage_params or not stage_params.publish.enabled:
                        total_processed += 1
                        await _save_autorun_log(
                            db=db, user_id=user_id, flow_id=flow.id,
                            flow_name=flow.name, module_name=gp_module_name,
                            blog_name=blog.name,
                            result={
                                "success": True, "skipped": True,
                                "message": f"발행 비활성 (stage: {stage_params.stage_name if stage_params else 'N/A'})",
                            },
                            duration_ms=0, action="publish"
                        )
                        continue

                    # FES 간격 체크 (action_type="publish")
                    fes = await _get_or_create_blog_fes(
                        db, flow.id, "publish", blog.id,
                    )
                    now = datetime.now()
                    if not _check_fes_interval(fes, now):
                        logger.info(
                            f"[FLOW_BG] 발행 간격 미경과 | blog={blog.name} | "
                            f"next={fes.next_execution_at}"
                        )
                        continue

                    # 워밍업 체크
                    warmup_status = await warmup_mgr.check_warmup(
                        blog.id, warmup_settings, active_hours,
                    )

                    # 발행 실행 (항상 1개)
                    blog_start_time = datetime.now()
                    try:
                        

                        if await _use_celery("use_celery_publish", db):
                            # Celery 워커에 발행 위임 (전체 워크플로우는 워커 내부에서 실행)
                            from app.core.task_dispatcher import (
                                get_dispatcher, PRIORITY_NORMAL,
                            )
                            dispatcher = get_dispatcher()
                            # 디스패치 시점에 발행 대상 글을 결정 (워커도 동일 ID 사용)
                            pre_title, pre_post_id = await _peek_next_publish_post(
                                db, blog.id,
                            )
                            if not pre_post_id:
                                # 발행 대상 없음 - 큐 등록 skip
                                # 활동 탭에 표시되도록 별도 queue_register skipped 로그 저장
                                skip_msg = (
                                    f"{blog.name} - 발행 큐 등록 생략 "
                                    f"(발행할 글 없음)"
                                )
                                await _save_autorun_log(
                                    db=db, user_id=user_id, flow_id=flow.id,
                                    flow_name=flow.name, module_name=gp_module_name,
                                    blog_name=blog.name,
                                    result={
                                        "success": True, "skipped": True,
                                        "message": skip_msg,
                                    },
                                    duration_ms=0, action="queue_register",
                                )
                                # 메인 흐름에는 단순 skipped 결과만 전달
                                result = {
                                    "success": True, "skipped": True,
                                    "message": "발행할 글 없음",
                                    "post_title": "",
                                }
                                logger.info(
                                    f"[FLOW_BG] 발행 대상 없음, 큐 등록 skip | blog={blog.name}"
                                )
                            else:
                                try:
                                    task_id = dispatcher.dispatch_publish(
                                        blog_id=blog.id,
                                        post_id=pre_post_id,
                                        priority=PRIORITY_NORMAL,
                                        flow_id=flow.id,
                                    )
                                    result = {
                                        "success": True,
                                        "message": f"Celery 큐 등록: {task_id}",
                                        "post_title": pre_title,
                                    }
                                    logger.info(
                                        f"[FLOW_BG] 발행 Celery 디스패치 | "
                                        f"blog={blog.name} | post_id={pre_post_id} | "
                                        f"task={task_id}"
                                    )
                                except Exception as e:
                                    result = {
                                        "success": False,
                                        "message": f"Celery 디스패치 실패: {e}",
                                        "post_title": pre_title,
                                    }
                                    logger.error(
                                        f"[FLOW_BG] 발행 Celery 디스패치 오류 | "
                                        f"blog={blog.name} | {e}"
                                    )
                        else:
                            # OFF 모드: 직접 발행 워크플로우 실행
                            result = await publisher.publish_for_blog(
                                blog, warmup_status,
                            )

                            if not result.get("skipped"):
                                crawled_post = result.get("crawled_post")
                                if crawled_post and result.get("success"):
                                    credential = getattr(blog, "google_credential", None)
                                    pub_result = await pipeline.publish_post(
                                        blog, crawled_post, credential=credential,
                                    )
                                    if pub_result.success:
                                        complete_info = await publisher.complete_publish(
                                            blog.id, crawled_post.id,
                                            published_url=pub_result.published_url,
                                        )
                                        result["inventory"] = complete_info["inventory"]
                                        result["needs_generation"] = complete_info["needs_generation"]
                                        result["published_url"] = pub_result.published_url
                                        result["image_uploaded"] = pub_result.image_uploaded
                                    else:
                                        result = {
                                            "success": False,
                                            "message": pub_result.error or "플랫폼 발행 실패",
                                        }

                        if not result.get("skipped"):
                            # FES 업데이트 (skipped가 아닌 경우만)
                            effective_interval = (
                                warmup_status.effective_interval
                                if warmup_status.is_active and warmup_status.effective_interval
                                else (stage_params.publish.computed_interval if stage_params else None)
                            )
                            _update_fes_after_execution(
                                fes, success=result.get("success", False),
                                interval_minutes=effective_interval or 60,
                                gp_context=gp_context,
                            )

                        blog_duration_ms = int(
                            (datetime.now() - blog_start_time).total_seconds() * 1000
                        )
                        await _save_autorun_log(
                            db=db, user_id=user_id, flow_id=flow.id,
                            flow_name=flow.name, module_name=gp_module_name,
                            blog_name=blog.name, result=result,
                            duration_ms=blog_duration_ms, action="publish"
                        )
                        if result.get("success") and not result.get("skipped"):
                            success_count += 1
                        elif not result.get("success"):
                            fail_count += 1
                        total_processed += 1

                    except Exception as e:
                        fail_count += 1
                        total_processed += 1
                        blog_duration_ms = int(
                            (datetime.now() - blog_start_time).total_seconds() * 1000
                        )
                        logger.error(f"[FLOW_BG] 발행 오류 | blog={blog.name} | error={e}")
                        await _save_autorun_log(
                            db=db, user_id=user_id, flow_id=flow.id,
                            flow_name=flow.name, module_name=gp_module_name,
                            blog_name=blog.name,
                            result={"success": False, "message": str(e)},
                            duration_ms=blog_duration_ms, action="publish"
                        )

            # 8. GP 기반 재발행 (republish 모듈 불필요 - GP가 직접 실행)
            if gp_context and gp_context.has_growth_profile() and blogs:
                gp_module_name_re = "GP 재발행"
                for _link in flow.module_links:
                    if _link.module and _link.module.module_type:
                        if _link.module.module_type.code == "growth_profile":
                            gp_module_name_re = _link.module.name
                            break

                for blog in blogs:
                    stage_params = gp_context.get_stage_for_blog(blog.id)

                    # republish 비활성 → 스킵
                    if not stage_params or not stage_params.republish.enabled:
                        total_processed += 1
                        await _save_autorun_log(
                            db=db, user_id=user_id, flow_id=flow.id,
                            flow_name=flow.name, module_name=gp_module_name_re,
                            blog_name=blog.name,
                            result={
                                "success": True, "skipped": True,
                                "message": f"재발행 비활성 (stage: {stage_params.stage_name if stage_params else 'N/A'})",
                            },
                            duration_ms=0, action="republish"
                        )
                        continue

                    # FES 간격 체크 (action_type="republish")
                    fes = await _get_or_create_blog_fes(
                        db, flow.id, "republish", blog.id,
                    )
                    now = datetime.now()
                    if not _check_fes_interval(fes, now):
                        logger.info(
                            f"[FLOW_BG] 재발행 간격 미경과 | blog={blog.name} | "
                            f"next={fes.next_execution_at}"
                        )
                        continue

                    blog_start_time = datetime.now()
                    logger.info(
                        f"[FLOW_BG] 재발행 처리: {blog.name} | "
                        f"stage={stage_params.stage_name if stage_params else 'unknown'}"
                    )

                    try:
                        

                        if await _use_celery("use_celery_publish", db):
                            # Celery 워커에 재발행 위임
                            from app.core.task_dispatcher import (
                                get_dispatcher, PRIORITY_NORMAL,
                            )
                            dispatcher = get_dispatcher()
                            try:
                                task_id = dispatcher.dispatch_republish(
                                    blog_id=blog.id,
                                    priority=PRIORITY_NORMAL,
                                    flow_id=flow.id,
                                )
                                result = {
                                    "success": True,
                                    "message": f"Celery 큐 등록: {task_id}",
                                }
                                logger.info(
                                    f"[FLOW_BG] 재발행 Celery 디스패치 | "
                                    f"blog={blog.name} | task={task_id}"
                                )
                            except Exception as e:
                                result = {
                                    "success": False,
                                    "message": f"Celery 디스패치 실패: {e}",
                                }
                                logger.error(
                                    f"[FLOW_BG] 재발행 Celery 디스패치 오류 | "
                                    f"blog={blog.name} | {e}"
                                )
                        else:
                            result = await _execute_republish_for_blog(blog)

                        blog_duration_ms = int(
                            (datetime.now() - blog_start_time).total_seconds() * 1000
                        )

                        if result.get("success"):
                            _update_fes_after_execution(
                                fes, success=True,
                                interval_minutes=(
                                    stage_params.republish.computed_interval or 60
                                    if stage_params else 60
                                ),
                                gp_context=gp_context,
                            )

                        await _save_autorun_log(
                            db=db, user_id=user_id, flow_id=flow.id,
                            flow_name=flow.name, module_name=gp_module_name_re,
                            blog_name=blog.name, result=result,
                            duration_ms=blog_duration_ms, action="republish"
                        )

                        if result.get("success"):
                            success_count += 1
                            logger.info(f"[FLOW_BG] 재발행 성공 | blog={blog.name}")
                        else:
                            fail_count += 1
                            logger.warning(f"[FLOW_BG] 재발행 실패 | blog={blog.name}")
                        total_processed += 1

                    except Exception as e:
                        fail_count += 1
                        total_processed += 1
                        blog_duration_ms = int(
                            (datetime.now() - blog_start_time).total_seconds() * 1000
                        )
                        logger.error(f"[FLOW_BG] 재발행 오류 | blog={blog.name} | error={e}")
                        await _save_autorun_log(
                            db=db, user_id=user_id, flow_id=flow.id,
                            flow_name=flow.name, module_name=gp_module_name_re,
                            blog_name=blog.name,
                            result={"success": False, "message": str(e)},
                            duration_ms=blog_duration_ms, action="republish"
                        )

            # 9. prompt 모듈 실행 (GP 컨텍스트 기반 생성)
            if "prompt" in modules_by_type:
                if not blogs:
                    logger.warning(f"[FLOW_BG] 생성 모듈이 있지만 블로그가 없음: {flow_id}")
                    for prompt_module in modules_by_type["prompt"]:
                        fail_count += 1
                        total_processed += 1
                        await _save_autorun_log(
                            db=db,
                            user_id=user_id,
                            flow_id=flow.id,
                            flow_name=flow.name,
                            module_name=prompt_module.name,
                            blog_name="-",
                            result={"success": False, "message": "플로우에 연결된 블로그가 없습니다"},
                            duration_ms=0,
                            action="generate"
                        )
                else:
                    from app.services.generation.flow_generate_executor import FlowGenerateExecutor
                    gen_executor = FlowGenerateExecutor(db, user_id)

                    for prompt_module in modules_by_type["prompt"]:
                        logger.info(f"[FLOW_BG] 생성 모듈 실행: {prompt_module.name}")

                        for blog in blogs:
                            # GP 컨텍스트에서 블로그별 StageParams 조회
                            stage_params = gp_context.get_stage_for_blog(blog.id)

                            # generate.enabled 체크
                            if stage_params and not stage_params.generate.enabled:
                                logger.info(
                                    f"[FLOW_BG] 생성 비활성 | blog={blog.name} | "
                                    f"stage={stage_params.stage_name}"
                                )
                                total_processed += 1
                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=prompt_module.name,
                                    blog_name=blog.name,
                                    result={
                                        "success": True,
                                        "skipped": True,
                                        "message": f"생성 비활성 (stage: {stage_params.stage_name})",
                                    },
                                    duration_ms=0,
                                    action="generate"
                                )
                                continue

                            blog_start_time = datetime.now()
                            logger.info(
                                f"[FLOW_BG] 생성 처리: {blog.name} | "
                                f"module={prompt_module.name} | "
                                f"stage={stage_params.stage_name if stage_params else 'unknown'}"
                            )

                            try:
                                # Celery 기능 플래그 체크
                                
                                if await _use_celery("use_celery_generation", db):
                                    from dataclasses import asdict
                                    from app.core.task_dispatcher import get_dispatcher, PRIORITY_NORMAL
                                    dispatcher = get_dispatcher()
                                    try:
                                        sp_dict = asdict(stage_params) if stage_params else None
                                        task_id = dispatcher.dispatch_generation(
                                            blog_id=blog.id,
                                            module_id=prompt_module.id,
                                            title_id=0,
                                            priority=PRIORITY_NORMAL,
                                            flow_id=flow.id,
                                            user_id=user_id,
                                            stage_params_dict=sp_dict,
                                            force=False,
                                        )
                                        result = {"success": True, "message": f"Celery 큐 등록: {task_id}"}
                                        logger.info(
                                            f"[FLOW_BG] Celery 디스패치 성공 | blog={blog.name} | task_id={task_id}"
                                        )
                                    except Exception as e:
                                        result = {"success": False, "message": f"Celery 디스패치 실패: {e}"}
                                        logger.warning(
                                            f"[FLOW_BG] Celery 디스패치 실패 | blog={blog.name} | {e}"
                                        )
                                else:
                                    result = await gen_executor.execute_for_blog(
                                        prompt_module, blog,
                                        stage_params=stage_params,
                                    )
                                blog_duration_ms = int(
                                    (datetime.now() - blog_start_time).total_seconds() * 1000
                                )

                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=prompt_module.name,
                                    blog_name=blog.name,
                                    result=result,
                                    duration_ms=blog_duration_ms,
                                    action="generate"
                                )

                                if result.get("success"):
                                    if result.get("skipped"):
                                        logger.info(
                                            f"[FLOW_BG] 생성 스킵 | blog={blog.name} | "
                                            f"{result.get('message')}"
                                        )
                                    else:
                                        success_count += 1
                                        logger.info(f"[FLOW_BG] 생성 성공 | blog={blog.name}")
                                else:
                                    fail_count += 1
                                    logger.warning(f"[FLOW_BG] 생성 실패 | blog={blog.name}")

                                total_processed += 1

                            except Exception as e:
                                fail_count += 1
                                total_processed += 1
                                blog_duration_ms = int(
                                    (datetime.now() - blog_start_time).total_seconds() * 1000
                                )
                                logger.error(
                                    f"[FLOW_BG] 생성 오류 | blog={blog.name} | error={e}"
                                )

                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=prompt_module.name,
                                    blog_name=blog.name,
                                    result={"success": False, "message": str(e)},
                                    duration_ms=blog_duration_ms,
                                    action="generate"
                                )

            # 9. 실행 완료
            completed_at = datetime.now()
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)

            logger.info(f"[FLOW_BG] ========== 백그라운드 실행 완료 ==========")
            logger.info(
                f"[FLOW_BG] 결과: 성공 {success_count}/{total_processed} | "
                f"실패 {fail_count}/{total_processed} | 소요시간 {duration_ms}ms"
            )

    except Exception as e:
        logger.error(f"[FLOW_BG] 백그라운드 실행 치명적 오류 | flow_id={flow_id} | error={e}")
        import traceback
        logger.error(f"[FLOW_BG] 스택 트레이스: {traceback.format_exc()}")


async def _build_growth_profile_context(
    modules_by_type: Dict[str, List[Module]],
    blogs: list,
    flow: Flow,
) -> Optional[FlowExecutionContext]:
    """
    Growth Profile Step 0: GP 로드 + 활성 시간 체크 + 컨텍스트 생성

    Returns:
        FlowExecutionContext: 정상 진행 시
        None: GP 미설정 / 비활성 시간대 / 블로그 없음 → Flow 실행 중단

    설계 문서: growth_stage_strategy_plan.md - Section 6-1 Step 0
    """
    # (1) GP 모듈 및 settings 검증
    gp_module, gp_settings = _extract_gp_settings(modules_by_type, flow)
    if gp_module is None:
        return None

    # (2) schedule_matrix 활성 시간 체크
    if not _check_active_time(gp_settings, flow):
        return None

    # (3) 블로그별 포스트 수 매핑 + 컨텍스트 생성
    return _build_context(gp_settings, blogs, flow, gp_module)


def _extract_gp_settings(
    modules_by_type: Dict[str, List[Module]],
    flow: Flow,
) -> tuple:
    """GP 모듈 존재 확인 + settings 추출 (W4: 미설정 시 즉시 중단)"""
    if "growth_profile" not in modules_by_type:
        logger.error(
            f"[FLOW_BG] Growth Profile 미설정 | flow_id={flow.id} | "
            f"이 Flow에 Growth Profile이 설정되지 않았습니다"
        )
        return None, None

    gp_module = modules_by_type["growth_profile"][0]
    gp_settings = gp_module.settings or {}

    if not gp_settings.get("stages"):
        logger.error(
            f"[FLOW_BG] Growth Profile에 stages가 없습니다 | "
            f"flow_id={flow.id} | module_id={gp_module.id}"
        )
        return None, None

    return gp_module, gp_settings


def _check_active_time(gp_settings: dict, flow: Flow) -> bool:
    """schedule_matrix 기반 활성 시간 확인. False면 비활성."""
    import pytz

    schedule_matrix = gp_settings.get("schedule_matrix")
    if not schedule_matrix:
        return True

    KST = pytz.timezone("Asia/Seoul")
    now_kst = datetime.now(KST)
    weekday = now_kst.weekday()
    hour = now_kst.hour

    if (
        isinstance(schedule_matrix, list)
        and len(schedule_matrix) == 7
        and isinstance(schedule_matrix[weekday], list)
        and len(schedule_matrix[weekday]) == 24
    ):
        if not schedule_matrix[weekday][hour]:
            logger.info(
                f"[FLOW_BG] 비활성 시간대 | flow_id={flow.id} | "
                f"weekday={weekday} | hour={hour} | Flow 실행 스킵"
            )
            return False

    return True


def _build_context(
    gp_settings: dict, blogs: list, flow: Flow, gp_module: Module,
) -> Optional[FlowExecutionContext]:
    """블로그별 포스트 수 매핑 + FlowExecutionContext 생성"""
    if not blogs:
        logger.warning(
            f"[FLOW_BG] Growth Profile 있지만 블로그 없음 | flow_id={flow.id}"
        )
        return None

    blog_post_counts = {
        blog.id: (blog.total_post_count or 0) for blog in blogs
    }

    try:
        context = GrowthProfileResolver.build_execution_context(
            flow_id=flow.id,
            gp_settings=gp_settings,
            blog_post_counts=blog_post_counts,
        )
    except ValueError as e:
        logger.error(
            f"[FLOW_BG] Growth Profile 컨텍스트 생성 실패 | "
            f"flow_id={flow.id} | error={e}"
        )
        return None

    logger.info(
        f"[FLOW_BG] Growth Profile Step 0 완료 | "
        f"flow_id={flow.id} | blogs={len(context.blog_stages)}개 | "
        f"module={gp_module.name}"
    )
    return context


async def _execute_collect_module(
    module: Module,
    db: AsyncSession = None
) -> Dict[str, Any]:
    """
    수집 모듈 실행

    수집 모듈은 블로그 없이 독립적으로 실행됩니다.
    키워드/제목 수집 작업을 수행합니다.

    시드 키워드 없이 자동으로 트렌딩 키워드를 수집합니다.
    """
    from app.services.keyword_collector_service import KeywordCollectorService

    try:
        settings = module.settings or {}

        # 수집 유형 확인 (keyword, title, both)
        collect_type = settings.get("collect_type", "both")

        # 키워드 소스 목록 (기본값 False - 명시적으로 선택된 소스만 사용)
        keyword_sources = []
        if settings.get("source_google_trends", False):
            keyword_sources.append("google_trends")
        if settings.get("source_naver_datalab", False):
            keyword_sources.append("naver_datalab")
        if settings.get("source_naver_ads", False):
            keyword_sources.append("naver_ads")

        # 제목 소스 목록 (기본값 False - 명시적으로 선택된 소스만 사용)
        title_sources = []
        if settings.get("source_naver_news", False):
            title_sources.append("naver_news")
        if settings.get("source_google_news", False):
            title_sources.append("google_news")
        if settings.get("source_naver_webdoc", False):
            title_sources.append("naver_webdoc")

        # collect_type에 따라 소스 필터링
        sources = []
        if collect_type == "keyword":
            sources = keyword_sources
        elif collect_type == "title":
            sources = title_sources
        else:  # both
            sources = keyword_sources + title_sources

        if not sources:
            return {
                "success": False,
                "message": f"수집 소스가 설정되지 않았습니다 (타입: {collect_type})",
                "collected_count": 0
            }

        logger.info(
            f"[COLLECT] 모듈={module.name} | 타입={collect_type} | 소스={sources}"
        )

        # 사용자 설정 조회
        query = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query)
        user_settings = result.scalar_one_or_none()

        if not user_settings:
            return {
                "success": False,
                "message": "사용자 설정을 찾을 수 없습니다",
                "collected_count": 0
            }

        # KeywordCollectorService를 사용하여 자동 수집
        collector = KeywordCollectorService(db=db, settings=user_settings)

        # 수집 수량 제한 적용 (키워드/제목 분리)
        keyword_limit = settings.get("keyword_collect_limit", 100)
        keyword_limit = max(10, min(1000, keyword_limit))
        # title_limit: 0 또는 None이면 무제한
        title_limit_setting = settings.get("title_collect_limit", 0)
        title_limit = None if title_limit_setting == 0 else title_limit_setting

        # 연관검색 확장 옵션 (기본값 True)
        enable_related_search = settings.get("enable_related_search", True)

        # 수집 유형 옵션 (일반/대량) - 기본값 False (명시적으로 활성화해야 동작)
        enable_normal_collect = settings.get("enable_normal_collect", False)
        enable_bulk_collect = settings.get("enable_bulk_collect", False)
        bulk_collect_delay = settings.get("bulk_collect_delay", 0.5)
        bulk_urls_per_cycle = settings.get("bulk_urls_per_cycle", 3)

        logger.info(
            f"[COLLECT] 옵션 | keyword_limit={keyword_limit}, "
            f"title_limit={'무제한' if not title_limit else title_limit}, "
            f"enable_related_search={enable_related_search}, "
            f"enable_normal_collect={enable_normal_collect}, enable_bulk_collect={enable_bulk_collect}"
        )

        # 선택된 소스에서만 수집 (수량 제한 분리 적용)
        collect_result = await collector.collect_all(
            sources=sources,
            keyword_limit=keyword_limit,
            title_limit=title_limit,
            enable_related_search=enable_related_search,
            enable_normal_collect=enable_normal_collect,
            enable_bulk_collect=enable_bulk_collect,
            bulk_collect_delay=bulk_collect_delay,
            bulk_urls_per_cycle=bulk_urls_per_cycle
        )

        if collect_result.get("success"):
            total_collected = collect_result.get("total_collected", 0)
            total_saved = collect_result.get("total_saved", 0)
            results_detail = collect_result.get("results", {})

            # 각 소스별 결과 메시지 생성
            source_messages = []
            for source, src_result in results_detail.items():
                if src_result.get("success"):
                    source_messages.append(
                        f"{source}: {src_result.get('collected', 0)}개 수집, {src_result.get('saved', 0)}개 저장"
                    )
                else:
                    source_messages.append(
                        f"{source}: 오류 - {src_result.get('error', '알 수 없음')}"
                    )

            # 키워드 추출 실행 (설정에서 enable_keyword_extraction이 활성화된 경우)
            extraction_result = None
            if settings.get("enable_keyword_extraction", False):
                try:
                    from app.services.keyword_extractor_service import KeywordExtractorService

                    extraction_method = settings.get("keyword_extraction_method", "all")
                    extraction_title_limit = settings.get("keyword_extraction_title_limit", 100)
                    extraction_keyword_limit = settings.get("keyword_extraction_limit", 50)

                    logger.info(
                        f"[COLLECT] 키워드 추출 시작 | method={extraction_method}, "
                        f"title_limit={extraction_title_limit}, keyword_limit={extraction_keyword_limit}"
                    )

                    extractor = KeywordExtractorService(db)
                    extraction_result = await extractor.extract_and_save_keywords(
                        title_limit=extraction_title_limit,
                        keyword_limit=extraction_keyword_limit,
                        method=extraction_method,
                        title_status="new"
                    )

                    if extraction_result.get("success"):
                        extracted_count = extraction_result.get("keywords_saved", 0)
                        source_messages.append(f"키워드 추출: {extracted_count}개 저장")
                        logger.info(f"[COLLECT] 키워드 추출 완료 | 저장={extracted_count}개")
                    else:
                        logger.warning(f"[COLLECT] 키워드 추출 실패: {extraction_result.get('error', '알 수 없음')}")

                except Exception as extract_error:
                    logger.error(f"[COLLECT] 키워드 추출 오류: {extract_error}")

            return {
                "success": True,
                "message": f"총 {total_collected}개 수집, {total_saved}개 저장 ({', '.join(source_messages)})",
                "collected_count": total_collected,
                "saved_count": total_saved,
                "sources": sources,
                "collect_type": collect_type,
                "results": results_detail,
                "extraction_result": extraction_result,
                "api_connected": True
            }
        else:
            return {
                "success": False,
                "message": collect_result.get("error", "수집 실패"),
                "collected_count": 0,
                "sources": sources,
                "collect_type": collect_type,
                "api_connected": False
            }

    except Exception as e:
        logger.error(f"[COLLECT] 수집 실패 | module={module.name} | error={e}")
        return {
            "success": False,
            "message": str(e),
            "collected_count": 0
        }


async def _execute_data_module(
    module: Module,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    데이터 모듈 실행 (제목 이동 등)

    모듈 settings에 저장된 옵션을 사용하여 TitleTransferService를 호출합니다.
    """
    from app.services.title_transfer_service import TitleTransferService

    try:
        settings = module.settings or {}

        # 설정 값 추출
        # transfer_mode: auto (카테고리 있는 것만), all (전체), selected (선택된 ID만)
        transfer_mode = settings.get("transfer_mode", "auto")

        # 실행 조건
        execution = settings.get("execution", {})
        max_titles_unlimited = execution.get("max_titles_unlimited", False)
        max_titles_raw = execution.get("max_titles_per_run", 100)
        # 전체 선택(-1) 또는 무제한 플래그일 경우 제한 없음
        max_titles = 100000 if (max_titles_unlimited or max_titles_raw == -1) else max_titles_raw
        min_titles = execution.get("min_titles_required", 1)

        # 그룹화 설정
        auto_group = settings.get("auto_group", True)
        threshold = settings.get("similarity_threshold", 75)

        # 필터 설정
        filter_opts = settings.get("filter", {})
        categories = filter_opts.get("categories", [])
        duplicate_handling = filter_opts.get("duplicate_handling", "skip")

        logger.info(
            f"[DATA] 데이터 모듈 실행 | module={module.name} | "
            f"mode={transfer_mode} (topic+subtopic required) | max={max_titles} | min={min_titles} | "
            f"auto_group={auto_group} | threshold={threshold}"
        )

        # TitleTransferService 생성 (threshold는 0-100 범위)
        service = TitleTransferService(db=db, threshold=threshold)

        # 이동 가능한 제목 수 확인
        from sqlalchemy import select, func
        from app.models.title import TempTitle

        query = select(func.count(TempTitle.id)).where(
            TempTitle.status.in_(["new", "categorized"])
        )

        # transfer_mode에 따른 필터링
        if transfer_mode == "auto":
            # 토픽과 서브토픽이 모두 있는 것만 (완전히 분류된 제목)
            query = query.where(
                TempTitle.topic_id.isnot(None),
                TempTitle.subtopic_id.isnot(None)
            )

        # 토픽(카테고리) 필터 적용
        if categories:
            query = query.where(TempTitle.topic_id.in_(categories))

        result = await db.execute(query)
        available_count = result.scalar() or 0

        logger.info(f"[DATA] 이동 가능 제목 수: {available_count} | 최소 조건: {min_titles}")

        # 최소 제목 수 조건 체크
        if available_count < min_titles:
            return {
                "success": True,
                "message": f"이동 가능한 제목({available_count}개)이 최소 조건({min_titles}개)보다 적어 스킵",
                "moved": 0,
                "grouped": 0,
                "duplicates": 0,
                "skipped_reason": "min_titles_not_met"
            }

        # 이동 대상 제목 ID 조회
        id_query = select(TempTitle.id).where(
            TempTitle.status.in_(["new", "categorized"])
        )

        if transfer_mode == "auto":
            # 토픽과 서브토픽이 모두 있는 것만 (완전히 분류된 제목)
            id_query = id_query.where(
                TempTitle.topic_id.isnot(None),
                TempTitle.subtopic_id.isnot(None)
            )

        if categories:
            id_query = id_query.where(TempTitle.topic_id.in_(categories))

        id_query = id_query.limit(max_titles)

        id_result = await db.execute(id_query)
        temp_ids = [row[0] for row in id_result.all()]

        if not temp_ids:
            return {
                "success": True,
                "message": "이동할 제목이 없습니다",
                "moved": 0,
                "grouped": 0,
                "duplicates": 0
            }

        logger.info(f"[DATA] 이동 대상 제목 수: {len(temp_ids)}")

        # 제목 이동 실행
        transfer_result = await service.move_to_main(temp_ids, auto_group=auto_group)

        moved = transfer_result.get("moved", 0)
        grouped = transfer_result.get("grouped", 0)
        duplicates = transfer_result.get("duplicates", 0)
        errors = transfer_result.get("errors", [])

        logger.info(
            f"[DATA] 제목 이동 완료 | moved={moved} | grouped={grouped} | "
            f"duplicates={duplicates} | errors={len(errors)}"
        )

        return {
            "success": True,
            "message": f"제목 이동 완료: {moved}개 이동, {grouped}개 그룹화, {duplicates}개 중복",
            "moved": moved,
            "grouped": grouped,
            "duplicates": duplicates,
            "errors": errors
        }

    except Exception as e:
        logger.error(f"[DATA] 데이터 모듈 실패 | module={module.name} | error={e}")
        import traceback
        logger.error(f"[DATA] 스택 트레이스: {traceback.format_exc()}")
        return {
            "success": False,
            "message": str(e),
            "moved": 0,
            "grouped": 0,
            "duplicates": 0
        }


async def _collect_from_naver_ads(
    db: AsyncSession,
    seed_keywords: List[str],
    max_keywords: int = 50
) -> Dict[str, Any]:
    """
    네이버 검색광고 API에서 키워드 수집

    Args:
        db: DB 세션
        seed_keywords: 시드 키워드 목록
        max_keywords: 최대 수집 키워드 수

    Returns:
        수집 결과
    """
    from sqlalchemy import select

    try:
        if not seed_keywords:
            return {
                "success": False,
                "error": "시드 키워드가 없습니다"
            }

        # AsyncSession으로 설정 조회
        query = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            return {
                "success": False,
                "error": "설정을 찾을 수 없습니다"
            }

        service = NaverAdsService(settings)

        if not service.is_configured():
            return {
                "success": False,
                "error": "네이버 검색광고 API가 설정되지 않았습니다"
            }

        # 키워드 수집
        collect_result = await service.collect_keywords(
            seed_keywords=seed_keywords,
            max_related=max_keywords
        )

        if collect_result.get("success"):
            keywords = collect_result.get("keywords", [])
            logger.info(
                f"[NAVER_ADS] 키워드 수집 성공: "
                f"seed={len(seed_keywords)}, collected={len(keywords)}"
            )
            return {
                "success": True,
                "collected_count": len(keywords),
                "keywords": keywords
            }
        else:
            return {
                "success": False,
                "error": collect_result.get("error", "수집 실패")
            }

    except Exception as e:
        logger.error(f"[NAVER_ADS] 수집 오류: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def _collect_from_google_trends(
    seed_keywords: List[str],
    max_keywords: int = 50
) -> Dict[str, Any]:
    """
    구글 트렌드에서 키워드 수집

    Args:
        seed_keywords: 시드 키워드 목록
        max_keywords: 최대 수집 키워드 수

    Returns:
        수집 결과
    """
    from app.services.google_trends_service import GoogleTrendsService

    try:
        if not seed_keywords:
            return {
                "success": False,
                "error": "시드 키워드가 없습니다"
            }

        service = GoogleTrendsService()

        # 키워드 수집
        collect_result = await service.collect_keywords(
            seed_keywords=seed_keywords,
            max_keywords=max_keywords
        )

        if collect_result.get("success"):
            keywords = collect_result.get("keywords", [])
            logger.info(
                f"[GOOGLE_TRENDS] 키워드 수집 성공: "
                f"seed={len(seed_keywords)}, collected={len(keywords)}"
            )
            return {
                "success": True,
                "collected_count": len(keywords),
                "keywords": keywords
            }
        else:
            return {
                "success": False,
                "error": collect_result.get("error", "수집 실패")
            }

    except Exception as e:
        logger.error(f"[GOOGLE_TRENDS] 수집 오류: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def _collect_from_naver_datalab(
    seed_keywords: List[str],
    db: AsyncSession,
    max_keywords: int = 50
) -> Dict[str, Any]:
    """
    네이버 데이터랩에서 키워드 트렌드 수집

    Args:
        seed_keywords: 시드 키워드 목록
        db: 데이터베이스 세션
        max_keywords: 최대 수집 키워드 수

    Returns:
        수집 결과
    """
    from app.services.naver_datalab_service import NaverDatalabService

    try:
        if not seed_keywords:
            return {
                "success": False,
                "error": "시드 키워드가 없습니다"
            }

        # 설정 조회
        query = select(UserSettings).where(UserSettings.user_id == 1)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            return {
                "success": False,
                "error": "사용자 설정을 찾을 수 없습니다"
            }

        service = NaverDatalabService(settings)

        if not service.is_configured():
            return {
                "success": False,
                "error": "네이버 데이터랩 API가 설정되지 않았습니다"
            }

        # 키워드 트렌드 수집
        collect_result = await service.collect_trending_keywords(
            seed_keywords=seed_keywords,
            max_keywords=max_keywords
        )

        if collect_result.get("success"):
            keywords = collect_result.get("keywords", [])
            logger.info(
                f"[NAVER_DATALAB] 키워드 수집 성공: "
                f"seed={len(seed_keywords)}, collected={len(keywords)}"
            )
            return {
                "success": True,
                "collected_count": len(keywords),
                "keywords": keywords
            }
        else:
            return {
                "success": False,
                "error": collect_result.get("error", "수집 실패")
            }

    except Exception as e:
        logger.error(f"[NAVER_DATALAB] 수집 오류: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def _get_or_create_blog_fes(
    db: AsyncSession,
    flow_id: int,
    action_type: str,
    blog_id: int,
) -> FlowExecutionState:
    """
    (flow_id, action_type, blog_id) 단위의 FES를 조회하거나 생성합니다.

    Args:
        db: DB 세션
        flow_id: 플로우 ID
        action_type: 액션 타입 (generate/publish/republish/collect/data)
        blog_id: 블로그 ID

    Returns:
        FlowExecutionState: 기존 또는 신규 생성된 FES
    """
    result = await db.execute(
        select(FlowExecutionState).where(
            FlowExecutionState.flow_id == flow_id,
            FlowExecutionState.action_type == action_type,
            FlowExecutionState.blog_id == blog_id,
        )
    )
    state = result.scalar_one_or_none()

    if state is None:
        state = FlowExecutionState(
            flow_id=flow_id,
            action_type=action_type,
            blog_id=blog_id,
        )
        db.add(state)
        await db.flush()
        logger.debug(
            f"[FES] 신규 생성 | flow={flow_id} action={action_type} blog={blog_id}"
        )

    return state


def _check_fes_interval(
    state: FlowExecutionState,
    now: datetime,
) -> bool:
    """
    FES 간격이 경과했는지 확인합니다.

    Args:
        state: FlowExecutionState 인스턴스
        now: 현재 시간

    Returns:
        True: 실행 가능 (간격 경과 또는 첫 실행)
        False: 실행 불가 (간격 미경과 또는 일시정지)
    """
    if state.is_paused:
        return False
    if state.next_execution_at is None:
        return True
    next_exec = state.next_execution_at
    if next_exec.tzinfo is None:
        import pytz
        next_exec = pytz.timezone('Asia/Seoul').localize(next_exec)
    if now.tzinfo is None:
        import pytz
        now = pytz.timezone('Asia/Seoul').localize(now)
    return now >= next_exec


def _update_fes_after_execution(
    state: FlowExecutionState,
    success: bool,
    interval_minutes: int,
    gp_context: FlowExecutionContext,
) -> None:
    """
    실행 후 FES를 업데이트합니다.

    Args:
        state: FlowExecutionState 인스턴스
        success: 실행 성공 여부
        interval_minutes: 다음 실행까지 간격 (분)
        gp_context: GP 실행 컨텍스트
    """
    state.record_execution(success)
    state.calculate_next_execution(
        interval_minutes=interval_minutes,
        schedule_matrix=gp_context.schedule_matrix,
        jitter_enabled=(
            gp_context.jitter.get("enabled", False)
            if gp_context.jitter else False
        ),
        jitter_min_percent=(
            gp_context.jitter.get("min_percent", -20)
            if gp_context.jitter else -20
        ),
        jitter_max_percent=(
            gp_context.jitter.get("max_percent", 30)
            if gp_context.jitter else 30
        ),
    )


def _count_active_hours(schedule_matrix: Optional[list]) -> int:
    """
    오늘의 schedule_matrix에서 활성 시간 수를 계산합니다.

    Args:
        schedule_matrix: 7x24 bool 매트릭스 (없으면 24 반환)

    Returns:
        활성 시간 수 (최소 1)
    """
    if not schedule_matrix:
        return 24
    if not isinstance(schedule_matrix, list) or len(schedule_matrix) != 7:
        return 24

    day_of_week = datetime.now().weekday()
    day_schedule = schedule_matrix[day_of_week]

    if not isinstance(day_schedule, list) or len(day_schedule) != 24:
        return 24

    active = sum(1 for h in day_schedule if h)
    return max(active, 1)


async def _execute_republish_for_blog(blog: Blog) -> Dict[str, Any]:
    """블로그에 재발행 수행"""
    if blog.platform == BlogPlatform.WORDPRESS:
        service = WordPressRepublishService()
        return await service.republish(blog)
    elif blog.platform == BlogPlatform.BLOGGER:
        if not blog.google_credential:
            return {
                "success": False,
                "message": "Google 인증 정보가 없습니다"
            }
        service = BloggerRepublishService()
        return await service.republish(blog, blog.google_credential)
    else:
        return {
            "success": False,
            "message": f"지원하지 않는 플랫폼: {blog.platform.value}"
        }


async def _save_autorun_log(
    db: AsyncSession,
    user_id: int,
    flow_id: int,
    flow_name: str,
    module_name: str,
    blog_name: str,
    result: Dict[str, Any],
    duration_ms: int,
    action: str = "republish"
) -> None:
    """AutorunLog DB 저장"""
    try:
        # 상태 결정: hold > skipped > success/failed
        # (flow_scheduler.py:_save_autorun_log와 동일 우선순위)
        if result.get("hold"):
            status = "hold"
        elif result.get("skipped"):
            status = "skipped"
        else:
            is_success = result.get("success", False)
            status = "success" if is_success else "failed"
        post_title = result.get("post_title", "")

        # action_time 포맷팅 (YYYY/MM/DD/HH:MM:SS)
        # new_date가 있으면 사용, 없으면 현재 시간
        action_time = None
        new_date = result.get("new_date")
        if new_date:
            try:
                # ISO 형식 파싱 시도
                if "T" in new_date:
                    parsed = datetime.fromisoformat(new_date.replace("Z", "+00:00"))
                    action_time = parsed.strftime("%Y/%m/%d/%H:%M:%S")
                else:
                    action_time = new_date
            except Exception:
                action_time = datetime.now().strftime("%Y/%m/%d/%H:%M:%S")
        else:
            action_time = datetime.now().strftime("%Y/%m/%d/%H:%M:%S")

        # 메시지: 성공/실패 모두 result["message"] 사용
        log_message = result.get("message", "")

        # Celery 큐 등록/디스패치 메시지는 action을 "queue_register"로 변경하고
        # "[블로그명] - [글제목] - [워커종류] 등록 완료/실패" 포맷으로 재가공
        is_queue_dispatch = "Celery 큐 등록" in log_message
        is_dispatch_failed = "Celery 디스패치 실패" in log_message
        if is_queue_dispatch or is_dispatch_failed:
            worker_kind_map = {
                "generate": "생성",
                "publish": "발행",
                "republish": "재발행",
                "collect": "수집",
                "data": "데이터",
            }
            worker_kind = worker_kind_map.get(action, "유틸")
            title_part = ""
            pre_title = post_title.strip() if post_title else ""
            if pre_title:
                title_text = pre_title
                if len(title_text) > 30:
                    title_text = title_text[:30] + "..."
                title_part = f" - {title_text}"
            suffix = "등록 완료" if is_queue_dispatch else "등록 실패"
            action = "queue_register"
            log_message = (
                f"{blog_name}{title_part} - {worker_kind} {suffix}"
            )

        # AutorunLog 생성
        log = AutorunLog.create_execution_log(
            user_id=user_id,
            flow_id=flow_id,
            action=action,
            status=status,
            flow_name=flow_name,
            module_name=module_name,
            blog_name=blog_name,
            post_title=post_title,
            action_time=action_time,
            duration_ms=duration_ms,
            message=log_message
        )

        db.add(log)
        await db.commit()
        logger.info(f"[FLOW_EXECUTE] AutorunLog 저장 완료 | blog={blog_name} | status={status}")

    except Exception as e:
        logger.error(f"[FLOW_EXECUTE] AutorunLog 저장 실패 | blog={blog_name} | error={e}")
        # 로그 저장 실패해도 재발행 결과에는 영향 없음


@router.post("/{flow_id}/modules/{module_id}/execute")
async def execute_single_module(
    flow_id: int,
    module_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    플로우 내 특정 모듈을 개별 실행합니다.

    - prompt/generate: 백그라운드 실행 (AI 파이프라인이 수분 소요)
    - collect: 1회 수집 (동기 실행)
    - data: 1회 이동 (동기 실행)
    - growth_profile: 실행 불가 (400 반환)
    """
    logger.info(f"[MODULE_EXEC] 모듈 개별 실행 | flow_id={flow_id} | module_id={module_id}")

    # 1. 플로우 + 모듈 조회
    result = await db.execute(
        select(Flow)
        .where(Flow.id == flow_id, Flow.user_id == current_user.id)
        .options(
            selectinload(Flow.module_links)
            .selectinload(FlowModule.module)
            .selectinload(Module.module_type),
            selectinload(Flow.blog_links)
            .selectinload(FlowBlog.blog)
        )
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail="플로우를 찾을 수 없습니다")

    # 2. 모듈이 플로우에 연결되어 있는지 확인
    target_module = None
    for link in flow.module_links:
        if link.module and link.module.id == module_id:
            target_module = link.module
            break

    if not target_module:
        raise HTTPException(status_code=404, detail="해당 모듈이 플로우에 연결되어 있지 않습니다")

    type_code = target_module.module_type.code if target_module.module_type else "unknown"

    # 3. growth_profile은 개별 실행 불가
    if type_code == "growth_profile":
        raise HTTPException(status_code=400, detail="성장 프로파일은 개별 실행할 수 없습니다")

    # 4. prompt/generate는 백그라운드 실행 (AI 호출이 수분 소요)
    if type_code in ("prompt", "generate"):
        blogs = [link.blog for link in flow.blog_links if link.blog]
        if not blogs:
            raise HTTPException(status_code=400, detail="플로우에 연결된 블로그가 없습니다")

        execution_id = str(uuid.uuid4())

        # Celery 기능 플래그 체크
        
        if await _use_celery("use_celery_generation", db):
            # Celery 큐로 디스패치
            from app.core.task_dispatcher import get_dispatcher, PRIORITY_CRITICAL
            dispatcher = get_dispatcher()
            task_ids: list[str] = []
            module_settings = (
                target_module.settings if target_module.settings else {}
            )
            for blog in blogs:
                # 디스패치 시점에 다음 처리 대상 제목을 결정 (워커도 동일 ID 사용)
                pre_title, pre_title_id = await _peek_next_generate_title(
                    db, blog.id, module_settings,
                )
                # 사용 가능 제목이 없으면 큐 등록 자체를 skip (자원 낭비 방지)
                # 활동 로그에 표시하기 위해 action="queue_register" + status=skipped로 기록
                if not pre_title_id:
                    skip_msg = (
                        f"{blog.name} - 생성 큐 등록 생략 "
                        f"(사용 가능 제목 없음)"
                    )
                    await _save_autorun_log(
                        db=db, user_id=current_user.id, flow_id=flow_id,
                        flow_name=flow.name, module_name=target_module.name,
                        blog_name=blog.name,
                        result={
                            "success": True, "skipped": True,
                            "message": skip_msg,
                        },
                        duration_ms=0, action="queue_register",
                    )
                    logger.info(
                        f"[MODULE_EXEC] 사용 가능 제목 없음, 큐 등록 skip | blog={blog.name}"
                    )
                    continue
                try:
                    task_id = dispatcher.dispatch_generation(
                        blog_id=blog.id,
                        module_id=module_id,
                        title_id=pre_title_id,
                        priority=PRIORITY_CRITICAL,
                        flow_id=flow_id,
                        user_id=current_user.id,
                        stage_params_dict=None,
                        force=True,
                    )
                    task_ids.append(task_id)
                    logger.info(
                        f"[MODULE_EXEC] Celery 디스패치 성공 | blog={blog.name} | "
                        f"title_id={pre_title_id} | task_id={task_id}"
                    )
                    # 워커 등록 로그 (큐 등록 시점 INFO 표시)
                    await _save_autorun_log(
                        db=db, user_id=current_user.id, flow_id=flow_id,
                        flow_name=flow.name, module_name=target_module.name,
                        blog_name=blog.name,
                        result={
                            "success": True,
                            "message": f"Celery 큐 등록: {task_id}",
                            "post_title": pre_title,
                        },
                        duration_ms=0, action="generate",
                    )
                except Exception as e:
                    logger.warning(f"[MODULE_EXEC] Celery 디스패치 실패 | blog={blog.name} | {e}")
                    await _save_autorun_log(
                        db=db, user_id=current_user.id, flow_id=flow_id,
                        flow_name=flow.name, module_name=target_module.name,
                        blog_name=blog.name,
                        result={
                            "success": False,
                            "message": f"Celery 디스패치 실패: {e}",
                            "post_title": pre_title,
                        },
                        duration_ms=0, action="generate",
                    )

            return {
                "status": "queued",
                "module_type": type_code,
                "module_name": target_module.name,
                "execution_id": execution_id,
                "message": f"'{target_module.name}' 생성이 Celery 큐에 등록되었습니다 ({len(task_ids)}건)",
                "blog_count": len(blogs),
                "task_ids": task_ids,
            }
        else:
            # 기존 asyncio.create_task 방식 유지
            _module_exec_states[execution_id] = {
                "status": "running",
                "module_name": target_module.name,
                "blog_count": len(blogs),
                "message": "생성 진행 중...",
            }

            task = asyncio.create_task(
                _execute_generate_module_background(
                    flow_id=flow_id,
                    module_id=module_id,
                    user_id=current_user.id,
                    execution_id=execution_id,
                )
            )

            def _handle_exc(t):
                try:
                    exc = t.exception()
                    if exc:
                        logger.error(f"[MODULE_EXEC] 백그라운드 생성 예외: {exc}", exc_info=exc)
                        _module_exec_states[execution_id] = {
                            "status": "failed",
                            "message": f"오류: {str(exc)}",
                        }
                except asyncio.CancelledError:
                    pass

            task.add_done_callback(_handle_exc)

            return {
                "status": "started",
                "module_type": type_code,
                "module_name": target_module.name,
                "execution_id": execution_id,
                "message": f"'{target_module.name}' 생성을 시작했습니다. 완료 시 생성 이력에서 확인하세요.",
                "blog_count": len(blogs),
            }

    # 5. collect/data 실행 (Celery 기능 플래그에 따라 분기)
    

    if type_code in ("collect", "data") and await _use_celery("use_celery_utility", db):
        # Celery 큐로 디스패치
        from app.core.task_dispatcher import get_dispatcher, PRIORITY_NORMAL
        dispatcher = get_dispatcher()

        celery_task_name = (
            "tasks.collect_keywords" if type_code == "collect"
            else "tasks.transfer_titles"
        )
        task_id = dispatcher.dispatch_utility(
            celery_task_name,
            kwargs={"module_id": target_module.id, "flow_id": flow_id},
            priority=PRIORITY_NORMAL,
        )
        logger.info(
            f"[MODULE_EXEC] Celery 유틸리티 디스패치 | "
            f"type={type_code} | module={target_module.name} | task_id={task_id}"
        )
        await _save_autorun_log(
            db=db, user_id=current_user.id, flow_id=flow_id,
            flow_name=flow.name, module_name=target_module.name,
            blog_name="-",
            result={"success": True, "message": f"Celery 큐 등록: {task_id}"},
            duration_ms=0, action=type_code
        )
        return {
            "status": "queued",
            "module_type": type_code,
            "module_name": target_module.name,
            "message": f"'{target_module.name}' 작업이 Celery 큐에 등록되었습니다",
            "task_id": task_id,
        }

    # 기존 동기 실행 방식 유지
    started_at = datetime.now()
    results = []

    try:
        if type_code == "collect":
            exec_result = await _execute_collect_module(target_module, db)
            results.append({
                "blog_name": "-",
                "status": "success" if exec_result.get("success") else "failed",
                "detail": exec_result.get("message", "")
            })

        elif type_code == "data":
            exec_result = await _execute_data_module(target_module, db)
            results.append({
                "blog_name": "-",
                "status": "success" if exec_result.get("success") else "failed",
                "detail": exec_result.get("message", "")
            })

        else:
            raise HTTPException(status_code=400, detail=f"지원하지 않는 모듈 타입: {type_code}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MODULE_EXEC] 모듈 실행 오류 | module={target_module.name} | error={e}")
        raise HTTPException(status_code=500, detail=f"모듈 실행 중 오류: {str(e)}")

    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)

    await _save_autorun_log(
        db=db, user_id=current_user.id, flow_id=flow_id,
        flow_name=flow.name, module_name=target_module.name,
        blog_name="-", result=exec_result,
        duration_ms=duration_ms, action=type_code
    )

    return {
        "status": "completed",
        "module_type": type_code,
        "module_name": target_module.name,
        "results": results,
        "duration_ms": duration_ms
    }


@router.get("/module-exec/{execution_id}/status")
async def get_module_exec_status(
    execution_id: str,
    _user: User = Depends(get_current_user),
) -> dict:
    """
    모듈 백그라운드 실행 상태 조회

    Args:
        execution_id: execute_single_module이 반환한 실행 ID
    """
    state = _module_exec_states.get(execution_id)
    if not state:
        return {"status": "unknown", "message": "실행 정보 없음"}
    # 완료/실패 상태는 조회 후 정리 (메모리 절약)
    if state["status"] in ("completed", "failed"):
        _module_exec_states.pop(execution_id, None)
    return state


async def _execute_generate_module_background(
    flow_id: int,
    module_id: int,
    user_id: int,
    execution_id: str,
) -> None:
    """
    백그라운드에서 생성 모듈 실행

    자체 DB 세션을 생성하여 AI 파이프라인을 실행합니다.
    요청 세션과 분리되어 타임아웃 없이 동작합니다.
    """
    from app.core.database import db_manager

    started_at = datetime.now()
    logger.info(
        f"[MODULE_EXEC_BG] 생성 모듈 백그라운드 시작 | "
        f"flow_id={flow_id} | module_id={module_id} | exec_id={execution_id}"
    )

    async with db_manager.get_session() as db:
        try:
            # 1. 플로우 + 모듈 + 블로그 로드 (자체 세션)
            result = await db.execute(
                select(Flow)
                .where(Flow.id == flow_id)
                .options(
                    selectinload(Flow.module_links)
                    .selectinload(FlowModule.module)
                    .selectinload(Module.module_type),
                    selectinload(Flow.blog_links)
                    .selectinload(FlowBlog.blog),
                )
            )
            flow = result.scalar_one_or_none()
            if not flow:
                logger.error(f"[MODULE_EXEC_BG] 플로우 없음: {flow_id}")
                return

            target_module = None
            for link in flow.module_links:
                if link.module and link.module.id == module_id:
                    target_module = link.module
                    break

            if not target_module:
                logger.error(f"[MODULE_EXEC_BG] 모듈 없음: {module_id}")
                return

            blogs = [link.blog for link in flow.blog_links if link.blog]
            if not blogs:
                logger.warning(f"[MODULE_EXEC_BG] 연결된 블로그 없음")
                return

            # 2. GP 컨텍스트 구성 (활성 시간 체크 스킵 — 수동 실행)
            modules_by_type: Dict[str, List[Module]] = {}
            for link in flow.module_links:
                if link.module and link.module.module_type:
                    tc = link.module.module_type.code
                    if tc not in modules_by_type:
                        modules_by_type[tc] = []
                    modules_by_type[tc].append(link.module)

            gp_context = _build_gp_context_for_manual_exec(
                modules_by_type, blogs, flow
            )

            # 3. 블로그별 생성 실행
            from app.services.generation.flow_generate_executor import FlowGenerateExecutor
            gen_executor = FlowGenerateExecutor(db, user_id)

            success_count = 0
            skip_count = 0
            fail_count = 0
            skip_reasons = []

            for blog in blogs:
                # 수동 1회 실행: GP generate.enabled 체크 안 함
                # stage_params는 참고 정보로만 전달
                stage_params = None
                if gp_context:
                    stage_params = gp_context.get_stage_for_blog(blog.id)

                blog_start = datetime.now()
                blog_result = await gen_executor.execute_for_blog(
                    target_module, blog, stage_params=stage_params,
                    force=True,
                )
                blog_duration = int((datetime.now() - blog_start).total_seconds() * 1000)

                blog_msg = blog_result.get("message", "")
                if blog_result.get("success") and not blog_result.get("skipped"):
                    success_count += 1
                elif blog_result.get("skipped"):
                    skip_count += 1
                    skip_reasons.append(f"{blog.name}: {blog_msg}")
                else:
                    fail_count += 1
                    skip_reasons.append(f"{blog.name}: {blog_msg}")

                await _save_autorun_log(
                    db=db, user_id=user_id, flow_id=flow_id,
                    flow_name=flow.name, module_name=target_module.name,
                    blog_name=blog.name, result=blog_result,
                    duration_ms=blog_duration, action="generate"
                )

                logger.info(
                    f"[MODULE_EXEC_BG] 블로그 결과 | blog={blog.name} | "
                    f"result={blog_msg[:80]}"
                )

            elapsed = int((datetime.now() - started_at).total_seconds())
            msg = (
                f"성공 {success_count}건"
                + (f", 스킵 {skip_count}건" if skip_count else "")
                + (f", 실패 {fail_count}건" if fail_count else "")
                + f" ({elapsed}초)"
            )
            _module_exec_states[execution_id] = {
                "status": "completed",
                "message": msg,
                "success_count": success_count,
                "skip_count": skip_count,
                "fail_count": fail_count,
                "elapsed": elapsed,
            }
            reasons_str = "; ".join(skip_reasons) if skip_reasons else ""
            logger.info(
                f"[MODULE_EXEC_BG] 생성 모듈 완료 | "
                f"module={target_module.name} | {elapsed}초 | "
                f"성공={success_count} 스킵={skip_count} 실패={fail_count}"
                + (f" | 사유: {reasons_str}" if reasons_str else "")
            )

        except Exception as e:
            _module_exec_states[execution_id] = {
                "status": "failed",
                "message": f"오류: {str(e)}",
            }
            logger.error(
                f"[MODULE_EXEC_BG] 생성 모듈 오류 | "
                f"flow_id={flow_id} | module_id={module_id} | error={e}",
                exc_info=True,
            )


def _build_gp_context_for_manual_exec(
    modules_by_type: Dict[str, List[Module]],
    blogs: list,
    flow: Flow,
) -> Optional[FlowExecutionContext]:
    """
    수동 실행용 GP 컨텍스트 (활성 시간 체크 스킵)

    스케줄러가 아닌 수동 1회 실행이므로 schedule_matrix 활성 시간
    체크를 하지 않고 GP 스테이지 매핑만 수행합니다.
    """
    if "growth_profile" not in modules_by_type:
        return None

    gp_module = modules_by_type["growth_profile"][0]
    gp_settings = gp_module.settings or {}

    if not gp_settings.get("stages"):
        return None

    # 활성 시간 체크 없이 바로 컨텍스트 빌드
    return _build_context(gp_settings, blogs, flow, gp_module)


@router.post("/{flow_id}/blogs/{blog_id}/publish")
async def publish_single_blog(
    flow_id: int,
    blog_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    플로우 내 특정 블로그에 대해 1회 발행을 실행합니다.
    GP의 stage_params.publish 설정을 사용합니다.
    """
    return await _execute_blog_action(
        flow_id, blog_id, "publish", db, current_user
    )


@router.post("/{flow_id}/blogs/{blog_id}/republish")
async def republish_single_blog(
    flow_id: int,
    blog_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    플로우 내 특정 블로그에 대해 1회 재발행을 실행합니다.
    GP의 stage_params.republish 설정을 사용합니다.
    """
    return await _execute_blog_action(
        flow_id, blog_id, "republish", db, current_user
    )


async def _execute_blog_action(
    flow_id: int,
    blog_id: int,
    action: str,
    db: AsyncSession,
    current_user: User
) -> dict:
    """
    블로그별 발행/재발행 공통 실행 로직

    Args:
        action: "publish" 또는 "republish"
    """
    started_at = datetime.now()
    logger.info(f"[BLOG_EXEC] {action} | flow_id={flow_id} | blog_id={blog_id}")

    # 1. 플로우 조회
    result = await db.execute(
        select(Flow)
        .where(Flow.id == flow_id, Flow.user_id == current_user.id)
        .options(
            selectinload(Flow.module_links)
            .selectinload(FlowModule.module)
            .selectinload(Module.module_type),
            selectinload(Flow.blog_links)
            .selectinload(FlowBlog.blog)
            .selectinload(Blog.google_credential)
        )
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail="플로우를 찾을 수 없습니다")

    # 2. 블로그가 Flow에 연결되어 있는지 확인
    target_blog = None
    for link in flow.blog_links:
        if link.blog and link.blog.id == blog_id:
            target_blog = link.blog
            break
    if not target_blog:
        raise HTTPException(status_code=404, detail="해당 블로그가 플로우에 연결되어 있지 않습니다")

    # 3. GP 컨텍스트 구성
    modules = [link.module for link in flow.module_links if link.module]
    blogs = [link.blog for link in flow.blog_links if link.blog]
    modules_by_type: Dict[str, List[Module]] = {}
    for module in modules:
        tc = module.module_type.code if module.module_type else "unknown"
        if tc not in modules_by_type:
            modules_by_type[tc] = []
        modules_by_type[tc].append(module)

    if "growth_profile" not in modules_by_type:
        raise HTTPException(status_code=400, detail="플로우에 성장 프로파일 모듈이 필요합니다")

    gp_context = await _build_growth_profile_context(modules_by_type, blogs, flow)
    if not gp_context:
        raise HTTPException(status_code=400, detail="성장 프로파일 컨텍스트를 구성할 수 없습니다")

    # 4. 스테이지 확인
    stage_params = gp_context.get_stage_for_blog(blog_id)
    if not stage_params:
        raise HTTPException(status_code=400, detail="해당 블로그의 성장 단계를 찾을 수 없습니다")

    action_config = getattr(stage_params, action, None)
    if not action_config or not action_config.enabled:
        raise HTTPException(
            status_code=409,
            detail=f"{action} 기능이 현재 단계({stage_params.stage_name})에서 비활성화되어 있습니다"
        )

    # 5. 실행
    try:
        if action == "publish":
            
            if await _use_celery("use_celery_publish", db):
                from app.core.task_dispatcher import (
                    get_dispatcher, PRIORITY_CRITICAL,
                )
                dispatcher = get_dispatcher()
                task_id = dispatcher.dispatch_publish(
                    blog_id=blog_id, post_id=0,
                    priority=PRIORITY_CRITICAL, flow_id=flow_id,
                )
                exec_result = {
                    "success": True,
                    "message": f"발행 큐에 등록됨 (task_id={task_id})",
                    "celery_task_id": task_id,
                }
            else:
                from app.services.generation.publisher import Publisher
                from app.services.generation.warmup_manager import WarmupManager
                from app.services.publishing.publisher_pipeline import (
                    PublisherPipeline,
                )

                active_hours = _count_active_hours(gp_context.schedule_matrix)
                warmup_settings = (
                    gp_context.growth_profile.get("warmup", {})
                    if gp_context.growth_profile else {}
                )

                warmup_mgr = WarmupManager(db)
                publisher = Publisher(db)
                pipeline = PublisherPipeline(db)

                warmup_status = await warmup_mgr.check_warmup(
                    blog_id, warmup_settings, active_hours
                )

                exec_result = await publisher.publish_for_blog(
                    target_blog, warmup_status
                )

                if not exec_result.get("skipped"):
                    crawled_post = exec_result.get("crawled_post")
                    if crawled_post and exec_result.get("success"):
                        credential = getattr(
                            target_blog, "google_credential", None,
                        )
                        pub_result = await pipeline.publish_post(
                            target_blog, crawled_post,
                            credential=credential,
                        )
                        if pub_result.success:
                            await publisher.complete_publish(
                                blog_id, crawled_post.id,
                                published_url=pub_result.published_url,
                            )
                            exec_result["published_url"] = (
                                pub_result.published_url
                            )
                            exec_result["post_title"] = getattr(
                                crawled_post, "title", "",
                            )
                        else:
                            exec_result = {
                                "success": False,
                                "message": (
                                    pub_result.error or "플랫폼 발행 실패"
                                ),
                            }

        elif action == "republish":
            
            if await _use_celery("use_celery_publish", db):
                from app.core.task_dispatcher import (
                    get_dispatcher, PRIORITY_CRITICAL,
                )
                dispatcher = get_dispatcher()
                task_id = dispatcher.dispatch_republish(
                    blog_id=blog_id,
                    priority=PRIORITY_CRITICAL, flow_id=flow_id,
                )
                exec_result = {
                    "success": True,
                    "message": f"재발행 큐에 등록됨 (task_id={task_id})",
                    "celery_task_id": task_id,
                }
            else:
                exec_result = await _execute_republish_for_blog(target_blog)

        else:
            raise HTTPException(status_code=400, detail=f"지원하지 않는 액션: {action}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[BLOG_EXEC] {action} 오류 | blog={target_blog.name} | error={e}")
        raise HTTPException(status_code=500, detail=f"{action} 실행 중 오류: {str(e)}")

    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)

    gp_module_name = ""
    for _link in flow.module_links:
        if _link.module and _link.module.module_type:
            if _link.module.module_type.code == "growth_profile":
                gp_module_name = _link.module.name
                break

    # Celery 사용 시: 태스크 완료 후 celery_publish_tasks.py에서 로그 저장 (제목 포함)
    # Celery 미사용 시: 여기서 직접 로그 저장
    if not exec_result.get("celery_task_id"):
        await _save_autorun_log(
            db=db, user_id=current_user.id, flow_id=flow_id,
            flow_name=flow.name, module_name=gp_module_name or f"GP {action}",
            blog_name=target_blog.name, result=exec_result,
            duration_ms=duration_ms, action=action
        )

    return {
        "status": "completed",
        "action": action,
        "blog_name": target_blog.name,
        "result": {
            "success": exec_result.get("success", False),
            "post_title": exec_result.get("post_title", ""),
            "post_url": exec_result.get("published_url", ""),
            "detail": exec_result.get("message", "")
        },
        "duration_ms": duration_ms
    }


@router.get("/{flow_id}/execute/history")
async def get_execution_history(
    flow_id: int,
    limit: int = 10,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    플로우 실행 히스토리 조회

    TODO: 실행 결과 DB 저장 후 구현
    """
    return {
        "flow_id": flow_id,
        "executions": [],
        "total_count": 0,
        "message": "실행 히스토리 기능 준비 중"
    }
