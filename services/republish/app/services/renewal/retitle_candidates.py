"""제목 재조합 후보 목록 — 노출·색인은 됐는데 검색 유입이 없는 글 (2026-11-07, 1단계).

글은 고치지 않는다. 조건에 맞는 글과 제목에 든 검색어 후보만 logs/retitle_candidates.json 에 쓴다.
검색어가 글 내용과 맞는지는 판정하지 않는다(11/7 시범의 가장 큰 빈칸, 2단계 몫). AI 호출 없음.

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
TOP_KEYWORDS = 5


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


def match_keywords(title: str, volumes: Dict[str, int]) -> List[Dict[str, Any]]:
    """제목에 든 검색어를 검색량 큰 순으로. 순수 함수."""
    t = norm(title)
    best: Dict[str, tuple] = {}
    for word, vol in volumes.items():
        key = norm(word)
        if len(key) < MIN_KEYWORD_LEN:
            continue
        parts = word.split()
        if key in t or (len(parts) > 1 and all(norm(p) in t for p in parts)):
            if key not in best or vol > best[key][1]:
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


def _item(blog: Any, row: Row, volumes: Dict[str, int]) -> Dict[str, Any]:
    """목록 한 줄."""
    return {"blog_id": blog.id, "blog": blog.name, "post": row.id, "url": row.url,
            "title": row.title, "published": str(row.published_at)[:10],
            "naver": row.naver, "impressions": row.impressions,
            "keywords": match_keywords(row.title, volumes)}


async def for_blog(db: AsyncSession, blog: Any, volumes: Dict[str, int],
                   fix_ids: Set[int]) -> Optional[List[Dict[str, Any]]]:
    """블로그 한 곳의 후보. GA 수집이 모자라면 None(없는 것을 0 으로 읽지 않는다)."""
    if not (await renewal_ga.load_view(db, blog.id)).usable:
        return None
    cfg = blog.renewal_config or {}
    skip = {renewal_ga.url_path(p) for p in cfg.get("exclude_paths") or []}
    traffic = await load_traffic(db, blog.id)
    return [_item(blog, r, volumes) for r in await load_rows(db, blog.id)
            if renewal_ga.url_path(r.url) not in skip and r.id not in fix_ids
            and not renewal_pick.blocked_title(r.title) and has_no_search(r, traffic)]


def _top_volume(item: Dict[str, Any]) -> int:
    return item["keywords"][0]["volume"] if item["keywords"] else 0


async def build(db: AsyncSession) -> Dict[str, Any]:
    """전체 목록을 만들어 파일에 쓰고 돌려준다. 글·DB 는 바꾸지 않는다."""
    from ...models.blog import Blog

    volumes = await load_keywords(db)
    fix_open = renewal_fixlist.open_items(renewal_fixlist.read_lines())
    fix_ids = {r["post"] for r in fix_open}
    items: List[Dict[str, Any]] = []
    no_ga: List[str] = []
    for blog in (await db.execute(select(Blog).where(Blog.is_active))).scalars().all():
        got = await for_blog(db, blog, volumes, fix_ids)
        if got is None:
            no_ga.append(blog.name)
        else:
            items += got
    items.sort(key=_top_volume, reverse=True)
    result = {"at": datetime.now().isoformat(timespec="seconds"), "count": len(items),
              "with_keyword": sum(1 for i in items if i["keywords"]),
              "no_ga_blogs": no_ga, "fix_open": fix_open, "items": items}
    path = Path(LoggerConfig.LOG_DIR) / OUT_FILE
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    logger.info("[RETITLE_LIST] 후보 %d편(검색어 있음 %d) | 고칠 글 %d편 | GA 부족 %s",
                result["count"], result["with_keyword"], len(fix_open), no_ga)
    return result
