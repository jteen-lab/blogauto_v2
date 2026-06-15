"""
통합 동작로그 API

AutorunLog 테이블에서 플로우 실행 로그를 통합 조회합니다.
로그 바(/logs)와 동일한 데이터 소스를 사용하여 일관성을 유지합니다.
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.autorun_log import AutorunLog
from ..models.blog import Blog

logger = get_logger("dashboard_logs", "dashboard.log")

router = APIRouter(prefix="/dashboard", tags=["통합 로그"])

# 플랫폼 뱃지 정규식 (예: [워], [구], [티])
_BADGE_RE = re.compile(r"^\[(.)\]")

# 액션 표시 텍스트 매핑
_ACTION_DISPLAY = {
    "generate": "글/이미지 생성",
    "publish": "발행",
    "republish": "재발행",
    "collect": "제목 수집",
    "bulk_collect": "대량 수집",
    "data": "데이터 이동",
    "flow_init": "플로우 초기화",
    "queue_register": "워커 등록",
}


@router.get("/unified-logs")
async def get_unified_logs(
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    log_type: str = Query(default="all"),
    level: str = Query(default="all"),
    search: str = Query(default=""),
    blog_name: str = Query(default=""),
    action_type: str = Query(default=""),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """통합 동작로그 조회.

    AutorunLog 테이블에서 조회하여 로그 바(/logs)와 동일한 데이터를 표시합니다.

    Args:
        limit: 조회 건수 (1~200).
        offset: 시작 위치.
        log_type: "all"|"action"|"activity"|"generation" (탭 분류).
        level: "all"|"INFO"|"SUCCESS"|"WARN"|"ERROR".
        search: 메시지 검색어.
        blog_name: 특정 블로그명으로 필터 (빈 값이면 전체).
        action_type: 단일 액션 필터 "publish"|"republish"|"generate"|"collect"|
                     "bulk_collect"|"data"|"queue_register"|"queue_publish"|
                     "queue_republish"|"queue_generate".
                     queue_* 는 queue_register 중 발행/재발행/생성 종류 분리용.
        db: DB 세션.

    Returns:
        logs 목록, total 건수, has_more 여부.
    """
    try:
        # 기본 쿼리 (activity 필터 시 Celery 큐 등록 메시지 포함)
        query = select(AutorunLog).order_by(AutorunLog.created_at.desc())
        count_query = select(func.count(AutorunLog.id))

        # 작업/생성 탭에서만 워커 등록 로그 제외 (전체/활동 탭에서는 포함)
        if log_type in ("action", "generation"):
            from sqlalchemy import and_
            celery_filter = and_(
                AutorunLog.action != "queue_register",
                AutorunLog.message.notlike("%Celery 큐 등록%"),
            )
            query = query.where(celery_filter)
            count_query = count_query.where(celery_filter)

        # 필터 조건 적용 (탭/레벨/검색어)
        query, count_query = _apply_filters(
            query, count_query, log_type, level, search
        )

        # 블로그 필터 (빈 문자열이면 적용 안 함)
        if blog_name and blog_name.strip():
            query = query.where(AutorunLog.blog_name == blog_name.strip())
            count_query = count_query.where(
                AutorunLog.blog_name == blog_name.strip()
            )

        # 액션 타입 필터: 발행/재발행/생성 세분화 + queue_* 분리 검색
        if action_type:
            query, count_query = _apply_action_type_filter(
                query, count_query, action_type,
            )

        # 총 건수 조회
        total_result = await db.execute(count_query)
        total: int = total_result.scalar() or 0

        # 페이지네이션 적용 및 조회
        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        logs = result.scalars().all()

        # 블로그 플랫폼 캐시
        blog_platforms: dict[str, str] = {}

        formatted = []
        for log in logs:
            serialized = await _serialize_autorun_log(log, db, blog_platforms)
            formatted.append(serialized)

        return {
            "logs": formatted,
            "total": total,
            "has_more": (offset + limit) < total,
        }
    except Exception as e:
        logger.error(f"[UNIFIED_LOGS] 조회 실패: {e}")
        return {"logs": [], "total": 0, "has_more": False}


@router.get("/unified-logs/blog-list")
async def get_log_blog_list(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """동작 로그 검색용 블로그 목록.

    AutorunLog에 등장한 distinct blog_name을 반환한다.
    드롭다운 위젯에서 사용한다.

    Returns:
        {"blogs": ["수작남", "라이프인포", ...]}
    """
    try:
        result = await db.execute(
            select(AutorunLog.blog_name)
            .where(
                AutorunLog.blog_name.isnot(None),
                AutorunLog.blog_name != "",
                AutorunLog.blog_name != "-",
            )
            .distinct()
            .order_by(AutorunLog.blog_name.asc())
        )
        blogs = [row[0] for row in result.all() if row[0]]
        return {"blogs": blogs}
    except Exception as e:
        logger.warning(f"[UNIFIED_LOGS] 블로그 목록 실패: {e}")
        return {"blogs": []}


def _apply_action_type_filter(
    query, count_query, action_type: str,
) -> tuple:
    """단일 액션 타입 또는 queue_register 세분화 필터.

    action_type 값:
      - publish/republish/generate/collect: 단일 action 필터
      - queue_publish/queue_republish/queue_generate: queue_register 중 메시지 패턴 분리
    """
    queue_kind_map = {
        "queue_publish": "%발행 등록%",
        "queue_republish": "%재발행 등록%",
        "queue_generate": "%생성 등록%",
    }
    if action_type in queue_kind_map:
        pattern = queue_kind_map[action_type]
        query = query.where(
            AutorunLog.action == "queue_register",
            AutorunLog.message.like(pattern),
        )
        count_query = count_query.where(
            AutorunLog.action == "queue_register",
            AutorunLog.message.like(pattern),
        )
    elif action_type in (
        "publish", "republish", "generate", "collect",
        "bulk_collect", "data", "queue_register",
    ):
        query = query.where(AutorunLog.action == action_type)
        count_query = count_query.where(AutorunLog.action == action_type)
    return query, count_query


def _apply_filters(
    query, count_query, log_type: str, level: str, search: str,
) -> tuple:
    """쿼리에 레벨/카테고리/검색어 필터를 적용합니다."""
    # 레벨 필터 (AutorunLog.status → level 매핑)
    if level == "SUCCESS":
        query = query.where(AutorunLog.status == "success")
        count_query = count_query.where(AutorunLog.status == "success")
    elif level == "ERROR":
        query = query.where(AutorunLog.status == "failed")
        count_query = count_query.where(AutorunLog.status == "failed")
    elif level == "INFO":
        query = query.where(AutorunLog.status == "skipped")
        count_query = count_query.where(AutorunLog.status == "skipped")
    elif level == "WARN":
        query = query.where(AutorunLog.status == "warning")
        count_query = count_query.where(AutorunLog.status == "warning")

    # 카테고리 필터 (log_type → AutorunLog.action 매핑)
    # - action(작업): 모듈 실행 관련 (generate, publish, republish, collect, bulk_collect)
    # - activity(활동): 시스템 이벤트 (플로우 상태 변경, 블로그 변경 등 작업 외 모든 이벤트)
    # - generation(생성): 생성 전용 (generate만)
    if log_type == "action":
        query = query.where(
            AutorunLog.action.in_(
                ["generate", "publish", "republish", "collect", "bulk_collect"]
            )
        )
        count_query = count_query.where(
            AutorunLog.action.in_(
                ["generate", "publish", "republish", "collect", "bulk_collect"]
            )
        )
    elif log_type == "activity":
        # 활동: 시스템 이벤트 + 워커 등록 로그
        from sqlalchemy import or_
        activity_filter = or_(
            AutorunLog.action.notin_(
                ["generate", "publish", "republish", "collect", "bulk_collect"]
            ),
            AutorunLog.action == "queue_register",
        )
        query = query.where(activity_filter)
        count_query = count_query.where(activity_filter)
    elif log_type == "generation":
        query = query.where(AutorunLog.action == "generate")
        count_query = count_query.where(AutorunLog.action == "generate")

    # 메시지 검색 필터 (blog_name, post_title, message 대상)
    if search:
        pattern = f"%{search}%"
        search_filter = (
            AutorunLog.blog_name.ilike(pattern)
            | AutorunLog.post_title.ilike(pattern)
            | AutorunLog.message.ilike(pattern)
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    return query, count_query


async def _get_platform_prefix(
    blog_name: str,
    db: AsyncSession,
    cache: dict[str, str],
) -> str:
    """블로그 플랫폼 첫글자 약어 반환.

    Args:
        blog_name: 블로그 이름.
        db: DB 세션.
        cache: 플랫폼 캐시.

    Returns:
        str: 플랫폼 약어 ("워", "구", "?" 등).
    """
    if not blog_name or blog_name == "-":
        return ""
    if blog_name not in cache:
        r = await db.execute(
            select(Blog.platform).where(Blog.name == blog_name).limit(1)
        )
        row = r.scalar_one_or_none()
        if row:
            pmap = {"wordpress": "워", "blogger": "구"}
            platform_str = str(
                row.value if hasattr(row, "value") else row
            ).lower().strip()
            cache[blog_name] = pmap.get(platform_str, "?")
        else:
            cache[blog_name] = "?"
    return cache[blog_name]


async def _serialize_autorun_log(
    log: AutorunLog,
    db: AsyncSession,
    blog_platforms: dict[str, str],
) -> dict:
    """AutorunLog를 통합 로그 응답 형식으로 변환합니다.

    /logs 엔드포인트와 동일한 메시지 포맷을 사용합니다.

    Args:
        log: AutorunLog 엔트리.
        db: DB 세션.
        blog_platforms: 플랫폼 캐시.

    Returns:
        직렬화된 로그 딕셔너리.
    """
    prefix = await _get_platform_prefix(log.blog_name, db, blog_platforms)
    action_text = _ACTION_DISPLAY.get(log.action, log.action)

    # 상태 → 레벨/텍스트 변환
    if log.status == "success":
        level = "SUCCESS"
        status_text = "성공"
        # 수집/대량수집 성공 로그는 "성공" 대신 건수 요약(message)을 노출.
        # 예) "제목 152개, 키워드/URL 20개 수집 (소스 2개)".
        # 기존에는 message 를 버리고 "제목 수집 - 성공" 만 표시해
        # 몇 개를 수집했는지 사용자가 알 수 없었다.
        if log.action in ("collect", "bulk_collect") and log.message:
            status_text = log.message.strip()
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
        status_text = log.status or ""

    # 큐 등록 로그는 작업 시작 단계이므로 INFO 레벨로 표시.
    # SUCCESS는 워커가 작업을 완료한 시점에만 별도 로그로 남도록 분리한다.
    if log.action == "queue_register" and log.status == "success":
        level = "INFO"

    # 포스트 제목 (30자 초과 시 truncate)
    title_part = ""
    if log.post_title and log.post_title.strip():
        title_text = log.post_title.strip()
        if len(title_text) > 30:
            title_text = title_text[:30] + "..."
        title_part = f" - {title_text}"

    # 메시지 포맷
    # queue_register는 백엔드(_save_autorun_log)에서 이미 완성된 메시지를 message에 저장.
    # "[블로그명] - [글제목] - [워커종류] 등록 완료/실패" 그대로 사용.
    if log.action == "queue_register":
        raw = (log.message or "").strip()
        if not raw:
            raw = f"{log.blog_name or ''} - {action_text} {status_text}"
        if prefix and log.blog_name and log.blog_name != "-":
            title = f"[{prefix}]{raw}"
        else:
            title = raw
    elif prefix and log.blog_name and log.blog_name != "-":
        title = f"[{prefix}]{log.blog_name}{title_part} - {action_text} {status_text}"
    else:
        title = f"{action_text}{title_part} - {status_text}"

    platform: Optional[str] = None
    badge_match = _BADGE_RE.match(title)
    if badge_match:
        platform = badge_match.group(1)

    return {
        "id": f"action_{log.id}",
        "type": "action",
        "action_type": _get_action_type(log.action),
        "timestamp": log.created_at.isoformat() if log.created_at else None,
        "level": level,
        "title": title,
        "detail": "",
        "platform": platform,
        "metadata": {
            "category": log.action,
            "resource_type": "autorun",
            "resource_id": log.flow_id,
        },
    }


def _get_action_type(action: str) -> str:
    """AutorunLog.action을 UI 액션 타입으로 변환합니다."""
    if action in ("generate",):
        return "generate"
    if action in ("publish",):
        return "publish"
    if action in ("republish",):
        return "republish"
    if action in ("collect",):
        return "collect"
    if action in ("bulk_collect",):
        return "bulk_collect"
    if action in ("data",):
        return "data"
    if action in ("queue_register",):
        return "queue_register"
    return "system"
