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


class TestManualEntry:
    """직접 입력에는 어댑터를 고를 칸이 없어 테스트가 '모르는 어댑터: ' 로
    실패했다(2026-09-06 사용자 보고)."""

    def test_adapter_select_exists(self):
        assert 'x-model="form.adapter"' in MODAL
        assert 'value="fss_finlife"' in MODAL
        assert 'value="data_go_kr"' in MODAL

    def test_adapter_locked_when_preset(self):
        block = MODAL[MODAL.index('x-model="form.adapter"'):]
        assert ':disabled="!!form.preset"' in block[:300]

    def test_code_field_exists(self):
        """식별 코드도 입력칸이 없었다."""
        assert 'x-model="form.code"' in MODAL

    def test_client_blocks_before_calling(self):
        """서버까지 갔다 오면 느리고 메시지도 흐리다."""
        assert "_missing()" in JS
        assert "어댑터를 고르세요" in JS


class TestErrorResponse:
    """오류 응답에 query 가 없어 화면에 '질의 undefined' 가 떴다."""

    def test_error_paths_carry_query(self):
        src = (ROOT / "app/routers/external_sources.py").read_text(
            encoding="utf-8")
        body = src[src.index("async def test_source"):]
        # 모든 조기 반환이 base 를 펼쳐 query·entities 를 싣는다
        assert body.count("**base") >= 4
        assert 'base = {"query": plan.primary' in body

    def test_empty_adapter_says_what_to_do(self):
        src = (ROOT / "app/routers/external_sources.py").read_text(
            encoding="utf-8")
        assert "어댑터를 고르지 않았습니다" in src

    def test_js_hides_undefined_query(self):
        assert "d.query\n" in JS or "? `\\n(질의" in JS or "d.query" in JS
        # query 가 없으면 괄호 문구 자체를 붙이지 않는다
        assert "(d.query" in JS


class TestPresetEndpoint:
    def test_preset_leaves_endpoint_empty(self):
        """안내 문구를 넣으면 그게 주소로 저장된다."""
        assert "this.form.endpoint = '';" in JS


class TestFssMultiProduct:
    """금감원은 상품 종류마다 주소가 다르다.

    대출 니치는 주담대·전세·신용대출을 다 다룬다. 종류마다 소스를 따로
    등록하게 하면 같은 인증키를 세 번 넣어야 한다(사용자 지적 2026-09-06).
    """

    @pytest.mark.parametrize("title,expected", [
        ("우리아파트론 우리은행 대출", "mortgage"),
        ("전세자금대출 조건", "rent"),
        ("햇살론15 신용대출", "credit"),
        ("정기예금 금리 비교", "deposit"),
        ("청년 적금 추천", "saving"),
        ("연금저축 세액공제", "annuity"),
    ])
    def test_op_picked_from_title(self, title, expected):
        from app.services.reference.sources.fss_finlife import pick_op

        assert pick_op(title) == expected

    def test_rent_wins_over_generic_loan(self):
        """'전세자금대출' 은 '전세' 와 '대출' 에 다 걸린다 — 순서가 중요하다."""
        from app.services.reference.sources.fss_finlife import pick_op

        assert pick_op("전세자금대출") == "rent"

    def test_endpoint_resolved(self):
        from app.services.reference.sources.fss_finlife import resolve_endpoint

        base = "https://finlife.fss.or.kr/finlifeapi/{op}.json"
        assert "rentHouse" in resolve_endpoint(base, "전세자금대출", [])

    def test_fixed_endpoint_untouched(self):
        """종류를 고정한 옛 소스는 그대로 쓴다."""
        from app.services.reference.sources.fss_finlife import resolve_endpoint

        fixed = "https://finlife.fss.or.kr/finlifeapi/depositProductsSearch.json"
        assert resolve_endpoint(fixed, "전세자금대출", []) == fixed

    def test_unified_preset_exists(self):
        from app.services.reference.sources import presets

        found = presets.get("fss_all")
        assert "{op}" in found["endpoint"]
        assert "권장" in found["name"]


class TestAdapterDefaults:
    """직접 입력에서 주소를 몰라 '주소를 입력하세요' 로 막혔다."""

    def test_adapter_has_default_endpoint(self):
        from app.services.reference.sources import presets

        assert "{op}" in presets.adapter_default("fss_finlife")["endpoint"]

    def test_server_fills_endpoint_without_preset(self):
        from app.routers.external_sources import (
            SourceRequest, _resolve_preset,
        )

        req = SourceRequest(code="c1", name="n", adapter="fss_finlife",
                            match_keywords=["대출"])
        _resolve_preset(req)
        assert req.endpoint
        assert req.options

    def test_screen_fills_on_adapter_change(self):
        assert 'onAdapter()' in MODAL
        assert "app.form.endpoint = base.endpoint" in JS or \
            "this.form.endpoint = base.endpoint" in JS

    def test_code_is_optional(self):
        """식별 코드는 내부용이다. 사용자가 고민할 이유가 없다."""
        assert "비우면 자동" in MODAL
        assert "'src_' + Date.now()" in JS
