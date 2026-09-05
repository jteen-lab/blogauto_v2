"""유입 수집 Job — 하루 한 번.

GA4·서치콘솔 모두 최근 며칠치를 **나중에 보정한다.** 그래서 어제 것만
받아 오지 않고 28일 창을 통째로 다시 읽어 덮어쓴다. 하루 한 번이면
할당량에도 여유가 크다(무료 속성 20만 토큰/일 중 1% 미만).

계획서: docs/plans/analytics_integration_plan.md §4
"""
from ..core.database import db_manager
from ..core.logger import get_logger

logger = get_logger("analytics_job", "app.log")


async def collect_analytics_job() -> None:
    """활성 블로그의 유입을 모아 적재한다."""
    try:
        async with db_manager.get_session() as db:
            result = await collect_safely(db)
        logger.info("[ANALYTICS_JOB] 완료 | 블로그 %s | 행 %s",
                    result.get("blogs"), result.get("rows"))
    except Exception as e:  # noqa: BLE001 — 잡이 죽으면 다음 회차도 안 돈다
        logger.error("[ANALYTICS_JOB] 실패 | %s", e, exc_info=True)


async def collect_safely(db) -> dict:
    """연결이 하나도 없으면 조용히 넘어간다.

    미연동 상태에서 매일 오류 로그를 쌓으면 진짜 오류가 묻힌다.
    """
    from ..services.analytics.collector import collect_all
    from ..services.analytics.ga4_client import resolve_token
    from ..services.search_visibility.runner import resolve_gsc_token

    if not await resolve_token(db) and not await resolve_gsc_token(db):
        logger.info("[ANALYTICS_JOB] GA4·서치콘솔 모두 미연결 — 건너뜀")
        return {"blogs": 0, "rows": 0, "skipped": "미연결"}
    return await collect_all(db)
