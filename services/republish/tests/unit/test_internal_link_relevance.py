"""내부링크 관련성 판정 테스트 (2026-09-29).

블로그 '수작남' 실측에서 무관한 링크가 붙었다:
여드름 → 하나카드 분실신고, 지방흡입 → AIA생명보험 지점,
화목난로 → 외동딸 육아, 안경사 → 우창윤다이어트.
공통 토큰 1개('방법과', '총정리' 등 일반어)만으로 통과한 것이 원인.

순서도: docs/flowcharts/internal_link_relevance.md
"""
from types import SimpleNamespace

import pytest

from app.services.generation.internal_linker import InternalLinker
from app.services.generation.link_relevance import (
    MIN_SHARED_TOKENS,
    rank_related,
    restrict_by_category,
    shared_count,
    tokenize,
)


def _post(pid: int, title: str) -> SimpleNamespace:
    return SimpleNamespace(id=pid, title=title, url=f"http://x/{pid}")


class TestTokenize:
    def test_particles_stripped(self):
        assert tokenize("피부를 지키는 여드름은") >= {"피부", "여드름"}
        assert "피부를" not in tokenize("피부를 지키는 여드름은")
        # 같은 단어는 조사가 달라도 같은 토큰
        assert tokenize("화목난로의") == tokenize("화목난로로")

    def test_short_word_not_over_stripped(self):
        """떼고 남는 길이가 2 미만이면 떼지 않는다('아이' → '아' 방지)."""
        assert "아이" in tokenize("아이 수면")

    def test_stopwords_removed(self):
        title = "무엇인가요 방법과 효과 총정리 알아야 할 꿀팁 추천 가이드"
        assert tokenize(title) == set()

    def test_numbers_and_single_chars_dropped(self):
        assert tokenize("2026 여드름 5 가 A") == {"여드름"}


# (현재 글, 실제로 붙었던 무관 글) — 일반어를 일부러 겹치게 구성
BAD_PAIRS = [
    ("여드름 흉터 없애는 방법과 효과 총정리",
     "하나카드 분실신고 방법과 재발급 총정리"),
    ("지방흡입 부작용 비용 알아야 할 점 총정리",
     "AIA생명보험 지점 위치 비용 알아야 할 정보 총정리"),
    ("화목난로 설치 장단점 무엇인가요",
     "외동딸 육아 장단점 무엇인가요"),
    ("안경사 되는 방법 연봉 현실 가이드",
     "우창윤다이어트 방법 효과 현실 후기 가이드"),
]


class TestRealBadExamples:
    @pytest.mark.parametrize("current,bad", BAD_PAIRS)
    def test_bad_pair_not_linked(self, current, bad):
        assert shared_count(current, bad) < MIN_SHARED_TOKENS
        assert rank_related(current, [_post(1, bad)]) == []

    @pytest.mark.parametrize("current,bad", BAD_PAIRS)
    def test_linker_intro_and_conclusion_empty(self, current, bad):
        linker = InternalLinker(db=None)
        posts = [_post(1, bad)]
        assert linker._find_intro_posts(current, posts, set(), 2, None) == []
        assert linker._filter_related(current, posts) == []


class TestRelatedStillLinks:
    def test_genuine_pair_links(self):
        current = "여드름 피부 관리"
        related = _post(1, "지성 피부 여드름 흉터 관리")
        unrelated = _post(2, "하나카드 분실신고 방법")
        assert rank_related(current, [unrelated, related]) == [related]

    def test_ordered_by_score_not_random(self):
        current = "여드름 피부 관리 루틴"
        two = _post(1, "여드름 피부 진정")
        three = _post(2, "여드름 피부 관리 제품")
        assert rank_related(current, [two, three]) == [three, two]


class TestCategory:
    def test_same_topic_preferred(self):
        current = "여드름 피부 관리"
        same = _post(1, "여드름 피부 진정 크림")
        other = _post(2, "여드름 피부 보험 청구")
        cats = {1: (10, 100), 2: (20, 200)}
        assert rank_related(current, [other, same], cats, (10, 100)) == [same]

    def test_same_subtopic_ranked_first(self):
        current = "여드름 피부 관리"
        a = _post(1, "여드름 피부 관리 제품")      # 3개, 다른 subtopic
        b = _post(2, "여드름 피부 진정")           # 2개, 같은 subtopic
        cats = {1: (10, 101), 2: (10, 100)}
        assert rank_related(current, [a, b], cats, (10, 100)) == [b, a]

    def test_no_category_falls_back_to_all(self):
        posts = [_post(1, "a"), _post(2, "b")]
        assert restrict_by_category(posts, {}, (None, None)) == posts
        # 현재 topic 은 있지만 같은 topic 글이 없으면 빈 목록(10/8 — 블로그 전체로 넓히지 않음)
        assert restrict_by_category(posts, {1: (5, None)}, (9, None)) == []

    def test_recruit_words_are_not_shared_meaning(self):
        """'채용·공고'만 겹치는 무관 기관 글은 관련 글이 아니다(취업인포마스터 10/8)."""
        assert shared_count("한국수출입은행 채용 공고 일정", "삼척시청 채용 공고 절차") == 0


class TestZeroLink:
    def test_empty_when_nothing_related(self):
        posts = [_post(i, t) for i, t in enumerate(
            ["일본여행 환전", "자동차 보험 갱신", "강아지 산책 시간"])]
        assert rank_related("여드름 피부 관리", posts) == []

    def test_empty_when_title_has_no_meaning(self):
        assert rank_related("방법 총정리", [_post(1, "방법 총정리 가이드")]) == []

    def test_intro_block_not_inserted(self):
        body = "서론\n\n## 첫 섹션\n\n내용\n"
        out = InternalLinker(db=None)._insert_intro_links(
            body, [], set(), 2)
        assert out == body


class TestSectionLinkUsesTokenizer:
    def test_generic_section_title_no_match(self):
        from app.services.generation.internal_linker import SimilarityService

        linker = InternalLinker(db=None)
        sim = SimilarityService(threshold=75)
        posts = [_post(1, "하나카드 분실신고 방법과 재발급 총정리")]
        assert linker._find_similar_by_score(
            "여드름 없애는 방법과 총정리", posts, sim) == []
