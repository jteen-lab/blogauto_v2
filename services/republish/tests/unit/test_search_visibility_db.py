"""검색 노출 원장 DB 로직 테스트 (SQLite 인메모리).

실제 AsyncSession 위에서 멱등 upsert·결과 반영·집계를 검증한다.
PostgreSQL 전용 타입(JSONB)은 SQLite 컴파일 규칙으로 대체한다.
"""
import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base
from app.models.blog import Blog, BlogPlatform
from app.models.search_visibility import (
    IN_FAILED, IN_OK, IN_SKIPPED, IX_INDEXED, IX_UNKNOWN, SM_MISSING,
    SearchVisibilityUrl,
)
from app.models.user import User
from app.services.search_visibility import runner, tracker
from app.services.search_visibility.indexnow_service import SubmitOutcome


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # noqa: D103 — 테스트 전용 shim
    return "JSON"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def blog(db):
    user = User(email="t@example.com", full_name="테스터", hashed_password="x")
    db.add(user)
    await db.flush()
    item = Blog(
        user_id=user.id, name="테스트블로그", url="https://example.com",
        platform=BlogPlatform.WORDPRESS,
    )
    db.add(item)
    await db.flush()
    return item


@pytest.mark.asyncio
async def test_get_or_create_row_is_idempotent(db, blog):
    """같은 (blog, url) 은 행을 새로 만들지 않는다 — 재발행 대비."""
    first = await tracker.get_or_create_row(
        db, blog.id, "https://example.com/1/", crawled_post_id=None, title="가",
    )
    second = await tracker.get_or_create_row(db, blog.id, "https://example.com/1/")
    assert first.id == second.id


@pytest.mark.asyncio
async def test_get_or_create_row_backfills_title(db, blog):
    row = await tracker.get_or_create_row(db, blog.id, "https://example.com/1/")
    assert row.title is None
    again = await tracker.get_or_create_row(
        db, blog.id, "https://example.com/1/", title="나중에 채움",
    )
    assert again.title == "나중에 채움"


@pytest.mark.asyncio
async def test_apply_outcome_ok(db, blog):
    row = await tracker.get_or_create_row(db, blog.id, "https://example.com/1/")
    tracker._apply_outcome(row, SubmitOutcome(submitted=True, status_code=200))
    assert row.indexnow_status == IN_OK
    assert row.indexnow_submitted_at is not None


@pytest.mark.asyncio
async def test_apply_outcome_skip_keeps_no_timestamp(db, blog):
    """제출을 시도조차 안 한 경우는 skipped 이며 제출 시각을 남기지 않는다."""
    row = await tracker.get_or_create_row(db, blog.id, "https://example.com/1/")
    tracker._apply_outcome(row, SubmitOutcome(submitted=False, error="disabled"))
    assert row.indexnow_status == IN_SKIPPED
    assert row.indexnow_submitted_at is None
    assert row.indexnow_attempts == 0


@pytest.mark.asyncio
async def test_apply_outcome_failure_counts_attempt(db, blog):
    row = await tracker.get_or_create_row(db, blog.id, "https://example.com/1/")
    tracker._apply_outcome(
        row, SubmitOutcome(submitted=False, status_code=429, retryable=True),
    )
    assert row.indexnow_status == IN_FAILED
    assert row.indexnow_attempts == 1


@pytest.mark.asyncio
async def test_invalidate_key_verification_clears_flag(blog):
    blog.search_index_config = {
        "indexnow_key": "k", "indexnow_key_verified": True, "indexnow_enabled": True,
    }
    tracker.invalidate_key_verification(blog, "403 — 키 파일 없음")
    assert blog.search_index_config["indexnow_key_verified"] is False
    assert "403" in blog.search_index_config["indexnow_key_error"]


@pytest.mark.asyncio
async def test_blog_summary_counts_and_rate(db, blog):
    """색인율은 '확인된 것' 기준이어야 한다 — 미확인을 분모에 넣으면 과소평가된다."""
    for idx in range(4):
        await tracker.get_or_create_row(db, blog.id, f"https://example.com/{idx}/")
    rows = (await db.execute(
        SearchVisibilityUrl.__table__.select(),
    )).fetchall()
    assert len(rows) == 4

    items = (await db.execute(
        __import__("sqlalchemy").select(SearchVisibilityUrl),
    )).scalars().all()
    items[0].index_state = IX_INDEXED
    items[1].index_state = IX_INDEXED
    items[2].index_state = "not_indexed"
    items[3].index_state = IX_UNKNOWN
    items[3].sitemap_state = SM_MISSING
    await db.flush()

    summary = await runner.blog_summary(db, blog.id)
    assert summary["total"] == 4
    assert summary["indexed"] == 2
    assert summary["index_checked"] == 3
    assert summary["index_rate"] == pytest.approx(66.7)
    assert summary["sitemap_missing"] == 1


@pytest.mark.asyncio
async def test_blog_summary_rate_is_none_without_checks(db, blog):
    await tracker.get_or_create_row(db, blog.id, "https://example.com/1/")
    summary = await runner.blog_summary(db, blog.id)
    assert summary["index_rate"] is None


@pytest.mark.asyncio
async def test_track_published_url_skips_when_disabled(db, blog):
    """기본 설정(IndexNow off)에서는 원장에 남되 제출은 하지 않는다."""
    row = await tracker.track_published_url(
        db, blog, "https://example.com/9/", title="제목",
    )
    assert row is not None
    assert row.indexnow_status == IN_SKIPPED
    assert row.indexnow_error == "disabled"


@pytest.mark.asyncio
async def test_track_published_url_ignores_empty_url(db, blog):
    assert await tracker.track_published_url(db, blog, "") is None


# ---------- 백필 ----------

@pytest_asyncio.fixture
async def posts(db, blog):
    """발행 완료 글 5건 + 미발행 1건 + URL 없는 1건."""
    from datetime import datetime, timedelta

    from app.models.crawled_post import CrawledPost

    items = []
    for i in range(5):
        items.append(CrawledPost(
            blog_id=blog.id, title=f"글{i}", url=f"https://example.com/{i}/",
            published_at=datetime.now() - timedelta(days=i),
        ))
    items.append(CrawledPost(blog_id=blog.id, title="미발행", url=None))
    items.append(CrawledPost(
        blog_id=blog.id, title="URL없음", url=None,
        published_at=datetime.now(),
    ))
    for item in items:
        db.add(item)
    await db.flush()
    return items


@pytest.mark.asyncio
async def test_backfill_creates_rows_for_published_only(db, blog, posts):
    from app.services.search_visibility import backfill

    result = await backfill.backfill_blog(db, blog.id, limit=100)
    assert result["scanned"] == 5  # 미발행·URL없음 제외
    assert result["created"] == 5


@pytest.mark.asyncio
async def test_backfill_is_idempotent(db, blog, posts):
    """두 번 돌려도 중복 행이 생기지 않는다."""
    from app.services.search_visibility import backfill

    await backfill.backfill_blog(db, blog.id, limit=100)
    second = await backfill.backfill_blog(db, blog.id, limit=100)
    assert second["created"] == 0
    assert second["existing"] == 5


@pytest.mark.asyncio
async def test_backfill_does_not_submit_indexnow(db, blog, posts):
    """기존 발행분을 IndexNow 로 재제출하면 스팸이 된다 — skipped 로 표시."""
    import sqlalchemy

    from app.services.search_visibility import backfill

    await backfill.backfill_blog(db, blog.id, limit=100)
    rows = (await db.execute(
        sqlalchemy.select(SearchVisibilityUrl),
    )).scalars().all()
    assert all(r.indexnow_status == IN_SKIPPED for r in rows)
    assert all(r.indexnow_error == backfill.REASON for r in rows)


@pytest.mark.asyncio
async def test_backfill_respects_limit_newest_first(db, blog, posts):
    from app.services.search_visibility import backfill

    result = await backfill.backfill_blog(db, blog.id, limit=2)
    assert result["created"] == 2
    import sqlalchemy
    urls = set((await db.execute(
        sqlalchemy.select(SearchVisibilityUrl.url),
    )).scalars().all())
    # 최근 2건 = 글0(오늘), 글1(어제)
    assert urls == {"https://example.com/0/", "https://example.com/1/"}


@pytest.mark.asyncio
async def test_backfill_caps_absurd_limit(db, blog, posts):
    from app.services.search_visibility import backfill

    result = await backfill.backfill_blog(db, blog.id, limit=999999)
    assert result["scanned"] == 5


@pytest.mark.asyncio
async def test_backfill_preserves_aware_published_at(db, blog):
    """운영 DB의 published_at 은 aware 다 — 그대로 복사돼야 한다."""
    from datetime import datetime, timedelta, timezone

    from app.models.crawled_post import CrawledPost
    from app.services.search_visibility import backfill

    when = datetime.now(timezone.utc) - timedelta(days=1)
    db.add(CrawledPost(
        blog_id=blog.id, title="aware 글", url="https://example.com/aware/",
        published_at=when,
    ))
    await db.flush()

    result = await backfill.backfill_blog(db, blog.id, limit=10)
    assert result["created"] == 1

    import sqlalchemy
    row = (await db.execute(
        sqlalchemy.select(SearchVisibilityUrl).where(
            SearchVisibilityUrl.url == "https://example.com/aware/",
        ),
    )).scalar_one()
    assert row.published_at is not None


@pytest.mark.asyncio
async def test_track_published_url_sets_aware_timestamp(db, blog):
    row = await tracker.track_published_url(db, blog, "https://example.com/tz/")
    assert row.published_at.tzinfo is not None


@pytest.mark.asyncio
async def test_index_check_reports_remaining_when_not_connected(db, blog):
    """미연동이면 조용히 0건 성공으로 위장하지 않는다."""
    from app.services.search_visibility import runner

    result = await runner.run_index_check(db, blog)
    assert result["skipped"] == "gsc_not_connected"


@pytest.mark.asyncio
async def test_index_check_skips_when_disabled(db, blog):
    from app.services.search_visibility import runner

    blog.search_index_config = {"index_check_enabled": False}
    result = await runner.run_index_check(db, blog)
    assert result["skipped"] == "disabled"
