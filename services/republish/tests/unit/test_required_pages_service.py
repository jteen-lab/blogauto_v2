"""필수 페이지 생성 오케스트레이션 단위 테스트 (애드센스 F1)."""
from unittest.mock import AsyncMock

import pytest

from app.models.blog import Blog, BlogPlatform
from app.services.publishing.publish_result import PublishResult
from app.services.publishing.required_pages_service import RequiredPagesService


def _make_blog(**overrides) -> Blog:
    blog = Blog(
        user_id=1,
        name="테스트블로그",
        url="https://example.com",
        platform=BlogPlatform.WORDPRESS,
    )
    for key, value in overrides.items():
        setattr(blog, key, value)
    return blog


def _ok(page_id: str) -> PublishResult:
    return PublishResult(
        success=True, platform="wordpress",
        published_url=f"https://example.com/{page_id}",
        platform_post_id=page_id,
    )


@pytest.mark.asyncio
async def test_generate_all_success_marks_status_complete():
    db = AsyncMock()
    blog = _make_blog()
    service = RequiredPagesService(db)
    service._publish_one = AsyncMock(
        side_effect=[_ok("1"), _ok("2"), _ok("3"), _ok("4")],
    )

    outcome = await service.generate_all(blog, "owner@example.com")

    assert outcome["success"] is True
    assert outcome["status"] == "complete"
    assert blog.required_pages_status == "complete"
    assert set(blog.required_page_ids.keys()) == {
        "privacy", "terms", "about", "contact",
    }
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_all_skips_already_created_pages():
    db = AsyncMock()
    blog = _make_blog(required_page_ids={"privacy": "existing-1"})
    service = RequiredPagesService(db)
    service._publish_one = AsyncMock(
        side_effect=[_ok("2"), _ok("3"), _ok("4")],
    )

    outcome = await service.generate_all(blog, "owner@example.com")

    assert outcome["results"]["privacy"] == {"success": True, "skipped": True}
    assert blog.required_page_ids["privacy"] == "existing-1"
    assert service._publish_one.await_count == 3


@pytest.mark.asyncio
async def test_generate_all_partial_failure_marks_status_partial():
    db = AsyncMock()
    blog = _make_blog()
    service = RequiredPagesService(db)
    failed = PublishResult(success=False, platform="wordpress", error="403 Forbidden")
    service._publish_one = AsyncMock(
        side_effect=[_ok("1"), failed, _ok("3"), failed],
    )

    outcome = await service.generate_all(blog, "owner@example.com")

    assert outcome["status"] == "partial"
    assert blog.required_pages_status == "partial"
    assert "terms" not in blog.required_page_ids
    assert "contact" not in blog.required_page_ids


@pytest.mark.asyncio
async def test_generate_all_rejects_unsupported_platform():
    db = AsyncMock()
    blog = _make_blog(platform=BlogPlatform.OTHER)
    service = RequiredPagesService(db)

    outcome = await service.generate_all(blog, "owner@example.com")

    assert outcome["success"] is False
    assert "지원하지 않는 플랫폼" in outcome["error"]
    db.commit.assert_not_awaited()
