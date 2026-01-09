"""
대시보드 API 라우터
- 글로벌 요약 통계
- 대시보드 상세 데이터
- 최근 활동 로그
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.blog import Blog, BlogPlatform
from ..models.module import Module
from ..models.flow import Flow

logger = get_logger("dashboard", "dashboard.log")

router = APIRouter(prefix="/dashboard", tags=["대시보드"])


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
    """
    try:
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        week_ago = today_start - timedelta(days=7)

        # 전체 카운트
        total_blogs = db.query(func.count(Blog.id)).scalar() or 0
        total_modules = db.query(func.count(Module.id)).scalar() or 0
        total_flows = db.query(func.count(Flow.id)).scalar() or 0

        # 활성 카운트
        active_blogs = db.query(func.count(Blog.id)).filter(
            Blog.is_active == True
        ).scalar() or 0

        active_flows = db.query(func.count(Flow.id)).filter(
            Flow.status == "active"
        ).scalar() or 0

        # 플랫폼별 블로그 수
        wordpress_count = db.query(func.count(Blog.id)).filter(
            Blog.platform == BlogPlatform.WORDPRESS
        ).scalar() or 0

        blogger_count = db.query(func.count(Blog.id)).filter(
            Blog.platform == BlogPlatform.BLOGGER
        ).scalar() or 0

        # 모듈 타입별 수
        module_stats = db.query(
            Module.module_type_id,
            func.count(Module.id)
        ).group_by(Module.module_type_id).all()

        module_by_type = {str(type_id): count for type_id, count in module_stats if type_id}

        # 이번 주 생성된 항목
        week_modules = db.query(func.count(Module.id)).filter(
            Module.created_at >= week_ago
        ).scalar() or 0

        week_flows = db.query(func.count(Flow.id)).filter(
            Flow.created_at >= week_ago
        ).scalar() or 0

        return {
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
            "modules_by_type": module_by_type,
            "week_created": {
                "modules": week_modules,
                "flows": week_flows
            }
        }
    except Exception as e:
        logger.error(f"[DASHBOARD] stats 에러: {str(e)}")
        return {
            "totals": {"blogs": 0, "modules": 0, "flows": 0},
            "active": {"blogs": 0, "flows": 0},
            "blogs_by_platform": {"wordpress": 0, "blogger": 0},
            "modules_by_type": {},
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
