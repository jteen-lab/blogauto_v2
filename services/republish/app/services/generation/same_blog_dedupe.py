"""같은 블로그 안 비슷한 제목 거르기 — 모듈 스위치(settings.dedupe_same_blog).

취업인포마스터(블로그 17) 애드센스 거절(10/8) 원인 하나: '김해 알바천국',
'경산 알바천국', '수원 알바천국'처럼 지역만 바꾼 글과 'LG전자 채용'·
'엘지전자 채용 공고'처럼 이름 표기만 다른 글이 한 블로그에 쌓였다.
제목 관문의 7일 중복 비교는 **다른** 블로그만 보고, 제목 묶기는 지역이 다르면
안 묶는다.

자기 블로그 최근 60일 발행 제목과 비교해, 지역명(시·군·구·광역시도)·연도·
회사명 영문/한글 표기를 지운 뒤 같은 글이면 **이번만 건너뛴다**(보관 아님 —
제목은 창고에 남아 다른 블로그가 쓴다). 같은 글 기준: 의미 낱말(내부 링크와
같은 토큰화, '7가지' 같은 숫자 낱말 제외)이 2개 이상 겹치고, 두 제목 낱말 전체의
절반 이상이 겹침(자카드 0.5 — 0.4 는 '○○ 자격증 취득'끼리 같다고 봄, 모의 10/8). 블로그 간 기준(topic_gate.same_topic)은 '직장인을 위한 …
7가지' 같은 틀 문구만 겹쳐도 같다고 봐서 같은 블로그에는 너무 넓다(모의 10/8).

순서도: docs/flowcharts/title_topic_gate.md (같은 블로그 비슷한 제목)
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set

from ...core.logger import get_logger
from .link_relevance import _strip_suffix, tokenize

logger = get_logger("same_blog_dedupe", "app.log")

DAYS = 60
MIN_SHARED = 2
MIN_JACCARD = 0.5
COMMON_SHARE = 0.15   # 블로그 주제어로 볼 비율
# status 는 DB 에만 있고 모델에 없다(정리로 내린 글 = 'unpublished')
UNPUBLISHED_SQL = "coalesce(crawled_posts.status, '') <> 'unpublished'"
# 회사명 한글 표기 → 영문(소문자). 긴 것부터 바꾼다.
ALIASES = (
    ("에스케이", "sk"), ("엘지", "lg"), ("케이티", "kt"), ("씨제이", "cj"),
    ("지에스", "gs"), ("엘에이치", "lh"), ("케이비", "kb"), ("엔에이치", "nh"),
    ("에이치디", "hd"), ("에스오일", "s-oil"),
)
YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}\s*년?(?:도)?|(?<!\d)\d{2}년(?:도)?")
_NON_WORD = re.compile(r"[^0-9a-z가-힣\s-]")
_REGIONS: Optional[Set[str]] = None


def _regions() -> Set[str]:
    """시·군·구·광역시도 이름(별칭 포함). 못 읽으면 빈 집합(지역은 안 지움)."""
    global _REGIONS
    if _REGIONS is None:
        for path in ("/app/shared", "/home/jteen/blogauto_v2/shared"):
            if os.path.exists(path) and path not in sys.path:
                sys.path.insert(0, path)
        try:
            from services.location_service import LocationService

            _REGIONS = set(LocationService().get_all_location_names())
        except Exception as e:  # noqa: BLE001
            logger.warning("[SAME_BLOG] 지역명 목록 로드 실패: %s", e)
            _REGIONS = set()
    return _REGIONS


def normalize(title: str, regions: Optional[Set[str]] = None) -> str:
    """지역명·연도를 지우고 회사명 표기를 맞춘 비교용 제목."""
    regions = _regions() if regions is None else regions
    s = unicodedata.normalize("NFKC", title or "").lower()
    for ko, en in ALIASES:
        s = s.replace(ko, en)
    s = YEAR.sub(" ", s)
    s = _NON_WORD.sub(" ", s)
    words = [w for w in s.split()
             if w not in regions and _strip_suffix(w) not in regions]
    return " ".join(words)


def _meaning(title: str, regions: Set[str], common: Set[str] = frozenset()) -> Set[str]:
    """정규화한 제목의 의미 낱말(숫자로 시작하는 낱말·블로그 공통어 제외)."""
    return {t for t in tokenize(normalize(title, regions))
            if not t[0].isdigit() and t not in common}


def is_same(a: str, b: str, regions: Optional[Set[str]] = None,
            common: Set[str] = frozenset()) -> bool:
    """지역·연도·회사 표기를 지운 뒤 같은 글로 볼 만큼 겹치나."""
    regions = _regions() if regions is None else regions
    ta, tb = _meaning(a, regions, common), _meaning(b, regions, common)
    if ta and ta == tb:          # 주제어를 빼면 똑같다(예: '간호조무사' 만 남음)
        return True
    shared = len(ta & tb)
    if not ta or not tb or shared < MIN_SHARED:
        return False
    return shared / len(ta | tb) >= MIN_JACCARD


def blog_common_words(recent: List[str], regions: Set[str]) -> Set[str]:
    """이 블로그 최근 제목의 COMMON_SHARE 이상(최소 3편)에 나오는 낱말.

    취업 블로그의 '자격증·취득'처럼 블로그 주제어는 겹쳐도 같은 글이 아니다
    ('보육교사 자격증 취득' ≠ '간호조무사 자격증 취득').
    """
    df: dict = {}
    for t in recent:
        for w in _meaning(t, regions):
            df[w] = df.get(w, 0) + 1
    cut = max(3, COMMON_SHARE * len(recent))
    return {w for w, n in df.items() if n >= cut}


def find_similar(title: str, recent: List[str],
                 regions: Optional[Set[str]] = None) -> Optional[str]:
    """최근 제목 중 같은 글이 있으면 그 제목, 없으면 None."""
    regions = _regions() if regions is None else regions
    common = blog_common_words(recent, regions)
    for other in recent:
        if is_same(title, other, regions, common):
            return other
    return None


async def recent_titles(db, blog_id: int, days: int = DAYS) -> List[str]:
    """이 블로그가 최근 days 일에 낸 글 제목(정리로 내린 글 제외)."""
    from sqlalchemy import select, text

    from ...models.crawled_post import CrawledPost

    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await db.execute(
        select(CrawledPost.title).where(
            CrawledPost.blog_id == blog_id,
            CrawledPost.created_at >= since,
            CrawledPost.url.isnot(None), CrawledPost.url != "",
            text(UNPUBLISHED_SQL)))
    return [t for (t,) in rows.all() if t]


async def apply(db, blog, title, module_settings: Optional[dict]) -> Optional[str]:
    """스위치가 켜진 모듈만. 건너뛰면 사유, 아니면 None. 판정 오류는 통과."""
    if not (module_settings or {}).get("dedupe_same_blog"):
        return None
    text = getattr(title, "title", "") or ""
    try:
        hit = find_similar(text, await recent_titles(db, blog.id))
    except Exception as e:  # noqa: BLE001
        logger.warning("[SAME_BLOG] 판정 실패(통과) | blog=%s | %s", blog.id, e)
        return None
    if not hit:
        return None
    msg = f"제목 관문(같은블로그중복) — {DAYS}일 안에 이 블로그에 「{hit[:30]}」"
    logger.info("[SAME_BLOG] 건너뜀 | blog=%s | title_id=%s | '%s' | %s",
                blog.id, getattr(title, "id", None), text[:40], msg)
    return msg
