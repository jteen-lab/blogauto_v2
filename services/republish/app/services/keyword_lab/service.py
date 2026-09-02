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
from ...models.keyword_metric import PRIMARY_ENGINE
from ...models.user_settings import UserSettings
from ..naver_ads_service import NaverAdsService
from ..naver_search_service import NaverSearchService
from .metrics import upsert_metric
from .scoring import Thresholds, judge, saturation_of, supply_of
from .supply import PUB_WINDOW_DAYS, measure_supply

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
        # 수집 시점과 측정 시점의 기준이 달라 모듈 설정이 안 먹던 문제
        # (검토서 D-8). 두 단계가 같은 기준 객체를 본다.
        self.thresholds: Optional[Thresholds] = None

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

        return await self._collect_rows(seed_rows, blog_id, limit)

    async def _collect_rows(
        self, seed_rows: List[Dict[str, Any]], blog_id: Optional[int],
        limit: int,
    ) -> Dict[str, Any]:
        """시드 목록으로 실제 조회·저장을 수행한다."""
        ads = NaverAdsService(self.settings)
        if not ads.is_configured():
            return {"success": False,
                    "error": "네이버 검색광고 API 키가 설정에 없습니다"}

        existing = await self._existing_keywords(blog_id)
        saved, skipped, api_calls = 0, 0, 0
        # 화면이 "몇 개" 만이 아니라 "무엇이" 들어왔는지 보여줄 수 있게 한다
        samples: List[str] = []
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
            meta = chunk[0]

            for item in rows:
                if saved >= limit:
                    break
                kw = (item.get("keyword") or "").strip()
                if not kw or kw.lower() in existing:
                    skipped += 1
                    continue
                existing.add(kw.lower())
                samples.append(kw)
                # 니치는 **키워드 자체를 분류해서** 정한다. 시드를 그대로
                # 물려주면 '마라탕' 으로 모은 것이 전부 '음식 효능' 이 되어
                # 나중에 카테고리별로 넘길 수가 없다.
                niche = await self._classify(kw, meta)
                self.db.add(self._build(kw, item, niche, blog_id))
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
                "samples": samples[:40],
                "api_calls": api_calls, "errors": errors}

    async def collect_with_config(
        self, cfg, blog_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """모듈 설정으로 수집한다 — 수동 화면과 스케줄러가 같이 쓴다.

        시드 선정(직접 입력 → 채택 키워드 재귀 → 블로그 카테고리)과
        수식어 결합을 거쳐 collect() 에 넘긴다. 카테고리만 쓰면 매번 같은
        결과가 나와 소재가 고갈된다.
        """
        from .expander import expand, pick_seeds

        category_seeds = (
            await self.seeds_for_blog(blog_id)
            if blog_id and cfg.use_blog_categories else []
        )
        picked = await pick_seeds(
            self.db, self.user_id, cfg, category_seeds, blog_id)
        if not picked:
            return {"success": False, "error": (
                "쓸 수 있는 시드가 없습니다 — 모듈에 시드 키워드를 입력하거나, "
                "플로우에 블로그를 연결하고 그 블로그의 카테고리를 활성화하세요"
            )}

        self.thresholds = Thresholds.build(
            cfg.min_volume, cfg.min_saturation, cfg.max_volume)
        expanded = expand(picked, cfg)
        logger.info(
            "[KEYWORD_LAB] 시드 %d개 → 수식어 결합 %d개 | blog=%s",
            len(picked), len(expanded), blog_id,
        )
        result = await self._collect_rows(expanded, blog_id, cfg.collect_limit)
        # 재귀로 promoted 를 켠 것을 저장한다.
        await self.db.commit()

        # 검색광고 밖의 소스(자동완성·플래너·트렌드·서치콘솔)
        remaining = max(0, cfg.collect_limit - (result.get("saved") or 0))
        extra = await self._collect_sources(
            cfg, blog_id, [m["seed"] for m in expanded], remaining)
        result["saved"] = (result.get("saved") or 0) + extra.get("saved", 0)
        result["by_source"] = extra.get("by_source") or {}
        result["samples"] = (list(result.get("samples") or [])
                             + list(extra.get("samples") or []))[:40]
        result["source_errors"] = extra.get("errors") or []
        if extra.get("errors"):
            result.setdefault("errors", []).extend(extra["errors"])

        result["seed_count"] = len(picked)
        result["expanded_count"] = len(expanded)
        return result

    async def _collect_sources(self, cfg, blog_id: Optional[int],
                               seeds: List[str],
                               limit: int) -> Dict[str, Any]:
        """검색광고 외 소스에서 모아 저장한다.

        소스 하나가 실패해도 회차를 죽이지 않는다. 검색량이 없는 후보는
        검색광고로 보강한 뒤 저장한다 — 검색량이 없으면 판정이 영원히
        pending 이라 재고로 이어지지 않는다.
        """
        from .ingest import IdeaIngestor
        from .sources.base import SRC_NAVER_ADS
        from .sources import registry

        others = [c for c in cfg.sources if c != SRC_NAVER_ADS]
        if not others or limit <= 0:
            return {"saved": 0, "by_source": {}, "errors": []}

        blog = await self._blog(blog_id) if blog_id else None
        gathered = await registry.gather(
            self.db, self.settings, blog, seeds, others,
            user_id=self.user_id,
            niche_filter=getattr(cfg, "discovery_niche_filter", True))

        existing = await self._existing_keywords(blog_id)
        fresh = [i for i in gathered["ideas"]
                 if i.keyword.lower() not in existing]

        enriched = await registry.enrich_volumes(
            self.settings, fresh, cfg.enrich_limit)

        ingestor = IdeaIngestor(self.db, self.user_id, self._classify,
                                self.thresholds)
        stored = await ingestor.save(fresh, blog_id, existing, limit)
        await self.db.commit()

        errors = list(gathered.get("errors") or [])
        errors.extend(enriched.get("errors") or [])
        logger.info(
            "[KEYWORD_LAB] 추가 소스 | 수집 %d · 저장 %d · 검색량 보강 %d",
            len(gathered["ideas"]), stored["saved"], enriched["filled"],
        )
        return {"saved": stored["saved"], "by_source": stored["by_source"],
                "samples": stored.get("samples") or [],
                "enriched": enriched["filled"], "errors": errors}

    async def _blog(self, blog_id: int):
        """대상 블로그. 서치콘솔 속성 해석에 쓴다."""
        return (await self.db.execute(
            select(Blog).where(Blog.id == blog_id)
        )).scalar_one_or_none()

    def _build(self, keyword: str, item: dict, niche: dict,
               blog_id: Optional[int]) -> KeywordCandidate:
        volume = item.get("total_search_volume")
        verdict, reason, risk = judge(keyword, volume, None, self.thresholds)
        return KeywordCandidate(
            user_id=self.user_id,
            keyword=keyword,
            seed=niche.get("seed"),          # 어느 시드에서 나왔는지(추적용)
            blog_id=blog_id,
            topic_id=niche.get("topic_id"),
            subtopic_id=niche.get("subtopic_id"),
            search_volume_pc=item.get("pc_search_volume"),
            search_volume_mobile=item.get("mobile_search_volume"),
            search_volume=volume,
            competition=item.get("competition"),
            verdict=verdict,
            verdict_reason=reason,
            risk_label=risk,
            source="naver_ads",
        )

    async def _classify(self, keyword: str, fallback: dict) -> Dict[str, Any]:
        """키워드를 블로그오토 카테고리에 붙인다.

        **분류가 안 되면 비워 둔다(미분류).** 시드 카테고리를 물려주면
        「물류창고」와 「프랑스디저트」가 둘 다 '음식 효능' 이 된다 —
        실제로 그렇게 나왔다. 틀린 분류는 미분류보다 나쁘다.

        미분류 목록은 그 자체로 쓸모가 있다: 분류표에 무엇이 빠져 있는지
        알려 준다(현재 896개 분류 키워드로는 18%만 붙는다).
        """
        matcher = await self._matcher()
        if matcher:
            try:
                topic_id, subtopic_id, _ = \
                    await matcher.match_and_apply_to_keyword(keyword)
                if topic_id or subtopic_id:
                    return {"topic_id": topic_id, "subtopic_id": subtopic_id,
                            "seed": fallback.get("seed")}
            except Exception as e:  # noqa: BLE001
                logger.warning("[KEYWORD_LAB] 카테고리 매칭 실패 | %s | %s",
                               keyword, e)
        return {"topic_id": None, "subtopic_id": None,
                "seed": fallback.get("seed")}

    async def _matcher(self):
        """카테고리 매칭기. 한 번만 만든다."""
        if getattr(self, "_matcher_cache", "unset") == "unset":
            try:
                from ..category_matcher_service import CategoryMatcherService

                self._matcher_cache = CategoryMatcherService(self.db)
            except Exception as e:  # noqa: BLE001
                logger.warning("[KEYWORD_LAB] 카테고리 매칭기 초기화 실패 | %s", e)
                self._matcher_cache = None
        return self._matcher_cache

    async def _existing_keywords(self, blog_id: Optional[int]) -> set:
        """이미 가진 키워드 — **이 블로그 것만** 본다.

        사용자 전역으로 보면 1번 블로그가 먼저 잡은 키워드를 나머지 블로그가
        영원히 재수집하지 못한다(검토서 D-6). 니치가 겹치는 블로그끼리는
        같은 키워드를 각자 갖는 것이 정상이다.
        """
        q = select(KeywordCandidate.keyword).where(
            KeywordCandidate.user_id == self.user_id)
        q = q.where(KeywordCandidate.blog_id == blog_id) if blog_id \
            else q.where(KeywordCandidate.blog_id.is_(None))
        rows = (await self.db.execute(q)).scalars().all()
        return {k.lower() for k in rows if k}

    # ── 2단계: 문서수 측정 ───────────────────────────────
    async def measure(
        self, limit: int = 50, blog_id: Optional[int] = None,
        min_volume: Optional[int] = None,
        min_saturation: Optional[float] = None,
        max_volume: Optional[int] = None,
        window_days: int = PUB_WINDOW_DAYS,
    ) -> Dict[str, Any]:
        """아직 안 잰 후보의 **공급**을 조회하고 판정한다.

        공급은 누적 문서수가 아니라 최근 30일 발행량이 기준이다. 누적은
        10년치 총합이라 지금 경쟁이 붙는지 말해 주지 않는다.

        끊어서 여러 번 부를 수 있다. 이미 잰 것은 다시 재지 않는다.
        """
        search = NaverSearchService(self.settings)
        if not search.is_configured():
            return {"success": False,
                    "error": "네이버 검색 API 키가 설정에 없습니다"}

        th = Thresholds.build(min_volume, min_saturation, max_volume)
        rows = await self._unmeasured(limit, blog_id)

        now = datetime.now(pytz.timezone("Asia/Seoul"))
        measured, failed = 0, 0
        for row in rows:
            try:
                supply = await measure_supply(search, row.keyword, window_days)
            except Exception as e:  # noqa: BLE001
                logger.warning("[KEYWORD_LAB] 공급 조회 실패 | %s | %s",
                               row.keyword, e)
                failed += 1
                continue
            if not supply.get("success"):
                failed += 1
                continue

            await self._apply_supply(row, supply, th, now)
            measured += 1
            await asyncio.sleep(DOC_LOOKUP_DELAY)

        await self.db.commit()
        remaining = await self._pending_count(blog_id)
        logger.info("[KEYWORD_LAB] 측정 | %d건 | 실패 %d | 남은 %d",
                    measured, failed, remaining)
        return {"success": True, "measured": measured, "failed": failed,
                "remaining": remaining}

    async def _unmeasured(self, limit: int,
                          blog_id: Optional[int]) -> List[KeywordCandidate]:
        """아직 공급을 재지 않은 후보. 검색량이 큰 것부터 잰다."""
        q = (select(KeywordCandidate)
             .where(KeywordCandidate.user_id == self.user_id,
                    KeywordCandidate.measured_at.is_(None))
             .order_by(KeywordCandidate.search_volume.desc().nullslast())
             .limit(limit))
        if blog_id:
            q = q.where(KeywordCandidate.blog_id == blog_id)
        return list((await self.db.execute(q)).scalars().all())

    async def _apply_supply(self, row: KeywordCandidate, supply: dict,
                            th: Thresholds, now: datetime) -> None:
        """측정값을 엔진 지표로 저장하고 판정을 갱신한다."""
        pub = supply.get("monthly_pub_count")
        doc = supply.get("doc_count")
        sat = saturation_of(row.search_volume, supply_of(pub, doc))
        verdict, reason, risk = judge(
            row.keyword, row.search_volume, doc, th, monthly_pub_count=pub)

        await upsert_metric(
            self.db, row, PRIMARY_ENGINE,
            search_volume=row.search_volume,
            search_volume_pc=row.search_volume_pc,
            search_volume_mobile=row.search_volume_mobile,
            competition=row.competition,
            doc_count=doc, monthly_pub_count=pub,
            pub_count_capped=1 if supply.get("capped") else 0,
            saturation=sat, measured_at=now,
        )
        row.verdict, row.verdict_reason, row.risk_label = verdict, reason, risk
        row.measured_at = now

    async def _pending_count(self, blog_id: Optional[int]) -> int:
        from sqlalchemy import func as _f

        q = (select(_f.count(KeywordCandidate.id))
             .where(KeywordCandidate.user_id == self.user_id,
                    KeywordCandidate.measured_at.is_(None)))
        if blog_id:
            q = q.where(KeywordCandidate.blog_id == blog_id)
        return (await self.db.execute(q)).scalar() or 0

    # ── 재판정 ───────────────────────────────────────────
    async def rejudge(self, min_volume: Optional[int],
                      min_saturation: Optional[float],
                      max_volume: Optional[int] = None) -> Dict[str, Any]:
        """기준만 바꿔 다시 판정한다. API 를 부르지 않는다."""
        th = Thresholds.build(min_volume, min_saturation, max_volume)
        rows = (await self.db.execute(
            select(KeywordCandidate)
            .where(KeywordCandidate.user_id == self.user_id)
        )).scalars().all()
        for row in rows:
            row.verdict, row.verdict_reason, row.risk_label = judge(
                row.keyword, row.search_volume, row.doc_count, th,
                monthly_pub_count=row.monthly_pub_count)
        await self.db.commit()
        adopted = sum(1 for r in rows if r.verdict == VERDICT_ADOPT)
        return {"success": True, "total": len(rows), "adopted": adopted}
