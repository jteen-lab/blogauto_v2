"""근거 등급과 보류 — 확인된 것과 확인 안 된 것을 섞지 않는다.

2026-09-07 실측: "AK론 대출 금리와 조건" 글에 우리은행 신용대출 정보가
공식 자료로 붙었다. AK론은 금감원 공시에 없고, 웹에서도 10년 전 글에서
"업체 실체를 알기 어렵다" 는 말이 나온다.

증명은 불가능하다. 셋을 구분할 수 있을 뿐이다.
    회사가 실재하는가 / 상품이 공시 대상인가 / 이 수치가 맞는가(불가)
"""
import pathlib
from types import SimpleNamespace

import pytest

from app.services.reference.evidence import (
    GRADE_A, GRADE_B, GRADE_C, GRADE_NONE, Evidence, directive, evaluate,
    is_official, is_ymyl,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
TITLE = "AK론 대출 금리와 조건"


def _docs(*urls, postdate="20260901"):
    return [SimpleNamespace(url=u, postdate=postdate) for u in urls]


class TestScope:
    """요리·여행까지 보류하면 아무것도 못 쓴다."""

    @pytest.mark.parametrize("topics,title,expected", [
        (["금융/대출"], "", True),
        (["보험"], "", True),
        (["건강/의학"], "", True),
        (["음식/레시피"], "김치찌개 끓이는 법", False),
        (["자동차"], "타이어 교체 주기", False),
        ([], "AK론 대출 금리", True),        # 니치가 없어도 제목으로 잡는다
    ])
    def test_ymyl_detection(self, topics, title, expected):
        assert is_ymyl(topics, title) is expected

    def test_non_ymyl_never_held(self):
        found = evaluate(["음식/레시피"], "김치찌개", False, [])
        assert found.grade == GRADE_NONE
        assert found.hold is False


class TestOfficialSource:
    @pytest.mark.parametrize("url,expected", [
        ("https://www.fss.or.kr/x", True),
        ("https://www.korea.kr/news", True),
        ("https://www.wooribank.com/p", True),
        ("https://blog.naver.com/x", False),
        ("https://cafe.naver.com/x", False),
        ("https://someone.tistory.com/1", False),
        ("", False),
    ])
    def test_classification(self, url, expected):
        assert is_official(url) is expected

    def test_platform_wins_over_hint(self):
        """도메인에 bank 가 들어가도 블로그 플랫폼이면 남의 글이다."""
        assert is_official("https://blog.naver.com/bank-story") is False


class TestGrades:
    def test_api_hit_is_a(self):
        found = evaluate(["금융/대출"], TITLE, True,
                         _docs("https://blog.naver.com/a"))
        assert found.grade == GRADE_A
        assert found.allow_numbers is True

    def test_official_doc_is_b(self):
        found = evaluate(["금융/대출"], TITLE, False,
                         _docs("https://www.fss.or.kr/a"))
        assert found.grade == GRADE_B
        assert found.allow_numbers is False, "B 에서 수치를 쓰면 안 된다"

    def test_two_fresh_docs_is_b(self):
        found = evaluate(["금융/대출"], TITLE, False,
                         _docs("https://blog.naver.com/a",
                               "https://x.tistory.com/b"))
        assert found.grade == GRADE_B

    def test_single_doc_is_c(self):
        """한 곳만 있으면 그 글의 오류를 그대로 받는다."""
        found = evaluate(["금융/대출"], TITLE, False,
                         _docs("https://blog.naver.com/a"))
        assert found.grade == GRADE_C
        assert found.hold is True

    def test_stale_docs_are_c(self):
        """금리·제도는 오래된 값이 틀린 값이다."""
        found = evaluate(["금융/대출"], TITLE, False,
                         _docs("https://blog.naver.com/a",
                               "https://x.tistory.com/b",
                               postdate="20200101"))
        assert found.grade == GRADE_C

    def test_no_docs_is_c(self):
        assert evaluate(["금융/대출"], TITLE, False, []).grade == GRADE_C

    def test_reason_is_recorded(self):
        found = evaluate(["금융/대출"], TITLE, False, [])
        assert found.summary()


class TestDirective:
    def test_a_allows_numbers(self):
        text = directive(Evidence(grade=GRADE_A))
        assert "공식 자료의 값만" in text

    def test_b_forbids_numbers(self):
        text = directive(Evidence(grade=GRADE_B))
        assert "숫자를 쓰지 마세요" in text
        assert "파인" in text or "금융감독원" in text

    def test_b_points_to_where_to_check(self):
        """독자가 실제로 찾아갈 곳을 알려 줘야 한다."""
        text = directive(Evidence(grade=GRADE_B))
        assert "공식 홈페이지" in text

    def test_none_is_silent(self):
        assert directive(Evidence(grade=GRADE_NONE)) == ""


class TestHoldNotDelete:
    """지우면 우리가 놓친 잘못을 확인할 방법이 사라진다."""

    def test_generator_counts_instead_of_deleting(self):
        src = (ROOT / "app/services/generation/generator.py").read_text(
            encoding="utf-8")
        block = src[src.index("async def _grade_evidence"):]
        assert "hold_count" in block
        assert "delete" not in block.lower()

    def test_generator_blocks_before_ai_call(self):
        """보류할 글에 AI 를 부르면 비용만 나간다."""
        src = (ROOT / "app/services/generation/generator.py").read_text(
            encoding="utf-8")
        assert (src.index("evidence.hold")
                < src.index("reference_injection=_with_directive"))

    def test_review_threshold_is_three(self):
        from app.routers.held_titles import REVIEW_THRESHOLD

        assert REVIEW_THRESHOLD == 3

    def test_archive_keeps_the_row(self):
        src = (ROOT / "app/routers/held_titles.py").read_text(encoding="utf-8")
        block = src[src.index("async def resolve_held"):]
        assert 'row.status = "archived"' in block
        assert "db.delete" not in block

    def test_reset_allows_retry(self):
        src = (ROOT / "app/routers/held_titles.py").read_text(encoding="utf-8")
        assert "row.hold_count = 0" in src


class TestScreen:
    HTML = (ROOT / "app/templates/collection/_held_titles.html").read_text(
        encoding="utf-8")

    def test_listed_in_main_titles_tab(self):
        page = (ROOT / "app/templates/collection/_titles_main.html").read_text(
            encoding="utf-8")
        assert "_held_titles.html" in page

    def test_shows_reason(self):
        assert "row.hold_reason" in self.HTML

    def test_shows_pending_count(self):
        """문턱에 못 미친 것도 얼마나 쌓이는지 보여 준다."""
        assert "쌓이는 중" in self.HTML

    def test_explains_why_not_deleted(self):
        assert "지워지지 않습니다" in self.HTML or "지우지 않습니다" in self.HTML
