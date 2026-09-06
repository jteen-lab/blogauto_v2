"""1차 출처 API 등록 — 화면에서 관리한다.

레지스트리는 `options` 에 items_path·field_map 같은 값을 받는다. 그걸
화면에서 손으로 적게 하면 아무도 못 쓴다. 프리셋을 고르면 서버가 채우고
사용자는 인증키만 넣는다.
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODAL = (ROOT / "app/templates/settings/modal.html").read_text(
    encoding="utf-8")
JS = (ROOT / "app/static/js/settings/external_sources.js").read_text(
    encoding="utf-8")


class TestPresets:
    def test_presets_exist(self):
        from app.services.reference.sources import presets

        codes = {p["code"] for p in presets.listing()}
        assert "fss_mortgage" in codes      # 금감원 주담대
        assert "policy_briefing" in codes   # 보도자료

    def test_preset_carries_everything_but_the_key(self):
        from app.services.reference.sources import presets

        found = presets.get("fss_mortgage")
        assert found["adapter"] == "fss_finlife"
        assert found["endpoint"].startswith("https://")
        assert found["match_topics"] and found["match_keywords"]
        assert "auth_key" not in found      # 키는 사람이 넣는다

    def test_listing_hides_options(self):
        """화면은 items_path 같은 걸 몰라도 된다."""
        from app.services.reference.sources import presets

        for row in presets.listing():
            assert "options" not in row

    def test_server_fills_from_preset(self):
        from app.routers.external_sources import (
            SourceRequest, _resolve_preset,
        )

        req = SourceRequest(code="fss_mortgage", name="주담대",
                            preset="fss_mortgage")
        _resolve_preset(req)
        assert req.adapter == "fss_finlife"
        assert "mortgageLoanProductsSearch" in req.endpoint
        assert req.options.get("top_fin_grp_no")

    def test_user_topics_win_over_preset(self):
        """사용자가 지정했으면 프리셋이 덮어쓰지 않는다."""
        from app.routers.external_sources import (
            SourceRequest, _resolve_preset,
        )

        req = SourceRequest(code="x1", name="n", preset="fss_mortgage",
                            match_topics=["내가 고른 주제"])
        _resolve_preset(req)
        assert req.match_topics == ["내가 고른 주제"]

    def test_unknown_preset_is_rejected(self):
        from fastapi import HTTPException

        from app.routers.external_sources import (
            SourceRequest, _resolve_preset,
        )

        with pytest.raises(HTTPException):
            _resolve_preset(SourceRequest(code="x1", name="n",
                                          preset="없는프리셋"))


class TestSafety:
    def test_key_is_never_returned(self):
        """목록 응답에 인증키가 실려 나가면 안 된다."""
        from types import SimpleNamespace

        from app.routers.external_sources import _serialize

        row = SimpleNamespace(
            id=1, code="c", name="n", adapter="fss_finlife", endpoint="e",
            auth_key_encrypted="비밀", options={}, match_topics=[],
            match_keywords=[], enabled=True, daily_limit=1000, note="")
        out = _serialize(row)
        assert "비밀" not in str(out)
        assert out["has_key"] is True

    def test_blank_key_keeps_existing(self):
        """수정할 때마다 키를 다시 넣게 하면 실수로 지운다."""
        src = (ROOT / "app/routers/external_sources.py").read_text(
            encoding="utf-8")
        block = src[src.index("def _apply("):]
        assert "if key and MASK not in key:" in block

    def test_source_without_conditions_is_rejected(self):
        """조건이 비면 영영 안 불린다. 등록해 놓고 왜 안 되는지 묻게 된다."""
        src = (ROOT / "app/routers/external_sources.py").read_text(
            encoding="utf-8")
        assert "주제 또는 제목 낱말 중 하나는 지정해야 합니다" in src


class TestScreen:
    def test_block_in_settings(self):
        """연결 설정은 매일 보는 값이 아니다 — 설정 창이 맞다."""
        assert "1차 출처 API" in MODAL

    def test_script_loaded(self):
        base = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
        assert "settings/external_sources.js" in base

    def test_test_button_exists(self):
        """등록만 해 두고 글 생성 때 조용히 실패하면 아무도 모른다."""
        assert "runTest(" in MODAL
        assert "external-sources/test" in JS

    def test_test_shows_what_came_back(self):
        """건수만으로는 맞는 자료인지 알 수 없다."""
        src = (ROOT / "app/routers/external_sources.py").read_text(
            encoding="utf-8")
        assert '"preview"' in src
        assert "testResult" in MODAL

    def test_endpoint_locked_when_preset(self):
        assert ':disabled="!!form.preset"' in MODAL

    def test_warns_when_no_key(self):
        assert "키 없음" in MODAL
