"""키워드 모듈 실행기 — 한 회차를 온전히 수행한다.

**수동 화면과 스케줄러가 같은 함수를 부른다.** 다른 코드를 타면 한쪽
에서만 나는 버그가 생긴다.

입력은 `blog_id` + `settings` dict 뿐이다(모듈 settings 와 같은 모양).
출력은 다른 실행기와 같은 `{success, ...}` 형태다.

순서도: docs/flowcharts/keyword_module.md
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from ...models.title import MainTitle
from ...models.user_settings import UserSettings
from .service import KeywordLabService
from .settings import KeywordModuleSettings
from .title_maker import TitleMaker

logger = get_logger("keyword_runner", "app.log")


class KeywordModuleRunner:
    """수집 → 측정 → 제목 생성을 한 번에 수행한다."""

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
            steps: 일부 단계만 — ['collect','measure','titles'] 중
        """
        cfg = KeywordModuleSettings.parse(settings)
        if not cfg.enabled and not force:
            return {"success": True, "skipped": True,
                    "message": "모듈이 꺼져 있습니다"}

        steps = steps or ["collect", "measure", "titles"]
        blog = await self._blog(blog_id) if blog_id else None

        # 재고를 먼저 본다. 충분하면 돌지 않는다 — 매번 도는 것은 API 낭비다.
        if not force and "collect" in steps:
            stock = await self._inventory(blog)
            if stock >= cfg.min_inventory:
                msg = f"재고 충분 ({stock}/{cfg.min_inventory})"
                logger.info("[KEYWORD_RUNNER] %s | blog=%s", msg, blog_id)
                return {"success": True, "skipped": True, "message": msg,
                        "inventory": stock}

        user_settings = await self._user_settings()
        if not user_settings:
            return {"success": False,
                    "error": "사용자 설정이 없습니다. API 키를 먼저 등록하세요"}

        svc = KeywordLabService(self.db, user_settings, self.user_id)
        out: Dict[str, Any] = {"success": True, "blog_id": blog_id}

        if "collect" in steps:
            out["collect"] = await svc.collect_with_config(cfg, blog_id)
            if not out["collect"].get("success"):
                # 수집이 실패하면 잴 것도 만들 것도 없다.
                return {"success": False,
                        "error": out["collect"].get("error"), **out}

        if "measure" in steps:
            out["measure"] = await svc.measure(
                limit=cfg.measure_limit, blog_id=blog_id,
                min_volume=cfg.min_volume, min_saturation=cfg.min_saturation)

        if "titles" in steps and cfg.make_titles:
            out["titles"] = await self._make_titles(cfg, blog)

        logger.info(
            "[KEYWORD_RUNNER] 회차 완료 | blog=%s | 수집 %s | 측정 %s | 제목 %s",
            blog_id,
            (out.get("collect") or {}).get("saved"),
            (out.get("measure") or {}).get("measured"),
            (out.get("titles") or {}).get("made"),
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
        collected = measured = made = 0
        ok = skipped = failed = 0
        errors: list = []
        details: list = []

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
            c = (result.get("collect") or {}).get("saved") or 0
            m = (result.get("measure") or {}).get("measured") or 0
            t = (result.get("titles") or {}).get("made") or 0
            collected += c
            measured += m
            made += t
            details.append({
                "blog_name": name, "status": "success",
                "detail": f"키워드 {c}개 · 측정 {m}건 · 제목 {t}편",
            })

        # 전부 실패했을 때만 실패다. 일부 블로그가 건너뛰는 것은 정상 동작이다.
        success = failed < len(rows) or not rows
        message = (f"블로그 {len(rows)}개 | 성공 {ok} · 건너뜀 {skipped} · "
                   f"실패 {failed} | 키워드 {collected}개 · 측정 {measured}건 · "
                   f"제목 {made}편")
        out: Dict[str, Any] = {
            "success": success, "message": message, "details": details,
            "collected": collected, "measured": measured, "titles_made": made,
            "blogs": len(rows), "ok": ok, "skipped_count": skipped,
            "failed": failed,
        }
        if errors:
            out["errors"] = errors
            if not success:
                out["error"] = errors[0]
        return out

    async def _make_titles(self, cfg: KeywordModuleSettings,
                           blog) -> Dict[str, Any]:
        from ..ai.ai_service import AIService

        try:
            maker = TitleMaker(self.db, AIService(self.db), self.user_id)
            return await maker.run(cfg, blog)
        except Exception as e:  # noqa: BLE001
            # 제목 생성이 실패해도 수집·측정 결과는 남는다.
            logger.warning("[KEYWORD_RUNNER] 제목 생성 실패 | %s", e)
            return {"success": False, "error": str(e)[:120], "made": 0}

    async def _inventory(self, blog) -> int:
        """이 니치의 사용 가능한 제목 수.

        블로그가 있으면 그 블로그의 활성 카테고리로 좁힌다. 전체 재고가
        많아도 그 니치가 비어 있으면 채워야 한다.
        """
        q = select(func.count(MainTitle.id)).where(
            MainTitle.status == "available")
        if blog is not None:
            from ...models.category import BlogCategory

            subs = (await self.db.execute(
                select(BlogCategory.subtopic_id).where(
                    BlogCategory.blog_id == blog.id,
                    BlogCategory.is_active.is_(True))
            )).scalars().all()
            subs = [s for s in subs if s]
            if subs:
                q = q.where(MainTitle.subtopic_id.in_(subs))
        return (await self.db.execute(q)).scalar() or 0

    async def _blog(self, blog_id: int):
        return (await self.db.execute(
            select(Blog).where(Blog.id == blog_id)
        )).scalar_one_or_none()

    async def _user_settings(self):
        return (await self.db.execute(
            select(UserSettings).where(UserSettings.user_id == self.user_id)
        )).scalar_one_or_none()
