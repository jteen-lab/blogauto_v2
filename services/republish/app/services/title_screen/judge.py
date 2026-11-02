"""4단계 판정 + 통과 검색어를 채택 검색어 창고에 넣기.

통과 = 가장 큰 말이 월 500 이상 + 맡은 칸에 맞음(AI 칸 번호가 목록 안).
보류 = 그 말이 사이트 이름 자체(알바천국 류) — 사람들이 블로그를 거치지 않는다(B5).
나머지는 떨어짐(낮은 검색량·칸 없음·못 잼).

순서도: docs/flowcharts/title_screen_d.md (4)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.keyword_candidate import VERDICT_ADOPT, KeywordCandidate
from .extract import Picked
from .measure import biggest, key, norm_col

PASS_VOLUME = 500

PASS = "pass"
HOLD = "hold"
FAIL = "fail"
SKIP = "skip"   # AI·검색량 조회 실패 — 이번엔 판정하지 않고 그대로 둔다(지우지 않는다)

SITE_NAMES = {key(s) for s in (
    "알바천국 알바몬 잡코리아 사람인 워크넷 고용24 잡플래닛 인크루트 네이버 다음 구글 유튜브 "
    "쿠팡 11번가 G마켓 지마켓 옥션 티몬 위메프 당근마켓 당근 번개장터 중고나라 카카오톡 "
    "카카오맵 네이버지도 정부24 홈택스 손택스 위택스 복지로 인터넷등기소 배달의민족 요기요 "
    "쿠팡이츠 야놀자 여기어때 에어비앤비 아고다 스카이스캐너 코레일 SRT 넷플릭스 티빙 웨이브 "
    "디즈니플러스 왓챠 멜론 인스타그램 페이스북 틱톡 토스 카카오뱅크 국민건강보험공단 "
    "국민연금공단 건강보험공단 우체국 하이패스 올리브영 다이소 이마트 홈플러스"
).split()}
SITE_TAIL = re.compile(r"(홈페이지|바로가기|로그인|사이트|고객센터|앱다운로드)$")


@dataclass
class Verdict:
    """제목 하나 판정."""

    result: str
    reason: str
    keyword: Optional[str] = None
    volume: int = 0
    subtopic_id: Optional[int] = None


def site_name(word: str) -> bool:
    """사이트 이름 자체를 검색하는 말인가."""
    k = key(word)
    return k in SITE_NAMES or bool(SITE_TAIL.search(k))


def judge(picked: Optional[Picked], vols: Dict[str, int]) -> Verdict:
    """AI 답 + 검색량 → 판정."""
    if picked is None:
        return Verdict(SKIP, "no_answer")
    if not picked.candidates:
        return Verdict(FAIL, "no_keyword")
    best = biggest(picked.candidates, vols)
    if best is None:
        return Verdict(SKIP, "not_measured")
    word, vol = best
    v = Verdict(FAIL, "low_volume", word, vol, picked.subtopic_id)
    if vol < PASS_VOLUME:
        return v
    if picked.subtopic_id is None:
        v.reason = "off_niche"
        return v
    if site_name(word):
        v.result, v.reason = HOLD, "site_name"
        return v
    v.result, v.reason = PASS, "ok"
    return v


async def adopt(db: AsyncSession, user_id: int,
                words: List[Tuple[str, int, int, Optional[int]]]) -> Dict[str, int]:
    """통과 말(말, 검색량, 칸, 주제)을 창고에 넣고 {열쇠: candidate id}.

    이미 있는 말은 칸이 비었으면 채운다(지우거나 판정을 바꾸지 않는다).
    """
    if not words:
        return {}
    keys = {key(w[0]) for w in words}
    norm = norm_col(KeywordCandidate.keyword)
    found: Dict[str, KeywordCandidate] = {}
    for row in (await db.execute(select(KeywordCandidate).where(
            KeywordCandidate.user_id == user_id, norm.in_(list(keys)))
            .order_by(KeywordCandidate.id))).scalars().all():
        found.setdefault(key(row.keyword), row)
    now = datetime.now(timezone.utc)
    for word, vol, sid, tid in words:
        k = key(word)
        row = found.get(k)
        if row is None:
            row = KeywordCandidate(
                user_id=user_id, keyword=word[:200], topic_id=tid, subtopic_id=sid,
                search_volume=vol, verdict=VERDICT_ADOPT, verdict_reason="D 거르기 통과(제목에서)",
                source="title_screen", measured_at=now, titled=True, is_active=True)
            db.add(row)
            found[k] = row
        elif row.subtopic_id is None:
            row.subtopic_id, row.topic_id = sid, tid
    await db.flush()
    return {k: r.id for k, r in found.items()}
