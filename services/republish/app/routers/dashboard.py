"""
대시보드 API 라우터
- 글로벌 요약 통계
- 대시보드 상세 데이터
- 최근 활동 로그
- 고정 요약탭 설정
"""
from datetime import datetime, timedelta
from typing import Optional, List
import pytz
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy import func, select
from pydantic import BaseModel

# KST 기준 (서버 시간대와 무관하게 일관된 카운트)
KST = pytz.timezone('Asia/Seoul')

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.blog import Blog, BlogPlatform
from ..models.module import Module
from ..models.module_type import ModuleType
from ..models.flow import Flow
from ..models.category import Topic, SubTopic, Keyword
from ..models.flow_execution_state import FlowExecutionState
from ..models.autorun_log import AutorunLog
from ..models.action_log import ActionLog

logger = get_logger("dashboard", "dashboard.log")

router = APIRouter(prefix="/dashboard", tags=["대시보드"])


class PinnedTabsRequest(BaseModel):
    """고정 탭 설정 요청"""
    pinned_tabs: List[str]


@router.get("/summary")
async def get_dashboard_summary(db: AsyncSession = Depends(get_db_session)):
    """
    글로벌 요약 데이터 (헤더 요약탭용)
    """
    try:
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())

        # 활성 플로우 수 (status가 'active'인 플로우)
        result = await db.execute(
            select(func.count(Flow.id)).where(Flow.status == "active")
        )
        active_flows = result.scalar() or 0

        # 활성 블로그 수 (삭제되지 않은 블로그만)
        result = await db.execute(
            select(func.count(Blog.id)).where(
                Blog.is_active == True,
                Blog.is_deleted == False
            )
        )
        active_blogs = result.scalar() or 0

        # 오늘 생성된 항목 수 (모듈 + 플로우 + 블로그)
        result = await db.execute(
            select(func.count(Module.id)).where(Module.created_at >= today_start)
        )
        today_modules = result.scalar() or 0

        result = await db.execute(
            select(func.count(Flow.id)).where(Flow.created_at >= today_start)
        )
        today_flows = result.scalar() or 0

        result = await db.execute(
            select(func.count(Blog.id)).where(
                Blog.created_at >= today_start,
                Blog.is_deleted == False
            )
        )
        today_blogs = result.scalar() or 0

        today_created = today_modules + today_flows + today_blogs

        # 오늘 발행된 글 수 (임시 0)
        today_published = 0

        return {
            "active_flows": active_flows,
            "active_blogs": active_blogs,
            "today_created": today_created,
            "today_published": today_published
        }
    except Exception as e:
        logger.error(f"[DASHBOARD] summary 에러: {str(e)}")
        # 에러 발생 시 기본값 반환
        return {
            "active_flows": 0,
            "active_blogs": 0,
            "today_created": 0,
            "today_published": 0
        }


@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db_session)):
    """
    대시보드 상세 통계 (패널 확장 시)
    22개 요약탭 전체 카운팅 제공
    """
    try:
        # KST 기준 오늘/이번주 경계 (서버가 UTC라도 일관된 카운트).
        # AutorunLog.created_at은 timezone-aware라 TZ-aware datetime과 비교.
        now_kst = datetime.now(KST)
        today = now_kst.date()
        today_start = KST.localize(datetime.combine(today, datetime.min.time()))
        today_end = KST.localize(datetime.combine(today + timedelta(days=1), datetime.min.time()))

        # 이번주 계산 (월요일 0시 KST ~ 일요일 24시 KST)
        # weekday(): 월=0, 화=1, 수=2, 목=3, 금=4, 토=5, 일=6
        days_since_monday = today.weekday()
        week_start = KST.localize(datetime.combine(
            today - timedelta(days=days_since_monday), datetime.min.time()
        ))
        week_end = KST.localize(datetime.combine(
            week_start.date() + timedelta(days=7), datetime.min.time()
        ))

        # === 블로그 관련 (삭제되지 않은 블로그만) ===
        result = await db.execute(
            select(func.count(Blog.id)).where(Blog.is_deleted == False)
        )
        total_blogs = result.scalar() or 0

        result = await db.execute(
            select(func.count(Blog.id)).where(
                Blog.is_active == True,
                Blog.is_deleted == False
            )
        )
        active_blogs = result.scalar() or 0
        inactive_blogs = total_blogs - active_blogs

        result = await db.execute(
            select(func.count(Blog.id)).where(
                Blog.platform == BlogPlatform.WORDPRESS,
                Blog.is_deleted == False
            )
        )
        wordpress_count = result.scalar() or 0

        result = await db.execute(
            select(func.count(Blog.id)).where(
                Blog.platform == BlogPlatform.BLOGGER,
                Blog.is_deleted == False
            )
        )
        blogger_count = result.scalar() or 0

        # === 카테고리 관련 ===
        result = await db.execute(
            select(func.count(Topic.id)).where(Topic.is_deleted == False)
        )
        total_topics = result.scalar() or 0

        result = await db.execute(
            select(func.count(SubTopic.id)).where(SubTopic.is_deleted == False)
        )
        total_subtopics = result.scalar() or 0

        result = await db.execute(
            select(func.count(Keyword.id)).where(Keyword.is_deleted == False)
        )
        total_keywords = result.scalar() or 0

        # === 모듈 관련 ===
        result = await db.execute(select(func.count(Module.id)))
        total_modules = result.scalar() or 0

        # 모듈 타입별 카운트 (code 기준)
        result = await db.execute(
            select(ModuleType.code, func.count(Module.id))
            .join(Module, Module.module_type_id == ModuleType.id)
            .group_by(ModuleType.code)
        )
        module_type_stats = result.all()
        module_by_code = {code: count for code, count in module_type_stats}

        prompt_modules = module_by_code.get("prompt", 0)
        generate_modules = module_by_code.get("generate", 0)
        publish_modules = module_by_code.get("publish", 0)
        republish_modules = module_by_code.get("republish", 0)
        growth_profile_modules = module_by_code.get("growth_profile", 0)
        # 현재 시스템에서 생성/발행/재발행은 GP에 통합됨.
        # 수집/데이터 모듈은 별도 모듈로 운영.
        collect_modules = module_by_code.get("collect", 0)
        data_modules = module_by_code.get("data", 0)

        # === 플로우 관련 ===
        result = await db.execute(select(func.count(Flow.id)))
        total_flows = result.scalar() or 0

        result = await db.execute(
            select(func.count(Flow.id)).where(Flow.status == "active")
        )
        active_flows = result.scalar() or 0
        inactive_flows = total_flows - active_flows

        # === 이번 주 통계 (AutorunLog 기반: 월요일 0시 ~ 일요일 24시) ===
        # 이번주 성공한 작업 수 (action별)
        result = await db.execute(
            select(func.count(AutorunLog.id))
            .where(
                AutorunLog.action == "generate",
                AutorunLog.status == "success",
                AutorunLog.created_at >= week_start,
                AutorunLog.created_at < week_end
            )
        )
        week_generate = result.scalar() or 0

        result = await db.execute(
            select(func.count(AutorunLog.id))
            .where(
                AutorunLog.action == "publish",
                AutorunLog.status == "success",
                AutorunLog.created_at >= week_start,
                AutorunLog.created_at < week_end
            )
        )
        week_publish = result.scalar() or 0

        result = await db.execute(
            select(func.count(AutorunLog.id))
            .where(
                AutorunLog.action == "republish",
                AutorunLog.status == "success",
                AutorunLog.created_at >= week_start,
                AutorunLog.created_at < week_end
            )
        )
        week_republish = result.scalar() or 0

        # === 오늘 통계 (AutorunLog 기반: 오늘 0시 ~ 24시) ===
        result = await db.execute(
            select(func.count(AutorunLog.id))
            .where(
                AutorunLog.action == "generate",
                AutorunLog.status == "success",
                AutorunLog.created_at >= today_start,
                AutorunLog.created_at < today_end
            )
        )
        today_generate = result.scalar() or 0

        result = await db.execute(
            select(func.count(AutorunLog.id))
            .where(
                AutorunLog.action == "publish",
                AutorunLog.status == "success",
                AutorunLog.created_at >= today_start,
                AutorunLog.created_at < today_end
            )
        )
        today_publish = result.scalar() or 0

        result = await db.execute(
            select(func.count(AutorunLog.id))
            .where(
                AutorunLog.action == "republish",
                AutorunLog.status == "success",
                AutorunLog.created_at >= today_start,
                AutorunLog.created_at < today_end
            )
        )
        today_republish = result.scalar() or 0

        return {
            # 블로그
            "total_blogs": total_blogs,
            "wordpress": wordpress_count,
            "blogger": blogger_count,
            "active_blogs": active_blogs,
            "inactive_blogs": inactive_blogs,
            # 카테고리
            "topics": total_topics,
            "subtopics": total_subtopics,
            "keywords": total_keywords,
            # 모듈
            "total_modules": total_modules,
            "prompt_modules": prompt_modules,
            "generate_modules": generate_modules,
            "publish_modules": publish_modules,
            "republish_modules": republish_modules,
            "growth_profile_modules": growth_profile_modules,
            "collect_modules": collect_modules,
            "data_modules": data_modules,
            # 플로우
            "total_flows": total_flows,
            "active_flows": active_flows,
            "inactive_flows": inactive_flows,
            # 이번 주
            "week_generate": week_generate,
            "week_publish": week_publish,
            "week_republish": week_republish,
            # 오늘
            "today_generate": today_generate,
            "today_publish": today_publish,
            "today_republish": today_republish,
            # 레거시 호환
            "totals": {
                "blogs": total_blogs,
                "modules": total_modules,
                "flows": total_flows
            },
            "active": {
                "blogs": active_blogs,
                "flows": active_flows
            },
            "blogs_by_platform": {
                "wordpress": wordpress_count,
                "blogger": blogger_count
            },
            "week_created": {
                "modules": week_generate + week_publish + week_republish,
                "flows": 0  # 레거시 호환
            }
        }
    except Exception as e:
        logger.error(f"[DASHBOARD] stats 에러: {str(e)}")
        return {
            "total_blogs": 0, "wordpress": 0, "blogger": 0,
            "active_blogs": 0, "inactive_blogs": 0,
            "topics": 0, "subtopics": 0, "keywords": 0,
            "total_modules": 0, "prompt_modules": 0, "generate_modules": 0,
            "publish_modules": 0, "republish_modules": 0, "growth_profile_modules": 0,
            "total_flows": 0, "active_flows": 0, "inactive_flows": 0,
            "week_generate": 0, "week_publish": 0, "week_republish": 0,
            "today_generate": 0, "today_publish": 0, "today_republish": 0,
            "totals": {"blogs": 0, "modules": 0, "flows": 0},
            "active": {"blogs": 0, "flows": 0},
            "blogs_by_platform": {"wordpress": 0, "blogger": 0},
            "week_created": {"modules": 0, "flows": 0}
        }


@router.get("/activities")
async def get_recent_activities(
    limit: int = 10,
    db: AsyncSession = Depends(get_db_session)
):
    """
    최근 활동 로그
    """
    try:
        activities = []

        # 최근 블로그 (platform을 문자열로 변환)
        result = await db.execute(
            select(Blog).order_by(Blog.created_at.desc()).limit(5)
        )
        recent_blogs = result.scalars().all()

        for blog in recent_blogs:
            platform_str = blog.platform.value if blog.platform else None
            activities.append({
                "type": "blog",
                "action": "created",
                "name": blog.name,
                "platform": platform_str,
                "timestamp": blog.created_at.isoformat() if blog.created_at else None
            })

        # 최근 모듈 (selectinload로 module_type 미리 로드)
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(Module)
            .options(selectinload(Module.module_type))
            .order_by(Module.created_at.desc())
            .limit(5)
        )
        recent_modules = result.scalars().all()

        for module in recent_modules:
            module_type_code = None
            if module.module_type:
                module_type_code = module.module_type.code
            activities.append({
                "type": "module",
                "action": "created",
                "name": module.name,
                "module_type": module_type_code,
                "timestamp": module.created_at.isoformat() if module.created_at else None
            })

        # 최근 플로우
        result = await db.execute(
            select(Flow).order_by(Flow.created_at.desc()).limit(5)
        )
        recent_flows = result.scalars().all()

        for flow in recent_flows:
            activities.append({
                "type": "flow",
                "action": "created",
                "name": flow.name,
                "timestamp": flow.created_at.isoformat() if flow.created_at else None
            })

        # 시간순 정렬
        activities.sort(
            key=lambda x: x.get("timestamp") or "",
            reverse=True
        )

        return {
            "activities": activities[:limit]
        }
    except Exception as e:
        logger.error(f"[DASHBOARD] activities 에러: {str(e)}")
        return {
            "activities": []
        }


class LogCreateRequest(BaseModel):
    """로그 생성 요청"""
    level: str = "INFO"
    message: str
    category: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None


@router.get("/logs")
async def get_action_logs(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session)
):
    """
    동작 로그 조회 (Phase 2-1)
    autorun_logs 테이블에서 최신 로그를 조회하여 GlobalSummary에 표시
    """
    try:
        from ..models.blog import Blog

        result = await db.execute(
            select(AutorunLog)
            .where(
                AutorunLog.action != "queue_register",
                AutorunLog.message.notlike("%Celery 큐 등록%"),
            )
            .order_by(AutorunLog.created_at.desc())
            .offset(offset)
            .limit(limit + 1)
        )
        logs = result.scalars().all()

        has_more = len(logs) > limit
        if has_more:
            logs = logs[:limit]

        blog_platforms = {}

        async def get_platform_prefix(blog_name: str) -> str:
            """블로그 플랫폼 첫글자 약어 반환.

            Args:
                blog_name: 블로그 이름

            Returns:
                str: 플랫폼 약어 ("워", "구", "?" 등)
            """
            if not blog_name or blog_name == "-":
                return ""
            if blog_name not in blog_platforms:
                r = await db.execute(
                    select(Blog.platform).where(Blog.name == blog_name).limit(1)
                )
                row = r.scalar_one_or_none()
                if row:
                    pmap = {"wordpress": "워", "blogger": "구"}
                    # BlogPlatform(str, Enum) → Enum이든 문자열이든 안전하게 처리
                    platform_str = str(row.value if hasattr(row, 'value') else row).lower().strip()
                    blog_platforms[blog_name] = pmap.get(platform_str, "?")
                else:
                    blog_platforms[blog_name] = "?"
            return blog_platforms[blog_name]

        action_display = {
            "generate": "글/이미지 생성",
            "publish": "발행",
            "republish": "재발행",
            "collect": "제목 수집",
            "data": "데이터 이동",
            "flow_init": "플로우 초기화",
        }

        formatted = []
        for log in logs:
            prefix = await get_platform_prefix(log.blog_name)
            action_text = action_display.get(log.action, log.action)

            if log.status == "success":
                level = "SUCCESS"
                status_text = "성공"
            elif log.status == "skipped":
                level = "INFO"
                reason = log.message or "건너뜀"
                if len(reason) > 40:
                    reason = reason[:40] + "..."
                status_text = f"건너뜀({reason})"
            elif log.status == "failed":
                level = "ERROR"
                reason = log.message or "알 수 없음"
                if len(reason) > 40:
                    reason = reason[:40] + "..."
                status_text = f"실패({reason})"
            else:
                level = "WARN"
                status_text = log.status

            # 포스트 제목 (30자 초과 시 truncate)
            title_part = ""
            if log.post_title and log.post_title.strip():
                title_text = log.post_title.strip()
                if len(title_text) > 30:
                    title_text = title_text[:30] + "..."
                title_part = f" - {title_text}"

            if prefix and log.blog_name and log.blog_name != "-":
                # 플랫폼 뱃지용 대괄호 마커: [워] 또는 [구]
                msg = f"[{prefix}]{log.blog_name}{title_part} - {action_text} {status_text}"
            else:
                msg = f"{action_text}{title_part} - {status_text}"

            # 액션 타입 매핑
            action_type_map = {
                "generate": "generate", "publish": "publish",
                "republish": "republish", "collect": "collect", "data": "data",
            }
            action_type = action_type_map.get(log.action, "system")

            formatted.append({
                "id": log.id,
                "level": level,
                "message": msg,
                "action_type": action_type,
                "category": log.action,
                "resource_type": "autorun",
                "resource_id": log.flow_id,
                "timestamp": log.created_at.isoformat() if log.created_at else None,
            })

        return {"logs": formatted, "has_more": has_more}
    except Exception as e:
        logger.error(f"[DASHBOARD] logs 에러: {str(e)}")
        return {
            "logs": [],
            "has_more": False
        }


@router.post("/logs")
async def create_action_log(
    request: LogCreateRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    동작 로그 생성 (Phase 2-1)
    """
    try:
        log = ActionLog(
            level=request.level,
            message=request.message,
            category=request.category,
            resource_type=request.resource_type,
            resource_id=request.resource_id
        )
        db.add(log)
        await db.commit()
        await db.refresh(log)

        return {
            "success": True,
            "log_id": log.id
        }
    except Exception as e:
        logger.error(f"[DASHBOARD] log 생성 에러: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }
