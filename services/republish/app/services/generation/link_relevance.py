"""
내부링크 관련성 판정 (순수 함수 모듈)

InternalLinker 가 "이 글에 저 글 링크를 걸어도 되는가" 를 판정할 때 쓴다.
DB·앱 의존성이 없어 단위 테스트에서 바로 import 할 수 있다.

배경(2026-09-29, 블로그 '수작남' 실측): 여드름 글 → '하나카드 분실신고',
지방흡입 글 → 'AIA생명보험 지점' 같은 무관 링크가 붙었다. 원인은
1) 공통 토큰 1개만으로 통과, 2) 조사·어미가 붙은 일반어('방법과',
'무엇인가요')끼리 매칭, 3) 카테고리 무시였다.

순서도: docs/flowcharts/internal_link_relevance.md
"""
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# 서론·결론 링크가 되려면 필요한 공통 의미토큰 수 (전 블로그 공통 기본값)
MIN_SHARED_TOKENS = 2

# 단어 끝에서 떼어낼 조사·어미. 긴 것부터 검사한다.
# 떼고 남는 길이가 2글자 이상일 때만 뗀다('아이' → '아' 방지).
# 양쪽 제목에 똑같이 적용되므로 약간의 과잉 제거는 매칭에 영향이 없다.
_SUFFIXES: Tuple[str, ...] = tuple(sorted({
    "인가요", "일까요", "할까요", "될까요", "있나요", "없나요", "했나요",
    "으로는", "에서는", "에게는", "이라면", "이라는", "라는",
    "나요", "까요", "인가", "일까", "할까", "될까",
    "하는", "하기", "해야", "하면", "하고", "했던", "되는", "된",
    "으로", "에서", "에게", "까지", "부터", "보다", "처럼", "이란",
    "이나", "이랑", "에는", "과의", "와의",
    "은", "는", "이", "가", "을", "를", "과", "와", "의", "에",
    "로", "도", "만", "란", "요",
}, key=len, reverse=True))

# 어느 주제에나 붙는 일반어. 이것끼리 겹쳐도 관련 글이 아니다.
STOPWORDS: frozenset = frozenset({
    # 방법·안내류
    "방법", "방법과", "방법은", "하는법", "법", "사용법", "활용법", "선택법",
    "해결법", "가이드", "안내", "정리", "총정리", "완벽", "완벽정리",
    "알아보기", "알아보자", "알아볼까", "알아야", "알아두면", "알아둘",
    "꿀팁", "팁", "노하우", "비법", "요령", "체크리스트",
    # 질문·어미류
    "무엇", "무엇인가요", "무엇인가", "뭘까", "어떻게", "어떤", "왜",
    "있나요", "있을까", "될까", "할까", "인가요", "일까", "하는", "하기",
    "해야", "하면", "되는", "대한", "위한", "관련", "모든", "모두",
    # 평가·비교류
    "효과", "효능", "추천", "비교", "차이", "차이점", "장단점", "장점",
    "단점", "후기", "리뷰", "순위", "베스트", "최고", "최신", "인기",
    # 일반 명사류
    "확인", "초보자", "초보", "입문", "가지", "이유", "원인", "증상",
    "종류", "비용", "가격", "신청", "조건", "기간", "시기", "기준",
    "정보", "내용", "주의", "주의사항", "주의점", "필수", "핵심",
    "준비", "선택", "해결", "필요", "실제", "현실", "정확", "제대로",
    "올바른", "쉬운", "쉽게", "간단", "좋은", "나쁜", "the", "and",
    # 채용·모집류(2026-10-08, 취업인포마스터: 무관 기관 글끼리 '채용·공고'로 이어짐)
    "채용", "공고", "채용공고", "모집", "모집공고", "절차", "일정",
    "for", "how", "to", "of", "in",
})

_NON_WORD = re.compile(r"[^0-9a-z가-힣\s]")


def _strip_suffix(word: str) -> str:
    """단어 끝 조사·어미 하나를 떼어낸다(남는 길이 ≥ 2일 때만).

    Args:
        word: 소문자·정규화된 단어

    Returns:
        조사·어미를 뗀 단어 (뗄 게 없으면 원본)
    """
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 2:
            return word[: -len(suf)]
    return word


def tokenize(text: Optional[str]) -> Set[str]:
    """제목을 의미토큰 집합으로 바꾼다.

    NFKC·소문자 → 특수문자 제거 → 공백 분리 → 조사·어미 제거 →
    불용어·1글자·숫자 제거.

    Args:
        text: 원본 제목 또는 섹션 제목

    Returns:
        의미토큰 집합 (비어 있을 수 있음)
    """
    if not text:
        return set()
    norm = unicodedata.normalize("NFKC", text).lower()
    norm = _NON_WORD.sub(" ", norm)
    tokens: Set[str] = set()
    for raw in norm.split():
        if raw in STOPWORDS:
            continue
        tok = _strip_suffix(raw)
        if len(tok) < 2 or tok.isdigit() or tok in STOPWORDS:
            continue
        tokens.add(tok)
    return tokens


def shared_count(a: str, b: str) -> int:
    """두 제목의 공통 의미토큰 수.

    Args:
        a: 제목 A
        b: 제목 B

    Returns:
        공통 토큰 수
    """
    return len(tokenize(a) & tokenize(b))


def restrict_by_category(
    posts: Sequence[Any],
    post_cats: Dict[Any, Tuple[Optional[int], Optional[int]]],
    current_cat: Tuple[Optional[int], Optional[int]],
) -> List[Any]:
    """같은 topic 글로 후보를 좁힌다. 판단 근거가 없으면 전체를 돌려준다.

    Args:
        posts: 후보 글 목록 (``id`` 속성 사용)
        post_cats: 글 id → (topic_id, subtopic_id)
        current_cat: 현재 글의 (topic_id, subtopic_id)

    Returns:
        같은 topic 글 목록. 현재 글 topic 을 모르면 원래 목록 전체.
        topic 을 아는데 같은 topic 글이 없으면 **빈 목록**(2026-10-08) —
        예전에는 블로그 전체로 넓혀 무관한 글이 붙었다.
    """
    topic = current_cat[0] if current_cat else None
    if topic is None:
        return list(posts)
    return [p for p in posts
            if post_cats.get(getattr(p, "id", None), (None, None))[0] == topic]


def rank_related(
    current_title: str,
    posts: Iterable[Any],
    post_cats: Optional[Dict[Any, Tuple[Optional[int], Optional[int]]]] = None,
    current_cat: Tuple[Optional[int], Optional[int]] = (None, None),
    min_shared: int = MIN_SHARED_TOKENS,
) -> List[Any]:
    """관련 글만 골라 점수순으로 정렬한다. 부족해도 채우지 않는다.

    정렬 키: (같은 subtopic 여부, 공통 의미토큰 수) 내림차순. 동점은
    입력 순서를 유지한다(안정 정렬). 무작위 셔플은 하지 않는다.

    Args:
        current_title: 현재 글 제목
        posts: 후보 글 (``title``·``url``·``id`` 속성)
        post_cats: 글 id → (topic_id, subtopic_id). 없으면 카테고리 무시
        current_cat: 현재 글의 (topic_id, subtopic_id)
        min_shared: 필요한 공통 의미토큰 수

    Returns:
        관련 글 목록 (0개일 수 있음)
    """
    target = tokenize(current_title)
    if len(target) < min_shared:
        return []
    cats = post_cats or {}
    pool = restrict_by_category(list(posts), cats, current_cat)
    sub = current_cat[1] if current_cat else None
    scored = []
    for post in pool:
        if not getattr(post, "url", None) or not getattr(post, "title", None):
            continue
        overlap = len(target & tokenize(post.title))
        if overlap < min_shared:
            continue
        post_sub = cats.get(getattr(post, "id", None), (None, None))[1]
        same_sub = 1 if sub is not None and post_sub == sub else 0
        scored.append((same_sub, overlap, post))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [p for _, _, p in scored]
