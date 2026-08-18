"""F10 — Tally 문의 폼 서비스 순수 로직 + 프로비저너 폴백 테스트."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.publishing.tally_forms_service import (
    build_contact_blocks,
    get_tally_api_key,
)
from app.services.publishing.contact_form_provisioner import ensure_contact_form


class TestContactBlocks:
    def test_first_block_is_form_title(self):
        blocks = build_contact_blocks("군타 문의")
        assert blocks[0]["type"] == "FORM_TITLE"
        assert blocks[0]["payload"]["title"] == "군타 문의"

    def test_three_fields_as_label_input_pairs(self):
        blocks = build_contact_blocks("t")
        # FORM_TITLE + (TITLE+INPUT)*3 = 7블록
        assert len(blocks) == 7
        types = [b["type"] for b in blocks[1:]]
        assert types == ["TITLE", "INPUT_TEXT", "TITLE", "INPUT_EMAIL", "TITLE", "TEXTAREA"]

    def test_label_and_input_share_group_uuid(self):
        blocks = build_contact_blocks("t")
        # 각 (라벨, 입력) 쌍은 같은 groupUuid
        pairs = [(blocks[1], blocks[2]), (blocks[3], blocks[4]), (blocks[5], blocks[6])]
        for label, inp in pairs:
            assert label["groupUuid"] == inp["groupUuid"]
        # 쌍끼리는 서로 다른 groupUuid
        groups = {blocks[1]["groupUuid"], blocks[3]["groupUuid"], blocks[5]["groupUuid"]}
        assert len(groups) == 3

    def test_inputs_required(self):
        blocks = build_contact_blocks("t")
        inputs = [b for b in blocks if b["type"] in ("INPUT_TEXT", "INPUT_EMAIL", "TEXTAREA")]
        assert all(b["payload"]["isRequired"] for b in inputs)

    def test_labels_html(self):
        blocks = build_contact_blocks("t")
        labels = [b["payload"]["html"] for b in blocks if b["type"] == "TITLE"]
        assert labels == ["이름", "이메일", "문의 내용"]


class TestTallyApiKey:
    @pytest.mark.asyncio
    async def test_none_when_unset(self):
        with patch(
            "app.services.publishing.tally_forms_service.SystemSettingsService.get",
            new=AsyncMock(return_value=None),
        ):
            assert await get_tally_api_key(db=object()) is None


class TestProvisionerFallback:
    @pytest.mark.asyncio
    async def test_respects_manual_url(self):
        blog = SimpleNamespace(
            name="블로그", author_profile={"contact_form_url": "https://manual/form"}
        )
        assert await ensure_contact_form(blog, db=object()) == "https://manual/form"

    @pytest.mark.asyncio
    async def test_reuses_existing_auto_form(self):
        blog = SimpleNamespace(
            name="블로그",
            author_profile={"contact_form_id": "F1", "contact_form_url": "https://tally.so/r/abc"},
        )
        assert await ensure_contact_form(blog, db=object()) == "https://tally.so/r/abc"

    @pytest.mark.asyncio
    async def test_none_when_key_unset(self):
        blog = SimpleNamespace(name="블로그", author_profile={})
        with patch(
            "app.services.publishing.contact_form_provisioner.get_tally_api_key",
            new=AsyncMock(return_value=None),
        ):
            assert await ensure_contact_form(blog, db=object()) is None
