"""F10 — Tally 문의 폼 서비스 순수 로직 + 프로비저너 폴백/마이그레이션 테스트."""
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
        assert blocks[0]["groupType"] == "TEXT"
        assert blocks[0]["payload"]["title"] == "군타 문의"
        assert blocks[0]["payload"]["safeHTMLSchema"] == [["군타 문의"]]

    def test_three_fields_as_label_input_pairs(self):
        blocks = build_contact_blocks("t")
        # FORM_TITLE + (LABEL+INPUT)*3 = 7블록
        assert len(blocks) == 7
        types = [b["type"] for b in blocks[1:]]
        assert types == ["LABEL", "INPUT_TEXT", "LABEL", "INPUT_EMAIL", "LABEL", "TEXTAREA"]

    def test_all_blocks_have_group_type(self):
        for b in build_contact_blocks("t"):
            assert b.get("groupType"), f"groupType 누락: {b['type']}"

    def test_every_block_has_unique_group_uuid(self):
        # Tally 규칙: LABEL/TITLE은 입력과 groupUuid 공유 금지 → 전 블록 고유
        blocks = build_contact_blocks("t")
        group_uuids = [b["groupUuid"] for b in blocks]
        assert len(group_uuids) == len(set(group_uuids)), "groupUuid가 중복되면 400"

    def test_label_and_input_group_types(self):
        blocks = build_contact_blocks("t")
        pairs = [(blocks[1], blocks[2]), (blocks[3], blocks[4]), (blocks[5], blocks[6])]
        for label, inp in pairs:
            assert label["groupType"] == "LABEL"
            assert inp["groupType"] == "QUESTION"

    def test_inputs_required(self):
        blocks = build_contact_blocks("t")
        inputs = [b for b in blocks if b["type"] in ("INPUT_TEXT", "INPUT_EMAIL", "TEXTAREA")]
        assert all(b["payload"]["isRequired"] for b in inputs)

    def test_labels_use_safe_html_schema(self):
        blocks = build_contact_blocks("t")
        labels = [b["payload"]["safeHTMLSchema"][0][0] for b in blocks if b["type"] == "LABEL"]
        assert labels == ["이름", "이메일", "문의 내용"]


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
        blog = SimpleNamespace(
            name="블로그", author_profile={"contact_form_url": "https://manual/form"}
        )
        assert await ensure_contact_form(blog, db=object()) == "https://manual/form"

    @pytest.mark.asyncio
    async def test_reuses_existing_tally_form(self):
        blog = SimpleNamespace(
            name="블로그",
            author_profile={"contact_form_id": "F1", "contact_form_url": "https://tally.so/r/abc"},
        )
        assert await ensure_contact_form(blog, db=object()) == "https://tally.so/r/abc"

    @pytest.mark.asyncio
    async def test_legacy_google_url_is_regenerated(self):
        # 옛 구글폼 URL은 재사용하지 않고 (재)생성 경로로 진입 → 키 없으면 None
        blog = SimpleNamespace(
            name="블로그",
            author_profile={
                "contact_form_id": "gid",
                "contact_form_url": "https://docs.google.com/forms/d/e/X/viewform?embedded=true",
            },
        )
        with patch(
            "app.services.publishing.contact_form_provisioner.get_tally_api_key",
            new=AsyncMock(return_value=None),
        ):
            assert await ensure_contact_form(blog, db=object()) is None

    @pytest.mark.asyncio
    async def test_none_when_key_unset(self):
        blog = SimpleNamespace(name="블로그", author_profile={})
        with patch(
            "app.services.publishing.contact_form_provisioner.get_tally_api_key",
            new=AsyncMock(return_value=None),
        ):
            assert await ensure_contact_form(blog, db=object()) is None
