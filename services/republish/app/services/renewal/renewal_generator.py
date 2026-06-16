"""리뉴얼 전용 생성 경로 (P2b).

기존 ContentGenerator.generate()를 건드리지 않고, 그 하위 서비스
인스턴스(제목재조합·참조수집·본문생성·내부링크·치환·이미지생성)를
재사용해 라이브 글을 현재 양식·최신 내용으로 재생성한다.

- 제목: plan.recombine_title=False면 라이브 제목 그대로, True면 재조합.
- 이미지: plan.image_action="reuse"면 기존 이미지 URL을 주입, "new"면 생성.
- 출력만 만들고 라이브 글 갱신은 하지 않는다(P2c가 담당, 데이터 변경 분리).
"""
import random
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog, BlogPlatform
from ...models.module import Module
from ..generation.content_generator_helper import generate_content_with_meta
from ..generation.generator import ContentGenerator
from .renewal_plan import RenewalPlan

logger = get_logger("renewal_generator", "app.log")


@dataclass
class RenewalContent:
    """리뉴얼 재생성 결과(라이브 글 갱신 전 산출물)."""

    success: bool
    title: str = ""
    content_html: str = ""
    image_url: Optional[str] = None
    seo_meta: Optional[dict] = None
    error: str = ""
    warnings: list = field(default_factory=list)


class RenewalGenerator:
    """리뉴얼 재생성 오케스트레이터 (생성 파이프라인 하위 서비스 재사용)."""

    def __init__(self, db: AsyncSession, user_id: Optional[int] = None) -> None:
        self.db = db
        # 동일 설정의 하위 서비스 인스턴스를 그대로 재사용해 현재 양식 일치.
        self.gen = ContentGenerator(db, user_id)

    async def regenerate(
        self,
        blog: Blog,
        module: Module,
        live_title: str,
        plan: RenewalPlan,
        subtopic_id: Optional[int] = None,
        topic_id: Optional[int] = None,
        text_replace_enabled: bool = True,
    ) -> RenewalContent:
        """라이브 글을 현재 양식·최신 내용으로 재생성한다."""
        settings = module.settings or {}
        ai_config = blog.ai_config or {}
        warnings: list = []

        working_title = await self._resolve_title(
            blog, module, live_title, plan, settings, ai_config,
        )

        ref_result = await self._collect_references(
            working_title, module, settings, ai_config,
        )
        if ref_result.count == 0:
            if settings.get("reference", {}).get("required", False):
                return RenewalContent(
                    success=False,
                    error="참조자료 수집 실패 (required=True)",
                )
            warnings.append("참조자료 없이 생성됨")

        category_name = await self._category_name(subtopic_id, topic_id)

        content_result = await generate_content_with_meta(
            ai_service=self.gen.ai_service,
            title=working_title,
            reference_injection=ref_result.to_prompt_injection(),
            settings=settings,
            blog=blog,
            category_name=category_name,
            keywords_text="",
        )
        content_with_links = await self.gen.internal_linker.insert_links(
            content=content_result["content"],
            blog_id=blog.id,
            current_title=working_title,
            module_settings=settings,
        )
        final_html = await self.gen.substitution_processor.process(
            content=content_with_links,
            blog_id=blog.id,
            text_replace_enabled=text_replace_enabled,
        )

        final_html, image_url = await self._apply_image(
            blog, working_title, settings, final_html, plan,
        )

        seo_meta = self._build_seo(blog, working_title, final_html)

        return RenewalContent(
            success=True,
            title=working_title,
            content_html=final_html,
            image_url=image_url,
            seo_meta=seo_meta,
            warnings=warnings,
        )

    async def _resolve_title(
        self, blog, module, live_title, plan, settings, ai_config,
    ) -> str:
        """제목 결정: 유지면 그대로, 재조합이면 title_recombiner."""
        if not plan.recombine_title:
            return live_title
        title_ai = ai_config.get("title_ai", {})
        tr = settings.get("title_recombine", {})
        styles = tr.get("styles", [])
        style = random.choice(styles) if styles else None
        rec = await self.gen.title_recombiner.recombine(
            original_title=live_title,
            module_id=module.id,
            provider=title_ai.get("provider"),
            model=title_ai.get("model"),
            style=style,
        )
        return rec.recombined_title or live_title

    async def _collect_references(
        self, working_title, module, settings, ai_config,
    ):
        """참조자료 수집 (blog.reference_ai 우선)."""
        ref_ai = ai_config.get("reference_ai", {})
        if ref_ai.get("provider"):
            ref_settings = settings.get("reference", {}).copy()
            ref_settings["ai_provider"] = ref_ai["provider"]
            if ref_ai.get("model"):
                ref_settings["ai_model"] = ref_ai["model"]
            return await self.gen.reference_collector.collect_and_summarize(
                search_query=working_title, ref_settings=ref_settings,
            )
        return await self.gen.reference_collector.collect_and_summarize(
            search_query=working_title, module_id=module.id,
        )

    async def _category_name(self, subtopic_id, topic_id) -> str:
        """카테고리 표시명(프롬프트 플레이스홀더용). 없으면 빈 문자열."""
        from ...models.category import SubTopic, Topic

        if subtopic_id:
            sub = await self.db.get(SubTopic, subtopic_id)
            if sub:
                top = await self.db.get(Topic, sub.topic_id)
                return f"{top.name} > {sub.name}" if top else sub.name
        if topic_id:
            top = await self.db.get(Topic, topic_id)
            if top:
                return top.name
        return ""

    async def _apply_image(
        self, blog, working_title, settings, final_html, plan,
    ):
        """이미지 적용: reuse면 기존 URL 주입, new면 생성. (final_html, url)."""
        if plan.image_action == "reuse" and plan.reuse_image_url:
            from ..publishing.html_injector import HtmlInjector

            platform = (
                blog.platform.value
                if isinstance(blog.platform, BlogPlatform)
                else str(blog.platform)
            )
            html = HtmlInjector().inject_featured_image(
                html=final_html,
                image_url=plan.reuse_image_url,
                title=working_title,
                editor_type=getattr(blog, "editor_type", "classic"),
                platform=platform,
            )
            return html, plan.reuse_image_url

        img = await self.gen._generate_image_with_retry(
            blog=blog, working_title=working_title,
            settings=settings, final_html=final_html, keywords_text="",
        )
        if img and img.success and img.image_url:
            return (img.final_html or final_html), img.image_url
        return final_html, None

    @staticmethod
    def _build_seo(blog, working_title, final_html) -> Optional[dict]:
        """SEO 메타(규칙 기반). 실패 시 None."""
        try:
            from ..publishing.seo_meta_builder import SEOMetaBuilder

            return SEOMetaBuilder().build(
                blog=blog, title=working_title, content_html=final_html,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RENEWAL_GEN] SEO 메타 실패(무시): %s", exc)
            return None
