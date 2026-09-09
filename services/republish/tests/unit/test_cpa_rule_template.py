"""정형 규칙 항목 — 무엇이 비었는지 보이게 한다.

규칙을 유형별로만 늘어놓으면 "이 오퍼엔 원래 없는 것" 과 "AI 가 놓친 것" 이
구분되지 않는다. 요구가 가장 많은 오퍼(부산ㅎr늘안과, 규칙 22건·13유형)를
기준으로 칸을 미리 만들고, 빈 칸을 빈 채로 보여 준다.
"""
import pathlib

import pytest

from app.services.cpa.rule_template import (
    SLOTS, assign, critical_missing,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]


def R(kind, value, quote="", target=""):
    return {"type": kind, "scope": "all", "value": value, "target": target,
            "source_quote": quote, "severity": "block"}


# 안과 오퍼에서 나오는 규칙들
EYE = [
    R("must_include", "해당 포스팅은 부산ㅎr늘안과 주최로 진행되는 홍보성 내용",
      "8. 의료광고 주체 명시"),
    R("position", "본문 첫 부분", "제목 앞에 [광고] 표시"),
    R("must_not_include", "부산하늘안과", "0. 안과명 풀네임으로 사용 금지"),
    R("must_not_include", "강남점", "서울점,강남점,부산점 단어 사용 금지"),
    R("must_not_include", "최고", "4. 최상급 표현 사용불가"),
    R("must_not_include", "스마일라식", "5-5) 본원에 없는 수술프로그램"),
    R("forbidden_topic", "후기·치료경험담", "6. 수술후기 광고는 불법"),
    R("pattern", r"\d+%\s*할인", "2-1) 과도한 할인율 사용금지"),
    R("replace", "검사는 지원해드립니다", "사용권장 문구", "정밀검사 무료"),
    R("conditional", "시나가와 라식센터 연구결과", "출처가 꼭 들어가야", "시나가와"),
    R("channel", "포털사이트 검색광고 금지", "7. 포털사이트 검색광고 금지"),
    R("asset", "심의 받은 이미지 배너", "10. 심의 받은 이미지 배너 사용"),
    R("conversion", "미승인: 오류,결번,중복", "전환 정보"),
    R("content_axis", "라식잘하는곳, 부산라식", "*추천 키워드"),
    R("content_source", "부산 서면역 10번출구 1분거리", "*내용"),
    R("advisory", "성의 있는 홍보 게시물", "성의 있는 홍보 게시물 등록 부탁"),
]


class TestAssignment:
    """유형만 보고 넣으면 첫 칸으로 다 몰린다(실측으로 잡음)."""

    def setup_method(self):
        self.out = assign(EYE, ftc_notice="이 포스팅은 애드릭스 수익이 발생합니다.")
        self.by = {s["key"]: s for s in self.out["slots"]}

    @pytest.mark.parametrize("key,needle", [
        ("ftc_notice", "애드릭스 수익"),
        ("subject_notice", "주최"),
        ("brand_form", "부산하늘안과"),
        ("confusable", "강남점"),
        ("banned_words", "최고"),
        ("absent_items", "스마일라식"),
        ("banned_topics", "후기"),
        ("banned_patterns", "할인"),
        ("softening", "지원해드립니다"),
        ("conditional", "시나가와"),
        ("channels", "검색광고"),
        ("assets", "배너"),
        ("targeting", "미승인"),
        ("keywords", "라식잘하는곳"),
        ("facts", "서면역"),
        ("advisory", "성의"),
    ])
    def test_lands_in_the_right_slot(self, key, needle):
        values = " ".join(f"{r.get('value')} {r.get('target')}"
                          for r in self.by[key]["rules"])
        assert needle in values, f"{key} 칸이 비었거나 다른 값이 들어갔다"

    def test_banned_word_is_not_a_brand_rule(self):
        """'최고' 가 브랜드 표기 칸으로 가면 안 된다."""
        brand = " ".join(r["value"] for r in self.by["brand_form"]["rules"])
        assert "최고" not in brand

    def test_counts(self):
        assert self.out["filled"] >= 16
        assert self.out["total"] == len(SLOTS)


class TestEmptySlots:
    """빈 칸을 감추지 않는다 — 원래 없는 건지 놓친 건지 사람이 본다."""

    def test_missing_listed(self):
        out = assign([R("content_axis", "이사견적")])
        assert "banned_words" in out["missing"]
        assert out["filled"] == 1

    def test_slot_keeps_its_hint(self):
        out = assign([])
        empty = [s for s in out["slots"] if not s["count"]]
        assert all(s["hint"] for s in empty), "빈 칸도 무엇을 넣을지 알려야 한다"

    def test_critical_missing_is_reported(self):
        """대가성 문구가 없으면 위법이다. 조용히 넘기면 안 된다."""
        assert "공정위 대가성 문구" in critical_missing(assign([]))

    def test_ftc_from_fixed_section_fills_the_slot(self):
        out = assign([], ftc_notice="이 포스팅은 애드릭스 수익이 발생합니다.")
        assert critical_missing(out) == ["문구 위치"]


class TestExtras:
    """칸에 없는 규칙을 버리면 그 요구가 조용히 사라진다."""

    def test_unknown_type_goes_to_extras(self):
        out = assign([R("format", "글자 크기 1/3 이상")])
        assert len(out["extras"]) == 1

    def test_known_types_never_become_extras(self):
        out = assign(EYE)
        assert out["extras"] == []


class TestWiring:
    API = (ROOT / "app/routers/cpa.py").read_text(encoding="utf-8")
    HTML = (ROOT / "app/templates/collection/_cpa_offers.html").read_text(
        encoding="utf-8")
    JS = (ROOT / "app/static/js/cpa/offers.js").read_text(encoding="utf-8")

    def test_detail_returns_template(self):
        assert '"template": template' in self.API

    def test_screen_shows_slots_and_hints(self):
        assert "정형 항목" in self.HTML and "sl.hint" in self.HTML

    def test_screen_shows_extras(self):
        assert "정형 칸에 없는 규칙" in self.HTML

    def test_blog_picker_removed(self):
        """블로그 연결은 여기서 다루지 않는다."""
        assert "toggleBlog" not in self.HTML
        assert "toggleBlog" not in self.JS
        assert "담당 블로그" not in self.HTML

    def test_titles_no_longer_require_a_blog(self):
        assert "담당 블로그를 먼저 지정하세요" not in self.API


class TestDetailStaysFresh:
    """화면이 낡은 정형 항목을 보여주면 **채운 칸을 못 채운 칸으로 읽는다.**

    실측(2026-09-09 안과 오퍼): 규칙 97건을 뽑아 정형 항목이 17/19 가 됐는데,
    화면은 뽑기 전 값인 3/19 를 계속 보여줬다. `extract()` 가 목록만 새로
    고치고 상세를 다시 부르지 않았기 때문이다.

    **동작마다 갱신을 기억하게 두면 또 잊는다.** 목록을 고치는 모든 길이
    지나가는 `load()` 한 곳에서 상세도 함께 새로 고친다.
    """

    JS = (ROOT / "app/static/js/cpa/offers.js").read_text(encoding="utf-8")
    HTML = (ROOT / "app/templates/collection/_cpa_offers.html").read_text(
        encoding="utf-8")

    def _body(self, name):
        """함수 하나의 본문. 다음 함수 정의 앞까지."""
        start = self.JS.index(f"async {name}(")
        rest = self.JS[start:]
        end = rest.find("\n        },")
        return rest[:end]

    def test_detail_fetch_is_one_function(self):
        """상세를 받는 곳이 둘이면 한쪽만 고치는 일이 생긴다."""
        assert "async fetchDetail(" in self.JS
        assert self.JS.count("this.tpl = d.template") == 1

    def test_load_refreshes_the_open_detail(self):
        """목록을 새로 고치면 열린 상세도 같이 새로워져야 한다."""
        body = self._body("load")
        assert "this.openId" in body and "fetchDetail" in body

    def test_extract_shows_the_result(self):
        """뽑고 나서 접힌 채로 두면 사람이 결과를 못 본다."""
        body = self._body("extract")
        assert "this.openId = off.id" in body
        assert "정형 항목" in body, "뽑은 뒤 채움 수를 알려야 한다"

    def test_open_uses_the_shared_fetch(self):
        body = self._body("open")
        assert "fetchDetail" in body

    def test_close_clears_the_old_template(self):
        """남겨두면 다른 오퍼 카드에 옛 정형 항목이 비친다."""
        assert "closeDetail()" in self.JS
        block = self.JS[self.JS.index("closeDetail() {"):]
        assert "this.tpl = null" in block[:300]

    def test_script_is_cache_busted(self):
        """?v= 를 안 올리면 브라우저가 옛 파일을 계속 쓴다 — 증상이 그대로다."""
        assert "/static/js/cpa/offers.js?v=" in self.HTML


class TestImages:
    API = (ROOT / "app/routers/cpa_assets.py").read_text(encoding="utf-8")

    def test_upload_endpoint(self):
        assert "async def upload_image" in self.API

    def test_extension_checked(self):
        assert "이미지만 올릴 수 있습니다" in self.API

    def test_size_limited(self):
        assert "MAX_IMAGE_BYTES" in self.API

    def test_serving_blocks_path_escape(self):
        """/media 를 통째로 열면 남의 파일까지 나간다."""
        block = self.API[self.API.index("async def get_image"):]
        assert "startswith(str(MEDIA_ROOT.resolve()))" in block

    def test_delete_removes_the_file(self):
        block = self.API[self.API.index("async def delete_image"):]
        assert "unlink" in block


class TestRetype:
    """AI 는 유형을 must_not_include 로 몰아넣는다.

    실측(2026-09-09 안과 오퍼): 규칙 60건 중 41건이 그 유형이라 후기 금지·
    검색광고 금지·심의 배너가 전부 '금지 낱말' 칸에 들어갔다. 프롬프트를
    고쳐도 되풀이되므로 신호로 바로잡는다.
    """

    @pytest.mark.parametrize("value,quote,expected", [
        ("수술후기", "6. 수술후기 광고는 불법", "forbidden_topic"),
        ("자세한 비용", "3. 자세한 비용 오픈 금지", "forbidden_topic"),
        ("전화번호", "9. 대표전화번호가 아닌 전화번호", "pattern"),
        ("할인율", "2. 할인율, 할인비용", "pattern"),
        ("파워링크", "7. 포털사이트 검색광고 금지", "channel"),
        ("인스타그램", "10. SNS 광고", "channel"),
    ])
    def test_signals_fix_the_type(self, value, quote, expected):
        from app.services.cpa.rule_template import retype

        got = retype({"type": "must_not_include", "value": value,
                      "source_quote": quote})
        assert got["type"] == expected

    def test_plain_banned_word_untouched(self):
        from app.services.cpa.rule_template import retype

        got = retype({"type": "must_not_include", "value": "최고",
                      "source_quote": "4. 최상급 표현 사용불가"})
        assert got["type"] == "must_not_include"

    def test_only_the_crowded_types_are_retyped(self):
        """제대로 고른 것까지 흔들면 안 된다."""
        from app.services.cpa.rule_template import retype

        got = retype({"type": "content_source", "value": "후기가 많은 병원",
                      "source_quote": "*내용"})
        assert got["type"] == "content_source"


class TestFixedSectionMerged:
    """고정 서식으로 뽑은 것을 칸에 안 넣으면 빈 칸으로 보여 놓친 줄 안다."""

    def test_conversion_fills_targeting(self):
        out = assign([], conversion={"fields": ["이름", "핸드폰번호"],
                                     "reject_reasons": ["오류", "중복"]})
        by = {s["key"]: s for s in out["slots"]}
        assert by["targeting"]["count"] == 1
        assert "이름" in by["targeting"]["rules"][0]["value"]

    def test_notice_position_filled(self):
        out = assign([], notice_position="title_or_body_start")
        by = {s["key"]: s for s in out["slots"]}
        assert "[광고]" in by["notice_position"]["rules"][0]["value"]

    def test_extracted_rule_wins_over_fixed(self):
        """AI 가 이미 뽑았으면 덮어쓰지 않는다."""
        out = assign([R("position", "본문 첫 부분")],
                     notice_position="title_or_body_start")
        by = {s["key"]: s for s in out["slots"]}
        assert by["notice_position"]["count"] == 1
        assert by["notice_position"]["rules"][0]["value"] == "본문 첫 부분"
