"""색인률을 발행량에 되먹인다 (2026-08-30).

12개 블로그가 전부 구글 색인 0건인데 하루 30개씩 발행하고 있었다. 색인 점검
기능은 있었지만 결과가 발행 결정에 반영되지 않아, 크롤 수요가 죽은 사이트에
색인 안 되는 URL 만 쌓였다.

진단: docs/plans/search_visibility_all_blogs.md
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base
from app.models.blog import Blog, BlogPlatform
from app.models.search_visibility import SearchVisibilityUrl
from app.models.user import User
from app.services.generation.index_feedback import (
    CAP_POOR,
    MIN_SAMPLE,
    STOP_AFTER_DAYS,
    IndexFeedback,
    _verdict,
)


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
    user = User(email="t@example.com", full_name="t", hashed_password="x")
    db.add(user)
    await db.flush()
    b = Blog(user_id=user.id, name="테스트", url="https://x.com",
             platform=BlogPlatform.WORDPRESS)
    db.add(b)
    await db.flush()
    return b


async def _urls(db, blog, total, indexed, days_ago=10):
    pub = datetime.now(timezone.utc) - timedelta(days=days_ago)
    for i in range(total):
        db.add(SearchVisibilityUrl(
            blog_id=blog.id, url=f"https://x.com/{i}/",
            published_at=pub,
            index_state="indexed" if i < indexed else "not_indexed",
        ))
    await db.flush()


# ── 판정 규칙 ────────────────────────────────────────────
def test_small_sample_does_not_block():
    """새 블로그는 점검 이력이 없다 — 그걸로 막으면 시작조차 못 한다."""
    v = _verdict(MIN_SAMPLE - 1, 0, 10, 4)
    assert v.cap is None and v.stop is False
    assert "표본 부족" in v.reason


def test_healthy_ratio_no_cap():
    v = _verdict(20, 10, 10, 4)
    assert v.cap is None and v.stop is False


def test_weak_ratio_halves_output():
    """10~30% 는 절반으로 줄인다."""
    v = _verdict(20, 4, 10, 4)      # 20%
    assert v.cap == 2 and v.stop is False


def test_weak_ratio_never_goes_below_one():
    """절반이 0이 되면 발행이 멈춘다 — 최소 1개는 남긴다."""
    v = _verdict(20, 4, 10, 1)
    assert v.cap == 1


def test_poor_ratio_caps_to_one():
    v = _verdict(20, 1, 10, 8)      # 5%
    assert v.cap == CAP_POOR and v.stop is False


def test_zero_recent_is_capped_not_stopped():
    """색인 0이어도 기간이 짧으면 기다려 본다."""
    v = _verdict(20, 0, STOP_AFTER_DAYS - 1, 4)
    assert v.stop is False and v.cap == CAP_POOR


def test_zero_for_long_stops_generation():
    """오래 0이면 멈춘다. 계속 찍으면 신호가 더 나빠진다."""
    v = _verdict(20, 0, STOP_AFTER_DAYS + 5, 4)
    assert v.stop is True
    assert "품질 점검" in v.reason


def test_reason_always_present():
    """막을 때 이유가 없으면 고장과 구분되지 않는다."""
    for args in ((3, 0, 5, 4), (20, 10, 5, 4), (20, 4, 5, 4),
                 (20, 0, 99, 4)):
        assert _verdict(*args).reason


# ── DB 연동 ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_evaluate_reads_recent_window(db, blog):
    await _urls(db, blog, total=20, indexed=0, days_ago=5)
    v = await IndexFeedback(db).evaluate(blog.id, base_daily=4)
    assert v.checked == 20 and v.indexed == 0
    assert v.cap == CAP_POOR


@pytest.mark.asyncio
async def test_old_urls_are_ignored(db, blog):
    """30일보다 오래된 발행분은 현재 상태를 말해 주지 않는다."""
    await _urls(db, blog, total=20, indexed=0, days_ago=90)
    v = await IndexFeedback(db).evaluate(blog.id, base_daily=4)
    assert v.checked == 0 and v.cap is None


@pytest.mark.asyncio
async def test_unknown_state_not_counted(db, blog):
    """점검하지 않은 URL 을 미색인으로 세면 실제보다 나쁘게 나온다."""
    pub = datetime.now(timezone.utc) - timedelta(days=5)
    for i in range(20):
        db.add(SearchVisibilityUrl(
            blog_id=blog.id, url=f"https://x.com/u{i}/",
            published_at=pub, index_state="unknown"))
    await db.flush()
    v = await IndexFeedback(db).evaluate(blog.id, base_daily=4)
    assert v.checked == 0 and v.cap is None


@pytest.mark.asyncio
async def test_recovery_removes_cap(db, blog):
    """색인이 살아나면 상한이 저절로 풀려야 한다."""
    await _urls(db, blog, total=20, indexed=12, days_ago=5)
    v = await IndexFeedback(db).evaluate(blog.id, base_daily=4)
    assert v.cap is None and v.stop is False


@pytest.mark.asyncio
async def test_other_blog_not_mixed(db, blog):
    other = Blog(user_id=blog.user_id, name="다른블로그",
                 url="https://y.com", platform=BlogPlatform.WORDPRESS)
    db.add(other)
    await db.flush()
    await _urls(db, blog, total=20, indexed=0, days_ago=5)
    v = await IndexFeedback(db).evaluate(other.id, base_daily=4)
    assert v.checked == 0, "다른 블로그 색인 상태가 섞이면 안 된다"


def test_executor_wires_feedback():
    """생성 경로에 연결돼 있지 않으면 판정해도 소용없다."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2]
           / "app/services/generation/flow_generate_executor.py").read_text(
        encoding="utf-8")
    assert "IndexFeedback" in src
    assert "verdict.stop" in src
    assert "verdict.cap" in src
    # 막을 때 사유를 응답에 실어야 화면에서 알 수 있다
    assert "index_feedback" in src
