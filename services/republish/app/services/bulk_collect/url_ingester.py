"""
대량 수집 모듈의 첫 사이클 URL 적재 로직.

`Module.settings.input_urls`를 읽어 URLClassifier + SitemapParser로 분류한 뒤
`CollectedUrl(source_module_id=module_id, title_fetch_status='pending')`로 적재한다.

외부 진입점: maybe_ingest_input_urls(db, module_id, settings, timebox)

4-2-B (lastmod_only_after_first):
    bulk_params.lastmod_only_after_first=True 일 때, 두 번째 사이클부터는
    sitemap.xml 의 <lastmod> 값을 직전 사이클에서 본 last_seen_lastmod 와
    비교하여 **새로 갱신된 글만** 적재한다.
    첫 사이클(_is_first_cycle=True)에는 기존과 동일하게 전수 적재한다.
    증분 적재 로직 본체는 `incremental_ingest.py` 에 분리.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bulk_collect_progress import BulkCollectProgress
from app.models.collected_url import CollectedUrl
from app.services.bulk_collect.incremental_ingest import (
    ingest_blog_url_incremental,
)
from app.services.bulk_collect.lastmod_tracker import LastmodTracker
from app.services.title_collect.sitemap import SitemapParser
from app.services.bulk_collect.timebox import Timebox
from app.services.bulk_collect.url_utils import (
    extract_domain_safe,
    guess_platform,
)
from app.services.url_classifier import URLClassifier

logger = logging.getLogger(__name__)

__all__ = ["maybe_ingest_input_urls"]


async def maybe_ingest_input_urls(
    db: AsyncSession,
    module_id: int,
    settings: dict,
    timebox: Timebox,
) -> Optional[dict]:
    """direct_input 모드일 때 input_urls 를 CollectedUrl 로 적재.

    동작 분기:
        - 첫 사이클: 기존과 동일하게 전수 적재.
        - 두 번째 사이클 이후 & lastmod_only_after_first=True:
          블로그 URL 의 sitemap lastmod 가 BulkCollectProgress.last_seen_lastmod
          이후인 글만 적재 (4-2-B).
        - 두 번째 사이클 이후 & lastmod_only_after_first=False: 스킵
          (기존 동작: 두 번째 사이클부터는 적재하지 않음).

    Returns:
        적재 통계 dict (skip 시 None).
    """
    mode = str(settings.get("url_source_mode", "from_collect_module"))
    if mode != "direct_input":
        return None

    input_urls = settings.get("input_urls") or []
    if not isinstance(input_urls, list) or not input_urls:
        return None

    is_first = await _is_first_cycle(db, module_id)
    bulk_params = settings.get("bulk_params", {}) or {}
    lastmod_only = bool(bulk_params.get("lastmod_only_after_first", False))

    # 두 번째 사이클 이후 & 증분 옵션 OFF → 기존 동작 유지 (스킵)
    if not is_first and not lastmod_only:
        return None

    logger.info(
        "[BULK_COLLECT:INGEST] 적재 시작 module=%s urls=%d "
        "first=%s lastmod_only=%s",
        module_id, len(input_urls), is_first, lastmod_only,
    )
    summary = await _ingest_input_urls(
        db=db,
        module_id=module_id,
        urls=input_urls,
        timebox=timebox,
        is_first_cycle=is_first,
        lastmod_only_after_first=lastmod_only,
    )
    _log_ingest_summary(module_id, summary)
    return summary


def _log_ingest_summary(module_id: int, summary: dict) -> None:
    """적재 결과 통계를 한 줄 로그로 남긴다."""
    logger.info(
        "[BULK_COLLECT:INGEST] 적재 완료 module=%s "
        "posts=%d blogs=%d dup=%d failed=%d unchanged=%d",
        module_id,
        summary.get("posts_ingested", 0),
        summary.get("blogs_processed", 0),
        summary.get("skipped_duplicate", 0),
        summary.get("failed", 0),
        summary.get("skipped_unchanged", 0),
    )


async def _is_first_cycle(db: AsyncSession, module_id: int) -> bool:
    """해당 모듈이 첫 사이클인지 BulkCollectProgress 로 판정.

    첫 사이클 조건 (이중 안전망): module_id row 가 없거나, 모든 row 의
    last_cycle_at IS NULL 이면 True.
    """
    try:
        result = await db.execute(
            select(BulkCollectProgress.last_cycle_at).where(
                BulkCollectProgress.module_id == module_id
            )
        )
        rows = list(result.scalars().all())
        if not rows:
            return True
        # 모든 row 의 last_cycle_at 가 NULL 이면 첫 사이클로 간주
        return all(r is None for r in rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[BULK_COLLECT:INGEST] _is_first_cycle 조회 실패 "
            "module=%s err=%s → 첫 사이클 아님으로 판단",
            module_id, exc,
        )
        return False


async def _ingest_input_urls(
    db: AsyncSession,
    module_id: int,
    urls: list,
    timebox: Timebox,
    is_first_cycle: bool = True,
    lastmod_only_after_first: bool = False,
) -> dict:
    """direct_input input_urls 를 CollectedUrl 로 적재.

    포스트 URL→직접 적재, 블로그 URL→사이트맵 추출 후 일괄 적재,
    불명→사이트맵 보강 후 분기.

    Args:
        is_first_cycle: 첫 사이클 여부.
        lastmod_only_after_first: 두 번째 사이클부터 증분 적재 옵션.

    Returns:
        {"posts_ingested", "blogs_processed", "skipped_duplicate", "failed"}
    """
    classifier = URLClassifier()
    sitemap_parser = SitemapParser()
    tracker = LastmodTracker(db)
    summary = {
        "posts_ingested": 0,
        "blogs_processed": 0,
        "skipped_duplicate": 0,
        "failed": 0,
        "skipped_unchanged": 0,
    }
    await _ingest_loop(
        db=db,
        module_id=module_id,
        urls=urls,
        classifier=classifier,
        sitemap_parser=sitemap_parser,
        tracker=tracker,
        summary=summary,
        timebox=timebox,
        is_first_cycle=is_first_cycle,
        lastmod_only_after_first=lastmod_only_after_first,
    )
    await _commit_ingest_safe(db, module_id)
    return summary


async def _ingest_loop(
    db: AsyncSession,
    module_id: int,
    urls: list,
    classifier: URLClassifier,
    sitemap_parser: SitemapParser,
    tracker: LastmodTracker,
    summary: dict,
    timebox: Timebox,
    is_first_cycle: bool,
    lastmod_only_after_first: bool,
) -> None:
    """URL 목록을 순회하며 적재 (타임박스 만료 시 즉시 중단)."""
    for raw_url in urls:
        if timebox.expired:
            logger.warning(
                "[BULK_COLLECT:INGEST] 타임박스 만료 → 적재 중단 "
                "module=%s 남은=%d",
                module_id, len(urls) - sum(summary.values()),
            )
            break
        url = (raw_url or "").strip()
        if not url:
            continue
        await _process_single_input_url(
            db=db,
            module_id=module_id,
            url=url,
            classifier=classifier,
            sitemap_parser=sitemap_parser,
            tracker=tracker,
            summary=summary,
            timebox=timebox,
            is_first_cycle=is_first_cycle,
            lastmod_only_after_first=lastmod_only_after_first,
        )


async def _process_single_input_url(
    db: AsyncSession,
    module_id: int,
    url: str,
    classifier: URLClassifier,
    sitemap_parser: SitemapParser,
    tracker: LastmodTracker,
    summary: dict,
    timebox: Timebox,
    is_first_cycle: bool,
    lastmod_only_after_first: bool,
) -> None:
    """단일 input URL 1건을 분류 후 post/blog 적재 경로로 분기."""
    try:
        kind = await _resolve_url_kind(classifier, url)
        if kind == "blog":
            await _ingest_blog_url(
                db=db,
                module_id=module_id,
                blog_url=url,
                sitemap_parser=sitemap_parser,
                tracker=tracker,
                summary=summary,
                timebox=timebox,
                is_first_cycle=is_first_cycle,
                lastmod_only_after_first=lastmod_only_after_first,
            )
        else:
            # post 또는 unknown → 포스트로 간주하여 직접 적재
            # (개별 포스트 URL 은 lastmod 비교 불가 → 첫 사이클에만 적재)
            if is_first_cycle:
                await _ingest_post_url(
                    db=db,
                    module_id=module_id,
                    post_url=url,
                    summary=summary,
                )
            else:
                summary["skipped_unchanged"] += 1
    except Exception as exc:  # noqa: BLE001
        summary["failed"] += 1
        logger.warning(
            "[BULK_COLLECT:INGEST] URL 처리 실패 url=%s err=%s",
            url, exc,
        )


async def _commit_ingest_safe(db: AsyncSession, module_id: int) -> None:
    """적재 결과를 분리 커밋 (실패 시 롤백, 사이클은 계속 진행)."""
    try:
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[BULK_COLLECT:INGEST] 적재 commit 실패 module=%s err=%s",
            module_id, exc,
        )
        await db.rollback()


async def _resolve_url_kind(classifier: URLClassifier, url: str) -> str:
    """URLClassifier 로 URL 종류를 결정 (unknown 은 사이트맵 보강).

    Returns: "post" | "blog" | "unknown".
    """
    cls = classifier.classify(url)
    if cls.kind != "unknown":
        return cls.kind

    # unknown → 사이트맵 존재 여부로 보강
    try:
        has_sitemap = await classifier.try_sitemap(url, timeout=5.0)
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "[BULK_COLLECT:INGEST] try_sitemap 실패 url=%s err=%s",
            url, exc,
        )
        has_sitemap = False

    return "blog" if has_sitemap else "post"


async def _ingest_post_url(
    db: AsyncSession,
    module_id: int,
    post_url: str,
    summary: dict,
) -> None:
    """단일 포스트 URL 을 CollectedUrl 로 적재 (중복 체크 포함)."""
    domain = extract_domain_safe(post_url)
    if not domain:
        summary["failed"] += 1
        logger.debug(
            "[BULK_COLLECT:INGEST] 도메인 추출 실패 url=%s", post_url,
        )
        return

    # 중복 체크: (url, source_module_id) UNIQUE
    existing = await db.execute(
        select(CollectedUrl.id).where(
            CollectedUrl.url == post_url,
            CollectedUrl.source_module_id == module_id,
        )
    )
    if existing.scalars().first() is not None:
        summary["skipped_duplicate"] += 1
        return

    row = CollectedUrl(
        url=post_url,
        domain=domain,
        platform=guess_platform(domain),
        source_module_id=module_id,
        title_fetch_status="pending",
        is_active=True,
    )
    db.add(row)
    summary["posts_ingested"] += 1


async def _ingest_blog_url_full_sitemap(
    db: AsyncSession,
    module_id: int,
    blog_url: str,
    domain: str,
    sitemap_parser: SitemapParser,
    summary: dict,
    timebox: Timebox,
) -> None:
    """기본 경로 — 사이트맵 전체를 적재 (첫 사이클 또는 증분 비활성)."""
    post_urls = await _fetch_sitemap_posts_safe(
        sitemap_parser, domain, summary,
    )
    if post_urls is None:
        return  # 사이트맵 파싱 자체가 실패 → summary['failed'] 이미 갱신됨
    if not post_urls:
        await _fallback_blog_to_post(
            db=db, module_id=module_id, blog_url=blog_url,
            domain=domain, summary=summary,
        )
        return

    summary["blogs_processed"] += 1
    logger.info(
        "[BULK_COLLECT:INGEST] 사이트맵 파싱 완료 domain=%s posts=%d",
        domain, len(post_urls),
    )
    await _ingest_blog_posts(
        db=db, module_id=module_id, domain=domain,
        post_urls=post_urls, summary=summary, timebox=timebox,
    )


async def _ingest_blog_url(
    db: AsyncSession,
    module_id: int,
    blog_url: str,
    sitemap_parser: SitemapParser,
    tracker: LastmodTracker,
    summary: dict,
    timebox: Timebox,
    is_first_cycle: bool,
    lastmod_only_after_first: bool,
) -> None:
    """블로그 루트 URL 의 사이트맵을 파싱해 포스트 URL 을 일괄 적재.

    4-2-B: 두 번째 사이클 + lastmod_only_after_first=True 일 때만
    BulkCollectProgress.last_seen_lastmod 와 비교해 새 글만 적재한다.
    """
    domain = _resolve_blog_domain(blog_url, summary)
    if not domain:
        return

    use_incremental = lastmod_only_after_first and not is_first_cycle

    if use_incremental:
        await ingest_blog_url_incremental(
            db=db, module_id=module_id, domain=domain,
            sitemap_parser=sitemap_parser, tracker=tracker,
            summary=summary, timebox=timebox,
            ingest_blog_posts_fn=_ingest_blog_posts,
        )
        return

    await _ingest_blog_url_full_sitemap(
        db=db, module_id=module_id, blog_url=blog_url, domain=domain,
        sitemap_parser=sitemap_parser, summary=summary, timebox=timebox,
    )




def _resolve_blog_domain(blog_url: str, summary: dict) -> str:
    """블로그 URL 에서 도메인 추출 (실패 시 summary['failed'] 증가)."""
    domain = extract_domain_safe(blog_url)
    if not domain:
        summary["failed"] += 1
        logger.debug(
            "[BULK_COLLECT:INGEST] blog 도메인 추출 실패 url=%s",
            blog_url,
        )
    return domain


async def _fallback_blog_to_post(
    db: AsyncSession,
    module_id: int,
    blog_url: str,
    domain: str,
    summary: dict,
) -> None:
    """사이트맵이 비어있으면 블로그 URL 자체를 포스트로 폴백 적재."""
    logger.warning(
        "[BULK_COLLECT:INGEST] 사이트맵 비어있음 domain=%s — "
        "blog_url 자체를 포스트로 폴백 적재",
        domain,
    )
    await _ingest_post_url(
        db=db,
        module_id=module_id,
        post_url=blog_url,
        summary=summary,
    )


async def _fetch_sitemap_posts_safe(
    sitemap_parser: SitemapParser,
    domain: str,
    summary: dict,
) -> Optional[list]:
    """사이트맵에서 포스트 URL 목록을 안전하게 가져온다 (실패 시 None)."""
    try:
        return await sitemap_parser.fetch_urls(domain, max_urls=None)
    except Exception as exc:  # noqa: BLE001
        summary["failed"] += 1
        logger.warning(
            "[BULK_COLLECT:INGEST] 사이트맵 파싱 실패 domain=%s err=%s",
            domain, exc,
        )
        return None


async def _ingest_blog_posts(
    db: AsyncSession,
    module_id: int,
    domain: str,
    post_urls: list,
    summary: dict,
    timebox: Timebox,
) -> None:
    """사이트맵에서 얻은 포스트 URL 들을 순차 적재 (타임박스 체크 포함)."""
    for post_url in post_urls:
        if timebox.expired:
            logger.warning(
                "[BULK_COLLECT:INGEST] 블로그 적재 중 타임박스 만료 "
                "domain=%s 처리=%d/%d",
                domain, summary["posts_ingested"], len(post_urls),
            )
            break
        try:
            await _ingest_post_url(
                db=db,
                module_id=module_id,
                post_url=post_url,
                summary=summary,
            )
        except Exception as exc:  # noqa: BLE001
            summary["failed"] += 1
            logger.debug(
                "[BULK_COLLECT:INGEST] 블로그 내 post 적재 실패 "
                "url=%s err=%s", post_url, exc,
            )


