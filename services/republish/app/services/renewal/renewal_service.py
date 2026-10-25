"""리뉴얼 오케스트레이터 (P2c).

한 글에 대해 source(라이브 fetch) → plan(제목/이미지 결정) →
generator(재생성) → updater(라이브 갱신)를 묶는다. dry_run=True면 재생성까지만
하고 라이브 글/DB를 건드리지 않는다(검증용, 기본값).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from ...models.crawled_post import CrawledPost
from .renewal_generator import RenewalGenerator
from .renewal_plan import decide_renewal_plan
from .renewal_source import RenewalSource
from .renewal_updater import RenewalUpdater
from . import renewal_ga, renewal_pick, renewal_record

logger = get_logger("renewal_service", "app.log")


class RenewalService:
    """단일 글 리뉴얼 오케스트레이터."""

    def __init__(self, db: AsyncSession, user_id: Optional[int] = None) -> None:
        self.db = db
        self.user_id = user_id

    async def renew_post(
        self, blog: Blog, crawled_post: CrawledPost,
        dry_run: bool = True, include_content: bool = False,
        force_action: Optional[str] = None, stage: str = "",
    ) -> dict:
        """글 1개 리뉴얼. dry_run이면 재생성 결과만 반환(갱신 안 함).

        include_content=True면 dry_run 결과에 원본/재생성 본문 전문을 포함
        (설정 시 원본 vs 리뉴얼 비교 미리보기용).
        force_action: 미리보기에서 판정을 정해 볼 때(augment/title/rewrite).
        stage: 고르기 단계(renewal_pick) — 기록용.
        """
        cfg = blog.renewal_config or {}
        live = await RenewalSource().fetch(
            blog, crawled_post.platform_post_id, crawled_post.url,
        )
        if not live:
            return await self._fetch_failed(blog, crawled_post, dry_run)

        plan, protected = await self._plan(blog, crawled_post, live, cfg, force_action)
        if plan.skip:
            logger.info("[RENEWAL] 건너뜀 | blog=%s | post=%s | %s",
                        blog.name, crawled_post.id, plan.action_reason)
            if not dry_run:
                # 주기만 미룬다. 다음 회차에 또 후보로 올라오면 의미가 없다.
                crawled_post.last_renewed_at = datetime.now()
                await self.db.commit()
            return {"success": True, "skipped": True,
                    "action": plan.action, "reason": plan.action_reason,
                    "title": live.title}

        rc = await self._regenerate(blog, crawled_post, live, plan, cfg)
        if isinstance(rc, dict):
            if rc.get("merge") and not dry_run:
                crawled_post.last_renewed_at = datetime.now()   # 같은 글을 매 회차 다시 고르지 않게
                await self.db.commit()
            return rc
        if dry_run:
            return self._preview(cfg, plan, live, rc, protected, stage, include_content)
        return await self._apply(blog, crawled_post, live, plan, rc, cfg, stage)

    async def _fetch_failed(self, blog: Blog, post: CrawledPost, dry_run: bool) -> dict:
        """라이브 글이 없으면(지운 글 등) 같은 글을 매 회차 다시 고르지 않게 미룬다."""
        if not dry_run and renewal_pick.enabled(blog.renewal_config):
            post.last_renewed_at = datetime.now()
            await self.db.commit()
            renewal_record.journal(blog, {"post": post.id, "url": post.url,
                                          "action": "fetch_failed"})
        return {"success": False, "error": "라이브 글 조회 실패"}

    async def _plan(self, blog: Blog, post: CrawledPost, live, cfg: dict,
                    force_action: Optional[str]):
        """(계획, 보호 글 여부). 보호 글은 rewrite 금지·제목 그대로."""
        view = None
        if renewal_pick.enabled(cfg):
            view = await renewal_ga.load_view(self.db, blog.id)
        perf = await self._performance(blog, post, view)
        protected = bool(view and post.id in view.top_ids)
        action, reason = force_action or perf.action, perf.reason
        if force_action:
            reason = f"미리보기 지정({force_action}) · 실제 판정: {perf.action} {perf.reason}"
        if protected and action in ("rewrite", "title"):
            action, reason = "augment", f"수익 상위 {renewal_ga.TOP_N} 보호 — 보강만 · {reason}"
        title_mode = cfg.get("title_mode", "keep")
        plan = decide_renewal_plan(
            title_mode, post.source == "generated", live.image_origin,
            live.featured_image_url or "", action=action, action_reason=reason,
        )
        if renewal_pick.enabled(cfg) and action == "rewrite" and not protected:
            plan.recombine_title = True
        if protected:
            plan.recombine_title = False
        return plan, protected

    async def _regenerate(self, blog: Blog, post: CrawledPost, live, plan, cfg: dict):
        """재생성 결과(RenewalContent) 또는 실패 dict."""
        module = await self._resolve_module(blog, post)
        if not module:
            return {"success": False, "error": "생성 프롬프트 모듈 확인 불가"}
        subtopic_id, topic_id = await self._resolve_category(post)
        main_title = None
        if post.matched_main_title_id:
            from ...models.title import MainTitle
            main_title = await self.db.get(MainTitle, post.matched_main_title_id)
        gaps = await self._gaps(blog, post, live, plan)
        rc = await RenewalGenerator(self.db, self.user_id or blog.user_id).regenerate(
            blog, module, live.title, plan,
            subtopic_id=subtopic_id, topic_id=topic_id,
            existing_content=live.content_html, gap_instruction=gaps,
            strict_title=renewal_pick.enabled(cfg), main_title=main_title,
            self_url=post.url or "", fact_cfg=self._fact_cfg(cfg),
        )
        if getattr(rc, "merge", False):
            renewal_record.merge_candidate(blog, {
                "post": post.id, "url": post.url, "title": live.title,
                "note": rc.title_note, "action": plan.action})
            return {"success": True, "skipped": True, "merge": True,
                    "reason": rc.error, "title": live.title}
        if not rc.success:
            return {"success": False, "error": rc.error, "warnings": rc.warnings}
        left = renewal_record.old_images(rc.content_html)
        if left:
            rc.warnings.append(f"옛 업로드 이미지 {len(left)}개 남음: {left[:2]}")
        rc.warnings.append(f"본문 그림 {len(renewal_record.image_urls(rc.content_html))}개")
        before, after = renewal_record.text_len(live.content_html), renewal_record.text_len(rc.content_html)
        rc.shrunk = plan.action == "augment" and after < before * renewal_record.MIN_KEEP
        if rc.shrunk:  # 보강인데 글이 줄면 갱신하지 않는다(수익 글 보호)
            rc.warnings.append(f"보강인데 글자 {before}→{after} 줄어듦 — 실제 갱신 안 함")
        if plan.action == "rewrite" and after < renewal_record.MIN_REWRITE:
            rc.shrunk = True  # 재작성은 줄어도 되지만 너무 짧으면 안 함
            rc.warnings.append(f"재작성 본문 {after}자 < {renewal_record.MIN_REWRITE}자 — 실제 갱신 안 함")
        return rc

    @staticmethod
    def _fact_cfg(cfg: dict):
        """사실 관문 설정 — 성과 고르기(pick=performance)일 때 기본으로 켠다."""
        if not renewal_pick.enabled(cfg):
            return None
        fc = cfg.get("fact_gate") if isinstance(cfg.get("fact_gate"), dict) else {}
        return None if fc.get("enabled") is False else fc

    def _preview(self, cfg: dict, plan, live, rc, protected: bool, stage: str,
                 include_content: bool) -> dict:
        """dry_run 결과(라이브·DB 안 건드림)."""
        result = {
            "success": True, "dry_run": True,
            "title_mode": cfg.get("title_mode", "keep"), "stage": stage,
            "recombine": plan.recombine_title, "protected": protected,
            "live_title": live.title, "new_title": rc.title, "title_note": getattr(rc, "title_note", ""),
            "image_origin": live.image_origin, "image_action": plan.image_action,
            "old_images": renewal_record.image_urls(live.content_html),
            "new_images": renewal_record.image_urls(rc.content_html),
            "new_image_file": rc.image_url,
            "original_len": len(live.content_html or ""),
            "content_len": len(rc.content_html),
            "text_len": [renewal_record.text_len(live.content_html),
                         renewal_record.text_len(rc.content_html)],
            "action": plan.action, "reason": plan.action_reason,
            "warnings": rc.warnings,
        }
        if include_content:
            # 설정 시 원본 vs 리뉴얼 비교용 본문 전문
            result["original_html"] = live.content_html
            result["new_html"] = rc.content_html
            result["reuse_image_url"] = plan.reuse_image_url
        return result

    async def _apply(self, blog: Blog, post: CrawledPost, live, plan, rc,
                     cfg: dict, stage: str) -> dict:
        """원본 백업 → 라이브 갱신 → DB·기록."""
        strict = renewal_pick.enabled(cfg)
        if getattr(rc, "shrunk", False):
            return {"success": False, "error": "본문이 줄거나 짧아 갱신 안 함"}
        if strict and not renewal_record.backup(blog, live.platform_post_id,
                                                live.title, live.content_html):
            return {"success": False, "error": "원본 백업 실패 — 갱신 안 함"}
        upd = await RenewalUpdater(self.db).update(
            blog, live.platform_post_id, rc.title, rc.content_html,
            bump_date=bool(cfg.get("bump_date", not strict)),
        )
        if not upd.get("success"):
            return {"success": False, "error": "갱신 실패: " + upd.get("error", "")}
        post.title = rc.title
        post.content_html = rc.content_html
        if rc.image_url:
            post.image_url = rc.image_url
        post.last_renewed_at = datetime.now()
        await self.db.commit()
        renewal_record.journal(blog, {
            "post": post.id, "url": post.url, "stage": stage, "action": plan.action,
            "reason": plan.action_reason, "old_title": live.title, "new_title": rc.title,
            "image": plan.image_action, "image_changed": plan.image_action == "new",
            "warnings": rc.warnings})
        logger.info(
            "[RENEWAL] 완료 | blog=%s | post=%s | title='%s' | image=%s",
            blog.name, post.id, rc.title[:30], plan.image_action,
        )
        return {
            "success": True, "title": rc.title,
            "url": upd.get("link"), "image_action": plan.image_action,
            "action": plan.action, "reason": plan.action_reason,
        }

    async def _performance(self, blog: Blog, crawled_post: CrawledPost, view=None):
        """이 글의 성과 판정.

        지표가 없으면 legacy — **지금 동작 그대로**다. 없는 데이터를 0 으로
        읽으면 "유입 없는 글" 이 되어 멀쩡한 글이 갈아엎힌다.
        서치콘솔 이력이 없으면 GA(page_metrics_daily)로 읽는다(view 가 있을 때).
        """
        from sqlalchemy import select

        from ...models.search_visibility import SearchVisibilityUrl
        from ..analytics.performance import Performance, evaluate

        cfg = (blog.renewal_config or {}).get("performance") or {}
        if not cfg.get("enabled", False):
            return Performance(url_id=0, reason="성과 판정 꺼짐")

        row = (await self.db.execute(
            select(SearchVisibilityUrl).where(
                SearchVisibilityUrl.crawled_post_id == crawled_post.id
            ).limit(1)
        )).scalars().first()
        if not row:
            if view is not None:
                return await renewal_ga.performance(self.db, blog.id, crawled_post.id, view)
            return Performance(url_id=0, reason="발행 URL 이력 없음")
        try:
            perf = await evaluate(self.db, row.id, thresholds=cfg.get("thresholds"))
        except Exception as e:  # noqa: BLE001 — 판정 실패로 리뉴얼을 막지 않는다
            logger.warning("[RENEWAL] 성과 판정 실패 | post=%s | %s",
                           crawled_post.id, e)
            return Performance(url_id=row.id, reason="판정 실패")
        if perf.action == "legacy" and view is not None:
            return await renewal_ga.performance(self.db, blog.id, crawled_post.id, view)
        return perf

    async def _gaps(self, blog: Blog, crawled_post: CrawledPost,
                    live, plan) -> str:
        """보강할 때만 니즈 갭을 붙인다.

        전면 재작성에는 넣지 않는다 — 새로 쓰는 글에 "빠진 것" 을 지시하면
        그것만 다루는 글이 된다.
        """
        if plan.action not in ("augment", "title"):
            return ""
        try:
            from ..analytics.intent_gap import gaps_for_url, to_prompt

            gaps = await gaps_for_url(
                self.db, blog, crawled_post.url or "",
                live.content_html or "")
            if gaps:
                logger.info("[RENEWAL] 니즈 갭 %d건 | post=%s | %s",
                            len(gaps), crawled_post.id,
                            [g["query"] for g in gaps[:3]])
            return to_prompt(gaps)
        except Exception as e:  # noqa: BLE001
            logger.warning("[RENEWAL] 니즈 갭 실패 | post=%s | %s",
                           crawled_post.id, e)
            return ""

    async def _resolve_module(self, blog: Blog, crawled_post: CrawledPost):
        """리뉴얼에 쓸 생성 프롬프트 모듈 결정.

        1순위: 그 블로그에 연동된 생성(prompt) 모듈(플로우 연결) — 현재 양식
            일치, 안전. (향후 카테고리별 프롬프트 분기 여지)
        2순위: 그 글의 원본 생성 모듈(GenerationHistory.prompt_module_id).
        둘 다 없으면 None(레거시 등) → 호출측 스킵.
        """
        from sqlalchemy import select

        from ...models.flow_blog import FlowBlog
        from ...models.flow_module import FlowModule
        from ...models.generation_history import GenerationHistory
        from ...models.module import Module
        from ...models.module_type import ModuleType

        # 1) 블로그에 연동된 생성(prompt) 모듈
        q = (
            select(Module)
            .join(FlowModule, FlowModule.module_id == Module.id)
            .join(FlowBlog, FlowBlog.flow_id == FlowModule.flow_id)
            .join(ModuleType, Module.module_type_id == ModuleType.id)
            .where(FlowBlog.blog_id == blog.id, ModuleType.code == "prompt")
            .limit(1)
        )
        module = (await self.db.execute(q)).scalars().first()
        if module:
            return module

        # 2) 원본 생성 모듈(이력)
        if crawled_post.generation_history_id:
            gh = await self.db.get(
                GenerationHistory, crawled_post.generation_history_id,
            )
            if gh and gh.prompt_module_id:
                module = await self.db.get(Module, gh.prompt_module_id)
                if module:
                    return module
        return None

    async def _resolve_category(self, crawled_post: CrawledPost):
        """매칭된 MainTitle에서 (subtopic_id, topic_id) 추출. 없으면 (None, None)."""
        if crawled_post.matched_main_title_id:
            from ...models.title import MainTitle

            mt = await self.db.get(
                MainTitle, crawled_post.matched_main_title_id,
            )
            if mt:
                return (
                    getattr(mt, "subtopic_id", None),
                    getattr(mt, "topic_id", None),
                )
        return None, None
