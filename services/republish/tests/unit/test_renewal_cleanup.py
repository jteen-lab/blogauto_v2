"""재발행 리뉴얼 P4 저장 정리(cleanup_purged_posts) 테스트."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.renewal.renewal_cleanup import cleanup_purged_posts


def _result(posts):
    r = MagicMock()
    r.scalars.return_value.all.return_value = posts
    return r


def _blog():
    return SimpleNamespace(id=9, name="테스트블로그")


@pytest.mark.asyncio
async def test_grace_zero_disables_cleanup():
    """delete_grace_days=0 이면 정리 비활성(no-op)."""
    db = MagicMock()
    db.execute = AsyncMock()
    out = await cleanup_purged_posts(db, _blog(), {"delete_grace_days": 0})
    assert out == {"posts": 0, "images": 0}
    db.execute.assert_not_called()  # 쿼리조차 안 함


@pytest.mark.asyncio
async def test_no_eligible_posts():
    """대상 글 없으면 no-op, commit 안 함."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result([]))
    db.commit = AsyncMock()
    out = await cleanup_purged_posts(db, _blog(), {"delete_grace_days": 7})
    assert out == {"posts": 0, "images": 0}
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_purges_content_and_marks():
    """대상 글: content_html=None, purged_at 기록, 이미지 삭제 호출, commit."""
    now = datetime.now(timezone.utc)
    post = SimpleNamespace(
        id=5, content_html="<p>old</p>", purged_at=None,
        image_url="/static/generated/images/x.png",
        generation_history_id=None,
        last_renewed_at=None, published_at=now - timedelta(days=100),
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result([post]))
    db.commit = AsyncMock()
    with patch(
        "app.services.renewal.renewal_cleanup.delete_post_images",
        new=AsyncMock(return_value=1),
    ):
        out = await cleanup_purged_posts(db, _blog(), {"delete_grace_days": 7})
    assert out == {"posts": 1, "images": 1}
    assert post.content_html is None
    assert post.purged_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_image_delete_error_is_nonblocking():
    """이미지 삭제 오류여도 본문 정리·기록은 진행(비차단)."""
    now = datetime.now(timezone.utc)
    post = SimpleNamespace(
        id=6, content_html="<p>old</p>", purged_at=None,
        image_url=None, generation_history_id=None,
        last_renewed_at=None, published_at=now - timedelta(days=100),
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result([post]))
    db.commit = AsyncMock()
    with patch(
        "app.services.renewal.renewal_cleanup.delete_post_images",
        new=AsyncMock(side_effect=RuntimeError("disk")),
    ):
        out = await cleanup_purged_posts(db, _blog(), {"delete_grace_days": 7})
    assert out["posts"] == 1
    assert post.content_html is None
    assert post.purged_at is not None
