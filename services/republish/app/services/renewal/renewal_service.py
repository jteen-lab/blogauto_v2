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

logger = get_logger("renewal_service", "app.log")


class RenewalService:
    """단일 글 리뉴얼 오케스트레이터."""

    def __init__(self, db: AsyncSession, user_id: Optional[int] = None) -> None:
        self.db = db
        self.user_id = user_id

    async def renew_post(
        self, blog: Blog, crawled_post: CrawledPost,
        dry_run: bool = True, include_content: bool = False,
    ) -> dict:
        """글 1개 리뉴얼. dry_run이면 재생성 결과만 반환(갱신 안 함).

        include_content=True면 dry_run 결과에 원본/재생성 본문 전문을 포함
        (설정 시 원본 vs 리뉴얼 비교 미리보기용).
        """
        cfg = blog.renewal_config or {}
        title_mode = cfg.get("title_mode", "keep")

        live = await RenewalSource().fetch(
            blog, crawled_post.platform_post_id, crawled_post.url,
        )
        if not live:
            return {"success": False, "error": "라이브 글 조회 실패"}

        is_blogauto = crawled_post.source == "generated"
        perf = await self._performance(blog, crawled_post)
        plan = decide_renewal_plan(
            title_mode, is_blogauto, live.image_origin,
            live.featured_image_url or "",
            action=perf.action, action_reason=perf.reason,
        )

        # **잘 되는 글은 건드리지 않는다.** 지금까지 없던 선택지다.
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

        module = await self._resolve_module(blog, crawled_post)
        if not module:
            return {"success": False, "error": "생성 프롬프트 모듈 확인 불가"}

        subtopic_id, topic_id = await self._resolve_category(crawled_post)
        # user_id 미지정 시 블로그 소유자로 폴백(AIService 키 조회용).
        gen_user_id = self.user_id or blog.user_id
        gaps = await self._gaps(blog, crawled_post, live, plan)
        rc = await RenewalGenerator(self.db, gen_user_id).regenerate(
            blog, module, live.title, plan,
            subtopic_id=subtopic_id, topic_id=topic_id,
            existing_content=live.content_html,
            gap_instruction=gaps,
        )
        if not rc.success:
            return {"success": False, "error": rc.error}

        if dry_run:
            result = {
                "success": True, "dry_run": True,
                "title_mode": title_mode,
                "recombine": plan.recombine_title,
                "live_title": live.title, "new_title": rc.title,
                "image_origin": live.image_origin,
                "image_action": plan.image_action,
                "content_len": len(rc.content_html),
                "action": plan.action, "reason": plan.action_reason,
                "gaps": gaps.splitlines()[4:] if gaps else [],
                "warnings": rc.warnings,
            }
            if include_content:
                # 설정 시 원본 vs 리뉴얼 비교용 본문 전문
                result["original_html"] = live.content_html
                result["new_html"] = rc.content_html
                result["reuse_image_url"] = plan.reuse_image_url
            return result

        upd = await RenewalUpdater(self.db).update(
            blog, live.platform_post_id, rc.title, rc.content_html,
        )
        if not upd.get("success"):
            return {"success": False, "error": "갱신 실패: " + upd.get("error", "")}

        crawled_post.title = rc.title
        crawled_post.content_html = rc.content_html
        if rc.image_url:
            crawled_post.image_url = rc.image_url
        crawled_post.last_renewed_at = datetime.now()
        await self.db.commit()
        logger.info(
            "[RENEWAL] 완료 | blog=%s | post=%s | title='%s' | image=%s",
            blog.name, crawled_post.id, rc.title[:30], plan.image_action,
        )
        return {
            "success": True, "title": rc.title,
            "url": upd.get("link"), "image_action": plan.image_action,
            "action": plan.action, "reason": plan.action_reason,
        }

    async def _performance(self, blog: Blog, crawled_post: CrawledPost):
        """이 글의 성과 판정.

        지표가 없으면 legacy — **지금 동작 그대로**다. 없는 데이터를 0 으로
        읽으면 "유입 없는 글" 이 되어 멀쩡한 글이 갈아엎힌다.
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
            return Performance(url_id=0, reason="발행 URL 이력 없음")
        try:
            return await evaluate(self.db, row.id,
                                  thresholds=cfg.get("thresholds"))
        except Exception as e:  # noqa: BLE001 — 판정 실패로 리뉴얼을 막지 않는다
            logger.warning("[RENEWAL] 성과 판정 실패 | post=%s | %s",
                           crawled_post.id, e)
            return Performance(url_id=row.id, reason="판정 실패")

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
