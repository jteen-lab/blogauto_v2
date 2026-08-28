"""검색 노출 주기 점검 Job — S2 사이트맵, S6 색인.

발행 시점에 처리하는 S1(IndexNow)과 달리, 사이트맵 반영과 색인은 시간이 지나야
확인할 수 있어 주기 실행이 필요하다.

- 사이트맵: 30분 간격. 블로그당 사이트맵 1회 fetch로 여러 URL을 한꺼번에 판정한다.
- 색인: 6시간 간격. 블로그별 일일 상한(index_check_daily_cap)을 넘지 않는다.
"""
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import db_manager
from ..core.logger import get_logger
from ..models.blog import Blog
from ..services.search_visibility import index_check_service, runner

logger = get_logger("search_visibility_job", "app.log")


async def _active_blogs(db: AsyncSession) -> List[Blog]:
    """점검 대상 블로그(활성)를 가져온다."""
    stmt = select(Blog).where(Blog.is_active.is_(True))
    return list((await db.execute(stmt)).scalars().all())


async def sitemap_check_job() -> None:
    """S2 — 블로그별 사이트맵 신선도 점검."""
    try:
        async with db_manager.get_session() as db:
            for blog in await _active_blogs(db):
                try:
                    result = await runner.run_sitemap_check(db, blog)
                    if result.get("missing"):
                        logger.warning(
                            "[SEARCH_VIS_JOB] 사이트맵 누락 | blog=%s | missing=%s | "
                            "lastmod=%s",
                            blog.name, result["missing"], result.get("latest_lastmod"),
                        )
                except Exception as exc:  # noqa: BLE001 — 한 블로그 실패가 전체를 막지 않는다
                    logger.warning(
                        "[SEARCH_VIS_JOB] 사이트맵 점검 실패 | blog=%s | %s",
                        blog.name, exc,
                    )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("[SEARCH_VIS_JOB] 사이트맵 Job 오류: %s", exc)


async def naver_index_check_job() -> None:
    """S6-N — 네이버 웹문서 검색으로 노출 여부 점검."""
    try:
        async with db_manager.get_session() as db:
            for blog in await _active_blogs(db):
                try:
                    result = await runner.run_naver_index_check(db, blog)
                    if result.get("checked"):
                        logger.info(
                            "[SEARCH_VIS_JOB] 네이버 점검 | blog=%s | %s",
                            blog.name, result,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[SEARCH_VIS_JOB] 네이버 점검 실패 | blog=%s | %s",
                        blog.name, exc,
                    )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("[SEARCH_VIS_JOB] 네이버 Job 오류: %s", exc)


async def index_check_job() -> None:
    """S6 — 블로그별 색인 상태 점검."""
    try:
        async with db_manager.get_session() as db:
            token = await runner.resolve_gsc_token(db)
            if not token:
                logger.info(
                    "[SEARCH_VIS_JOB] Search Console 미연동 → 색인 점검 건너뜀",
                )
                return

            try:
                sites = await index_check_service.list_sites(token)
            except index_check_service.IndexCheckError as exc:
                logger.error("[SEARCH_VIS_JOB] 속성 목록 조회 실패: %s", exc.message)
                return
            logger.info("[SEARCH_VIS_JOB] Search Console 속성 %d개", len(sites))

            for blog in await _active_blogs(db):
                try:
                    result = await runner.run_index_check(
                        db, blog, token=token, sites=sites,
                    )
                    if result.get("checked"):
                        logger.info(
                            "[SEARCH_VIS_JOB] 색인 점검 | blog=%s | %s",
                            blog.name, result,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[SEARCH_VIS_JOB] 색인 점검 실패 | blog=%s | %s",
                        blog.name, exc,
                    )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("[SEARCH_VIS_JOB] 색인 Job 오류: %s", exc)
