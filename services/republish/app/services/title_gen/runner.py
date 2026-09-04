"""제목 모듈 실행기 — 분류된 키워드로 제목을 만든다.

수집 모듈에서 떼어낸 단계다. 하는 일:

    1) 재고 확인 — 충분하면 돌지 않는다
    2) 클러스터 구성 — 비슷한 키워드를 묶는다
    3) 제목 생성 — 묶음은 대표 글 1편 + 곁가지 N편, 나머지는 단독
       (경쟁 제목 각도를 참고해 **겹치지 않게**)
    4) 품질 관문 — 금지어 → 분류 → 유사도 그룹핑 → 재고

**수동 화면·플로우·오토런이 같은 실행기를 부른다.** 다른 코드를 타면
한쪽에서만 나는 버그가 생긴다.

계획서: docs/plans/keyword_pipeline_restructure_review.md §5-2
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from ...models.user_settings import UserSettings
from ..keyword_lab.cluster_builder import ClusterBuilder
from ..keyword_lab.inventory import available_titles, target_inventory
from ..keyword_lab.title_maker import TitleMaker
from .settings import TitleModuleSettings

logger = get_logger("title_runner", "app.log")


class TitleModuleRunner:
    """제목 한 회차를 수행한다."""

    def __init__(self, db: AsyncSession, user_id: int,
                 subtopic_ids: tuple = ()):
        self.db = db
        self.user_id = user_id
        # 니치 하나만 채울 때(요약탭 카드). 비면 전체 — 모듈·오토런은
        # 늘 비어 있다.
        self.subtopic_ids = tuple(subtopic_ids or ())

    async def run_for_blogs(
        self, settings: Optional[dict], blogs: Optional[list] = None,
        force: bool = False, steps: Optional[list] = None,
    ) -> Dict[str, Any]:
        """연결된 블로그 전체를 돈다. 블로그가 없으면 전역으로 1회."""
        targets = list(blogs or [])
        if not targets:
            return _aggregate([("-", await self.run(settings, None, force,
                                                    steps))])
        rows = []
        for blog in targets:
            result = await self.run(settings, blog.id, force, steps)
            rows.append((getattr(blog, "name", None) or f"blog#{blog.id}",
                         result))
        return _aggregate(rows)

    async def run(self, settings: Optional[dict],
                  blog_id: Optional[int] = None, force: bool = False,
                  steps: Optional[list] = None) -> Dict[str, Any]:
        """한 회차.

        Args:
            settings: 모듈 settings
            blog_id: 대상 블로그(없으면 전역)
            force: 재고가 충분해도 실행(사용자가 직접 누른 실행)
            steps: ['cluster', 'titles'] 중 일부만
        """
        cfg = TitleModuleSettings.parse(settings)
        if not cfg.enabled and not force:
            return {"success": True, "skipped": True,
                    "message": "모듈이 꺼져 있습니다"}

        steps = steps or ["cluster", "titles"]
        blog = await self._blog(blog_id) if blog_id else None

        # 블로그가 없으면 재고를 판단할 수 없다(니치가 안 정해진다).
        # 판단 불가는 통과로 본다.
        if not force and blog is not None:
            stock = await available_titles(self.db, blog)
            target = await target_inventory(self.db, blog, cfg)
            if stock >= target:
                msg = f"재고 충분 ({stock}/{target})"
                logger.info("[TITLE_RUNNER] %s | blog=%s", msg, blog_id)
                return {"success": True, "skipped": True, "message": msg,
                        "inventory": stock, "target": target}

        maker_cfg = cfg.as_maker_config()
        out: Dict[str, Any] = {"success": True, "blog_id": blog_id}

        if "cluster" in steps:
            out["cluster"] = await ClusterBuilder(
                self.db, self.user_id).build(maker_cfg, blog)

        if "titles" in steps:
            out.update(await self._make(cfg, maker_cfg, blog))

        logger.info(
            "[TITLE_RUNNER] 회차 완료 | blog=%s | 묶음 %s | 제목 %s | 검증=%s",
            blog_id, (out.get("cluster") or {}).get("clusters"),
            (out.get("titles") or {}).get("made"), cfg.dry_run,
        )
        return out

    async def _make(self, cfg: TitleModuleSettings, maker_cfg: Any,
                    blog: Any) -> Dict[str, Any]:
        """묶음 제목 → 남은 단독 키워드 제목 순으로."""
        from ..ai.ai_service import AIService

        try:
            maker = TitleMaker(self.db, AIService(self.db), self.user_id)
            maker.angle_hint = await self._angle_hint(cfg)
            maker.subtopic_ids = self.subtopic_ids

            cluster_out: Dict[str, Any] = {}
            if cfg.cluster_enabled:
                cluster_out = await maker.run_clusters(
                    maker_cfg, blog, limit=cfg.cluster_limit)
            single_out = await maker.run(maker_cfg, blog,
                                         limit=cfg.keyword_limit)

            preview = (list(cluster_out.get("preview") or [])
                       + list(single_out.get("preview") or []))
            return {"titles": {
                "made": (cluster_out.get("made", 0)
                         + single_out.get("made", 0)),
                "clusters_titled": cluster_out.get("clusters", 0),
                "keywords": single_out.get("keywords", 0),
                "blocked": (cluster_out.get("blocked", 0)
                            + single_out.get("blocked", 0)),
                "queued": (cluster_out.get("queued", 0)
                           + single_out.get("queued", 0)),
                "dry_run": cfg.dry_run,
                "preview": preview,
                "error": cluster_out.get("error") or single_out.get("error"),
            }}
        except Exception as e:  # noqa: BLE001
            logger.warning("[TITLE_RUNNER] 제목 생성 실패 | %s", e)
            return {"titles": {"made": 0, "error": str(e)[:150],
                               "preview": [], "dry_run": cfg.dry_run}}

    async def _angle_hint(self, cfg: TitleModuleSettings):
        """경쟁 제목 각도를 넣어 주는 함수. 끄면 None."""
        if not cfg.use_angles:
            return None

        settings = await self._user_settings()
        if settings is None:
            return None

        from ..naver_search_service import NaverSearchService
        from .angles import fetch, hint
        from .niche import active_domains

        search = NaverSearchService(settings)
        if not search.is_configured():
            logger.info("[TITLE_RUNNER] 검색 API 미설정 — 각도 참고 생략")
            return None

        # 니치 도메인을 한 번만 읽어 회차 내내 재사용한다.
        # 비어 있으면 우선순위를 매기지 않는다(전부 통과).
        domains = await active_domains(self.db, self.user_id)

        async def provide(keyword: str) -> str:
            return hint(await fetch(search, keyword, cfg.angle_sample,
                                    niche=domains))

        return provide

    async def _blog(self, blog_id: int):
        return (await self.db.execute(
            select(Blog).where(Blog.id == blog_id)
        )).scalar_one_or_none()

    async def _user_settings(self):
        return (await self.db.execute(
            select(UserSettings).where(UserSettings.user_id == self.user_id)
        )).scalar_one_or_none()


def _aggregate(rows: List[tuple]) -> Dict[str, Any]:
    """블로그별 결과를 하나로 합친다."""
    made = blocked = queued = clusters = 0
    ok = skipped = failed = 0
    preview: list = []
    errors: list = []
    details: list = []
    dry_run = False

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
        titles = result.get("titles") or {}
        clusters += (result.get("cluster") or {}).get("clusters") or 0
        made += titles.get("made") or 0
        blocked += titles.get("blocked") or 0
        queued += titles.get("queued") or 0
        preview.extend(titles.get("preview") or [])
        if titles.get("dry_run"):
            dry_run = True
        if titles.get("error") and titles["error"] not in errors:
            errors.append(titles["error"])
        details.append({
            "blog_name": name, "status": "success",
            "detail": (f"묶음 {clusters}개 · 제목 "
                       f"{len(titles.get('preview') or []) if titles.get('dry_run') else titles.get('made', 0)}편"),
        })

    success = failed < len(rows) or not rows
    head = ""
    if ok == 0 and rows:
        reasons = [d["detail"] for d in details if d["status"] != "success"]
        head = f"실행 안 됨 — {reasons[0]} | " if reasons else ""

    tail = (f"제목 {len(preview)}편 미리보기(검증 모드 — 저장 안 함)"
            if dry_run else f"제목 {made}편")
    picks = [p["title"] for p in preview if p.get("state") == "ready"][:2]
    sample = " | 예: " + " / ".join(f'"{t}"' for t in picks) if picks else ""
    note = f" | ⚠ {errors[0]}" if not preview and errors else ""

    out: Dict[str, Any] = {
        "success": success,
        "message": (f"{head}블로그 {len(rows)}개 | 성공 {ok} · 건너뜀 {skipped} · "
                    f"실패 {failed} | 묶음 {clusters}개 · {tail}"
                    f" · 차단 {blocked} · 미분류 {queued}{sample}{note}"),
        "details": details, "preview": preview[:60],
        "made": made, "clusters": clusters, "blocked": blocked,
        "queued": queued, "dry_run": dry_run,
        "ok": ok, "skipped_count": skipped, "failed": failed,
    }
    if errors:
        out["errors"] = errors
        if not success:
            out["error"] = errors[0]
    return out
