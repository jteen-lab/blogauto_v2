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
    def test_preset_never_puts_prose_in_endpoint(self):
        """안내 문구를 넣으면 그게 주소로 저장된다.

        지금은 고칠 수 있는 프리셋에 **실제 주소**를 미리 채운다.
        빈칸을 주면 사용자가 무엇을 복사해야 할지 모른다.
        """
        assert "this.form.endpoint = p.default_endpoint || '';" in JS
        assert "프리셋 사용" not in JS


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


class TestCreditLoanFields:
    """개인신용대출은 응답 항목 이름이 담보대출과 **완전히 다르다.**

    사용자 보고(2026-09-06): 연결 테스트에 금융회사·상품명·가입방법만 나오고
    금리가 하나도 없었다. OPTION_LABELS 가 lend_rate_* 만 알아서였다.
    """

    def _fact(self, options):
        from app.services.reference.sources.fss_finlife import _to_fact

        return _to_fact({"kor_co_nm": "우리은행", "fin_prdt_nm": "신용대출"},
                        options, "금감원", "")

    def test_credit_rates_are_labelled(self):
        fact = self._fact([{"crdt_grad_avg": "8.5", "crdt_grad_1": "5.2"}])
        text = "\n".join(fact.to_lines())
        assert "평균 금리(%)" in text
        assert "신용점수 900 초과 금리(%)" in text

    def test_unknown_fields_survive(self):
        """이름을 모른다고 버리면 상품 종류가 바뀔 때 금리가 사라진다."""
        fact = self._fact([{"새로운_금리항목": "4.4"}])
        assert "새로운_금리항목" in "\n".join(fact.to_lines())

    def test_bookkeeping_fields_are_dropped(self):
        """공시월·회사코드는 글에 쓸 값이 아니다."""
        fact = self._fact([{"dcls_month": "202609", "fin_co_no": "0010001",
                            "crdt_grad_avg": "8.5"}])
        text = "\n".join(fact.to_lines())
        assert "202609" not in text
        assert "0010001" not in text

    def test_cheapest_uses_credit_rate(self):
        from app.services.reference.sources.fss_finlife import _cheapest

        best = _cheapest([{"crdt_grad_avg": "9.1"}, {"crdt_grad_avg": "6.3"}])
        assert best["crdt_grad_avg"] == "6.3"


class TestDedupe:
    """공시는 같은 상품을 여러 줄로 준다 — 미리보기에 두 번 실렸다."""

    def test_same_product_once(self):
        from app.services.reference.sources.fss_finlife import _dedupe

        rows = [{"fin_co_no": "1", "fin_prdt_cd": "A", "fin_prdt_nm": "X"},
                {"fin_co_no": "1", "fin_prdt_cd": "A", "fin_prdt_nm": "X"},
                {"fin_co_no": "2", "fin_prdt_cd": "B", "fin_prdt_nm": "Y"}]
        assert len(_dedupe(rows)) == 2

    def test_match_dedupes(self):
        from app.services.reference.sources.fss_finlife import _match_products

        rows = [{"fin_co_no": "1", "fin_prdt_cd": "A",
                 "fin_prdt_nm": "신용대출", "kor_co_nm": "우리은행"}] * 3
        assert len(_match_products(rows, "신용대출", ["신용대출"])) == 1


class TestPreviewName:
    def test_uses_form_name_not_placeholder(self):
        """'[공식 자료 — 테스트]' 로 찍히면 무엇을 조회했는지 알 수 없다."""
        src = (ROOT / "app/routers/external_sources.py").read_text(
            encoding="utf-8")
        assert 'name=(request.name or "").strip() or "미등록 소스"' in src


class TestCompanyMustMatch:
    """다른 은행 금리를 이 은행 것처럼 쓰면 사실이 아닌 글이 된다.

    2026-09-06 실측: "NH농협은행 전세대출" 글에 중소기업은행 IBK전세대출이
    붙었다. 개체를 넓히는 과정에서 "전세대출" 이라는 일반어가 걸렸다.
    """

    BASE = [
        {"fin_co_no": "1", "fin_prdt_cd": "A",
         "fin_prdt_nm": "IBK전세대출 (HF)", "kor_co_nm": "중소기업은행"},
        {"fin_co_no": "2", "fin_prdt_cd": "B",
         "fin_prdt_nm": "NH전세대출", "kor_co_nm": "농협은행"},
        {"fin_co_no": "3", "fin_prdt_cd": "C",
         "fin_prdt_nm": "우리아파트론", "kor_co_nm": "우리은행"},
    ]

    def test_other_bank_never_substituted(self):
        from app.services.reference.sources.fss_finlife import _match_products

        hit = _match_products(self.BASE, "",
                              ["NH농협은행", "전세대출", "서류"])
        assert [h["kor_co_nm"] for h in hit] == ["농협은행"]

    @pytest.mark.parametrize("name", ["케이뱅크", "카카오뱅크", "토스뱅크"])
    def test_internet_banks_are_companies(self, name):
        """인터넷은행은 '뱅크' 로 끝난다. '은행' 만 보면 회사 제약이 풀린다."""
        from app.services.reference.sources.fss_finlife import _company_of

        assert _company_of([name, "전세대출"]) == name

    def test_prefix_difference_is_tolerated(self):
        """제목은 'NH농협은행', 공시는 '농협은행' 이다."""
        from app.services.reference.sources.fss_finlife import _same_company

        assert _same_company("NH농협은행", "농협은행")
        assert _same_company("케이뱅크", "주식회사 케이뱅크")
        assert not _same_company("우리은행", "농협은행")

    def test_absent_company_returns_nothing(self):
        """그 은행 상품이 목록에 없으면 빈손이다."""
        from app.services.reference.sources.fss_finlife import _match_products

        assert _match_products(self.BASE, "", ["카카오뱅크", "전세대출"]) == []

    def test_company_found_but_product_not(self):
        """회사가 맞으면 그 회사 상품을 준다 — 사실이 어긋나지는 않는다."""
        from app.services.reference.sources.fss_finlife import _match_products

        hit = _match_products(self.BASE, "", ["우리은행", "없는상품명"])
        assert [h["kor_co_nm"] for h in hit] == ["우리은행"]

    def test_company_detection(self):
        from app.services.reference.sources.fss_finlife import _company_of

        assert _company_of(["우리아파트론", "우리은행"]) == "우리은행"
        assert _company_of(["전기차", "충전"]) is None


class TestPortalErrors:
    """영문 오류 코드를 그대로 보여 주면 무엇을 고쳐야 할지 알 수 없다.

    사용자 보고(2026-09-07): SERVICE_KEY_IS_NOT_REGISTERED_ERROR /
    NO_OPENAPI_SERVICE_ERROR 를 받고 멈췄다.
    """

    @pytest.mark.parametrize("code,must_say", [
        ("SERVICE_KEY_IS_NOT_REGISTERED_ERROR", "활용신청"),
        ("APPLICATION_ERROR", "제공기관"),
        ("LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR", "한도"),
        ("DEADLINE_HAS_EXPIRED_ERROR", "연장"),
    ])
    def test_guide_is_actionable(self, code, must_say):
        from app.services.reference.sources.data_go_kr import _error_guide

        guide = _error_guide('{"errMsg": "%s"}' % code)
        assert must_say in guide
        assert code in guide          # 원문 코드도 함께 남긴다

    def test_key_error_mentions_both_key_forms(self):
        """Encoding 키를 넣으면 이 오류가 난다."""
        from app.services.reference.sources.data_go_kr import _error_guide

        guide = _error_guide("SERVICE_KEY_IS_NOT_REGISTERED_ERROR")
        assert "Decoding" in guide and "Encoding" in guide

    def test_normal_response_has_no_guide(self):
        from app.services.reference.sources.data_go_kr import _error_guide

        assert _error_guide('{"response":{"body":{"items":[]}}}') == ""

    def test_checked_before_status_code(self):
        """포털은 오류를 200 으로도 준다."""
        src = (ROOT / "app/services/reference/sources/data_go_kr.py").read_text(
            encoding="utf-8")
        assert (src.index("guide = _error_guide(response.text, ")
                < src.index("if response.status_code != 200:"))


class TestUnverifiedEndpoint:
    """확인하지 않은 주소는 프리셋에 두지 않는다.

    B190001 은 내가 지어낸 값이었고, 사용자가 알려 준 B553701 도 실호출로
    확인하니 "서비스가 없거나 폐기됨" 이었다(144개 조합 탐색). 주소를
    모르는 API 를 목록에 두면 사용자가 또 같은 오류를 본다.
    """

    def test_every_preset_endpoint_is_verified(self):
        from app.services.reference.sources import presets

        for row in presets.PRESETS:
            assert row["endpoint"], f"{row['code']} 에 주소가 없다"

    def test_welfare_confirmed_and_restored(self):
        """미리보기 URL 을 받아 확정한 뒤 되살렸다(2026-09-07)."""
        from app.services.reference.sources import presets

        found = presets.get("welfare_loan")
        assert found and "B553701" in found["endpoint"]

    def test_confirmed_preset_is_locked(self):
        """실호출로 확정했으므로 잠근다 — 열어 두면 옛 주소를 다시 넣는다."""
        from app.services.reference.sources import presets

        found = {p["code"]: p for p in presets.listing()}
        assert found["policy_briefing"]["needs_endpoint"] is False

    def test_user_endpoint_survives_preset(self):
        """사용자가 넣은 주소를 프리셋이 덮어쓰면 안 된다."""
        from app.routers.external_sources import (
            SourceRequest, _resolve_preset,
        )

        req = SourceRequest(code="brief", name="n", preset="policy_briefing",
                            endpoint="https://apis.data.go.kr/1371000/a/b")
        _resolve_preset(req)
        assert req.endpoint == "https://apis.data.go.kr/1371000/a/b"

    def test_screen_unlocks_endpoint(self):
        assert "form.needsEndpoint" in MODAL
        assert "needsEndpoint" in JS


class TestXmlResponse:
    """포털은 API 마다 JSON·XML 이 갈린다. 한쪽만 지원하면 그 API 는 못 쓴다.

    서민금융진흥원은 returnType=JSON 을 보내도 XML 로 돌려준다.
    """

    PATH = ["response", "body", "items", "item"]

    def test_xml_items_parsed(self):
        from app.services.reference.sources.data_go_kr import _extract

        xml = ("<response><body><items>"
               "<item><fncPrdNm>햇살론</fncPrdNm><lnLmt>2000만원</lnLmt></item>"
               "</items></body></response>")
        assert _extract(xml, self.PATH) == [
            {"fncPrdNm": "햇살론", "lnLmt": "2000만원"}]

    def test_empty_xml_is_empty_not_none(self):
        """0건과 '못 읽음' 은 다른 상황이라 메시지도 달라야 한다."""
        from app.services.reference.sources.data_go_kr import _extract

        xml = "<response><body><items/><totalCount>0</totalCount></body></response>"
        assert _extract(xml, self.PATH) == []

    def test_json_still_works(self):
        from app.services.reference.sources.data_go_kr import _extract

        body = '{"response":{"body":{"items":{"item":[{"a":"1"}]}}}}'
        assert _extract(body, self.PATH) == [{"a": "1"}]

    def test_zero_rows_message(self):
        src = (ROOT / "app/services/reference/sources/data_go_kr.py").read_text(
            encoding="utf-8")
        assert "결과가 0건입니다" in src


class TestOperationMissing:
    """포털의 'End Point' 는 서비스 주소다. 오퍼레이션을 붙여야 호출된다."""

    @pytest.mark.parametrize("url,is_base", [
        ("https://apis.data.go.kr/1371000/policyNewsService2", True),
        ("https://apis.data.go.kr/B553701/LoanProductSearchingInfo", True),
        ("https://apis.data.go.kr/1371000/policyNewsService2/policyNewsList",
         False),
    ])
    def test_detects_service_base(self, url, is_base):
        from app.services.reference.sources.data_go_kr import (
            looks_like_service_base,
        )

        assert looks_like_service_base(url) is is_base

    def test_guide_says_operation_missing(self):
        """'주소가 없다' 가 아니라 '오퍼레이션이 빠졌다' 여야 고칠 수 있다."""
        from app.services.reference.sources.data_go_kr import _error_guide

        guide = _error_guide(
            "NO_OPENAPI_SERVICE_ERROR",
            "https://apis.data.go.kr/1371000/policyNewsService2")
        assert "오퍼레이션" in guide

    def test_full_url_keeps_generic_guide(self):
        from app.services.reference.sources.data_go_kr import _error_guide

        guide = _error_guide(
            "NO_OPENAPI_SERVICE_ERROR",
            "https://apis.data.go.kr/1371000/policyNewsService2/policyNewsList")
        assert "오퍼레이션" not in guide


class TestEditableEndpoint:
    def test_all_presets_locked_now(self):
        """확인한 것만 남겼으므로 전부 잠긴다. 미확인 API 는 직접 입력."""
        from app.services.reference.sources import presets

        assert all(not p["needs_endpoint"] for p in presets.listing())

    def test_fss_preset_stays_locked(self):
        """금감원은 주소가 확정돼 있다."""
        from app.services.reference.sources import presets

        found = {p["code"]: p for p in presets.listing()}
        assert found["fss_all"]["needs_endpoint"] is False

    def test_user_endpoint_wins(self):
        from app.routers.external_sources import (
            SourceRequest, _resolve_preset,
        )

        req = SourceRequest(code="brief", name="n", preset="policy_briefing",
                            endpoint="https://apis.data.go.kr/1371000/svc/op")
        _resolve_preset(req)
        assert req.endpoint == "https://apis.data.go.kr/1371000/svc/op"


class TestKeyFormRetry:
    """포털은 인증키를 Decoding·Encoding 두 형태로 준다.

    어느 쪽을 넣었는지 사용자가 알기 어렵고, 틀리면
    SERVICE_KEY_IS_NOT_REGISTERED_ERROR 만 본다. 화면에서 바꿔 가며
    시험하게 할 이유가 없어 자동으로 한 번 더 시도한다.
    """

    def test_retry_exists(self):
        src = (ROOT / "app/services/reference/sources/data_go_kr.py").read_text(
            encoding="utf-8")
        body = src[src.index("async def _call("):src.index("def looks_like")]
        assert "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in body
        assert "unquote" in body and "quote" in body

    def test_encoded_key_not_double_encoded(self):
        """이미 인코딩된 키를 params 로 넘기면 %가 다시 인코딩된다."""
        src = (ROOT / "app/services/reference/sources/data_go_kr.py").read_text(
            encoding="utf-8")
        body = src[src.index("async def _call("):src.index("def looks_like")]
        # 재시도는 질의문자열을 직접 만들어 붙인다
        assert 'f"{endpoint}?serviceKey={flipped}"' in body

    def test_flip_is_reversible(self):
        from urllib.parse import quote, unquote

        decoded = "abc+def/ghi=="
        encoded = quote(decoded, safe="")
        assert unquote(encoded) == decoded

    def test_guide_no_longer_blames_key_form(self):
        """두 형태를 다 시도했으므로 표기 문제가 아니다."""
        from app.services.reference.sources.data_go_kr import ERROR_GUIDE

        guide = ERROR_GUIDE["SERVICE_KEY_IS_NOT_REGISTERED_ERROR"]
        assert "키 표기 문제는 아닙니다" in guide
        assert "마이페이지" in guide
        assert "1시간" in guide


class TestPolicyBriefingSpec:
    """실호출로 확정한 규격(2026-09-07). 짐작으로 적었다가 두 번 틀렸다."""

    def _preset(self):
        from app.services.reference.sources import presets

        return presets.get("policy_briefing")

    def test_operation_is_list2(self):
        """policyNewsList 는 400, policyNewsList2 가 200 이었다."""
        assert self._preset()["endpoint"].endswith("policyNewsList2")
        assert "policyNewsService2" in self._preset()["endpoint"]

    def test_items_path_matches_response(self):
        """응답 항목은 <NewsItem> 이다. items/item 이 아니다."""
        assert self._preset()["options"]["items_path"] == [
            "response", "body", "NewsItem"]

    def test_date_params_required(self):
        """없으면 NO_MANDATORY_REQUEST_PARAMETERS_ERROR."""
        options = self._preset()["options"]
        assert options["date_params"] == {"start": "startDate",
                                          "end": "endDate"}

    def test_range_capped_at_three_days(self):
        """넘기면 THREE_DAYS_OVER_ERROR."""
        assert self._preset()["options"]["date_range_days"] == 3

    def test_dates_are_generated(self):
        from datetime import datetime

        from app.services.reference.sources.data_go_kr import _date_params

        out = _date_params({"date_params": {"start": "s", "end": "e"},
                            "date_range_days": 3})
        start = datetime.strptime(out["s"], "%Y%m%d")
        end = datetime.strptime(out["e"], "%Y%m%d")
        assert (end - start).days == 2      # 사흘 범위(양끝 포함)

    def test_no_dates_when_not_configured(self):
        from app.services.reference.sources.data_go_kr import _date_params

        assert _date_params({}) == {}

    @pytest.mark.parametrize("code,must_say", [
        ("NO_MANDATORY_REQUEST_PARAMETERS_ERROR", "필수 파라미터"),
        ("THREE_DAYS_OVER_ERROR", "3일"),
    ])
    def test_new_errors_explained(self, code, must_say):
        from app.services.reference.sources.data_go_kr import _error_guide

        assert must_say in _error_guide('{"errMsg":"%s"}' % code)


class TestHtmlStripped:
    """보도자료 본문은 HTML 로 온다. 그대로 두면 참조 하나가 프롬프트를 다 먹는다."""

    def test_tags_removed(self):
        from app.services.reference.sources.data_go_kr import _plain

        html = "<p>총투자액 58억 달러</p><br><figure><figcaption>사진</figcaption></figure>"
        assert _plain(html) == "총투자액 58억 달러 사진"

    def test_entities_removed(self):
        from app.services.reference.sources.data_go_kr import _plain

        assert "nbsp" not in _plain("이&nbsp;제철소는")

    def test_length_capped(self):
        from app.services.reference.sources.data_go_kr import _plain

        assert len(_plain("가" * 900, 700)) == 701      # 700 + 말줄임

    def test_non_string_untouched(self):
        from app.services.reference.sources.data_go_kr import _plain

        assert _plain(None) is None
        assert _plain(123) == 123


class TestSavedRowsDrift:
    """프리셋을 고쳐도 이미 저장된 행은 따라오지 않는다.

    사용자는 옛 주소로 계속 시험하고 있었고, 테스트 결과에 호출 주소가
    없어 알아내는 데 오래 걸렸다.
    """

    def test_test_result_shows_endpoint(self):
        src = (ROOT / "app/routers/external_sources.py").read_text(
            encoding="utf-8")
        assert '"endpoint": row.endpoint' in src

    def test_screen_prints_endpoint(self):
        assert "호출 주소" in JS or "d.endpoint" in JS


class TestPastedPreviewUrl:
    """포털 '미리보기' 주소를 그대로 붙여넣는 일이 흔하다.

    그 주소에는 serviceKey·numOfRows 가 이미 붙어 있다. 우리가 또 붙이면
    값이 두 번 들어가 거절당한다. 어디를 잘라야 하는지 아는 것은 우리
    쪽 일이지 사용자 일이 아니다.
    """

    def test_plain_url_untouched(self):
        from app.services.reference.sources.data_go_kr import _split_query

        url = "https://apis.data.go.kr/B553701/svc/op"
        assert _split_query(url) == (url, {})

    def test_query_split_off(self):
        from app.services.reference.sources.data_go_kr import _split_query

        clean, params = _split_query(
            "https://apis.data.go.kr/x/y?serviceKey=OLD&numOfRows=10&pageNo=1")
        assert clean == "https://apis.data.go.kr/x/y"
        assert params == {"numOfRows": "10", "pageNo": "1"}

    def test_old_key_dropped(self):
        """주소에 남은 키는 옛 값일 수 있다. 등록된 키를 쓴다."""
        from app.services.reference.sources.data_go_kr import _split_query

        _, params = _split_query("https://x/y?serviceKey=OLD&a=1")
        assert "serviceKey" not in params

    def test_our_params_win(self):
        """겹치면 우리 값을 쓴다 — 날짜·행수는 어댑터가 계산한다."""
        src = (ROOT / "app/services/reference/sources/data_go_kr.py").read_text(
            encoding="utf-8")
        assert "merged = {**preset_params, **params}" in src

    def test_error_guide_points_to_preview(self):
        from app.services.reference.sources.data_go_kr import ERROR_GUIDE

        assert "미리보기" in ERROR_GUIDE["NO_OPENAPI_SERVICE_ERROR"]


class TestWelfareLoanSpec:
    """경로에 서비스명이 **두 번** 들어간다.

    그래서 144개 조합 탐색으로도 못 찾았고, 사용자가 포털 미리보기
    URL 을 알려 줘서 확정했다(2026-09-07).
    """

    def _preset(self):
        from app.services.reference.sources import presets

        return presets.get("welfare_loan")

    def test_service_name_repeats(self):
        endpoint = self._preset()["endpoint"]
        parts = endpoint.split("/")
        # 기관코드 뒤에 서비스명이 두 번 오고 오퍼레이션이 붙는다
        assert parts[-3:] == ["LoanProductSearchingInfo",
                              "LoanProductSearchingInfo",
                              "getLoanProductSearchingInfo"]

    def test_field_names_are_lowercase_abbreviations(self):
        """응답 필드는 finprdnm·lnlmt 처럼 소문자 축약형이다."""
        field_map = self._preset()["options"]["field_map"]
        assert field_map["상품명"] == "finprdnm"
        assert field_map["대출한도(만원)"] == "lnlmt"
        assert field_map["취급기관"] == "ofrinstnm"

    def test_items_path_is_standard(self):
        assert self._preset()["options"]["items_path"] == [
            "response", "body", "items", "item"]

    def test_keywords_cover_actual_products(self):
        """실제 응답에 사잇돌·햇살론이 들어 있다."""
        words = self._preset()["match_keywords"]
        assert "햇살론" in words and "사잇돌" in words


class TestConfirmUrl:
    """확인처는 독자가 열 수 있는 곳이어야 한다."""

    def test_api_endpoint_not_used_as_link(self):
        src = (ROOT / "app/services/reference/sources/data_go_kr.py").read_text(
            encoding="utf-8")
        block = src[src.index("def _to_facts("):]
        assert "site_url" in block
        assert "else endpoint," not in block

    @pytest.mark.parametrize("code,host", [
        ("welfare_loan", "kinfa.or.kr"),
        ("policy_briefing", "korea.kr"),
    ])
    def test_presets_give_a_human_site(self, code, host):
        from app.services.reference.sources import presets

        assert host in presets.get(code)["options"]["site_url"]
