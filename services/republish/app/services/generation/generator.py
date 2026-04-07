"""
생성 모듈 메인 서비스 - 전체 생성 파이프라인 오케스트레이션

워크플로우: 제목 로드 → 재조합 → 참조수집 → 글생성 → 내부링크 → 치환 → 이미지 → 저장
설계 문서: generation_module_workplan.md - Phase 3 - 3.2.1
"""
import asyncio
import json
import logging
import random
import time
from typing import Optional
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.blog import Blog
from ...models.title import MainTitle
from ...models.module import Module
from ...models.crawled_post import CrawledPost
from ...models.generation_history import GenerationHistory
from ..ai.ai_service import AIService
from .title_recombiner import TitleRecombiner
from .reference_collector import ReferenceCollector
from .internal_linker import InternalLinker
from .substitution_processor import SubstitutionProcessor
from .image_generator import ImageGenerator, ImageResult
from .content_generator_helper import (
    generate_content_with_meta,
    DEFAULT_CONTENT_PROMPT,
)

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """생성 파이프라인 결과"""
    success: bool
    crawling_post_id: Optional[int] = None
    generation_history_id: Optional[int] = None
    recombined_title: Optional[str] = None
    final_html: Optional[str] = None
    reference_count: int = 0
    generation_time_seconds: int = 0
    content_length: int = 0
    ai_model_title: Optional[str] = None
    ai_model_content: Optional[str] = None
    ai_model_image: Optional[str] = None
    image_url: Optional[str] = None
    section_images: Optional[list] = None
    error: Optional[str] = None
    warnings: list = field(default_factory=list)


class ContentGenerator:
    """
    생성 모듈 메인 서비스

    전체 생성 파이프라인을 오케스트레이션합니다.
    Phase 2에서 구현된 서비스들을 조합하여 동작합니다.
    """

    def __init__(self, db: AsyncSession, user_id: int = 1):
        self.db = db
        self.user_id = user_id
        self.ai_service = AIService(db, user_id)
        self.title_recombiner = TitleRecombiner(db, user_id)
        self.reference_collector = ReferenceCollector(db, user_id)
        self.internal_linker = InternalLinker(db)
        self.substitution_processor = SubstitutionProcessor(db)
        self.image_generator = ImageGenerator(db, user_id)

    async def generate(
        self,
        blog_id: int,
        prompt_module_id: int,
        source_title_id: int,
        text_replace_enabled: bool = True,
    ) -> GenerationResult:
        """
        전체 생성 파이프라인 실행

        Args:
            blog_id: 블로그 ID
            prompt_module_id: 프롬프트 모듈 ID
            source_title_id: 원본 정식 제목 ID
            text_replace_enabled: 텍스트 치환 활성화 여부

        Returns:
            GenerationResult: 생성 결과
        """
        start_time = time.time()
        logger.info(
            f"[GENERATOR] 시작 | blog_id={blog_id} "
            f"| module_id={prompt_module_id} "
            f"| title_id={source_title_id}"
        )

        try:
            return await self._execute_pipeline(
                blog_id, prompt_module_id, source_title_id, start_time,
                text_replace_enabled=text_replace_enabled,
            )
        except Exception as e:
            elapsed = int(time.time() - start_time)
            logger.error(f"[GENERATOR] 파이프라인 실패: {e}")
            return GenerationResult(
                success=False,
                generation_time_seconds=elapsed,
                error=str(e),
            )

    async def _execute_pipeline(
        self,
        blog_id: int,
        prompt_module_id: int,
        source_title_id: int,
        start_time: float,
        text_replace_enabled: bool = True,
    ) -> GenerationResult:
        """파이프라인 실행 로직"""
        # 1. 원본 제목 로드
        source_title = await self.db.get(MainTitle, source_title_id)
        if not source_title:
            raise ValueError(f"제목을 찾을 수 없습니다: id={source_title_id}")

        blog = await self.db.get(Blog, blog_id)
        if not blog:
            raise ValueError(f"블로그를 찾을 수 없습니다: id={blog_id}")

        module = await self.db.get(Module, prompt_module_id)
        if not module:
            raise ValueError(f"모듈을 찾을 수 없습니다: id={prompt_module_id}")

        settings = module.settings or {}
        logger.debug(
            f"[GENERATOR] 1단계 완료: 데이터 로드 | "
            f"title='{source_title.title[:30]}' | blog={blog.name}"
        )

        # 2. 제목 재조합 (blog.title_ai 설정 사용, 스타일 랜덤 선택)
        ai_config = blog.ai_config or {}
        title_ai = ai_config.get("title_ai", {})
        title_provider = title_ai.get("provider")
        tr = settings.get("title_recombine", {})
        tr_styles = tr.get("styles", [])
        selected_style = random.choice(tr_styles) if tr_styles else None
        recombine_result = await self.title_recombiner.recombine(
            original_title=source_title.title,
            module_id=prompt_module_id,
            provider=title_provider,
            model=title_ai.get("model"),
            style=selected_style,
        )
        working_title = recombine_result.recombined_title
        logger.info(
            f"[GENERATOR] 제목 재조합 | "
            f"'{source_title.title[:30]}' → '{working_title[:30]}'"
        )

        # 3. 참조자료 수집 (blog.reference_ai 우선, 없으면 모듈 설정)
        ref_ai = ai_config.get("reference_ai", {})
        if ref_ai.get("provider"):
            # 블로그 AI 설정으로 모듈 참조자료 설정 오버라이드
            ref_settings = settings.get("reference", {}).copy()
            ref_settings["ai_provider"] = ref_ai["provider"]
            if ref_ai.get("model"):
                ref_settings["ai_model"] = ref_ai["model"]
            logger.info(
                f"[GENERATOR] 참조자료 AI: blog.reference_ai "
                f"| provider={ref_ai['provider']} "
                f"| model={ref_ai.get('model')}"
            )
            ref_result = await self.reference_collector.collect_and_summarize(
                search_query=working_title,
                ref_settings=ref_settings,
            )
        else:
            ref_result = await self.reference_collector.collect_and_summarize(
                search_query=working_title,
                module_id=prompt_module_id,
            )
        logger.info(
            f"[GENERATOR] 참조자료 수집 | count={ref_result.count}"
        )

        # 참조자료 검증: 0건일 때 required 여부에 따라 분기
        pipeline_warnings: list[str] = []
        if ref_result.count == 0:
            ref_required = settings.get("reference", {}).get(
                "required", False
            )
            if ref_required:
                elapsed = int(time.time() - start_time)
                logger.warning(
                    f"[GENERATOR] 참조자료 필수인데 0건 → 생성 중단 | "
                    f"title='{working_title[:30]}'"
                )
                return GenerationResult(
                    success=False,
                    generation_time_seconds=elapsed,
                    error="참조자료 수집 실패 (required=True)",
                    warnings=["참조자료 0건으로 생성 중단"],
                )
            else:
                logger.warning(
                    f"[GENERATOR] 참조자료 0건, 참조 없이 계속 | "
                    f"title='{working_title[:30]}'"
                )
                pipeline_warnings.append("참조자료 없이 생성됨")

        # 카테고리/키워드 정보 (프롬프트 플레이스홀더용)
        category_name = ""
        keywords_text = ""
        if source_title.subtopic_id or source_title.topic_id:
            from ...models.category import Topic, SubTopic
            if source_title.subtopic_id:
                subtopic = await self.db.get(SubTopic, source_title.subtopic_id)
                if subtopic:
                    topic = await self.db.get(Topic, subtopic.topic_id)
                    category_name = (
                        f"{topic.name} > {subtopic.name}" if topic
                        else subtopic.name
                    )
            elif source_title.topic_id:
                topic = await self.db.get(Topic, source_title.topic_id)
                if topic:
                    category_name = topic.name
        if source_title.keywords:
            try:
                kw_list = json.loads(source_title.keywords)
                if isinstance(kw_list, list):
                    keywords_text = ", ".join(str(k) for k in kw_list)
                elif isinstance(kw_list, str):
                    keywords_text = kw_list
            except (json.JSONDecodeError, TypeError):
                keywords_text = source_title.keywords or ""

        # 4. 글 생성
        logger.debug("[GENERATOR] 4단계 시작: AI 글 생성")
        content_result = await generate_content_with_meta(
            ai_service=self.ai_service,
            title=working_title,
            reference_injection=ref_result.to_prompt_injection(),
            settings=settings,
            blog=blog,
            category_name=category_name,
            keywords_text=keywords_text,
        )
        content_markdown = content_result["content"]
        ai_content_model = content_result.get("model")
        ai_content_provider = content_result.get("provider")

        # 5. 내부링크 삽입
        logger.debug("[GENERATOR] 5단계 시작: 내부링크 삽입")
        content_with_links = await self.internal_linker.insert_links(
            content=content_markdown,
            blog_id=blog_id,
            current_title=working_title,
            module_settings=settings,
        )

        # 6. 치환 처리 (마크다운 → HTML → 치환)
        logger.debug("[GENERATOR] 6단계 시작: 치환 처리")
        final_html = await self.substitution_processor.process(
            content=content_with_links,
            blog_id=blog_id,
            text_replace_enabled=text_replace_enabled,
        )

        # 6.5 이미지 생성 (재시도 포함, 실패해도 글 생성 계속)
        image_url = None
        ai_model_image = None
        section_images = None
        img_result = await self._generate_image_with_retry(
            blog=blog, working_title=working_title,
            settings=settings, final_html=final_html,
            keywords_text=keywords_text,
        )
        if img_result and img_result.success and img_result.image_url:
            image_url = img_result.image_url
            ai_model_image = img_result.ai_model
            section_images = img_result.section_images
            # both 모드: 섹션 이미지가 삽입된 HTML로 교체
            if img_result.final_html:
                final_html = img_result.final_html
            logger.info(
                f"[GENERATOR] 이미지 생성 완료 | "
                f"mode={img_result.image_mode} | "
                f"sections={len(section_images) if section_images else 0}"
            )
        else:
            if img_result is None:
                pipeline_warnings.append("이미지 생성 실패 (재시도 소진)")
            logger.warning(
                "[GENERATOR] 이미지 생성 최종 실패, 이미지 없이 계속"
            )

        # 6.7 SEO 메타 생성 (HTML 변환 후, 규칙 기반만 사용)
        seo_meta = None
        try:
            from ..publishing.seo_meta_builder import SEOMetaBuilder
            seo_builder = SEOMetaBuilder()
            seo_meta = seo_builder.build(
                blog=blog, title=working_title,
                content_html=final_html,
            )
            if seo_meta:
                logger.info(
                    "[GENERATOR] SEO 메타 | "
                    "kp='%s' | desc=%d자",
                    seo_meta.get(
                        "focus_keyphrase", ""
                    )[:30],
                    len(seo_meta.get(
                        "meta_description", ""
                    )),
                )
        except Exception as e:
            logger.warning(
                "[GENERATOR] SEO 메타 실패 (무시): %s", e
            )

        # 7. GenerationHistory 저장
        elapsed = int(time.time() - start_time)
        # section_images JSON 직렬화 (DB 저장용)
        section_images_json = (
            json.dumps(section_images, ensure_ascii=False)
            if section_images else None
        )
        history = GenerationHistory(
            blog_id=blog_id,
            source_title_id=source_title_id,
            prompt_module_id=prompt_module_id,
            recombined_title=working_title,
            ai_model_title=recombine_result.ai_model,
            ai_model_content=ai_content_model,
            ai_model_image=ai_model_image,
            image_url=image_url,
            section_images=section_images_json,
            content_html=final_html,
            reference_count=ref_result.count,
            generation_time_seconds=elapsed,
            content_length=len(final_html),
        )
        self.db.add(history)
        await self.db.flush()

        # 8. CrawledPost 저장 (source="generated", 원본 제목과 매칭)
        crawled_post = CrawledPost(
            blog_id=blog_id,
            title=working_title,
            source="generated",
            generation_history_id=history.id,
            matched_main_title_id=source_title_id,
            match_status="matched",
            match_score=100.0,
            image_url=image_url,
            content_html=final_html,
            seo_meta=seo_meta,
        )
        self.db.add(crawled_post)
        await self.db.flush()

        # GenerationHistory에 crawling_post_id 연결
        history.crawling_post_id = crawled_post.id

        # 9. 원본 제목 사용 처리
        source_title.mark_used()
        logger.debug(
            f"[GENERATOR] 9단계 완료: 제목 사용 처리 (id={source_title_id})"
        )

        await self.db.commit()

        logger.info(
            f"[GENERATOR] 완료 | time={elapsed}s "
            f"| content_length={len(final_html)} "
            f"| refs={ref_result.count}"
        )

        return GenerationResult(
            success=True,
            crawling_post_id=crawled_post.id,
            generation_history_id=history.id,
            recombined_title=working_title,
            final_html=final_html,
            reference_count=ref_result.count,
            generation_time_seconds=elapsed,
            content_length=len(final_html),
            ai_model_title=recombine_result.ai_model,
            ai_model_content=ai_content_model,
            ai_model_image=ai_model_image,
            image_url=image_url,
            section_images=section_images,
            warnings=pipeline_warnings,
        )

    async def _generate_image_with_retry(
        self,
        blog: Blog,
        working_title: str,
        settings: dict,
        final_html: str,
        keywords_text: str,
        max_retries: int = 2,
    ) -> Optional[ImageResult]:
        """이미지 생성 (지수 백오프 재시도, 실패 시 None 반환)

        Args:
            blog: 블로그 객체
            working_title: 재조합된 제목
            settings: 모듈 설정
            final_html: 치환 처리된 HTML
            keywords_text: 키워드 텍스트
            max_retries: 최대 재시도 횟수 (기본 2, 백오프 2초/4초)

        Returns:
            성공 시 ImageResult, 모든 시도 실패 시 None
        """
        total = max_retries + 1
        for attempt in range(total):
            try:
                result = await self.image_generator.generate(
                    blog=blog, title=working_title,
                    module_settings=settings, final_html=final_html,
                    keywords=keywords_text,
                )
                if result.success:
                    if attempt > 0:
                        logger.info(f"[GENERATOR] 이미지 재시도 성공 | attempt={attempt + 1}")
                    return result
                logger.warning(
                    f"[GENERATOR] 이미지 생성 실패 | attempt={attempt + 1}/{total} "
                    f"| error={getattr(result, 'error', 'unknown')}"
                )
            except Exception as e:
                logger.warning(
                    f"[GENERATOR] 이미지 생성 예외 | attempt={attempt + 1}/{total} | {e}"
                )
            if attempt < max_retries:
                wait = 2 ** (attempt + 1)  # 2초, 4초
                logger.debug(f"[GENERATOR] 이미지 재시도 대기 {wait}초")
                await asyncio.sleep(wait)

        return None


