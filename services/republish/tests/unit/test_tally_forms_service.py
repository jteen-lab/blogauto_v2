"""F10 — Tally 폼 서비스(필드→블록·해시)+프로비저너(멱등) 테스트."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.publishing.tally_forms_service import (
    build_blocks_from_fields,
    build_contact_blocks,
    config_hash,
    get_tally_api_key,
)
from app.services.publishing.contact_form_templates import (
    DEFAULT_FIELDS, TEMPLATES, get_template, list_templates,
)
from app.services.publishing import contact_form_provisioner as prov


class TestBuildBlocks:
    def test_form_title_first(self):
        blocks = build_blocks_from_fields("t", DEFAULT_FIELDS)
        assert blocks[0]["type"] == "FORM_TITLE"
        assert blocks[0]["groupType"] == "TEXT"

    def test_label_input_pairs_and_group_types(self):
        fields = [{"label": "이름", "type": "INPUT_TEXT", "required": True},
                  {"label": "메시지", "type": "TEXTAREA", "required": False}]
        blocks = build_blocks_from_fields("t", fields)
        assert len(blocks) == 1 + 2 * 2
        assert [b["type"] for b in blocks[1:]] == ["LABEL", "INPUT_TEXT", "LABEL", "TEXTAREA"]
        # 입력 블록 groupType = 자기 타입
        assert blocks[2]["groupType"] == "INPUT_TEXT"
        assert blocks[4]["groupType"] == "TEXTAREA"
        assert blocks[4]["payload"]["isRequired"] is False

    def test_every_block_unique_group_uuid(self):
        blocks = build_blocks_from_fields("t", DEFAULT_FIELDS)
        gu = [b["groupUuid"] for b in blocks]
        assert len(gu) == len(set(gu))

    def test_default_blocks_match_default_fields(self):
        assert len(build_contact_blocks("t")) == 1 + 2 * len(DEFAULT_FIELDS)


class TestConfigHash:
    def test_stable_and_sensitive(self):
        h1 = config_hash("{blog} 문의", DEFAULT_FIELDS)
        h2 = config_hash("{blog} 문의", DEFAULT_FIELDS)
        h3 = config_hash("{blog} 문의", DEFAULT_FIELDS + [{"label": "전화", "type": "INPUT_PHONE_NUMBER"}])
        assert h1 == h2 and h1 != h3


class TestTemplates:
    def test_at_least_five_templates(self):
        assert len(TEMPLATES) >= 5

    def test_get_and_list(self):
        assert get_template("basic")["code"] == "basic"
        codes = {t["code"] for t in list_templates()}
        assert "basic" in codes and "with_phone" in codes

    def test_only_supported_field_types(self):
        from app.services.publishing.contact_form_templates import SUPPORTED_FIELD_TYPES
        for t in TEMPLATES:
            for f in t["fields"]:
                assert f["type"] in SUPPORTED_FIELD_TYPES


class TestTallyApiKey:
    @pytest.mark.asyncio
    async def test_none_when_unset(self):
        with patch(
            "app.services.publishing.tally_forms_service.SystemSettingsService.get",
            new=AsyncMock(return_value=None),
        ):
            assert await get_tally_api_key(db=object()) is None


class TestProvisioner:
    @pytest.mark.asyncio
    async def test_respects_manual_url(self):
        blog = SimpleNamespace(name="B", author_profile={"contact_form_url": "https://manual/f"})
        assert await prov.ensure_contact_form(blog, db=object()) == "https://manual/f"

    @pytest.mark.asyncio
    async def test_skips_when_hash_matches(self):
        h = config_hash(prov.DEFAULT_TITLE_TEMPLATE, DEFAULT_FIELDS)
        blog = SimpleNamespace(name="B", author_profile={
            "contact_form_id": "F1", "contact_form_url": "https://tally.so/r/abc",
            "contact_form_config_hash": h,
        })
        with patch.object(prov, "get_tally_api_key", new=AsyncMock(return_value="k")), \
             patch.object(prov, "create_contact_form", new=AsyncMock()) as cc, \
             patch.object(prov, "update_contact_form", new=AsyncMock()) as uc:
            url = await prov.ensure_contact_form(blog, db=object())
        assert url == "https://tally.so/r/abc"
        cc.assert_not_called()
        uc.assert_not_called()

    @pytest.mark.asyncio
    async def test_patches_when_hash_differs(self):
        blog = SimpleNamespace(name="B", author_profile={
            "contact_form_id": "F1", "contact_form_url": "https://tally.so/r/abc",
            "contact_form_config_hash": "OLD",
        })
        db = AsyncMock()
        with patch.object(prov, "get_tally_api_key", new=AsyncMock(return_value="k")), \
             patch.object(prov, "update_contact_form", new=AsyncMock(return_value={
                 "form_id": "F1", "embed_url": "https://tally.so/r/abc"})) as uc:
            url = await prov.ensure_contact_form(blog, db=db)
        uc.assert_awaited_once()
        assert url == "https://tally.so/r/abc"

    @pytest.mark.asyncio
    async def test_legacy_google_regenerated(self):
        blog = SimpleNamespace(name="B", author_profile={
            "contact_form_id": "g", "contact_form_url": "https://docs.google.com/forms/x/viewform",
        })
        with patch.object(prov, "get_tally_api_key", new=AsyncMock(return_value=None)):
            assert await prov.ensure_contact_form(blog, db=object()) is None

    @pytest.mark.asyncio
    async def test_none_when_key_unset(self):
        blog = SimpleNamespace(name="B", author_profile={})
        with patch.object(prov, "get_tally_api_key", new=AsyncMock(return_value=None)):
            assert await prov.ensure_contact_form(blog, db=object()) is None
