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
