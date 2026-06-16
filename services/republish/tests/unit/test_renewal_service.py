"""리뉴얼 오케스트레이터 dry_run 테스트 (mock)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.renewal.renewal_service import RenewalService


@pytest.mark.asyncio
async def test_dry_run_no_update():
    db = MagicMock(); db.commit = AsyncMock()
    svc = RenewalService(db)
    svc._resolve_module = AsyncMock(return_value=SimpleNamespace(id=5, settings={}))
    blog = SimpleNamespace(id=1, name="t", user_id=1, renewal_config={"title_mode": "keep"})
    post = SimpleNamespace(id=9, platform_post_id="100", url="https://x/9",
                           source="generated", matched_main_title_id=None)
    live = SimpleNamespace(platform_post_id="100", title="라이브 제목",
                           content_html="<p>old</p>", featured_image_url="https://i.ibb.co/a.webp",
                           image_origin="blogauto")
    rc = SimpleNamespace(success=True, title="라이브 제목", content_html="<div>new</div>",
                         image_url="https://i.ibb.co/a.webp", warnings=[])
    with patch("app.services.renewal.renewal_service.RenewalSource") as Src, \
         patch("app.services.renewal.renewal_service.RenewalGenerator") as Gen, \
         patch("app.services.renewal.renewal_service.RenewalUpdater") as Upd:
        Src.return_value.fetch = AsyncMock(return_value=live)
        Gen.return_value.regenerate = AsyncMock(return_value=rc)
        res = await svc.renew_post(blog, post, dry_run=True)
        Upd.return_value.update.assert_not_called()  # 갱신 안 함
    assert res["success"] and res["dry_run"] is True
    assert res["new_title"] == "라이브 제목"
    assert res["image_action"] == "reuse"  # keep + blogauto + blogauto이미지
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_apply_updates_and_marks_renewed():
    db = MagicMock(); db.commit = AsyncMock()
    svc = RenewalService(db)
    svc._resolve_module = AsyncMock(return_value=SimpleNamespace(id=5, settings={}))
    blog = SimpleNamespace(id=1, name="t", user_id=1, renewal_config={"title_mode": "recombine"})
    post = SimpleNamespace(id=9, platform_post_id="100", url="https://x/9",
                           source="generated", matched_main_title_id=None,
                           title="", content_html="", image_url=None, last_renewed_at=None)
    live = SimpleNamespace(platform_post_id="100", title="라이브", content_html="<p>o</p>",
                           featured_image_url="", image_origin="none")
    rc = SimpleNamespace(success=True, title="재조합", content_html="<div>n</div>",
                         image_url="/static/x.webp", warnings=[])
    with patch("app.services.renewal.renewal_service.RenewalSource") as Src, \
         patch("app.services.renewal.renewal_service.RenewalGenerator") as Gen, \
         patch("app.services.renewal.renewal_service.RenewalUpdater") as Upd:
        Src.return_value.fetch = AsyncMock(return_value=live)
        Gen.return_value.regenerate = AsyncMock(return_value=rc)
        Upd.return_value.update = AsyncMock(return_value={"success": True, "link": "https://x/9"})
        res = await svc.renew_post(blog, post, dry_run=False)
    assert res["success"]
    assert post.title == "재조합" and post.content_html == "<div>n</div>"
    assert post.last_renewed_at is not None
    db.commit.assert_awaited_once()
