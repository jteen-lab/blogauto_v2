"""
플로우 실행 API

플로우를 1회 즉시 실행합니다.
오토런과 동일한 방식으로 각 모듈별로 연결된 블로그에 재발행을 수행합니다.
"""

import uuid
from datetime import datetime
from typing import Dict, Any, List

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
from app.core.logger import get_logger

router = APIRouter(prefix="/api/v1/flows", tags=["flows-execute"])
logger = get_logger("flow_execute", "app.log")


@router.post("/{flow_id}/execute")
async def execute_flow_once(
    flow_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    플로우 1회 즉시 실행 (테스트)

    오토런과 동일한 방식으로 각 모듈별로 연결된 블로그에 재발행을 수행합니다.
    - 각 모듈은 1회씩만 실행
    - 각 블로그는 1회씩만 재발행
    """
    execution_id = str(uuid.uuid4())
    started_at = datetime.now()

    logger.info(f"[FLOW_EXECUTE] ========== 테스트 실행 시작 ==========")
    logger.info(f"[FLOW_EXECUTE] flow_id={flow_id} | user_id={current_user.id} | execution_id={execution_id}")

    # 1. 플로우 조회 (모듈, 블로그 포함)
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
        logger.warning(f"[FLOW_EXECUTE] 플로우를 찾을 수 없음: {flow_id}")
        raise HTTPException(status_code=404, detail="플로우를 찾을 수 없습니다")

    # 2. 모듈과 블로그 확인
    modules = [link.module for link in flow.module_links if link.module]
    blogs = [link.blog for link in flow.blog_links if link.blog]

    if not modules:
        logger.warning(f"[FLOW_EXECUTE] 플로우에 모듈이 없음: {flow_id}")
        raise HTTPException(status_code=400, detail="플로우에 모듈이 없습니다")

    if not blogs:
        logger.warning(f"[FLOW_EXECUTE] 플로우에 블로그가 없음: {flow_id}")
        raise HTTPException(status_code=400, detail="플로우에 연결된 블로그가 없습니다")

    logger.info(f"[FLOW_EXECUTE] 플로우: {flow.name} | 모듈: {len(modules)}개 | 블로그: {len(blogs)}개")

    # 3. 각 블로그에 대해 1회씩 재발행 실행 (오토런과 동일)
    blog_results = []
    success_count = 0
    fail_count = 0

    # 첫 번째 모듈 이름 (로그용)
    first_module_name = modules[0].name if modules else "재발행 모듈"

    for blog in blogs:
        blog_start_time = datetime.now()
        logger.info(f"[FLOW_EXECUTE] 블로그 처리 시작: {blog.name} ({blog.platform.value})")

        try:
            result = await _execute_republish_for_blog(blog)
            blog_duration_ms = int((datetime.now() - blog_start_time).total_seconds() * 1000)

            blog_results.append({
                "blog_id": blog.id,
                "blog_name": blog.name,
                "platform": blog.platform.value,
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "post_id": result.get("post_id"),
                "post_title": result.get("post_title"),
                "old_date": result.get("old_date"),
                "new_date": result.get("new_date"),
                "link": result.get("link")
            })

            # AutorunLog DB 저장
            await _save_autorun_log(
                db=db,
                user_id=current_user.id,
                flow_id=flow.id,
                flow_name=flow.name,
                module_name=first_module_name,
                blog_name=blog.name,
                result=result,
                duration_ms=blog_duration_ms
            )

            if result.get("success"):
                success_count += 1
                logger.info(
                    f"[FLOW_EXECUTE] 재발행 성공 | blog={blog.name} | "
                    f"post={result.get('post_title', '')[:30]}"
                )
            else:
                fail_count += 1
                logger.warning(
                    f"[FLOW_EXECUTE] 재발행 실패 | blog={blog.name} | "
                    f"error={result.get('message', '')}"
                )

        except Exception as e:
            fail_count += 1
            blog_duration_ms = int((datetime.now() - blog_start_time).total_seconds() * 1000)
            logger.error(f"[FLOW_EXECUTE] 블로그 처리 오류 | blog={blog.name} | error={e}")
            blog_results.append({
                "blog_id": blog.id,
                "blog_name": blog.name,
                "platform": blog.platform.value,
                "success": False,
                "message": str(e)
            })

            # 에러 시에도 AutorunLog 저장
            await _save_autorun_log(
                db=db,
                user_id=current_user.id,
                flow_id=flow.id,
                flow_name=flow.name,
                module_name=first_module_name,
                blog_name=blog.name,
                result={"success": False, "message": str(e)},
                duration_ms=blog_duration_ms
            )

    # 4. 실행 완료
    completed_at = datetime.now()
    duration_ms = int((completed_at - started_at).total_seconds() * 1000)

    logger.info(
        f"[FLOW_EXECUTE] ========== 테스트 실행 완료 =========="
    )
    logger.info(
        f"[FLOW_EXECUTE] 결과: 성공 {success_count}/{len(blogs)} | "
        f"실패 {fail_count}/{len(blogs)} | 소요시간 {duration_ms}ms"
    )

    return {
        "execution_id": execution_id,
        "flow_id": flow.id,
        "flow_name": flow.name,
        "success": fail_count == 0,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_ms": duration_ms,
        "total_items_processed": success_count,
        "module_count": len(modules),
        "blog_count": len(blogs),
        "success_count": success_count,
        "fail_count": fail_count,
        "blog_results": blog_results,
        "error": None if fail_count == 0 else f"{fail_count}개 블로그 재발행 실패"
    }


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
    duration_ms: int
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

        # 에러 메시지
        error_msg = None if is_success else result.get("message", "")

        # AutorunLog 생성
        log = AutorunLog.create_execution_log(
            user_id=user_id,
            flow_id=flow_id,
            action="republish",
            status=status,
            flow_name=flow_name,
            module_name=module_name,
            blog_name=blog_name,
            post_title=post_title,
            action_time=action_time,
            duration_ms=duration_ms,
            message=error_msg
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
