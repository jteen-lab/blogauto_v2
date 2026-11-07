"""제목 재조합 후보 목록 — 노출·색인은 됐는데 검색 유입이 없는 글 (2026-11-07, 1단계).

글은 고치지 않는다. 조건에 맞는 글과 검색어 후보만 logs/retitle_candidates.json 에 쓴다.
검색어는 창고(keyword_metrics)와 네이버 검색광고 연관어(무료)에서 제목 낱말로 맞춘다.
글 내용과 맞는지는 판정하지 않는다(11/7 시범의 가장 큰 빈칸, 2단계 몫). AI 호출 없음.

순서도: docs/flowcharts/renewal_retitle_candidates.md (2. 제목 재조합 후보 목록)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import LoggerConfig, get_logger
from . import renewal_fixlist, renewal_ga, renewal_pick

logger = get_logger("retitle_candidates", "app.log")

OUT_FILE = "retitle_candidates.json"
MIN_AGE_DAYS = 60
WINDOW_DAYS = 60
GAP_DAYS = 90
MIN_VOLUME = 100
BIG_VOLUME = 3000     # 시범 A군(100~3,000)·B군(3,000 이상) 경계
MIN_KEYWORD_LEN = 3   # '적금' 같은 두 글자는 어느 제목에나 걸린다
SOLO_LEN = 5          # 한 낱말만으로 인정할 길이('꿈드리미카드'는 되고 '신용카드'는 안 된다)
TOP_KEYWORDS = 5
ADS_HINTS = 5         # 검색광고 한 번에 다섯 개까지
_WORD = re.compile(r"[0-9A-Za-z가-힣]+")


@dataclass
class Row:
    """후보 글 한 줄."""

    id: int
    title: str
    url: str
    published_at: Optional[datetime]
    naver: str
    impressions: int
    clicks: int


def norm(text: str) -> str:
    """띄어쓰기·대소문자를 뺀 비교용 글자."""
    return re.sub(r"\s+", "", text or "").lower()


def title_words(title: str) -> List[str]:
    """제목의 두 글자 이상 낱말(비교용)."""
    return [norm(w) for w in _WORD.findall(title or "") if len(w) >= 2]


def hint_pairs(title: str) -> List[str]:
    """검색광고에 물어볼 말 — 제목의 이웃한 두 낱말, 앞에서 다섯 개까지."""
    words = title_words(title)
    return [a + b for a, b in zip(words, words[1:])][:ADS_HINTS]


def fits_title(keyword: str, words: List[str], title_norm: str) -> bool:
    """제목 낱말 둘 이상으로 된 말, 또는 제목에 그대로 든 긴 말인가. 순수 함수.

    제목에 들었다는 것만 보면 '신한은행'·'어떻게'·'가이드' 처럼 글과 상관없이 큰 말이 1등이 된다(11/7 첫 실행).
    낱말 끝 한 글자는 조사일 수 있어 빼고도 본다('경매로' → '경매').
    """
    key = norm(keyword)
    if len(key) < MIN_KEYWORD_LEN:
        return False
    hits = sum(1 for w in words if w in key or (len(w) >= 3 and w[:-1] in key))
    return hits >= 2 or (len(key) >= SOLO_LEN and key in title_norm)


def match_keywords(title: str, volumes: Dict[str, int]) -> List[Dict[str, Any]]:
    """글 제목에 맞는 검색어를 검색량 큰 순으로. 순수 함수."""
    t, words = norm(title), title_words(title)
    best: Dict[str, tuple] = {}
    for word, vol in volumes.items():
        key = norm(word)
        if fits_title(word, words, t) and (key not in best or vol > best[key][1]):
            best[key] = (word, vol)
    ranked = sorted(best.values(), key=lambda x: x[1], reverse=True)[:TOP_KEYWORDS]
    return [{"keyword": w, "volume": v, "band": "B" if v >= BIG_VOLUME else "A",
             "lead": t.startswith(norm(w))} for w, v in ranked]


def has_no_search(row: Row, traffic: Dict[str, int]) -> bool:
    """60일 검색 유입이 없나(GA 네이버·구글, 서치콘솔 클릭). 순수 함수."""
    return row.clicks == 0 and traffic.get(renewal_ga.url_path(row.url).lower(), 0) == 0


async def load_keywords(db: AsyncSession) -> Dict[str, int]:
    """네이버 월 검색량 MIN_VOLUME 이상 검색어. 구간값은 절대 기준이 아니라 뺀다."""
    rows = (await db.execute(sql(
        "select c.keyword, max(m.search_volume) from keyword_candidates c "
        "join keyword_metrics m on m.candidate_id = c.id where m.engine = 'naver' "
        "and m.search_volume >= :v and coalesce(m.volume_is_range, 0) = 0 "
        "and c.is_active group by 1"), {"v": MIN_VOLUME})).all()
    return {r[0]: int(r[1]) for r in rows}


async def ads_service(db: AsyncSession) -> Optional[Any]:
    """네이버 검색광고 연결. 키가 없으면 None(창고 검색어만 쓴다)."""
    from ...models.user_settings import UserSettings
    from ..naver_ads_service import NaverAdsService

    settings = (await db.execute(select(UserSettings).where(
        UserSettings.naver_ads_api_key.isnot(None)).limit(1))).scalars().first()
    service = NaverAdsService(settings) if settings else None
    return service if service and service.is_configured() else None


async def ads_volumes(service: Optional[Any], title: str) -> Optional[Dict[str, int]]:
    """이 제목의 연관 검색어 검색량(무료 호출). 실패면 None."""
    hints = hint_pairs(title)
    if service is None or not hints:
        return {}
    got = await service.get_keyword_stats(hints, include_related=False)
    if not got.get("success"):
        logger.warning("[RETITLE_LIST] 검색량 조회 실패 | %s | %s", title[:30], got.get("error"))
        return None
    return {k["keyword"]: int(k.get("total_search_volume") or 0)
            for k in got.get("keywords") or []
            if int(k.get("total_search_volume") or 0) >= MIN_VOLUME}


async def fill_keywords(service: Optional[Any], items: List[Dict[str, Any]],
                        pool: Dict[str, int]) -> int:
    """글마다 창고 검색어 + 연관 검색어로 후보를 채운다. 조회 실패 글 수를 돌려준다."""
    failed = 0
    for item in items:
        extra = await ads_volumes(service, item["title"])
        failed += extra is None
        item["keywords"] = match_keywords(item["title"], {**pool, **(extra or {})})
    return failed


async def load_rows(db: AsyncSession, blog_id: int) -> List[Row]:
    """발행 60일 지나고 네이버 색인 또는 서치콘솔 노출이 있는 글."""
    now = datetime.now(timezone.utc)
    rows = (await db.execute(sql(
        "select c.id, coalesce(c.title, s.title, ''), coalesce(c.url, s.url), s.published_at, "
        "s.naver_index_state, coalesce(g.imp, 0), coalesce(g.clk, 0) "
        "from search_visibility_urls s join crawled_posts c on c.id = s.crawled_post_id "
        "left join (select url_id, sum(impressions) imp, sum(clicks) clk "
        "from post_metrics_daily where date > :since group by 1) g on g.url_id = s.id "
        "where s.blog_id = :b and s.published_at < :cut "
        "and coalesce(c.status, '') <> 'unpublished' "
        "and (c.last_renewed_at is null or c.last_renewed_at < :gap) "
        "and (s.naver_index_state = 'found' or coalesce(g.imp, 0) > 0)"),
        {"b": blog_id, "cut": now - timedelta(days=MIN_AGE_DAYS),
         "gap": now - timedelta(days=GAP_DAYS),
         "since": date.today() - timedelta(days=WINDOW_DAYS)})).all()
    return [Row(r[0], r[1], r[2], r[3], r[4], int(r[5]), int(r[6])) for r in rows]


async def load_traffic(db: AsyncSession, blog_id: int) -> Dict[str, int]:
    """경로별 60일 네이버·구글 유입."""
    rows = (await db.execute(sql(
        "select lower(path), sum(naver_sessions + google_sessions) from page_metrics_daily "
        "where blog_id = :b and date > :since group by 1"),
        {"b": blog_id, "since": date.today() - timedelta(days=WINDOW_DAYS)})).all()
    out: Dict[str, int] = {}
    for path, n in rows:   # 블로거 경로는 끝 빗금이 없고 ?m=1 이 붙기도 한다
        key = renewal_ga.url_path(path)
        out[key] = out.get(key, 0) + int(n or 0)
    return out


def _item(blog: Any, row: Row) -> Dict[str, Any]:
    """목록 한 줄."""
    return {"blog_id": blog.id, "blog": blog.name, "post": row.id, "url": row.url,
            "title": row.title, "published": str(row.published_at)[:10],
            "naver": row.naver, "impressions": row.impressions, "keywords": []}


async def for_blog(db: AsyncSession, blog: Any, fix_ids: Set[int]) -> Optional[List[Dict[str, Any]]]:
    """블로그 한 곳의 후보. GA 수집이 모자라면 None(없는 것을 0 으로 읽지 않는다)."""
    if not (await renewal_ga.load_view(db, blog.id)).usable:
        return None
    cfg = blog.renewal_config or {}
    skip = {renewal_ga.url_path(p) for p in cfg.get("exclude_paths") or []}
    traffic = await load_traffic(db, blog.id)
    return [_item(blog, r) for r in await load_rows(db, blog.id)
            if renewal_ga.url_path(r.url) not in skip and r.id not in fix_ids
            and not renewal_pick.blocked_title(r.title) and has_no_search(r, traffic)]


def _top_volume(item: Dict[str, Any]) -> int:
    return item["keywords"][0]["volume"] if item["keywords"] else 0


async def build(db: AsyncSession) -> Dict[str, Any]:
    """전체 목록을 만들어 파일에 쓰고 돌려준다. 글·DB 는 바꾸지 않는다."""
    from ...models.blog import Blog

    fix_open = renewal_fixlist.open_items(renewal_fixlist.read_lines())
    fix_ids = {r["post"] for r in fix_open}
    items: List[Dict[str, Any]] = []
    no_ga: List[str] = []
    for blog in (await db.execute(select(Blog).where(Blog.is_active))).scalars().all():
        got = await for_blog(db, blog, fix_ids)
        if got is None:
            no_ga.append(blog.name)
        else:
            items += got
    failed = await fill_keywords(await ads_service(db), items, await load_keywords(db))
    items.sort(key=_top_volume, reverse=True)
    result = {"at": datetime.now().isoformat(timespec="seconds"), "count": len(items),
              "with_keyword": sum(1 for i in items if i["keywords"]),
              "no_ga_blogs": no_ga, "ads_failed": failed, "fix_open": fix_open, "items": items}
    path = Path(LoggerConfig.LOG_DIR) / OUT_FILE
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    logger.info("[RETITLE_LIST] 후보 %d편(검색어 있음 %d) | 고칠 글 %d편 | GA 부족 %s",
                result["count"], result["with_keyword"], len(fix_open), no_ga)
    return result
