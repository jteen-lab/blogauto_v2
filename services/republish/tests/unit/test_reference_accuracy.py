"""참조자료 정확도 — 질의·관문·소스·요약.

2026-09-06 머니조아 실측: 제목 "우리은행 우리아파트론 대출 금리와 방식" 으로
모은 자료 3건이 **신용대출 일반 · 주담대 일반 · 우리은행 대표전화 안내** 였다.
세 건 다 그 상품이 아니다. 관련성을 판단하는 지점이 한 곳도 없었다.
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TITLE = "우리은행 우리아파트론 대출 금리와 방식"


def _result(title, desc="", postdate=""):
    from types import SimpleNamespace

    return SimpleNamespace(title=title, description=desc, link="x",
                           postdate=postdate)


def _doc(title, content, url="u"):
    from types import SimpleNamespace

    return SimpleNamespace(title=title, content=content, url=url)


class TestQueryRewrite:
    """① 제목 문장을 그대로 검색어로 쓰지 않는다."""

    def test_entity_leads_the_query(self):
        from app.services.reference.query_builder import build

        plan = build(TITLE)
        assert plan.entities[0] == "우리아파트론"
        assert plan.primary.startswith("우리아파트론")

    def test_query_is_short(self):
        """긴 문장을 주면 결과가 급격히 줄고, 적게 나온 결과는 엉뚱하다."""
        from app.services.reference.query_builder import build

        assert len(build(TITLE).primary.split()) <= 3

    def test_fallbacks_widen(self):
        from app.services.reference.query_builder import build

        queries = build(TITLE).queries()
        assert len(queries) >= 2
        assert queries[-1] == "우리아파트론"      # 가장 넓은 질의

    def test_verb_endings_are_not_entities(self):
        """'확인하세요' 가 상품명보다 길어 핵심 개체로 뽑히던 자리."""
        from app.services.reference.query_builder import build

        plan = build("무직자도 가능한 신용대출 비상금 확인하세요")
        assert "확인하세요" not in plan.entities
        assert plan.entities[0] == "신용대출"

    def test_no_mid_word_truncation(self):
        """예전에는 실패 시 search_query[:20] 으로 잘라 재시도했다.

        낱말 중간에서 끊겨 엉뚱한 검색어가 됐다. 주석에는 남아 있어도
        되지만 **실행되는 코드**에는 없어야 한다.
        """
        src = (ROOT / "app/services/generation/reference_collector.py"
               ).read_text(encoding="utf-8")
        code = "\n".join(line for line in src.splitlines()
                         if not line.lstrip().startswith("#"))
        assert "search_query[:20]" not in code
        assert "plan.queries()" in code

    def test_empty_title_is_safe(self):
        from app.services.reference.query_builder import build

        assert build("").queries() == []


class TestGates:
    """② 관련성 관문 — 무관한 자료는 자료가 없는 것보다 나쁘다."""

    def _entities(self):
        from app.services.reference.query_builder import build

        return build(TITLE).entities

    def test_phone_page_is_dropped(self):
        """이번 사고의 당사자."""
        from app.services.reference.relevance import filter_search_results

        results = [
            _result("우리아파트론 금리 안내", "우리은행"),
            _result("우리 아파트론 상환방식", "원리금균등"),
            _result("우리은행 대표전화 안내", "1588-5000"),
            _result("신용대출이란", "담보 없이"),
        ]
        kept = [r.title for r in filter_search_results(
            results, self._entities(), keep_min=2)]
        assert "우리은행 대표전화 안내" not in kept
        assert "우리아파트론 금리 안내" in kept

    def test_generic_entity_does_not_let_everything_through(self):
        """'대출' 같은 일반어를 OR 로 쓰면 아무것도 안 걸러진다."""
        from app.services.reference.relevance import filter_search_results

        results = [_result("우리아파트론 안내"), _result("신용대출이란"),
                   _result("주택담보대출 LTV"), _result("우리 아파트론 비교")]
        kept = filter_search_results(results, self._entities(), keep_min=2)
        assert len(kept) == 2      # 우리아파트론 둘만

    def test_falls_back_when_nothing_matches(self):
        """전부 걸러 0건이 되면 개체 추출이 빗나간 것이다."""
        from app.services.reference.relevance import filter_search_results

        results = [_result("전혀 다른 글"), _result("또 다른 글")]
        assert len(filter_search_results(results, ["없는개체"],
                                         keep_min=1)) == 2

    def test_no_entities_means_no_filtering(self):
        from app.services.reference.relevance import filter_search_results

        results = [_result("아무거나")]
        assert len(filter_search_results(results, [])) == 1

    def test_body_gate(self):
        from app.services.reference.relevance import filter_documents

        docs = [_doc("안내", "우리아파트론 한도는 …"),
                _doc("딴글", "오늘 날씨는 맑습니다")]
        kept = filter_documents(docs, self._entities(), keep_min=1)
        assert [d.title for d in kept] == ["안내"]

    def test_spacing_is_ignored(self):
        """'우리 아파트론' 과 '우리아파트론' 은 같은 말이다."""
        from app.services.reference.relevance import matches

        assert matches("우리 아파트론 상품", ["우리아파트론"])

    @pytest.mark.parametrize("text,expected", [
        ("관련 없음", True),
        ("관련 없음 — 전화번호 안내입니다", True),
        ("이 문서는 관련 없음이 아니다", False),
        ("한도는 5억원입니다", False),
    ])
    def test_no_match_detection(self, text, expected):
        from app.services.reference.relevance import is_no_match

        assert is_no_match(text) is expected


class TestFreshness:
    """⑤ 금리·제도는 1년 전 정보가 틀린 정보다."""

    def test_newest_first(self):
        from app.services.reference.relevance import sort_by_freshness

        rows = [_result("old", postdate="20240101"),
                _result("new", postdate="20260901"),
                _result("mid", postdate="20250601")]
        assert [r.title for r in sort_by_freshness(rows)] == \
            ["new", "mid", "old"]

    def test_undated_goes_last_not_dropped(self):
        """날짜가 없다고 오래된 것은 아니다 — 버리지는 않는다."""
        from app.services.reference.relevance import sort_by_freshness

        rows = [_result("no date"), _result("dated", postdate="20260101")]
        out = [r.title for r in sort_by_freshness(rows)]
        assert out == ["dated", "no date"]


class TestRegistry:
    """③a 소스 선택은 코드가 아니라 데이터로."""

    def _sources(self):
        from types import SimpleNamespace

        return [
            SimpleNamespace(code="fss", adapter="fss_finlife",
                            match_topics=["금융/대출"],
                            match_keywords=["대출", "금리"]),
            SimpleNamespace(code="briefing", adapter="data_go_kr",
                            match_topics=["정부지원금/복지"],
                            match_keywords=["정책", "지원금"]),
            SimpleNamespace(code="unset", adapter="data_go_kr",
                            match_topics=[], match_keywords=[]),
        ]

    def test_topic_match(self):
        from app.services.reference.sources.registry import pick

        picked = pick(self._sources(), TITLE, ["금융/대출", "대출 정보"])
        assert [s.code for s in picked] == ["fss"]

    def test_unrelated_niche_calls_nothing(self):
        """요리 글에서 금융 API 를 부르면 안 된다."""
        from app.services.reference.sources.registry import pick

        assert pick(self._sources(), "김치찌개 끓이는 법",
                    ["음식/레시피"]) == []

    def test_keyword_match_without_topic(self):
        from app.services.reference.sources.registry import pick

        picked = pick(self._sources(), "2026 청년 지원금 신청", ["기타"])
        assert [s.code for s in picked] == ["briefing"]

    def test_unconfigured_source_never_fires(self):
        """조건이 비면 '아무 때나' 가 아니라 '안 쓴다' 다."""
        from app.services.reference.sources.registry import pick

        picked = pick(self._sources(), "아무 제목", ["아무 주제"])
        assert all(s.code != "unset" for s in picked)


class TestFssAdapter:
    """③c 상품이 안 맞으면 **빈손으로** 돌아온다."""

    def _base(self):
        return [
            {"fin_prdt_cd": "A", "fin_prdt_nm": "우리아파트론",
             "kor_co_nm": "우리은행", "loan_lmt": "5억원"},
            {"fin_prdt_cd": "B", "fin_prdt_nm": "행복드림론",
             "kor_co_nm": "국민은행", "loan_lmt": "3억원"},
        ]

    def test_picks_the_right_product(self):
        from app.services.reference.sources.fss_finlife import _match_products

        hit = _match_products(self._base(), "우리아파트론", ["우리아파트론"])
        assert [p["fin_prdt_nm"] for p in hit] == ["우리아파트론"]

    def test_returns_nothing_when_no_match(self):
        """비슷한 상품을 대신 주면 사실이 아닌 글이 된다."""
        from app.services.reference.sources.fss_finlife import _match_products

        assert _match_products(self._base(), "없는상품", ["없는상품"]) == []

    def test_no_entities_returns_nothing(self):
        """목록 첫 상품을 주면 그게 곧 엉뚱한 상품이다."""
        from app.services.reference.sources.fss_finlife import _match_products

        assert _match_products(self._base(), "", []) == []

    def test_cheapest_option_chosen(self):
        from app.services.reference.sources.fss_finlife import _cheapest

        best = _cheapest([{"lend_rate_min": "5.1"},
                          {"lend_rate_min": "4.2"}])
        assert best["lend_rate_min"] == "4.2"


class TestDigest:
    """④ 제목과 함께 한 번에 읽는다."""

    def test_prompt_carries_the_title(self):
        """이게 없어서 문서의 주된 내용만 요약됐다."""
        from app.services.reference.digest import build_prompt

        prompt = build_prompt(TITLE, [_doc("안내", "내용" * 50)])
        assert TITLE in prompt

    def test_forbids_inventing_numbers(self):
        from app.services.reference.digest import build_prompt

        prompt = build_prompt(TITLE, [_doc("안내", "내용" * 50)])
        assert "문서에 있는 값만" in prompt
        assert "관련 없음" in prompt

    def test_conflicts_are_surfaced(self):
        from app.services.reference.digest import build_prompt

        prompt = build_prompt(TITLE, [_doc("a", "내용" * 50),
                                      _doc("b", "내용" * 50)])
        assert "값이 다르면" in prompt

    def test_empty_documents_yield_no_prompt(self):
        from app.services.reference.digest import build_prompt

        assert build_prompt(TITLE, []) == ""
        assert build_prompt(TITLE, [_doc("빈글", "")]) == ""

    def test_injection_tells_what_to_do(self):
        """딱지 없이 자료만 던지면 AI 가 베낄지 무시할지 스스로 정한다."""
        from app.services.reference.digest import to_prompt_injection

        text = to_prompt_injection("한도 5억 [1]", ["http://a"])
        assert "그대로 옮기지 마세요" in text
        assert "지어내지" in text
        assert "출처 URL 은 본문에 쓰지 마세요" in text


class TestPlaceholderSafetyNet:
    """빌더가 {reference_materials} 를 몰라 12개 모듈이 자료를 버렸다."""

    def test_appended_when_missing(self):
        src = (ROOT / "app/services/generation/content_generator_helper.py"
               ).read_text(encoding="utf-8")
        assert ('if reference_injection and "{reference_materials}" '
                'not in prompt_template:') in src

    def test_appended_before_directives(self):
        """분량 지시문이 마지막에 읽혀야 '위의 언급보다 우선' 이 뜻을 갖는다."""
        src = (ROOT / "app/services/generation/content_generator_helper.py"
               ).read_text(encoding="utf-8")
        assert (src.index('not in prompt_template:')
                < src.index("if not skip_length_directive:"))

    def test_builder_now_advertises_it(self):
        js = (ROOT / "app/static/js/modules/prompt-form-template-sections.js"
              ).read_text(encoding="utf-8")
        assert "{reference_materials}" in js

    def test_default_template_includes_it(self):
        js = (ROOT / "app/static/js/modules/prompt-form.js").read_text(
            encoding="utf-8")
        block = js[js.index("userPromptTemplate:"):]
        assert "{reference_materials}" in block[:400]


class TestResultAssembly:
    def test_official_comes_first(self):
        """공식 값과 웹문서가 다르면 공식을 따라야 한다."""
        from app.services.generation.reference_collector import (
            ReferenceCollectionResult,
        )

        out = ReferenceCollectionResult(
            count=2, digest="웹문서 정리", official="[공식 자료 — 금감원]")
        text = out.to_prompt_injection()
        assert text.index("공식 자료") < text.index("웹문서 정리")

    def test_empty_yields_empty(self):
        from app.services.generation.reference_collector import (
            ReferenceCollectionResult,
        )

        assert ReferenceCollectionResult(count=0).to_prompt_injection() == ""
