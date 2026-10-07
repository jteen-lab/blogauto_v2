"""제목 관문 — 글을 만들기 **전에** 제목만 보고 내보내면 안 될 주제를 거른다.

마케팅 검수(2026-10-07, 형 승인)에서 이미 공개된 글 11편이 비공개·수정
대상이 됐다. 원인은 모두 제목 단계에서 알 수 있던 것이다.

  1. 전화번호·영업시간·시간표가 핵심인 주제  — 지어낸 값이 그대로 나간다
  2. 지난 연도가 박힌 제목                    — 끝난 사업을 현재형으로 쓴다
  3. 대부업체 상품 글                          — 형 결정으로 금지
  4. 저축은행·캐피탈·소액대출 등 개별 대출 상품 — 3번과 같은 기준
  5. 제철이 아닌 주제(10월 '봄동 효능')        — 철 지난 글
  6. 7일 안에 다른 블로그가 같은 주제를 냈음  — 블로그 간 중복

1~4는 시간이 지나도 풀리지 않으므로 제목을 보관(archived)해 다시 뽑히지
않게 한다(지우지 않는다 — 되돌릴 수 있다). 5·6은 때가 지나면 풀리므로
이번 회차만 건너뛴다.

순서도: docs/flowcharts/title_topic_gate.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence, Set, Tuple

from ...core.logger import get_logger
from .quality_gate import RISKY_PATTERNS

logger = get_logger("topic_gate", "app.log")

DUP_DAYS = 7

# ── 대출 ──────────────────────────────────────────────────────────────
LENDER = re.compile(r"대부(?!분)|대부업")
LOAN_PRODUCT = re.compile(
    r"캐피탈|저축\s*은행|소액\s*대출|비상금\s*대출|당일\s*대출|무직자\s*대출|"
    r"주부\s*대출|카드론|사채|급전")
# '○○론' 은 대출 문맥(대출·한도·금리…)이 함께 있을 때만 상품으로 본다.
# 이론·결론·여론 같은 낱말은 대출 문맥이 없어 걸리지 않는다.
NAMED_LOAN = re.compile(r"[가-힣A-Za-z0-9]{2,}론(?=\s|$|\d)")
LOAN_CONTEXT = re.compile(r"대출|한도|금리|상환|승인|단박|신청\s*조건")
# 정부 정책 상품은 개별 업체 상품이 아니다 — 막지 않는다.
POLICY_LOAN = re.compile(r"햇살론|보금자리론|디딤돌|버팀목|새희망홀씨|적격대출|"
                         r"미소금융|안심전환")

# ── 제철 ──────────────────────────────────────────────────────────────
# (제목 패턴, 제철 달). 제철 시작 한 달 전부터는 허용한다(미리 쓰는 글).
SEASONAL: Tuple[Tuple[str, Tuple[int, ...]], ...] = (
    (r"봄\s*제철|봄철\s*(보약|나물|제철)", (2, 3, 4, 5)),
    (r"여름\s*제철", (5, 6, 7, 8)),
    (r"가을\s*제철", (8, 9, 10, 11)),
    (r"겨울\s*제철", (11, 12, 1, 2)),
    (r"봄동", (12, 1, 2, 3)),
    (r"냉이|달래", (2, 3, 4)),
    (r"두릅|쑥국|쑥떡|쑥버무리|도다리", (3, 4, 5)),
    (r"벚꽃|유채꽃", (3, 4)),
    (r"참외", (5, 6, 7, 8)),
    (r"수박|해수욕장|물놀이", (6, 7, 8)),
    (r"장마", (6, 7)),
    (r"복날|초복|중복|말복|삼계탕", (7, 8)),
    (r"복숭아", (6, 7, 8, 9)),
    (r"옥수수", (7, 8, 9)),
    (r"전어", (8, 9, 10, 11)),
    (r"대하\s*(구이|축제|효능|제철)|대하구이|단풍", (9, 10, 11)),
    (r"김장", (10, 11, 12)),
    (r"굴국밥|굴전|생굴|굴무침|굴\s*효능|꼬막", (11, 12, 1, 2, 3)),
    (r"방어회|대방어|과메기", (11, 12, 1, 2)),
    (r"동지\s*팥죽|동짓날", (12,)),
    (r"눈썰매|스키장", (12, 1, 2)),
)


@dataclass
class TopicVerdict:
    """제목 관문 판정. permanent 면 제목을 보관한다."""

    code: str
    reason: str
    permanent: bool

    @property
    def message(self) -> str:
        return f"제목 관문({self.code}) — {self.reason}"


def _risky(title: str) -> Optional[str]:
    for pattern, label in RISKY_PATTERNS:
        if re.search(pattern, title):
            return label
    return None


def _past_year(title: str, today: date) -> Optional[int]:
    years = [int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", title)]
    past = [y for y in years if y < today.year]
    return max(past) if past else None


def loan_product(title: str) -> Optional[str]:
    """대부업체·개별 대출 상품 제목이면 그 이유."""
    if LENDER.search(title):
        return "대부업체"
    if POLICY_LOAN.search(title):
        return None
    m = LOAN_PRODUCT.search(title)
    if m:
        return f"대출 상품({m.group(0)})"
    m = NAMED_LOAN.search(title)
    if m and LOAN_CONTEXT.search(title):
        return f"대출 상품({m.group(0)})"
    return None


def _season_ok(months: Iterable[int], month: int) -> bool:
    """제철 달이거나 제철 시작 한 달 전이면 허용."""
    allowed = set(months)
    return month in allowed or (month % 12) + 1 in allowed


def out_of_season(title: str, today: date) -> Optional[str]:
    """제철 주제인데 지금이 제철이 아니면 그 낱말."""
    for pattern, months in SEASONAL:
        m = re.search(pattern, title)
        if m and not _season_ok(months, today.month):
            return f"'{m.group(0)}' 제철 {'·'.join(map(str, months))}월"
    return None


def check_title(title: str, today: Optional[date] = None) -> Optional[TopicVerdict]:
    """제목만 보고 판정한다(DB 불필요). 통과면 None."""
    title = title or ""
    today = today or date.today()
    label = _risky(title)
    if label:
        return TopicVerdict("위험주제", f"{label}이 제목의 핵심(확인 불가한 값)", True)
    year = _past_year(title, today)
    if year:
        return TopicVerdict("지난연도", f"제목에 {year}년(올해 {today.year}년)", True)
    loan = loan_product(title)
    if loan:
        return TopicVerdict("대출상품", loan, True)
    season = out_of_season(title, today)
    if season:
        return TopicVerdict("제철아님", season, False)
    return None


# ── 블로그 간 같은 주제 ──────────────────────────────────────────────
STOP: Set[str] = set(
    "방법 정리 안내 총정리 확인 확인하기 알아보기 무엇 무엇인가 무엇인가요 "
    "어떻게 가능 필수 알아야 위한 그리고 이유 비법 완벽 최신 정보 가이드 "
    "소개 조건 신청 신청방법 관리 결제 맛있게 만드는 추천 어디 좋을까".split())


def _tokens(title: str) -> Set[str]:
    t = re.sub(r"[^\w가-힣]", " ", title or "")
    return {w for w in t.split()
            if len(w) >= 2 and w not in STOP and not w.isdigit()}


def _bigrams(title: str) -> Set[str]:
    s = re.sub(r"[^\w가-힣]", "", title or "")
    return {s[i:i + 2] for i in range(len(s) - 1)}


def same_topic(a: str, b: str) -> bool:
    """두 제목이 같은 주제인가 — 일일 점검(품질점검.py)과 같은 기준."""
    ba, bb = _bigrams(a), _bigrams(b)
    jac = len(ba & bb) / max(1, len(ba | bb))
    ta, tb = _tokens(a), _tokens(b)
    tj = len(ta & tb) / max(1, len(ta | tb))
    return jac >= 0.45 or (len(ta & tb) >= 2 and tj >= 0.3)


def find_duplicate(title: str, title_id: int,
                   recent: Sequence[Tuple[str, Optional[int], str]]) -> Optional[str]:
    """recent = (다른 블로그 이름, 정식제목 id, 글 제목). 겹치면 설명."""
    for blog_name, tid, other in recent:
        if (title_id and tid == title_id) or same_topic(title, other):
            return f"{DUP_DAYS}일 안에 {blog_name}가 같은 주제 「{other[:30]}」"
    return None


async def _recent_other_posts(db, blog_id: int):
    from sqlalchemy import select

    from ...models.blog import Blog
    from ...models.crawled_post import CrawledPost

    since = datetime.now(timezone.utc) - timedelta(days=DUP_DAYS)
    rows = await db.execute(
        select(Blog.name, CrawledPost.matched_main_title_id, CrawledPost.title)
        .join(Blog, Blog.id == CrawledPost.blog_id)
        .where(CrawledPost.blog_id != blog_id,
               CrawledPost.source == "generated",
               CrawledPost.created_at >= since))
    return [(n, t, s or "") for n, t, s in rows.all()]


async def apply(db, blog, title) -> Optional[str]:
    """자동 생성 직전에 부른다. 막으면 사유 문자열, 통과면 None.

    판정 오류로 생성을 막지는 않는다(로그만 남긴다).
    """
    text = getattr(title, "title", "") or ""
    try:
        verdict = check_title(text)
        if verdict is None:
            dup = find_duplicate(text, title.id,
                                 await _recent_other_posts(db, blog.id))
            if dup:
                verdict = TopicVerdict("타블로그중복", dup, False)
    except Exception as e:  # noqa: BLE001
        logger.warning("[TOPIC_GATE] 판정 실패(통과) | blog=%s | %s", blog.id, e)
        return None
    if verdict is None:
        return None
    if verdict.permanent:
        title.status = "archived"
        title.hold_reason = verdict.message
        await db.commit()
    logger.info("[TOPIC_GATE] 건너뜀%s | blog=%s | title_id=%s | '%s' | %s",
                "+보관" if verdict.permanent else "", blog.name, title.id,
                text[:40], verdict.message)
    return verdict.message
