"""리뉴얼 실패 글 미루기·기록 (2026-10-25 켜기 전 점검)."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.renewal.renewal_service import RenewalService

LIVE = SimpleNamespace(platform_post_id="542", title="완강기", content_html="<p>o</p>",
                       featured_image_url="", image_origin="none")
PLAN = SimpleNamespace(skip=False, action="rewrite", action_reason="GA 0")


def _post():
    return SimpleNamespace(id=26, platform_post_id="542", url="https://b/542/",
                           last_renewed_at=None)


async def _run(cfg):
    db = MagicMock(); db.commit = AsyncMock()
    svc = RenewalService(db)
    svc._plan = AsyncMock(return_value=(PLAN, False))
    svc._regenerate = AsyncMock(return_value={"success": False, "error": "사실 관문 통과 못 함",
                                              "warnings": ["사실 관문 보류: 법령"]})
    blog = SimpleNamespace(id=9, name="잡학다식", user_id=1, renewal_config=cfg)
    post = _post()
    with patch("app.services.renewal.renewal_service.RenewalSource") as Src, \
         patch("app.services.renewal.renewal_service.renewal_record") as rec:
        Src.return_value.fetch = AsyncMock(return_value=LIVE)
        res = await svc.renew_post(blog, post, dry_run=False, stage="3-rewrite")
    return res, post, rec, db


@pytest.mark.asyncio
async def test_held_post_is_deferred_and_journaled():
    res, post, rec, db = await _run({"pick": "performance"})
    assert not res["success"]
    # 어제 날짜 — 오늘 상한은 안 쓰고 min_gap_days 동안 후보에서 빠진다
    assert post.last_renewed_at < datetime.now() - timedelta(hours=23)
    row = rec.journal.call_args[0][1]
    assert row["result"] == "held" and row["stage"] == "3-rewrite"
    assert row["warnings"] == ["사실 관문 보류: 법령"]
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_pick_does_not_defer():
    res, post, rec, db = await _run({"enabled": True})
    assert post.last_renewed_at is None
    rec.journal.assert_not_called()
