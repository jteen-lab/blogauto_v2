"""키워드 모듈 실행기 — 한 회차를 온전히 수행한다.

**수동 화면과 스케줄러가 같은 함수를 부른다.** 다른 코드를 타면 한쪽
에서만 나는 버그가 생긴다.

입력은 `blog_id` + `settings` dict 뿐이다(모듈 settings 와 같은 모양).
출력은 다른 실행기와 같은 `{success, ...}` 형태다.

순서도: docs/flowcharts/keyword_module.md
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from ...models.user_settings import UserSettings
from .inventory import available_titles, target_inventory
from .service import KeywordLabService
from .settings import KeywordModuleSettings

logger = get_logger("keyword_runner", "app.log")


class KeywordModuleRunner:
    """수집 → 측정 → 분류 → 재판정을 한 회차에 수행한다.

    제목 생성은 여기 없다. 중간 결과를 걸러낼 자리가 필요해
    '제목 생성/수집' 모듈이 따로 맡는다.
    """

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id

    async def run(
        self, settings: Optional[dict], blog_id: Optional[int] = None,
        force: bool = False, steps: Optional[list] = None,
    ) -> Dict[str, Any]:
        """한 회차 실행.

        Args:
            settings: 모듈 settings
            blog_id: 대상 블로그
            force: 재고가 충분해도 강제로 실행(수동 테스트용)
            steps: 일부 단계만 — ['collect','measure','classify','rejudge'] 중
        """
        cfg = KeywordModuleSettings.parse(settings)
        if not cfg.enabled and not force:
            return {"success": True, "skipped": True,
                    "message": "모듈이 꺼져 있습니다"}

        # 모듈이 맡을 단계는 설정이 정한다. 하나만 켜면 그 단계 전용
        # 모듈이 된다(수집만 / 측정만 …). 제목은 여기 없다 — 중간 결과를
        # 걸러낼 자리가 필요해 별도 모듈이 맡는다(계획서 S5).
        if steps is None:
            steps = (["feedback"] if cfg.feedback_enabled else []) + cfg.steps
        blog = await self._blog(blog_id) if blog_id else None

        # 재고를 먼저 본다. 충분하면 돌지 않는다 — 매번 도는 것은 API 낭비다.
        # 목표치는 상수가 아니라 **소진 속도**로 정한다(inventory.py).
        #
        # 단, 블로그가 없으면 재고를 판단할 수 없다. 니치가 정해지지 않아
        # 전체 재고와 비교하게 되는데, 그러면 다른 블로그 몫까지 세어
        # (실제로 2,249/30) 영원히 건너뛴다. 판단 불가는 통과로 본다.
        if not force and blog is not None and "collect" in steps:
            stock = await available_titles(self.db, blog)
            target = await target_inventory(self.db, blog, cfg)
            if stock >= target:
                msg = f"재고 충분 ({stock}/{target})"
                logger.info("[KEYWORD_RUNNER] %s | blog=%s", msg, blog_id)
                return {"success": True, "skipped": True, "message": msg,
                        "inventory": stock, "target": target}

        user_settings = await self._user_settings()
        if not user_settings:
            return {"success": False,
                    "error": "사용자 설정이 없습니다. API 키를 먼저 등록하세요"}

        svc = KeywordLabService(self.db, user_settings, self.user_id)
        out: Dict[str, Any] = {"success": True, "blog_id": blog_id}

        # 되먹임을 먼저 돌린다. 시드 우선순위가 그 결과를 쓴다.
        if "feedback" in steps and cfg.feedback_enabled and blog is not None:
            out["feedback"] = await self._feedback(cfg, blog)

        if "collect" in steps:
            out["collect"] = await svc.collect_with_config(cfg, blog_id)
            if not out["collect"].get("success"):
                # 수집이 실패하면 잴 것도 만들 것도 없다.
                return {"success": False,
                        "error": out["collect"].get("error"), **out}

        if "measure" in steps:
            # 검색량 보강 → 공급 측정. 보강을 빼면 이관된 옛 시드처럼
            # 검색량이 아예 없는 후보가 영원히 "검색량 미측정" 에 머문다.
            # 측정은 블로그와 무관하므로(키워드 자체의 지표) 전역으로 돈다.
            from .pool_ops import measure as pool_measure

            out["measure"] = await pool_measure(
                self.db, user_settings, self.user_id,
                limit=cfg.measure_limit,
                min_volume=cfg.min_volume, max_volume=cfg.max_volume,
                min_saturation=cfg.min_saturation,
                window_days=cfg.pub_window_days)

        if "classify" in steps:
            out["classify"] = await self._classify_leftovers(cfg)

        if "rejudge" in steps:
            # 기준값을 바꿨을 때 이미 쌓인 후보에도 반영한다.
            out["rejudge"] = await self._rejudge(cfg)

        logger.info(
            "[KEYWORD_RUNNER] 회차 완료 | blog=%s | 단계 %s | 수집 %s | 측정 %s "
            "| 분류 %s",
            blog_id, steps,
            (out.get("collect") or {}).get("saved"),
            (out.get("measure") or {}).get("measured"),
            (out.get("classify") or {}).get("matched"),
        )
        return out

    async def run_for_blogs(
        self, settings: Optional[dict], blogs: Optional[list] = None,
        force: bool = False, steps: Optional[list] = None,
    ) -> Dict[str, Any]:
        """플로우에 연결된 **블로그 전체**를 돈다.

        블로그마다 니치가 다르므로 회차도 블로그마다 돈다. 첫 번째 블로그만
        처리하면 나머지 블로그의 재고는 아무도 채우지 않는다(검토서 2-2).

        블로그가 하나도 없으면 블로그 없이 1회 돈다(직접 입력 시드만 쓰는 경우).
        """
        targets = list(blogs or [])
        if not targets:
            result = await self.run(settings, blog_id=None,
                                    force=force, steps=steps)
            return self._aggregate([("-", result)])

        rows = []
        for blog in targets:
            result = await self.run(settings, blog_id=blog.id,
                                    force=force, steps=steps)
            rows.append((getattr(blog, "name", None) or f"blog#{blog.id}",
                         result))
        return self._aggregate(rows)

    @staticmethod
    def _aggregate(rows: list) -> Dict[str, Any]:
        """블로그별 결과를 하나로 합친다 — 로그·화면이 같은 모양을 쓴다."""
        collected = measured = classified = 0
        enriched = rejudged = filtered = 0
        ok = skipped = failed = 0
        errors: list = []
        details: list = []
        samples: list = []
        by_source: dict = {}

        for name, result in rows:
            result = result or {}
            if not result.get("success"):
                failed += 1
                reason = result.get("error") or "실행 실패"
                if reason not in errors:
                    errors.append(reason)
                details.append({"blog_name": name, "status": "failed",
                                "detail": reason})
                continue
            if result.get("skipped"):
                skipped += 1
                details.append({"blog_name": name, "status": "skipped",
                                "detail": result.get("message", "건너뜀")})
                continue
            ok += 1
            collect = result.get("collect") or {}
            classified += (result.get("classify") or {}).get("matched") or 0
            enriched += (result.get("measure") or {}).get("enriched") or 0
            rejudged += (result.get("rejudge") or {}).get("total") or 0
            samples.extend(collect.get("samples") or [])
            filtered += collect.get("blocked") or 0
            for code, n in (collect.get("by_source") or {}).items():
                by_source[code] = by_source.get(code, 0) + n
            c = collect.get("saved") or 0
            m = (result.get("measure") or {}).get("measured") or 0
            collected += c
            measured += m
            details.append({
                "blog_name": name, "status": "success",
                "detail": f"키워드 {c}개 · 측정 {m}건",
            })

        # 전부 실패했을 때만 실패다. 일부 블로그가 건너뛰는 것은 정상 동작이다.
        success = failed < len(rows) or not rows

        # 아무것도 안 돌았으면 그 사실을 **맨 앞에** 적는다. 뒤에 숫자만
        # 나열하면 화면이 "성공" 으로만 보이고 왜 0건인지 알 수 없다.
        head = ""
        if ok == 0 and rows:
            reasons = [d["detail"] for d in details if d["status"] != "success"]
            head = f"실행 안 됨 — {reasons[0]} | " if reasons else ""
        # 수집 키워드 예시를 붙인다. 숫자만 있으면 무엇이 들어왔는지 모른다.
        sample = ""
        if samples:
            sample = " | 예: " + " / ".join(f'"{k}"' for k in samples[:2])
        note = f" | ⚠ {errors[0]}" if errors else ""
        message = (f"{head}블로그 {len(rows)}개 | 성공 {ok} · 건너뜀 {skipped} · "
                   f"실패 {failed} | 키워드 {collected}개 · 측정 {measured}건"
                   f"{f' · 금지어 차단 {filtered}건' if filtered else ''}"
                   f" · 분류 {classified}건"
                   f"{f' · 검색량 보강 {enriched}건' if enriched else ''}"
                   f"{f' · 재판정 {rejudged}건' if rejudged else ''}"
                   f"{sample}{note}")
        out: Dict[str, Any] = {
            "success": success, "message": message, "details": details,
            # 화면이 "몇 개 중 몇 개 표시" 를 적을 수 있게 총계도 준다.
            "collected": collected, "measured": measured,
            "blogs": len(rows), "ok": ok, "skipped_count": skipped,
            "failed": failed, "classified": classified,
            "enriched": enriched, "rejudged": rejudged, "blocked": filtered,
            "samples": samples[:100],
            "by_source": by_source,
        }
        if errors:
            out["errors"] = errors
            if not success:
                out["error"] = errors[0]
        return out

    async def _classify_leftovers(self, cfg: KeywordModuleSettings,
                                  limit: int = 500) -> Dict[str, Any]:
        """수집 때 분류가 안 된 키워드를 한 번 더 훑는다.

        분류표는 계속 자란다. 처음 수집할 때 안 붙었어도 나중에 붙을 수
        있으므로, 회차마다 미분류를 다시 본다. API 를 부르지 않는다.
        """
        from .pool_ops import classify

        try:
            return await classify(self.db, self.user_id, limit=limit)
        except Exception as e:  # noqa: BLE001
            logger.warning("[KEYWORD_RUNNER] 분류 실패 | %s", e)
            return {"scanned": 0, "matched": 0, "error": str(e)[:120]}

    async def _rejudge(self, cfg: KeywordModuleSettings) -> Dict[str, Any]:
        """모듈 기준값으로 전체 후보를 다시 판정한다. API 를 부르지 않는다."""
        from .pool_ops import rejudge

        try:
            return await rejudge(self.db, self.user_id, cfg.min_volume,
                                 cfg.max_volume, cfg.min_saturation)
        except Exception as e:  # noqa: BLE001
            logger.warning("[KEYWORD_RUNNER] 재판정 실패 | %s", e)
            return {"total": 0, "error": str(e)[:120]}

    async def _feedback(self, cfg: KeywordModuleSettings,
                        blog) -> Dict[str, Any]:
        """실측 성과를 회수한다. 실패해도 회차는 계속 돈다."""
        from .feedback import FeedbackCollector

        try:
            collector = FeedbackCollector(self.db, self.user_id)
            return await collector.apply(blog, days=cfg.feedback_days)
        except Exception as e:  # noqa: BLE001
            logger.warning("[KEYWORD_RUNNER] 되먹임 실패 | %s", e)
            return {"success": False, "error": str(e)[:120]}

    async def _blog(self, blog_id: int):
        return (await self.db.execute(
            select(Blog).where(Blog.id == blog_id)
        )).scalar_one_or_none()

    async def _user_settings(self):
        return (await self.db.execute(
            select(UserSettings).where(UserSettings.user_id == self.user_id)
        )).scalar_one_or_none()
