"""커뮤니티 질문 소스 — 지식iN·카페.

팬아웃(치는 쿼리)과 층이 다르다는 것이 이 소스의 존재 이유다. 그래서
**상황 판정**과 **홍보글 배제**가 핵심 검사 대상이다.
"""
import pytest

from app.services.keyword_lab.sources import community as C
from app.services.keyword_lab.sources.base import (
    SITUATION_SOURCES, SRC_NAVER_CAFE, SRC_NAVER_KIN, KeywordIdea,
)


class TestQuestionDetection:
    def test_질문_신호가_있으면_질문이다(self):
        assert C.is_question("이사 견적 얼마나 나올까요?")
        assert C.is_question("원룸 퇴거 청소비 내야 하나요")

    def test_질문_신호가_없으면_아니다(self):
        assert not C.is_question("이사 업체 후기 남깁니다")

    def test_너무_짧으면_아니다(self):
        assert not C.is_question("얼마?")

    def test_카페는_상황까지_요구한다(self):
        평범 = "이사 견적 얼마나 할까요"
        assert C.is_question(평범, strict=False)
        assert not C.is_question(평범, strict=True)

        구체 = "2층에서 3층 이사인데 견적 얼마나 할까요"
        assert C.is_question(구체, strict=True)


class TestSituation:
    def test_숫자_단위가_있으면_상황이다(self):
        assert C.has_situation("15평 투룸에서 32평으로")
        assert C.has_situation("견적이 70만원 나왔는데")

    def test_조건_접속어도_상황이다(self):
        assert C.has_situation("엘리베이터가 없는데 어떻게 하나요")

    def test_밋밋하면_상황이_아니다(self):
        assert not C.has_situation("이사 견적 방법")


class TestPromoFilter:
    @pytest.mark.parametrize("text", [
        "무료견적 문의주세요", "최저가 보장 이벤트", "카톡 상담문의",
        "010-1234-5678 연락주세요", "체험단 모집합니다",
    ])
    def test_홍보글은_버린다(self, text):
        assert C.is_promo(text)

    def test_평범한_질문은_홍보가_아니다(self):
        assert not C.is_promo("2층에서 3층 이사 견적 얼마나 하나요")


class TestToPhrase:
    def test_짧으면_그대로(self):
        assert C.to_phrase("원룸 이사 견적 얼마인가요", "이사 견적") \
            == "원룸 이사 견적 얼마인가요"

    def test_인사말을_걷어낸다(self):
        assert C.to_phrase("안녕하세요 이사 견적 문의드립니다", "이사") \
            == "이사 견적 문의드립니다"

    def test_대괄호_머리말을_걷어낸다(self):
        assert C.to_phrase("[질문] 이사 견적 얼마인가요", "이사") \
            == "이사 견적 얼마인가요"

    def test_길면_잘라도_키워드_상한을_넘지_않는다(self):
        긴제목 = "안녕하세요 " + "이사 견적 문의 " * 12
        got = C.to_phrase(긴제목, "이사 견적")
        assert got                      # normalize 에 걸려 비지 않아야 한다
        assert len(got) <= 60


class TestParsing:
    def _items(self):
        return [
            {"title": "<b>이사</b> 견적 얼마나 하나요",
             "description": "2층에서 3층인데요", "link": "http://a"},
            {"title": "무료견적 문의주세요",
             "description": "최저가 보장", "link": "http://b"},
            {"title": "이사 업체 후기입니다",
             "description": "잘 했습니다", "link": "http://c"},
        ]

    def test_지식인은_질문만_남긴다(self):
        got = C._to_questions(self._items(), "이사 견적", SRC_NAVER_KIN)
        assert len(got) == 1
        assert got[0].title == "이사 견적 얼마나 하나요"   # 태그 제거됨

    def test_카페도_홍보글을_버린다(self):
        got = C._to_questions(self._items(), "이사 견적", SRC_NAVER_CAFE)
        assert all(not C.is_promo(q.text) for q in got)

    def test_빈_응답은_빈_목록(self):
        assert C._to_questions([], "이사", SRC_NAVER_KIN) == []


class TestRegistryContract:
    def test_상황_소스는_검색량_보강_대상에서_빠진다(self):
        from app.services.keyword_lab.sources import registry

        ideas = [
            KeywordIdea(keyword="이사 견적", source="naver_suggest"),
            KeywordIdea(keyword="2층에서 3층 이사", source=SRC_NAVER_KIN),
        ]
        targets = [i for i in ideas
                   if i.search_volume is None
                   and i.source not in SITUATION_SOURCES]
        assert len(targets) == 1
        assert targets[0].source == "naver_suggest"
        assert registry is not None

    def test_상황_소스_상수가_등록돼_있다(self):
        assert SRC_NAVER_KIN in SITUATION_SOURCES
        assert SRC_NAVER_CAFE in SITUATION_SOURCES


class TestReferenceSources:
    def test_엔드포인트가_전부_정의돼_있다(self):
        from app.services.reference_search_service import ReferenceSearchService

        for src in ("web", "news", "kin", "cafe", "encyc", "law"):
            assert src in ReferenceSearchService.ENDPOINTS
            assert ReferenceSearchService.ENDPOINTS[src].startswith("https://")

    def test_시의성_소스는_날짜순이다(self):
        from app.services.reference_search_service import ReferenceSearchService

        assert ReferenceSearchService.SORT["news"] == "date"
        assert ReferenceSearchService.SORT["web"] == "sim"
