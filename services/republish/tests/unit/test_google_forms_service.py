"""F10 — Google Forms 서비스 순수 로직 + 프로비저너 폴백 테스트."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.publishing.google_forms_service import (
    build_contact_form_items,
    to_embed_url,
    get_forms_access_token,
)
from app.services.publishing.contact_form_provisioner import ensure_contact_form


class TestFormItems:
    def test_three_questions(self):
        items = build_contact_form_items()
        assert len(items) == 3

    def test_titles_and_order(self):
        items = build_contact_form_items()
        titles = [it["createItem"]["item"]["title"] for it in items]
        assert titles == ["이름", "이메일", "문의 내용"]
        for idx, it in enumerate(items):
            assert it["createItem"]["location"]["index"] == idx

    def test_message_is_paragraph_others_not(self):
        items = build_contact_form_items()
        q = [it["createItem"]["item"]["questionItem"]["question"] for it in items]
        assert q[0]["textQuestion"]["paragraph"] is False
        assert q[1]["textQuestion"]["paragraph"] is False
        assert q[2]["textQuestion"]["paragraph"] is True
        assert all(x["required"] for x in q)


class TestEmbedUrl:
    def test_empty(self):
        assert to_embed_url("") == ""

    def test_appends_query(self):
        assert to_embed_url("https://docs.google.com/forms/d/e/X/viewform") == \
            "https://docs.google.com/forms/d/e/X/viewform?embedded=true"

    def test_appends_with_existing_query(self):
        assert to_embed_url("https://x/viewform?usp=share") == \
            "https://x/viewform?usp=share&embedded=true"


class TestFormsAccessToken:
    @pytest.mark.asyncio
    async def test_none_when_unset(self):
        with patch(
            "app.services.publishing.google_forms_service.SystemSettingsService.get",
            new=AsyncMock(return_value=None),
        ):
            assert await get_forms_access_token(db=object()) is None


class TestProvisionerFallback:
    @pytest.mark.asyncio
    async def test_respects_manual_url(self):
        blog = SimpleNamespace(
            name="블로그", author_profile={"contact_form_url": "https://manual/form"}
        )
        # 수동 입력값이 있으면 자동 생성 없이 그대로 반환
        assert await ensure_contact_form(blog, db=object()) == "https://manual/form"

    @pytest.mark.asyncio
    async def test_reuses_existing_auto_form(self):
        blog = SimpleNamespace(
            name="블로그",
            author_profile={"contact_form_id": "F1", "contact_form_url": "https://auto/embed"},
        )
        assert await ensure_contact_form(blog, db=object()) == "https://auto/embed"

    @pytest.mark.asyncio
    async def test_none_when_account_unset(self):
        blog = SimpleNamespace(name="블로그", author_profile={})
        with patch(
            "app.services.publishing.contact_form_provisioner.get_forms_access_token",
            new=AsyncMock(return_value=None),
        ):
            assert await ensure_contact_form(blog, db=object()) is None
