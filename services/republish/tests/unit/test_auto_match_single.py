"""재발행 리뉴얼 #4 단일 글 자동매칭(match_single_post) 테스트."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.auto_match_service import AutoMatchService


def _post(blog_id=9, title="여름 휴가 추천"):
    p = SimpleNamespace(
        id=5, blog_id=blog_id, title=title,
        matched_main_title_id=None, match_status="unmatched",
        match_score=None,
    )

    def mark_matched(mid, score):
        p.matched_main_title_id = mid
        p.match_status = "matched"
        p.match_score = score

    p.mark_matched = mark_matched
    return p


@pytest.mark.asyncio
async def test_no_candidates_returns_false():
    db = MagicMock()
    db.commit = AsyncMock()
    svc = AutoMatchService(db)
    with patch.object(
        svc, "_get_category_filtered_titles",
        new=AsyncMock(return_value=[]),
    ):
        ok = await svc.match_single_post(_post())
    assert ok is False
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_match_success_marks_and_commits():
    db = MagicMock()
    db.commit = AsyncMock()
    post = _post()
    titles = [SimpleNamespace(id=11, title="여름 휴가 추천 베스트")]
    svc = AutoMatchService(db)
    with patch.object(
        svc, "_get_category_filtered_titles",
        new=AsyncMock(return_value=titles),
    ), patch.object(svc, "_find_best_match", return_value=(11, 90.0)):
        ok = await svc.match_single_post(post, threshold=65.0)
    assert ok is True
    assert post.matched_main_title_id == 11
    assert post.match_status == "matched"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_below_threshold_returns_false():
    db = MagicMock()
    db.commit = AsyncMock()
    post = _post()
    titles = [SimpleNamespace(id=11, title="전혀 다른 주제")]
    svc = AutoMatchService(db)
    with patch.object(
        svc, "_get_category_filtered_titles",
        new=AsyncMock(return_value=titles),
    ), patch.object(svc, "_find_best_match", return_value=(11, 40.0)):
        ok = await svc.match_single_post(post, threshold=65.0)
    assert ok is False
    assert post.matched_main_title_id is None
    db.commit.assert_not_called()
