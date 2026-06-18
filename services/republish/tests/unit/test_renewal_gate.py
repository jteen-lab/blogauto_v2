"""재발행 리뉴얼 게이트(주기 도래 판정) 테스트."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.generation.publish_workflow import PublishWorkflow


def _result(posts):
    r = MagicMock()
    r.scalars.return_value.all.return_value = posts
    return r


@pytest.mark.asyncio
async def test_due_post_selected():
    now = datetime.now(timezone.utc)
    recent = SimpleNamespace(id=1, last_renewed_at=None,
                             published_at=now - timedelta(days=20),
                             matched_main_title_id=None)
    old = SimpleNamespace(id=2, last_renewed_at=None,
                          published_at=now - timedelta(days=200),
                          matched_main_title_id=None)
    db = MagicMock(); db.execute = AsyncMock(return_value=_result([old, recent]))
    wf = PublishWorkflow(db)
    due = await wf._find_due_renewable_post(
        SimpleNamespace(id=9), {"default_period_months": 3, "category_periods": {}},
    )
    assert due is old  # 200일 > 3개월


@pytest.mark.asyncio
async def test_none_due_when_all_recent():
    now = datetime.now(timezone.utc)
    recent = SimpleNamespace(id=1, last_renewed_at=None,
                             published_at=now - timedelta(days=20),
                             matched_main_title_id=None)
    db = MagicMock(); db.execute = AsyncMock(return_value=_result([recent]))
    wf = PublishWorkflow(db)
    due = await wf._find_due_renewable_post(
        SimpleNamespace(id=9), {"default_period_months": 3, "category_periods": {}},
    )
    assert due is None  # 20일 < 3개월


@pytest.mark.asyncio
async def test_last_renewed_at_takes_precedence():
    now = datetime.now(timezone.utc)
    # 오래 전 발행이지만 최근 리뉴얼 → 미도래
    p = SimpleNamespace(id=3, last_renewed_at=now - timedelta(days=10),
                        published_at=now - timedelta(days=300),
                        matched_main_title_id=None)
    db = MagicMock(); db.execute = AsyncMock(return_value=_result([p]))
    wf = PublishWorkflow(db)
    due = await wf._find_due_renewable_post(
        SimpleNamespace(id=9), {"default_period_months": 2, "category_periods": {}},
    )
    assert due is None  # last_renewed 10일 < 2개월
