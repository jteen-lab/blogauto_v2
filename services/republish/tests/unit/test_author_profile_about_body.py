"""저자 프로필 API의 about_body 저장 테스트 (수정 6: 블로그별 소개 본문)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routers import blog_settings_adsense as mod
from app.routers.blog_settings_adsense import AuthorProfileRequest, save_author_profile
from app.services.publishing.required_pages_templates import ABOUT_BODY_MAX_LEN


def _run(profile, request):
    blog = SimpleNamespace(author_profile=profile)
    db = SimpleNamespace(commit=AsyncMock())
    with patch.object(mod, "get_blog_or_404", AsyncMock(return_value=blog)), \
            patch.object(mod, "flag_modified", lambda *a, **k: None):
        result = asyncio.run(save_author_profile(1, request, SimpleNamespace(), db))
    return result["author_profile"]


def test_about_body_saved_and_truncated():
    saved = _run({}, AuthorProfileRequest(about_body="  " + "가" * (ABOUT_BODY_MAX_LEN + 100)))
    assert len(saved["about_body"]) == ABOUT_BODY_MAX_LEN


def test_about_body_omitted_keeps_existing_value():
    saved = _run({"about_body": "기존", "contact_form_id": "x"}, AuthorProfileRequest(name="홍"))
    assert saved["about_body"] == "기존"
    assert saved["contact_form_id"] == "x"


def test_about_body_empty_string_clears():
    saved = _run({"about_body": "기존"}, AuthorProfileRequest(about_body=""))
    assert saved["about_body"] == ""
