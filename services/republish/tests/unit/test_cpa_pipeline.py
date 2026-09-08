"""CPA 파이프라인 — 규칙 추출부터 발행 전 검증까지.

규칙 유형 체계는 실제 오퍼 7건(의료·법률·생활·통신·금융·교육) 80건을
분해해 얻었다. 게이트는 업종을 모르고 유형만 안다.
"""
import pathlib
from types import SimpleNamespace as NS

import pytest

from app.services.cpa import conflicts, gate, lexicon, prompt, subid
from app.services.cpa.consult_page import MIN_CHARS, build as build_page
from app.services.cpa.rule_extractor import _lines, _parse_response, _valid
from app.services.cpa.title_builder import build as build_titles

ROOT = pathlib.Path(__file__).resolve().parents[2]


def rule(**kw):
    base = {"type": "must_not_include", "scope": "all", "target": "",
            "value": "", "source_quote": "", "severity": "block"}
    base.update(kw)
    return base


def offer(**kw):
    base = dict(id=1, name="테스트 오퍼", rules=[], conversion={},
                ftc_notice="이 포스팅은 애드릭스 수익이 발생합니다.",
                landing_url="https://ex.com/l", subid_param=None,
                is_deleted=False)
    base.update(kw)
    return NS(**base)


# ── P2 규칙 추출 ────────────────────────────────────────

class TestExtractInput:
    def test_fixed_sections_are_not_sent_to_ai(self):
        """고정 서식은 offer_parser 담당이다. AI 에게 두 번 시키지 않는다."""
        text = "홍보 부탁드립니다\n금지어는 최고입니다\n전환 정보\n미승인조건 : 오류"
        lines = _lines(text)
        assert not any("미승인조건" in x for x in lines)

    def test_decoration_lines_dropped(self):
        assert _lines("※※※\n----\n1.\n실제 규칙 문장입니다") == [
            "실제 규칙 문장입니다"]


class TestExtractOutput:
    def test_unknown_type_rejected(self):
        assert _valid({"type": "made_up", "value": "x"}, []) is None

    def test_unknown_scope_widens(self):
        """범위를 모르면 가장 넓게 잡는다."""
        got = _valid({"type": "must_not_include", "scope": "???",
                      "value": "최고"}, [])
        assert got["scope"] == "all"

    def test_source_quote_attached(self):
        """규칙이 원문 어디서 왔는지 못 되짚으면 사람이 확인할 수 없다."""
        lines = ["첫 줄", "최고 라는 말을 쓰지 마세요"]
        got = _valid({"type": "must_not_include", "value": "최고", "line": 2},
                     lines)
        assert got["source_quote"] == "최고 라는 말을 쓰지 마세요"

    def test_garbage_response_is_empty(self):
        assert _parse_response("설명만 하고 JSON 이 없음", []) == []

    def test_extracts_json_from_prose(self):
        text = '앞말 [{"type":"must_include","value":"광고책임변호사"}] 뒷말'
        assert len(_parse_response(text, [])) == 1


# ── 업종 사전 ──────────────────────────────────────────

class TestLexicon:
    @pytest.mark.parametrize("text,expected", [
        ("부산 서면 안과에서 라식 수술", "medical"),
        ("법무법인 중정 개인회생 상담", "legal"),
        ("주식담보대출 금리 안내", "finance"),
    ])
    def test_vertical_detection(self, text, expected):
        assert expected in lexicon.verticals_in(text)

    def test_no_vertical_for_plain_text(self):
        assert lexicon.verticals_in("이사 견적 비교") == []

    def test_legal_rules_carry_their_basis(self):
        """왜 막혔는지 모르면 사람이 판단할 수 없다."""
        rules = lexicon.legal_rules(["medical"])
        assert rules and all("[법정]" in r["source_quote"] for r in rules)
        assert any("의료법" in r["source_quote"] for r in rules)

    def test_generic_words_only_warn(self):
        """차단하면 광고주가 준 문구까지 막힌다."""
        assert all(r["severity"] == "warn" for r in lexicon.generic_warnings())


# ── 충돌 감지 ──────────────────────────────────────────

class TestConflicts:
    def test_offer_contradicting_itself(self):
        """법무법인 중정은 '전문' 을 금지하면서 소개문에 쓴다."""
        raw = ("7. '무료', '전문, 전담' 키워드 금지\n"
               "전문화된 법률서비스로 의뢰인의 개별적 특성에 맞는 전략을 세웁니다")
        found = conflicts.detect(raw, [rule(
            value="전문", source_quote="7. '무료', '전문, 전담' 키워드 금지")])
        assert len(found) == 1
        assert found[0]["word"] == "전문"
        assert "확인이 필요합니다" in found[0]["hint"]

    def test_rule_line_itself_is_not_a_conflict(self):
        """금지 규칙을 만든 그 줄은 당연히 그 낱말을 담고 있다."""
        raw = "'최고' 라는 표현 금지"
        assert conflicts.detect(raw, [rule(
            value="최고", source_quote="'최고' 라는 표현 금지")]) == []

    def test_legal_word_in_advertiser_copy(self):
        """현금사은품은 금지사항이 없는데 소개문에 '최고' 가 있다."""
        found = conflicts.legal_vs_offer([
            rule(type="content_source", value="전국 최고 현금지급 센터"),
            rule(value="최고", source_quote="[법정] 의료법 제56조 — 최상급 표현"),
        ])
        assert len(found) == 1


# ── P3 제목 ────────────────────────────────────────────

class TestTitles:
    def test_axis_becomes_titles(self):
        got = build_titles(offer(rules=[
            rule(type="content_axis", value="개인회생, 개인회생신청자격")]))
        assert any("개인회생" in t for t in got["titles"])
        assert len(got["titles"]) >= 5

    def test_offer_banned_word_not_in_title(self):
        got = build_titles(offer(rules=[
            rule(type="content_axis", value="무료상담"),
            rule(value="무료", scope="title"),
        ]))
        assert all("무료" not in t for t in got["titles"])
        assert got["skipped"], "걸린 후보를 보여줘야 왜 적은지 안다"

    def test_review_titles_never_built(self):
        """의료는 후기가 의료법 위반이다. 오퍼가 안 적어도 만들지 않는다."""
        got = build_titles(offer(rules=[
            rule(type="content_axis", value="라식")]))
        assert all("후기" not in t for t in got["titles"])

    def test_offer_without_axis_still_works(self):
        """이사스토리·카바딜러는 추천 키워드가 없다."""
        got = build_titles(offer(name="[자격증]산지식물자원관리사"))
        assert got["titles"]

    def test_limit_respected(self):
        got = build_titles(offer(rules=[rule(
            type="content_axis",
            value="개인회생,개인파산,워크아웃,신용회복")]), limit=7)
        assert len(got["titles"]) == 7

    def test_single_char_keywords_dropped(self):
        """한 글자는 키워드가 아니다."""
        got = build_titles(offer(name="오퍼", rules=[
            rule(type="content_axis", value="a,b,c")]))
        assert all("a " not in t for t in got["titles"])


# ── P4 프롬프트 ────────────────────────────────────────

class TestPrompt:
    def test_notice_goes_first(self):
        text = prompt.build(offer())
        assert "본문 맨 앞" in text
        assert "애드릭스 수익이 발생합니다" in text

    def test_no_facts_means_no_numbers(self):
        """사실 원천이 없으면 수치를 못 쓰게 한다. 없으면 AI 가 지어낸다."""
        text = prompt.build(offer())
        assert "수치를 쓰지 마세요" in text

    def test_facts_present_changes_instruction(self):
        text = prompt.build(offer(rules=[
            rule(type="content_source", value="월 0.4%대 금리")]))
        assert "여기 있는 것만" in text
        assert "수치를 쓰지 마세요" not in text

    def test_reject_reasons_become_targeting(self):
        """대상이 아닌 사람을 부르면 미승인 DB 가 되어 수익이 0 이다."""
        text = prompt.build(offer(conversion={
            "reject_reasons": ["미성년자", "해외거주자"]}))
        assert "미성년자" in text and "상담이 어렵습니다" in text


# ── P5 게이트 ──────────────────────────────────────────

class TestGate:
    BODY = "이 포스팅은 애드릭스 수익이 발생합니다.\n본문입니다."

    def test_passes_clean_content(self):
        assert gate.check(offer(), "제목", self.BODY).blocked is False

    def test_missing_notice_blocks(self):
        found = gate.check(offer(), "제목", "문구 없는 본문")
        assert found.blocked
        assert "위법" in found.summary()

    def test_notice_at_the_end_blocks(self):
        """2024-12-01 개정으로 끝부분 게재가 막혔다."""
        body = "가" * 900 + "\n이 포스팅은 애드릭스 수익이 발생합니다."
        found = gate.check(offer(), "제목", body)
        assert found.blocked
        assert "앞부분" in found.summary()

    def test_ad_prefix_in_title_is_accepted(self):
        body = "가" * 900 + "\n이 포스팅은 애드릭스 수익이 발생합니다."
        assert gate.check(offer(), "[광고] 제목", body).blocked is False

    def test_banned_word(self):
        found = gate.check(offer(rules=[rule(value="최고")]),
                           "최고의 선택", self.BODY)
        assert found.blocked and "최고" in found.summary()

    def test_scope_keeps_body_free(self):
        """스탁론은 '금리' 를 금지키워드로 두면서 본문에 '월 0.4%대' 를 쓴다."""
        o = offer(rules=[rule(value="금리", scope="title")])
        assert gate.check(o, "주식대출 조건", self.BODY + " 금리 안내").blocked is False
        assert gate.check(o, "금리 비교", self.BODY).blocked is True

    def test_required_phrase_missing(self):
        o = offer(rules=[rule(type="must_include", value="광고책임변호사 이종욱")])
        assert gate.check(o, "제목", self.BODY).blocked is True

    def test_pattern_catches_numbers(self):
        o = offer(rules=[rule(type="pattern", value=r"\d+%\s*할인")])
        assert gate.check(o, "제목", self.BODY + " 60% 할인").blocked is True

    def test_conditional(self):
        o = offer(rules=[rule(type="conditional", target="시나가와",
                              value="연구결과")])
        assert gate.check(o, "제목", self.BODY + " 시나가와 자료").blocked is True
        assert gate.check(
            o, "제목", self.BODY + " 시나가와 연구결과").blocked is False

    def test_link_policy(self):
        o = offer(rules=[rule(type="link_policy", value="타사")])
        found = gate.check(o, "제목", self.BODY + " https://other.com/x",
                           ["https://other.com/x"])
        assert found.blocked

    def test_unmachine_checkable_goes_to_review(self):
        """advisory 는 검사하지 않는다. 대신 사람 목록에 올린다."""
        o = offer(rules=[rule(type="advisory", value="성의 있게 작성")])
        found = gate.check(o, "제목", self.BODY)
        assert found.blocked is False
        assert len(found.reviews) == 1

    def test_warn_does_not_block(self):
        o = offer(rules=[rule(value="무조건", severity="warn")])
        found = gate.check(o, "제목", self.BODY + " 무조건 됩니다")
        assert found.blocked is False
        assert found.violations

    def test_reason_names_the_rule_source(self):
        o = offer(rules=[rule(value="최고", source_quote="4. 최상급 표현 금지")])
        found = gate.check(o, "최고", self.BODY)
        assert found.violations[0].source_quote == "4. 최상급 표현 금지"


# ── P6 상담 페이지 ─────────────────────────────────────

class TestConsultPage:
    def test_notice_first(self):
        html = build_page(offer(), "https://ex.com/l")["html"]
        assert html.index("애드릭스 수익") < html.index("<h2>")

    def test_thin_page_flagged(self):
        """바깥 링크를 다 없애도 쓸모 있어야 한다. 아니면 브릿지 페이지다."""
        found = build_page(offer(), "https://ex.com/l")
        assert found["thin"] is True
        assert any("분량" in m for m in found["missing"])

    def test_facts_fill_the_page(self):
        o = offer(rules=[rule(type="content_source", value="가" * 200)] * 6)
        assert build_page(o, "https://ex.com/l", "도입부")["chars"] >= MIN_CHARS

    def test_no_facts_avoids_numbers(self):
        html = build_page(offer(), "https://ex.com/l")["html"]
        assert "상담에서 확인" in html

    def test_eligibility_filters_out_generic_reasons(self):
        """'오류·중복' 은 독자에게 알릴 내용이 아니다."""
        o = offer(conversion={"reject_reasons": ["오류", "중복", "미성년자"]})
        html = build_page(o, "https://ex.com/l")["html"]
        assert "미성년자" in html and "중복" not in html

    def test_sponsored_link(self):
        html = build_page(offer(), "https://ex.com/l")["html"]
        assert 'rel="nofollow sponsored"' in html


# ── P7 서브아이디 ──────────────────────────────────────

class TestSubid:
    def test_round_trip(self):
        value = subid.make(12, 345, 7)
        assert subid.parse(value) == {"offer_id": 12, "post_id": 345,
                                      "blog_id": 7}

    def test_applied_to_url(self):
        url = subid.apply("https://ex.com/l?a=1", offer(id=3), 9, 2)
        assert "subid=o3-p9-b2" in url and "a=1" in url

    def test_not_duplicated(self):
        once = subid.apply("https://ex.com/l", offer(id=3), 9)
        twice = subid.apply(once, offer(id=3), 9)
        assert twice.count("subid=") == 1

    def test_custom_param(self):
        url = subid.apply("https://ex.com/l", offer(id=3, subid_param="p_id"),
                          9)
        assert "p_id=o3-p9" in url


# ── 파이프라인 연결 ────────────────────────────────────

class TestWiring:
    SRC = (ROOT / "app/services/generation/generator.py").read_text(
        encoding="utf-8")

    def test_unusable_offer_blocks_generation(self):
        assert "CPA 오퍼가 확인되지 않았거나" in self.SRC

    def test_offer_lookup_failure_blocks(self):
        """오퍼를 못 읽었는데 통과시키면 규칙 없는 글이 나간다."""
        block = self.SRC[self.SRC.index("async def _cpa_offer"):]
        block = block[:block.index("async def _cpa_check")]
        assert "return False" in block

    def test_directive_reaches_the_prompt(self):
        assert "cpa_directive)" in self.SRC

    def test_gate_runs_before_publish(self):
        assert self.SRC.index("_cpa_check") < self.SRC.index("gate_cfg =")

    def test_titles_are_scoped_to_the_offer(self):
        """CPA 제목이 일반 재고에 섞이면 애드센스 블로그가 뽑아 쓴다."""
        model = (ROOT / "app/models/title.py").read_text(encoding="utf-8")
        assert "cpa_offer_id" in model
        api = (ROOT / "app/routers/cpa.py").read_text(encoding="utf-8")
        assert "cpa_offer_id=offer_id" in api
