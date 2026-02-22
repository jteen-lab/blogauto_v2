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
                # GP 미설정 또는 비활성 시간 → Flow 실행 중단
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

            # 7. publish 모듈 실행 (GP 컨텍스트 기반 발행 + 워밍업)
            if "publish" in modules_by_type:
                if not blogs:
                    logger.warning(f"[FLOW_BG] 발행 모듈이 있지만 블로그가 없음: {flow_id}")
                    for publish_module in modules_by_type["publish"]:
                        fail_count += 1
                        total_processed += 1
                        await _save_autorun_log(
                            db=db,
                            user_id=user_id,
                            flow_id=flow.id,
                            flow_name=flow.name,
                            module_name=publish_module.name,
                            blog_name="-",
                            result={"success": False, "message": "플로우에 연결된 블로그가 없습니다"},
                            duration_ms=0,
                            action="publish"
                        )
                else:
                    from app.services.generation.publisher import Publisher
                    from app.services.generation.warmup_manager import WarmupManager

                    # schedule_matrix에서 오늘의 활성 시간 수 계산
                    active_hours = _count_active_hours(gp_context.schedule_matrix)

                    # warmup 설정 로드
                    warmup_settings = (
                        gp_context.growth_profile.get("warmup", {})
                        if gp_context.growth_profile else {}
                    )

                    warmup_mgr = WarmupManager(db)
                    publisher = Publisher(db)

                    for publish_module in modules_by_type["publish"]:
                        logger.info(f"[FLOW_BG] 발행 모듈 실행: {publish_module.name}")

                        for blog in blogs:
                            # (1) GP publish.enabled 체크
                            stage_params = gp_context.get_stage_for_blog(blog.id)
                            if stage_params and not stage_params.publish.enabled:
                                logger.info(
                                    f"[FLOW_BG] 발행 비활성 | blog={blog.name} | "
                                    f"stage={stage_params.stage_name}"
                                )
                                total_processed += 1
                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=publish_module.name,
                                    blog_name=blog.name,
                                    result={
                                        "success": True,
                                        "skipped": True,
                                        "message": f"발행 비활성 (stage: {stage_params.stage_name})",
                                    },
                                    duration_ms=0,
                                    action="publish"
                                )
                                continue

                            # (2) FES 간격 체크
                            fes = await _get_or_create_blog_fes(
                                db, flow.id, publish_module.id, blog.id,
                            )
                            now = datetime.now()
                            if not _check_fes_interval(fes, now):
                                logger.info(
                                    f"[FLOW_BG] 발행 간격 미경과 | blog={blog.name} | "
                                    f"next={fes.next_execution_at}"
                                )
                                continue

                            # (3) 워밍업 체크
                            warmup_status = await warmup_mgr.check_warmup(
                                blog.id, warmup_settings, active_hours,
                            )

                            # (4) 발행 실행
                            blog_start_time = datetime.now()
                            try:
                                result = await publisher.publish_for_blog(
                                    blog, warmup_status,
                                )
                                blog_duration_ms = int(
                                    (datetime.now() - blog_start_time).total_seconds() * 1000
                                )

                                # 발행 대상이 있으면 플랫폼 API 호출
                                if result.get("success") and not result.get("skipped"):
                                    crawled_post = result.get("crawled_post")
                                    if crawled_post:
                                        platform_result = await _execute_republish_for_blog(blog)
                                        if platform_result.get("success"):
                                            complete_info = await publisher.complete_publish(
                                                blog.id, crawled_post.id,
                                                published_url=platform_result.get("url"),
                                            )
                                            result["inventory"] = complete_info["inventory"]
                                            result["needs_generation"] = complete_info["needs_generation"]
                                        else:
                                            result = platform_result

                                # (5) FES 업데이트 (skipped가 아닌 경우만)
                                # 의도적 설계: 재고 0이나 워밍업 한도 초과로 스킵된 경우
                                # FES를 업데이트하지 않아, 재고 확보 시 즉시 발행 가능
                                if not result.get("skipped"):
                                    effective_interval = (
                                        warmup_status.effective_interval
                                        if warmup_status.is_active and warmup_status.effective_interval
                                        else (stage_params.publish.computed_interval if stage_params else None)
                                    )
                                    _update_fes_after_execution(
                                        fes,
                                        success=result.get("success", False),
                                        interval_minutes=effective_interval or 60,
                                        gp_context=gp_context,
                                    )

                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=publish_module.name,
                                    blog_name=blog.name,
                                    result=result,
                                    duration_ms=blog_duration_ms,
                                    action="publish"
                                )
                                if result.get("success"):
                                    success_count += 1
                                else:
                                    fail_count += 1
                                total_processed += 1

                            except Exception as e:
                                fail_count += 1
                                total_processed += 1
                                blog_duration_ms = int(
                                    (datetime.now() - blog_start_time).total_seconds() * 1000
                                )
                                logger.error(
                                    f"[FLOW_BG] 발행 오류 | blog={blog.name} | error={e}"
                                )
                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=publish_module.name,
                                    blog_name=blog.name,
                                    result={"success": False, "message": str(e)},
                                    duration_ms=blog_duration_ms,
                                    action="publish"
                                )

            # 8. republish 모듈 실행 (GP 컨텍스트 기반 재발행)
            if "republish" in modules_by_type:
                if not blogs:
                    logger.warning(f"[FLOW_BG] 재발행 모듈이 있지만 블로그가 없음: {flow_id}")
                    for republish_module in modules_by_type["republish"]:
                        fail_count += 1
                        total_processed += 1
                        await _save_autorun_log(
                            db=db,
                            user_id=user_id,
                            flow_id=flow.id,
                            flow_name=flow.name,
                            module_name=republish_module.name,
                            blog_name="-",
                            result={"success": False, "message": "플로우에 연결된 블로그가 없습니다"},
                            duration_ms=0,
                            action="republish"
                        )
                else:
                    for republish_module in modules_by_type["republish"]:
                        logger.info(f"[FLOW_BG] 재발행 모듈 실행: {republish_module.name}")

                        for blog in blogs:
                            # GP 컨텍스트에서 블로그별 StageParams 조회
                            stage_params = gp_context.get_stage_for_blog(blog.id)

                            # republish.enabled 체크
                            if stage_params and not stage_params.republish.enabled:
                                logger.info(
                                    f"[FLOW_BG] 재발행 비활성 | blog={blog.name} | "
                                    f"stage={stage_params.stage_name}"
                                )
                                total_processed += 1
                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=republish_module.name,
                                    blog_name=blog.name,
                                    result={
                                        "success": True,
                                        "skipped": True,
                                        "message": f"재발행 비활성 (stage: {stage_params.stage_name})",
                                    },
                                    duration_ms=0,
                                    action="republish"
                                )
                                continue

                            # FES 간격 체크 (Phase D 추가)
                            fes = await _get_or_create_blog_fes(
                                db, flow.id, republish_module.id, blog.id,
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
                                f"module={republish_module.name} | "
                                f"stage={stage_params.stage_name if stage_params else 'unknown'}"
                            )

                            try:
                                result = await _execute_republish_for_blog(blog)
                                blog_duration_ms = int(
                                    (datetime.now() - blog_start_time).total_seconds() * 1000
                                )

                                # 실행 성공 후 FES 업데이트 (Phase D 추가)
                                if result.get("success"):
                                    _update_fes_after_execution(
                                        fes,
                                        success=True,
                                        interval_minutes=(
                                            stage_params.republish.computed_interval or 60
                                            if stage_params else 60
                                        ),
                                        gp_context=gp_context,
                                    )

                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=republish_module.name,
                                    blog_name=blog.name,
                                    result=result,
                                    duration_ms=blog_duration_ms,
                                    action="republish"
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
                                logger.error(
                                    f"[FLOW_BG] 재발행 오류 | blog={blog.name} | error={e}"
                                )

                                await _save_autorun_log(
                                    db=db,
                                    user_id=user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=republish_module.name,
                                    blog_name=blog.name,
                                    result={"success": False, "message": str(e)},
                                    duration_ms=blog_duration_ms,
                                    action="republish"
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
    module_id: int,
    blog_id: int,
) -> FlowExecutionState:
    """
    (flow_id, module_id, blog_id) 단위의 FES를 조회하거나 생성합니다.

    Args:
        db: DB 세션
        flow_id: 플로우 ID
        module_id: 모듈 ID
        blog_id: 블로그 ID

    Returns:
        FlowExecutionState: 기존 또는 신규 생성된 FES
    """
    result = await db.execute(
        select(FlowExecutionState).where(
            FlowExecutionState.flow_id == flow_id,
            FlowExecutionState.module_id == module_id,
            FlowExecutionState.blog_id == blog_id,
        )
    )
    state = result.scalar_one_or_none()

    if state is None:
        state = FlowExecutionState(
            flow_id=flow_id,
            module_id=module_id,
            blog_id=blog_id,
        )
        db.add(state)
        await db.flush()
        logger.debug(
            f"[FES] 신규 생성 | flow={flow_id} module={module_id} blog={blog_id}"
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
