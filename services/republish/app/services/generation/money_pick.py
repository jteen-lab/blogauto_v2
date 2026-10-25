"""P3 광고 단가 높은 정보형 — 하루 N편은 '돈 되는 정보' 제목을 먼저 고른다 (2026-10-25).

마케팅 지시·형 승인: 승인 4곳은 하루 1편 이상을 카드 혜택·연회비, 보험 청구·실손,
세금 환급·연말정산, 정부 지원금·바우처, 병원비·검사 비용 같은 주제로(블로그 맡은 칸 안에서).

- 모듈 ``money_info_daily``(정수)가 있을 때만. 오늘 이 블로그가 만든 글 중 P3 글이
  그만큼 안 됐으면, 재고 후보(맡은 칸 안) 중 P3 제목을 먼저 쓴다. 없으면 원래 제목.
- 관문(대출 상품·건강 공식 출처·N1~N4·형제 중복)은 그대로 — 고른 뒤 똑같이 거친다.
- 기록: 글마다 logs/money_info.jsonl 한 줄(p3 참/거짓). 마케팅이 4주 뒤 방문·체류를 비교.

순서도: docs/flowcharts/approved4_lanes_money.md
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text as sql

from ...core.logger import LoggerConfig, get_logger

logger = get_logger("money_pick", "app.log")

KEY = "money_info_daily"
JOURNAL = "money_info.jsonl"
KST = timezone(timedelta(hours=9))
MONEY = re.compile(
    r"연회비|카드\s*혜택|캐시백|포인트\s*(적립|전환)|실손|보험금|보험\s*청구|보험료|"
    r"환급|연말정산|종합소득세|세액\s*공제|소득\s*공제|절세|지원금|바우처|보조금|수당|"
    r"장려금|급여\s*신청|실업급여|국민내일배움|병원비|진료비|검사\s*비용|검진\s*비용|"
    r"치료비|수술비|본인부담|의료비|연금|청년\s*(지원|도약|월세)|감면|할인\s*혜택")


def is_money(title: str) -> bool:
    """P3 '돈 되는 정보' 제목인가. 순수 함수."""
    return bool(MONEY.search(title or ""))


def wanted(settings: Optional[dict]) -> int:
    """하루 P3 목표 편수(없으면 0 = 꺼짐)."""
    try:
        return max(0, int((settings or {}).get(KEY) or 0))
    except (TypeError, ValueError):
        return 0


async def done_today(db: Any, blog_id: int) -> int:
    """오늘(한국 날짜) 이 블로그가 만든 P3 글 수."""
    start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (await db.execute(sql(
        "select title from crawled_posts where blog_id = :b and source = 'generated' "
        "and created_at >= :s"), {"b": blog_id, "s": start})).all()
    return sum(1 for (t,) in rows if is_money(t))


async def prefer(executor: Any, blog: Any, title_id: int, settings: dict) -> int:
    """오늘 P3 가 모자라면 P3 후보 id, 아니면 원래 title_id. 오류면 원래 그대로."""
    need = wanted(settings)
    if not need or not title_id:
        return title_id
    try:
        if await done_today(executor.db, blog.id) >= need:
            return title_id
        from .volume_floor import remembered
        from . import lead_keyword
        low = lead_keyword.floor(settings) if lead_keyword.enabled(settings) else None
        titles = await executor.inventory_trigger.find_available_titles(
            blog.id, limit=40, module_settings=settings)
        for t in titles:
            if t.id == title_id and is_money(t.title):
                return title_id
        for t in titles:
            if is_money(t.title) and not (low and remembered(t, low) is False):
                logger.info("[MONEY_PICK] P3 먼저 | blog=%s | %s → %s | '%s'",
                            blog.name, title_id, t.id, (t.title or "")[:40])
                return t.id
        logger.info("[MONEY_PICK] P3 후보 없음 — 원래 제목 | blog=%s", blog.name)
    except Exception as e:  # noqa: BLE001
        logger.warning("[MONEY_PICK] 판정 실패(원래 제목) | blog=%s | %s", blog.name, e)
    return title_id


def journal(blog: Any, settings: Optional[dict], post_id: Any, title: str) -> None:
    """글마다 한 줄(P3 켠 모듈만). 실패해도 생성은 그대로."""
    if not wanted(settings):
        return
    try:
        p = Path(LoggerConfig.LOG_DIR) / JOURNAL
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {"at": datetime.now().isoformat(timespec="seconds"),
               "blog_id": getattr(blog, "id", None), "blog": getattr(blog, "name", None),
               "post_id": post_id, "title": title, "p3": is_money(title)}
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning("[MONEY_PICK] 기록 실패(무시) | %s", e)
