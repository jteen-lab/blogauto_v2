"""키워드 실험실 — 수요를 먼저 재고 후보를 만든다.

기존 수집(`seed_keywords`·`temp_titles`)을 건드리지 않는다. 운영 중인
블로그가 그 위에서 돌고 있어, 검증 안 된 방식을 섞으면 무엇이 원인인지
가릴 수 없다.

수집과 측정을 나눈 이유: 검색광고 API 는 시드 5개씩 한 번에 처리되지만
문서수는 키워드마다 한 번씩 호출해야 한다. 한 요청에 묶으면 타임아웃이
나고, 중간에 끊기면 무엇까지 쟀는지 알 수 없다.

순서도: docs/flowcharts/keyword_lab.md
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from ...models.category import BlogCategory, SubTopic
from ...models.keyword_candidate import (
    KeywordCandidate, VERDICT_ADOPT, VERDICT_PENDING,
)
from ...models.user_settings import UserSettings
from ..naver_ads_service import NaverAdsService
from ..naver_search_service import NaverSearchService
from .scoring import Thresholds, judge, saturation_of

logger = get_logger("keyword_lab", "app.log")

# 검색광고 API 는 시드 5개까지 받는다.
SEED_CHUNK = 5

# 문서수 조회 간격(초). 상대 서비스에 부담을 주지 않는다.
DOC_LOOKUP_DELAY = 0.2


class KeywordLabService:
    """수요 지표를 붙인 키워드 후보를 만들고 잰다."""

    def __init__(self, db: AsyncSession, settings: UserSettings, user_id: int):
        self.db = db
        self.settings = settings
        self.user_id = user_id

    # ── 시드 ─────────────────────────────────────────────
    async def seeds_for_blog(self, blog_id: int) -> List[Dict[str, Any]]:
        """블로그의 **활성 카테고리** 이름을 시드로 쓴다.

        지금 데이터랩 수집은 ['뉴스','이슈','트렌드'] 로 고정돼 있어
        취업/자격증 블로그에도 '뉴스' 로 조회한다. 그래서 그 니치의
        제목 유입이 30일간 0건이었다.
        """
        rows = (await self.db.execute(
            select(BlogCategory, SubTopic)
            .join(SubTopic, SubTopic.id == BlogCategory.subtopic_id)
            .where(
                BlogCategory.blog_id == blog_id,
                BlogCategory.is_active.is_(True),
            )
        )).all()
        return [
            {"seed": st.name, "topic_id": bc.topic_id,
             "subtopic_id": bc.subtopic_id}
            for bc, st in rows if st and st.name
        ]

    # ── 1단계: 연관키워드 + 검색량 ───────────────────────
    async def collect(
        self, blog_id: Optional[int] = None,
        seeds: Optional[List[str]] = None, limit: int = 200,
    ) -> Dict[str, Any]:
        """시드로 연관키워드와 월간 검색량을 받아 후보로 저장한다."""
        ads = NaverAdsService(self.settings)
        if not ads.is_configured():
            return {"success": False,
                    "error": "네이버 검색광고 API 키가 설정에 없습니다"}

        seed_rows: List[Dict[str, Any]] = []
        if blog_id:
            seed_rows = await self.seeds_for_blog(blog_id)
            if not seed_rows:
                return {"success": False,
                        "error": "이 블로그에 활성 카테고리가 없습니다"}
        for s in (seeds or []):
            s = (s or "").strip()
            if s:
                seed_rows.append({"seed": s, "topic_id": None,
                                  "subtopic_id": None})
        if not seed_rows:
            return {"success": False, "error": "시드가 비어 있습니다"}

        existing = await self._existing_keywords()
        saved, skipped, api_calls = 0, 0, 0
        # 실패를 삼키지 않는다. 로그에만 남기면 화면에는 '0개 수집' 만
        # 보이고 사용자는 무엇을 고쳐야 할지 알 수 없다.
        errors: List[str] = []

        for i in range(0, len(seed_rows), SEED_CHUNK):
            chunk = seed_rows[i:i + SEED_CHUNK]
            result = await ads.get_keyword_stats(
                [c["seed"] for c in chunk], include_related=True)
            api_calls += 1
            if not result.get("success"):
                reason = result.get("error") or "알 수 없는 오류"
                logger.warning("[KEYWORD_LAB] 검색광고 조회 실패 | %s", reason)
                if reason not in errors:
                    errors.append(reason)
                continue

            # 시드 자신도 후보다. 연관만 보면 시드가 좋은 키워드일 때 놓친다.
            rows = list(result.get("keywords") or []) \
                + list(result.get("related_keywords") or [])
            # 카테고리는 첫 시드 것을 붙인다 — 연관키워드가 어느 시드에서
            # 나왔는지 API 가 알려주지 않는다.
            meta = chunk[0]

            for item in rows:
                if saved >= limit:
                    break
                kw = (item.get("keyword") or "").strip()
                if not kw or kw.lower() in existing:
                    skipped += 1
                    continue
                existing.add(kw.lower())
                self.db.add(self._build(kw, item, meta, blog_id))
                saved += 1
            if saved >= limit:
                break

        await self.db.commit()
        logger.info(
            "[KEYWORD_LAB] 수집 완료 | blog=%s | 시드 %d개 | 저장 %d | "
            "중복 %d | API %d회 | 오류 %d",
            blog_id, len(seed_rows), saved, skipped, api_calls, len(errors),
        )

        # 한 건도 못 받았고 오류가 있으면 실패다. 성공으로 돌려주면
        # 화면이 '0개 수집' 이라고만 말한다.
        if saved == 0 and errors:
            return {"success": False, "error": errors[0], "errors": errors,
                    "api_calls": api_calls}

        return {"success": True, "saved": saved, "skipped": skipped,
                "seeds": [s["seed"] for s in seed_rows],
                "api_calls": api_calls, "errors": errors}

    def _build(self, keyword: str, item: dict, meta: dict,
               blog_id: Optional[int]) -> KeywordCandidate:
        volume = item.get("total_search_volume")
        verdict, reason, risk = judge(keyword, volume, None)
        return KeywordCandidate(
            user_id=self.user_id,
            keyword=keyword,
            seed=meta.get("seed"),
            blog_id=blog_id,
            topic_id=meta.get("topic_id"),
            subtopic_id=meta.get("subtopic_id"),
            search_volume_pc=item.get("pc_search_volume"),
            search_volume_mobile=item.get("mobile_search_volume"),
            search_volume=volume,
            competition=item.get("competition"),
            verdict=verdict,
            verdict_reason=reason,
            risk_label=risk,
            source="naver_ads",
        )

    async def _existing_keywords(self) -> set:
        rows = (await self.db.execute(
            select(KeywordCandidate.keyword)
            .where(KeywordCandidate.user_id == self.user_id)
        )).scalars().all()
        return {k.lower() for k in rows if k}

    # ── 2단계: 문서수 측정 ───────────────────────────────
    async def measure(
        self, limit: int = 50, blog_id: Optional[int] = None,
        min_volume: Optional[int] = None,
        min_saturation: Optional[float] = None,
    ) -> Dict[str, Any]:
        """아직 안 잰 후보의 블로그 문서수를 조회하고 판정한다.

        끊어서 여러 번 부를 수 있다. 이미 잰 것은 다시 재지 않는다.
        """
        search = NaverSearchService(self.settings)
        if not search.is_configured():
            return {"success": False,
                    "error": "네이버 검색 API 키가 설정에 없습니다"}

        th = Thresholds.build(min_volume, min_saturation)
        q = (select(KeywordCandidate)
             .where(KeywordCandidate.user_id == self.user_id,
                    KeywordCandidate.doc_count.is_(None))
             .order_by(KeywordCandidate.search_volume.desc().nullslast())
             .limit(limit))
        if blog_id:
            q = q.where(KeywordCandidate.blog_id == blog_id)
        rows = (await self.db.execute(q)).scalars().all()

        now = datetime.now(pytz.timezone("Asia/Seoul"))
        measured, failed = 0, 0
        for row in rows:
            try:
                res = await search.search_blog(row.keyword, display=1)
            except Exception as e:  # noqa: BLE001
                logger.warning("[KEYWORD_LAB] 문서수 조회 실패 | %s | %s",
                               row.keyword, e)
                failed += 1
                continue
            if not res.get("success"):
                failed += 1
                continue

            row.doc_count = int(res.get("total") or 0)
            row.saturation = saturation_of(row.search_volume, row.doc_count)
            row.verdict, row.verdict_reason, row.risk_label = judge(
                row.keyword, row.search_volume, row.doc_count, th)
            row.measured_at = now
            measured += 1
            await asyncio.sleep(DOC_LOOKUP_DELAY)

        await self.db.commit()
        remaining = await self._pending_count(blog_id)
        logger.info("[KEYWORD_LAB] 측정 | %d건 | 실패 %d | 남은 %d",
                    measured, failed, remaining)
        return {"success": True, "measured": measured, "failed": failed,
                "remaining": remaining}

    async def _pending_count(self, blog_id: Optional[int]) -> int:
        from sqlalchemy import func as _f

        q = (select(_f.count(KeywordCandidate.id))
             .where(KeywordCandidate.user_id == self.user_id,
                    KeywordCandidate.doc_count.is_(None)))
        if blog_id:
            q = q.where(KeywordCandidate.blog_id == blog_id)
        return (await self.db.execute(q)).scalar() or 0

    # ── 재판정 ───────────────────────────────────────────
    async def rejudge(self, min_volume: Optional[int],
                      min_saturation: Optional[float]) -> Dict[str, Any]:
        """기준만 바꿔 다시 판정한다. API 를 부르지 않는다."""
        th = Thresholds.build(min_volume, min_saturation)
        rows = (await self.db.execute(
            select(KeywordCandidate)
            .where(KeywordCandidate.user_id == self.user_id)
        )).scalars().all()
        for row in rows:
            row.verdict, row.verdict_reason, row.risk_label = judge(
                row.keyword, row.search_volume, row.doc_count, th)
        await self.db.commit()
        adopted = sum(1 for r in rows if r.verdict == VERDICT_ADOPT)
        return {"success": True, "total": len(rows), "adopted": adopted}
