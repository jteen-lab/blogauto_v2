"""F5 발행 케이던스 게이트(_check_publish_cadence_cap) 단위 테스트."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.blog import Blog, BlogPlatform
from app.scheduler.flow_scheduler import FlowScheduler


def _make_blog(**overrides) -> Blog:
    blog = Blog(
        id=1,
        user_id=1,
        name="테스트블로그",
        url="https://example.com",
        platform=BlogPlatform.WORDPRESS,
        adsense_status="none",
        publish_daily_cap=None,
    )
    for key, value in overrides.items():
        setattr(blog, key, value)
    return blog


def _db_with_today_count(count: int) -> MagicMock:
    result = MagicMock()
    result.scalar.return_value = count
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.get = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_cap_unset_returns_none_regardless_of_status():
    blog = _make_blog(publish_daily_cap=None, adsense_status="preparing")
    scheduler = FlowScheduler()

    result = await scheduler._check_publish_cadence_cap(_db_with_today_count(5), blog)

    assert result is None


@pytest.mark.asyncio
async def test_approved_status_bypasses_cap_even_if_set():
    blog = _make_blog(publish_daily_cap=1, adsense_status="approved")
    scheduler = FlowScheduler()

    result = await scheduler._check_publish_cadence_cap(_db_with_today_count(5), blog)

    assert result is None


@pytest.mark.asyncio
async def test_cap_exceeded_returns_skip_result():
    blog = _make_blog(publish_daily_cap=2, adsense_status="preparing")
    scheduler = FlowScheduler()

    result = await scheduler._check_publish_cadence_cap(_db_with_today_count(2), blog)

    assert result == {
        "success": True,
        "skipped": True,
        "message": "애드센스 승인 전 저속 모드 발행 상한 도달 (2/2)",
    }


@pytest.mark.asyncio
async def test_cap_not_yet_reached_returns_none():
    blog = _make_blog(publish_daily_cap=5, adsense_status="preparing")
    scheduler = FlowScheduler()

    result = await scheduler._check_publish_cadence_cap(_db_with_today_count(1), blog)

    assert result is None
