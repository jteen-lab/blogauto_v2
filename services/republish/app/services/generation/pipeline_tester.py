"""파이프라인 단계별 테스트 서비스 (Phase D)"""
import random
import time
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.module import Module
from ...models.blog import Blog
from ...models.title import MainTitle
from .inventory_trigger import InventoryTrigger
from .title_recombiner import TitleRecombiner, RecombineStyleResult
from .reference_collector import ReferenceCollector
from .internal_linker import InternalLinker
from .substitution_processor import SubstitutionProcessor
from .image_generator import ImageGenerator
from .generator import ContentGenerator, DEFAULT_CONTENT_PROMPT
from ..ai.ai_service import AIService

logger = logging.getLogger(__name__)


class PipelineTester:
    """파이프라인 단계별 테스트 서비스 (DB 변경 없음, dry_run 제외)"""

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id
        self.inventory_trigger = InventoryTrigger(db)
        self.title_recombiner = TitleRecombiner(db, user_id)
        self.reference_collector = ReferenceCollector(db, user_id)
        self.ai_service = AIService(db, user_id)
        self.internal_linker = InternalLinker(db)
        self.substitution_processor = SubstitutionProcessor(db)
        self.image_generator = ImageGenerator(db, user_id)

    async def test_select_title(
        self, blog_id: int, module_id: int,
    ) -> dict:
        """Step 1: 제목 선택 테스트"""
        module = await self.db.get(Module, module_id)
        if not module:
            return self._error("select_title", "모듈을 찾을 수 없습니다")

        settings = module.settings or {}

        candidates = await self.inventory_trigger.find_available_titles(
            blog_id, limit=10, module_settings=settings,
        )

        if not candidates:
            return self._error("select_title", "사용 가능한 제목이 없습니다")

        selected = random.choice(candidates)
        has_module_cats = bool(settings.get("categories"))

        # 실제 적용된 카테고리 정보 조회
        if has_module_cats:
            subtopic_ids, topic_only_ids = (
                self.inventory_trigger._parse_module_categories(
                    settings["categories"]
                )
            )
            category_source = "module_settings"
        else:
            subtopic_ids, topic_only_ids = (
                await self.inventory_trigger._get_blog_category_filter_ids(
                    blog_id
                )
            )
            category_source = "blog_category"

        return {
            "step": "select_title",
            "success": True,
            "result": {
                "selected_title": {
                    "id": selected.id, "title": selected.title,
                },
                "total_candidates": len(candidates),
                "candidates": [
                    {"id": t.id, "title": t.title} for t in candidates
                ],
                "filter_info": {
                    "source": category_source,
                    "categories": settings.get("categories", []),
                    "applied_subtopic_ids": sorted(subtopic_ids),
                    "applied_topic_only_ids": sorted(topic_only_ids),
                    "has_category_filter": bool(
                        subtopic_ids or topic_only_ids
                    ),
                    "selection_method": "random",
                },
            },
        }

    async def test_recombine_title(
        self,
        module_id: int,
        blog_id: int,
        title_id: Optional[int] = None,
        title_text: Optional[str] = None,
        styles: Optional[list[str]] = None,
    ) -> dict:
        """Step 2: 제목 재조합 테스트 (스타일별 다중 결과, blog.title_ai 기준)"""
        original = await self._resolve_title(title_id, title_text)
        if not original:
            return self._error("recombine_title", "제목을 지정해주세요")

        module = await self.db.get(Module, module_id)
        settings = module.settings or {} if module else {}
        # 제목 재조합은 title_ai 설정만 사용 (content_generation은 글 생성용)
        blog = await self.db.get(Blog, blog_id)
        ai_config = blog.ai_config or {} if blog else {}
        title_ai = ai_config.get("title_ai", {})
        provider = title_ai.get("provider")
        model = title_ai.get("model")

        tr_settings = settings.get("title_recombine", {})

        start = time.time()
        style_results = await self.title_recombiner.recombine_with_styles(
            original_title=original,
            module_id=module_id,
            provider=provider,
            model=model,
            override_styles=styles,
        )
        elapsed = int(time.time() - start)

        first = style_results[0] if style_results else None
        # provider_source 판별
        if title_ai.get("provider"):
            prov_src = "blog_title_ai"
        else:
            prov_src = "none"

        # 에러 상세 정보 수집
        error_details = [
            r.error_detail for r in style_results if r.error_detail
        ]

        return {
            "step": "recombine_title", "success": True,
            "result": {
                "original_title": original,
                "recombined_title": first.recombined_title if first else original,
                "is_modified": any(r.is_modified for r in style_results),
                "ai_provider": first.ai_provider if first else "none",
                "ai_model": first.ai_model if first else "none",
                "style_results": [
                    {"style": r.style, "style_label": r.style_label,
                     "recombined_title": r.recombined_title,
                     "is_modified": r.is_modified,
                     "ai_provider": r.ai_provider, "ai_model": r.ai_model,
                     "error_detail": r.error_detail}
                    for r in style_results
                ],
                "total_styles": len(style_results),
                "generation_time_seconds": elapsed,
                "error_details": error_details if error_details else None,
                "settings_used": {
                    "enabled": tr_settings.get("enabled", False),
                    "styles": styles if styles is not None else tr_settings.get("styles", []),
                    "styles_source": "request" if styles is not None else "db",
                    "custom_prompt": tr_settings.get("custom_prompt"),
                    "provider_source": prov_src,
                    "resolved_provider": provider,
                    "resolved_model": model,
                    "title_ai_provider": title_ai.get("provider"),
                    "title_ai_model": title_ai.get("model"),
                },
            },
        }

    async def test_collect_references(
        self, module_id: int, search_query: str,
        ref_settings: Optional[dict] = None,
        blog_id: Optional[int] = None,
    ) -> dict:
        """Step 3: 참조자료 수집 테스트

        Args:
            module_id: 모듈 ID
            search_query: 검색어
            ref_settings: UI에서 전달된 참조자료 설정 (선택)
            blog_id: 블로그 ID (reference_ai 오버라이드용)
        """
        module = await self.db.get(Module, module_id)
        settings = module.settings or {} if module else {}
        db_ref_settings = settings.get("reference", {})
        # UI에서 전달된 설정이 있으면 사용, 없으면 DB 설정 사용
        effective_settings = ref_settings if ref_settings else db_ref_settings

        # 블로그 ai_config.reference_ai로 AI 설정 오버라이드
        ref_ai_source = "module"
        if blog_id:
            blog = await self.db.get(Blog, blog_id)
            if blog:
                ref_ai = (blog.ai_config or {}).get("reference_ai", {})
                if ref_ai.get("provider"):
                    effective_settings = effective_settings.copy()
                    effective_settings["ai_provider"] = ref_ai["provider"]
                    if ref_ai.get("model"):
                        effective_settings["ai_model"] = ref_ai["model"]
                    ref_ai_source = "blog_reference_ai"

        start = time.time()
        # 블로그 오버라이드가 적용된 경우 ref_settings로 직접 전달
        if ref_ai_source == "blog_reference_ai" or ref_settings:
            result = await self.reference_collector.collect_and_summarize(
                search_query=search_query,
                ref_settings=effective_settings,
            )
        else:
            result = await self.reference_collector.collect_and_summarize(
                search_query=search_query,
                module_id=module_id,
            )
        elapsed = int(time.time() - start)
        return {
            "step": "collect_references", "success": True,
            "result": {
                "search_query": search_query,
                "total_collected": result.count,
                "summaries": [
                    {"source_url": s.url, "summary": s.summary,
                     "length": len(s.summary)} for s in result.summaries
                ],
                "reference_injection": result.to_prompt_injection(),
                "generation_time_seconds": elapsed,
                "settings_used": {
                    "max_search": effective_settings.get("max_search"),
                    "crawl_target": effective_settings.get("crawl_target"),
                    "summary_count": effective_settings.get("summary_count"),
                    "summary_method": effective_settings.get("summary_method"),
                    "summary_style": effective_settings.get("summary_style"),
                    "ai_provider": effective_settings.get("ai_provider"),
                    "ai_model": effective_settings.get("ai_model"),
                    "ai_source": ref_ai_source,
                    "max_length": effective_settings.get("max_length"),
                },
            },
        }

    async def test_generate_content(
        self, module_id: int, blog_id: int,
        title: str, reference_text: Optional[str] = None,
    ) -> dict:
        """Step 4: AI 글 생성 테스트 (마크다운 반환)"""
        module = await self.db.get(Module, module_id)
        blog = await self.db.get(Blog, blog_id)
        if not module:
            return self._error("generate_content", "모듈을 찾을 수 없습니다")
        if not blog:
            return self._error("generate_content", "블로그를 찾을 수 없습니다")
        settings = module.settings or {}
        start = time.time()
        content_result, settings_info = await self._call_ai_generate(
            title, reference_text or "", settings, blog)
        elapsed = int(time.time() - start)
        if not content_result:
            return self._error("generate_content", "AI 글 생성 실패")
        content_md = content_result["content"]
        return {
            "step": "generate_content", "success": True,
            "result": {
                "content_markdown": content_md[:1000], "content_html": "",
                "content_length": len(content_md),
                "ai_provider": content_result.get("provider"),
                "ai_model": content_result.get("model"),
                "generation_time_seconds": elapsed,
                "settings_used": settings_info,
            },
        }

    async def test_add_internal_links(
        self, blog_id: int, module_id: int,
        current_title: str, content: str,
    ) -> dict:
        """Step 5: 내부링크 삽입 테스트"""
        module = await self.db.get(Module, module_id)
        settings = module.settings or {} if module else {}
        il_settings = settings.get("internal_links", {})

        start = time.time()
        result = await self.internal_linker.insert_links(
            content=content, blog_id=blog_id,
            current_title=current_title, module_settings=settings,
        )
        elapsed = int(time.time() - start)

        return {
            "step": "add_internal_links",
            "success": True,
            "result": {
                "content_with_links": result[:1000],
                "content_length": len(result),
                "generation_time_seconds": elapsed,
                "settings_used": {
                    "enabled": il_settings.get("enabled", True),
                    "intro_count": il_settings.get("intro_count"),
                    "conclusion_count": il_settings.get("conclusion_count"),
                },
            },
        }

    async def test_generate_image(
        self, module_id: int, blog_id: int, title: str,
    ) -> dict:
        """Step 6: 이미지 생성 테스트"""
        module = await self.db.get(Module, module_id)
        blog = await self.db.get(Blog, blog_id)
        if not module:
            return self._error("generate_image", "모듈을 찾을 수 없습니다")
        if not blog:
            return self._error("generate_image", "블로그를 찾을 수 없습니다")

        settings = module.settings or {}

        start = time.time()
        result = await self.image_generator.generate(
            blog=blog, title=title, module_settings=settings,
        )
        elapsed = int(time.time() - start)

        img_settings = settings.get("image_generation", {})

        return {
            "step": "generate_image",
            "success": result.success,
            "result": {
                "image_url": result.image_url,
                "image_mode": result.image_mode,
                "provider": result.provider,
                "ai_model": result.ai_model,
                "generation_time_seconds": elapsed,
                "blog_image_mode": getattr(blog, "image_mode", None),
                "enabled": img_settings.get("enabled", False),
            },
            **({"error": result.error} if result.error else {}),
        }

    async def test_substitution_html(
        self, blog_id: int, content: str,
        text_replace_enabled: bool = True,
    ) -> dict:
        """Step 7: 치환 처리 + HTML 변환 테스트"""
        start = time.time()
        final_html = await self.substitution_processor.process(
            content=content, blog_id=blog_id,
            text_replace_enabled=text_replace_enabled,
        )
        elapsed = int(time.time() - start)

        return {
            "step": "substitution_html",
            "success": True,
            "result": {
                "final_html": final_html[:1000],
                "html_length": len(final_html),
                "generation_time_seconds": elapsed,
                "text_replace_enabled": text_replace_enabled,
            },
        }

    async def test_full_pipeline(
        self, blog_id: int, module_id: int, dry_run: bool = True,
    ) -> dict:
        """전체 파이프라인 테스트 (7단계)"""
        start = time.time()
        steps = {}

        # Step 1: 제목 선택
        step1 = await self.test_select_title(blog_id, module_id)
        steps["1_select_title"] = self._summarize(step1)
        if not step1["success"]:
            return self._pipeline_result(steps, start, dry_run)

        title_id = step1["result"]["selected_title"]["id"]
        original_title = step1["result"]["selected_title"]["title"]

        # Step 2: 제목 재조합
        step2 = await self.test_recombine_title(
            module_id, blog_id=blog_id, title_id=title_id,
        )
        steps["2_recombine"] = self._summarize(step2)
        working_title = (
            step2["result"]["recombined_title"]
            if step2["success"] else original_title
        )

        # Step 3: 참조자료 수집
        step3 = await self.test_collect_references(
            module_id, working_title, blog_id=blog_id,
        )
        steps["3_references"] = self._summarize(step3)
        ref_text = (
            step3["result"].get("reference_injection", "")
            if step3["success"] else ""
        )

        # Step 4: AI 글 생성 (마크다운)
        step4 = await self.test_generate_content(
            module_id, blog_id, working_title, ref_text,
        )
        steps["4_generate"] = self._summarize(step4)
        content_md = (
            step4["result"].get("content_markdown", "")
            if step4["success"] else ""
        )

        # Step 5: 내부링크 삽입
        if content_md:
            step5 = await self.test_add_internal_links(
                blog_id, module_id, working_title, content_md,
            )
            steps["5_internal_links"] = self._summarize(step5)
            content_with_links = (
                step5["result"].get("content_with_links", content_md)
                if step5["success"] else content_md
            )
        else:
            content_with_links = ""

        # Step 6: 이미지 생성
        step6 = await self.test_generate_image(module_id, blog_id, working_title)
        steps["6_image"] = self._summarize(step6)

        # Step 7: 치환 처리 + HTML 변환
        if content_with_links:
            step7 = await self.test_substitution_html(blog_id, content_with_links)
            steps["7_substitution"] = self._summarize(step7)

        # dry_run=False면 실제 저장
        saved = False
        if not dry_run and step4["success"]:
            try:
                gen = ContentGenerator(self.db, self.user_id)
                await gen.generate(
                    blog_id=blog_id,
                    prompt_module_id=module_id,
                    source_title_id=title_id,
                )
                saved = True
            except Exception as e:
                logger.error(f"[PIPELINE_TEST] 저장 실패: {e}")

        return self._pipeline_result(steps, start, dry_run, saved)

    # ============================================================
    # 내부 헬퍼 메서드
    # ============================================================

    async def _resolve_title(
        self, title_id: Optional[int], title_text: Optional[str],
    ) -> Optional[str]:
        """title_id 또는 title_text에서 제목 문자열 가져오기"""
        if title_id:
            title_obj = await self.db.get(MainTitle, title_id)
            return title_obj.title if title_obj else title_text
        return title_text

    async def _call_ai_generate(
        self, title: str, ref_injection: str, settings: dict, blog: Blog,
    ) -> tuple:
        """AI 글 생성 호출 (generator.py 로직 재현)"""
        cg = settings.get("content_generation", {})
        writing_ai = (blog.ai_config or {}).get("writing_ai", {})
        prompt_template = (
            cg.get("user_prompt_template")
            or settings.get("generation_prompt") or DEFAULT_CONTENT_PROMPT
        )
        full_prompt = prompt_template.replace(
            "{title}", title).replace("{reference_materials}", ref_injection)
        # AI 제공자: 블로그 ai_config.writing_ai 설정만 사용
        provider = writing_ai.get("provider")
        model = writing_ai.get("model")
        temperature = cg.get("temperature", 0.7)
        max_tokens = cg.get("max_tokens", 4000)
        system_prompt = cg.get("system_prompt") or None
        settings_info = {
            "provider_source": "blog.writing_ai",
            "temperature": temperature, "max_tokens": max_tokens,
            "has_system_prompt": system_prompt is not None,
            "prompt_source": self._get_prompt_source(cg, settings),
        }
        result = await self.ai_service.generate(
            prompt=full_prompt, provider=provider, model=model,
            max_tokens=max_tokens, temperature=temperature,
            system_prompt=system_prompt,
        )
        return result, settings_info

    def _get_prompt_source(self, cg: dict, settings: dict) -> str:
        """사용된 프롬프트 소스 판별"""
        if cg.get("user_prompt_template"):
            return "content_generation.user_prompt_template"
        if settings.get("generation_prompt"):
            return "generation_prompt (legacy)"
        return "DEFAULT_CONTENT_PROMPT"

    def _error(self, step: str, message: str) -> dict:
        """에러 응답 생성"""
        return {"step": step, "success": False, "error": message}

    def _summarize(self, step_result: dict) -> dict:
        """Step 결과를 전체 파이프라인용으로 축약"""
        summary = {"success": step_result["success"]}
        if not step_result["success"]:
            summary["error"] = step_result.get("error", "실패")
            return summary
        r, step = step_result.get("result", {}), step_result.get("step", "")
        if step == "select_title":
            sel = r.get("selected_title", {})
            summary.update(title_id=sel.get("id"), title=sel.get("title"),
                           candidates=r.get("total_candidates", 0))
        elif step == "recombine_title":
            summary.update(title=r.get("recombined_title"), is_modified=r.get("is_modified"))
        elif step == "collect_references":
            summary["count"] = r.get("total_collected", 0)
        elif step == "generate_content":
            summary.update(length=r.get("content_length", 0), provider=r.get("ai_provider"))
        elif step == "add_internal_links":
            summary["length"] = r.get("content_length", 0)
        elif step == "generate_image":
            summary.update(url=r.get("image_url"), mode=r.get("image_mode"))
        elif step == "substitution_html":
            summary["html_length"] = r.get("html_length", 0)
        return summary

    def _pipeline_result(
        self, steps: dict, start: float, dry_run: bool, saved: bool = False,
    ) -> dict:
        """전체 파이프라인 결과 생성"""
        elapsed = int(time.time() - start)
        all_success = all(s.get("success") for s in steps.values())
        return {
            "step": "full_pipeline",
            "success": all_success,
            "dry_run": dry_run,
            "steps": steps,
            "total_time_seconds": elapsed,
            "saved": saved,
        }
