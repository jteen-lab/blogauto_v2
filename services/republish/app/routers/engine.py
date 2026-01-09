"""
플로우 엔진 API 라우터

Features:
- 수동 재발행 실행
- 블로그 API 연결 테스트
- 스케줄러 상태 조회
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.flow import Flow
from ..models.flow_module import FlowModule
from ..models.module import Module
from ..models.flow_blog import FlowBlog
from ..models.blog import Blog
from ..models.google_credential import GoogleCredential
from ..engine.flow_engine import FlowEngine
from ..scheduler.flow_scheduler import get_flow_scheduler

logger = get_logger("engine_router", "republish.log")

router = APIRouter(prefix="/engine", tags=["엔진"])


# ============================================================
# 플로우 엔진 인스턴스
# ============================================================

flow_engine = FlowEngine()


# ============================================================
# API Endpoints
# ============================================================

@router.post("/execute/{flow_id}")
async def execute_flow(
    flow_id: int,
    action_type: str = Query(default="republish", description="액션 타입 (republish, publish 등)"),
    blog_id: Optional[int] = Query(default=None, description="특정 블로그만 실행"),
    db: AsyncSession = Depends(get_db_session)
):
    """
    플로우 수동 실행

    - flow_id: 실행할 플로우 ID
    - action_type: 실행할 액션 타입 (기본: republish)
    - blog_id: 특정 블로그만 실행 (선택)
    """
    try:
        logger.info(f"[ENGINE_API] Execute request | FlowID={flow_id} | ActionType={action_type}")

        # 플로우 조회
        query = (
            select(Flow)
            .options(
                selectinload(Flow.module_links).selectinload(FlowModule.module).selectinload(Module.module_type),
                selectinload(Flow.blog_links).selectinload(FlowBlog.blog)
            )
            .where(Flow.id == flow_id)
        )
        result = await db.execute(query)
        flow = result.scalar_one_or_none()

        if not flow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"플로우를 찾을 수 없습니다: {flow_id}"
            )

        # 플로우 실행
        execution_result = await flow_engine.execute(
            db=db,
            flow=flow,
            action_type=action_type,
            target_blog_id=blog_id
        )

        return {
            "success": execution_result.get("success", False),
            "message": execution_result.get("message", ""),
            "data": execution_result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ENGINE_API] Execute error | FlowID={flow_id} | Error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"실행 오류: {e}"
        )


@router.get("/test-connection/{blog_id}")
async def test_blog_connection(
    blog_id: int,
    db: AsyncSession = Depends(get_db_session)
):
    """
    블로그 API 연결 테스트

    - blog_id: 테스트할 블로그 ID
    """
    try:
        logger.info(f"[ENGINE_API] Connection test | BlogID={blog_id}")

        # 블로그 조회
        query = select(Blog).where(Blog.id == blog_id, Blog.is_deleted == False)
        result = await db.execute(query)
        blog = result.scalar_one_or_none()

        if not blog:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"블로그를 찾을 수 없습니다: {blog_id}"
            )

        # 연결 테스트
        test_result = await flow_engine.test_connection(db, blog)

        return {
            "success": test_result.get("success", False),
            "message": test_result.get("message", ""),
            "blog_id": blog_id,
            "blog_name": blog.name,
            "platform": blog.platform.value,
            "data": test_result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ENGINE_API] Connection test error | BlogID={blog_id} | Error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"연결 테스트 오류: {e}"
        )


@router.get("/scheduler/status")
async def get_scheduler_status():
    """
    스케줄러 상태 조회
    """
    try:
        scheduler = get_flow_scheduler()

        if not scheduler:
            return {
                "success": True,
                "data": {
                    "is_initialized": False,
                    "is_running": False,
                    "jobs": [],
                    "message": "스케줄러가 초기화되지 않았습니다"
                }
            }

        status_data = scheduler.get_status()

        return {
            "success": True,
            "data": status_data
        }

    except Exception as e:
        logger.error(f"[ENGINE_API] Scheduler status error | Error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"스케줄러 상태 조회 오류: {e}"
        )


@router.post("/scheduler/trigger")
async def trigger_scheduler_check():
    """
    스케줄러 수동 트리거 (현재 시간 기준 플로우 실행)
    """
    try:
        logger.info("[ENGINE_API] Manual scheduler trigger")

        scheduler = get_flow_scheduler()

        if not scheduler:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="스케줄러가 초기화되지 않았습니다"
            )

        # 수동 트리거
        await scheduler.check_and_execute_flows()

        return {
            "success": True,
            "message": "스케줄러 체크 완료"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ENGINE_API] Scheduler trigger error | Error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"스케줄러 트리거 오류: {e}"
        )
