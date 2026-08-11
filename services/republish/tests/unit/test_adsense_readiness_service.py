"""애드센스 준비도 감사 단위 테스트 (F9)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.blog import Blog, BlogPlatform
from app.services.publishing.adsense_readiness_service import AdsenseReadinessService


def _make_blog(**overrides) -> Blog:
    blog = Blog(
        id=1,
        user_id=1,
        name="테스트블로그",
        url="https://example.com",
        platform=BlogPlatform.WORDPRESS,
    )
    for key, value in overrides.items():
        setattr(blog, key, value)
    return blog


def _db_with_post_count(count: int) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = count
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_audit_all_signals_configured_scores_full_checklist():
    blog = _make_blog(
        required_pages_status="complete",
        author_profile={"name": "홍길동", "contact_form_url": "https://forms.gle/abc"},
    )
    service = AdsenseReadinessService(_db_with_post_count(25))

    outcome = await service.audit(blog)

    assert outcome["author_profile_configured"] is True
    assert outcome["contact_channel"] == "form"
    assert outcome["checklist"] == {
        "required_pages": True,
        "author_profile": True,
        "contact_form": True,
        "post_count_20plus": True,
    }
    assert outcome["checklist_score"] == 4
    assert outcome["checklist_total"] == 4


@pytest.mark.asyncio
async def test_audit_no_signals_configured_scores_zero():
    blog = _make_blog(required_pages_status="none")
    service = AdsenseReadinessService(_db_with_post_count(3))

    outcome = await service.audit(blog)

    assert outcome["author_profile_configured"] is False
    assert outcome["contact_channel"] == "email"
    assert outcome["checklist_score"] == 0
    assert outcome["post_count"] == 3


@pytest.mark.asyncio
async def test_audit_partial_signals_mixed_checklist():
    blog = _make_blog(
        required_pages_status="partial",
        author_profile={"name": "홍길동", "contact_form_url": ""},
    )
    service = AdsenseReadinessService(_db_with_post_count(20))

    outcome = await service.audit(blog)

    assert outcome["checklist"] == {
        "required_pages": False,
        "author_profile": True,
        "contact_form": False,
        "post_count_20plus": True,
    }
    assert outcome["checklist_score"] == 2
