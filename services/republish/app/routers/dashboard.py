"""
대시보드 API 라우터
- 글로벌 요약 통계
- 대시보드 상세 데이터
- 최근 활동 로그
- 고정 요약탭 설정
"""
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from pydantic import BaseModel

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.blog import Blog, BlogPlatform
from ..models.module import Module
from ..models.module_type import ModuleType
from ..models.flow import Flow
from ..models.category import Topic, SubTopic, Keyword

logger = get_logger("dashboard", "dashboard.log")

router = APIRouter(prefix="/dashboard", tags=["대시보드"])


class PinnedTabsRequest(BaseModel):
    """고정 탭 설정 요청"""
    pinned_tabs: List[str]


@router.get("/summary")
async def get_dashboard_summary(db: Session = Depends(get_db_session)):
    """
    글로벌 요약 데이터 (헤더 요약탭용)
    """
    try:
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())

        # 활성 플로우 수 (status가 'active'인 플로우)
        active_flows = db.query(func.count(Flow.id)).filter(
            Flow.status == "active"
        ).scalar() or 0

        # 활성 블로그 수
        active_blogs = db.query(func.count(Blog.id)).filter(
            Blog.is_active == True
        ).scalar() or 0

        # 오늘 생성된 항목 수 (모듈 + 플로우 + 블로그)
        today_modules = db.query(func.count(Module.id)).filter(
            Module.created_at >= today_start
        ).scalar() or 0

        today_flows = db.query(func.count(Flow.id)).filter(
            Flow.created_at >= today_start
        ).scalar() or 0

        today_blogs = db.query(func.count(Blog.id)).filter(
            Blog.created_at >= today_start
        ).scalar() or 0

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
async def get_dashboard_stats(db: Session = Depends(get_db_session)):
    """
    대시보드 상세 통계 (패널 확장 시)
    22개 요약탭 전체 카운팅 제공
    """
    try:
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        week_ago = today_start - timedelta(days=7)

        # === 블로그 관련 ===
        total_blogs = db.query(func.count(Blog.id)).scalar() or 0
        active_blogs = db.query(func.count(Blog.id)).filter(
            Blog.is_active == True
        ).scalar() or 0
        inactive_blogs = total_blogs - active_blogs

        wordpress_count = db.query(func.count(Blog.id)).filter(
            Blog.platform == BlogPlatform.WORDPRESS
        ).scalar() or 0
        blogger_count = db.query(func.count(Blog.id)).filter(
            Blog.platform == BlogPlatform.BLOGGER
        ).scalar() or 0

        # === 카테고리 관련 ===
        total_topics = db.query(func.count(Topic.id)).filter(
            Topic.is_deleted == False
        ).scalar() or 0
        total_subtopics = db.query(func.count(SubTopic.id)).filter(
            SubTopic.is_deleted == False
        ).scalar() or 0
        total_keywords = db.query(func.count(Keyword.id)).filter(
            Keyword.is_deleted == False
        ).scalar() or 0

        # === 모듈 관련 ===
        total_modules = db.query(func.count(Module.id)).scalar() or 0

        # 모듈 타입별 카운트 (code 기준)
        module_type_stats = db.query(
            ModuleType.code,
            func.count(Module.id)
        ).join(Module, Module.module_type_id == ModuleType.id).group_by(
            ModuleType.code
        ).all()
        module_by_code = {code: count for code, count in module_type_stats}

        prompt_modules = module_by_code.get("prompt", 0)
        generate_modules = module_by_code.get("generate", 0)
        publish_modules = module_by_code.get("publish", 0)
        republish_modules = module_by_code.get("republish", 0)

        # === 플로우 관련 ===
        total_flows = db.query(func.count(Flow.id)).scalar() or 0
        active_flows = db.query(func.count(Flow.id)).filter(
            Flow.status == "active"
        ).scalar() or 0
        inactive_flows = total_flows - active_flows

        # === 이번 주 통계 ===
        week_modules = db.query(func.count(Module.id)).filter(
            Module.created_at >= week_ago
        ).scalar() or 0
        week_flows = db.query(func.count(Flow.id)).filter(
            Flow.created_at >= week_ago
        ).scalar() or 0

        # 이번 주 생성/발행/재발행 (임시: 모듈 생성 기준)
        week_generate = db.query(func.count(Module.id)).join(
            ModuleType, Module.module_type_id == ModuleType.id
        ).filter(
            ModuleType.code == "generate",
            Module.created_at >= week_ago
        ).scalar() or 0

        week_publish = db.query(func.count(Module.id)).join(
            ModuleType, Module.module_type_id == ModuleType.id
        ).filter(
            ModuleType.code == "publish",
            Module.created_at >= week_ago
        ).scalar() or 0

        week_republish = db.query(func.count(Module.id)).join(
            ModuleType, Module.module_type_id == ModuleType.id
        ).filter(
            ModuleType.code == "republish",
            Module.created_at >= week_ago
        ).scalar() or 0

        # === 오늘 통계 ===
        today_modules = db.query(func.count(Module.id)).filter(
            Module.created_at >= today_start
        ).scalar() or 0

        today_generate = db.query(func.count(Module.id)).join(
            ModuleType, Module.module_type_id == ModuleType.id
        ).filter(
            ModuleType.code == "generate",
            Module.created_at >= today_start
        ).scalar() or 0

        today_publish = db.query(func.count(Module.id)).join(
            ModuleType, Module.module_type_id == ModuleType.id
        ).filter(
            ModuleType.code == "publish",
            Module.created_at >= today_start
        ).scalar() or 0

        today_republish = db.query(func.count(Module.id)).join(
            ModuleType, Module.module_type_id == ModuleType.id
        ).filter(
            ModuleType.code == "republish",
            Module.created_at >= today_start
        ).scalar() or 0

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
                "modules": week_modules,
                "flows": week_flows
            }
        }
    except Exception as e:
        logger.error(f"[DASHBOARD] stats 에러: {str(e)}")
        return {
            "total_blogs": 0, "wordpress": 0, "blogger": 0,
            "active_blogs": 0, "inactive_blogs": 0,
            "topics": 0, "subtopics": 0, "keywords": 0,
            "total_modules": 0, "prompt_modules": 0, "generate_modules": 0,
            "publish_modules": 0, "republish_modules": 0,
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
    db: Session = Depends(get_db_session)
):
    """
    최근 활동 로그
    """
    try:
        activities = []

        # 최근 블로그 (platform을 문자열로 변환)
        recent_blogs = db.query(Blog).order_by(
            Blog.created_at.desc()
        ).limit(5).all()

        for blog in recent_blogs:
            platform_str = blog.platform.value if blog.platform else None
            activities.append({
                "type": "blog",
                "action": "created",
                "name": blog.name,
                "platform": platform_str,
                "timestamp": blog.created_at.isoformat() if blog.created_at else None
            })

        # 최근 모듈 (joinedload로 module_type 미리 로드)
        recent_modules = db.query(Module).options(
            joinedload(Module.module_type)
        ).order_by(
            Module.created_at.desc()
        ).limit(5).all()

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
        recent_flows = db.query(Flow).order_by(
            Flow.created_at.desc()
        ).limit(5).all()

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
