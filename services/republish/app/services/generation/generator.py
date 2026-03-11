"""
생성 모듈 메인 서비스

전체 생성 파이프라인을 오케스트레이션합니다.

워크플로우:
1. 원본 제목 로드
2. 제목 재조합 (TitleRecombiner)
3. 참조자료 수집 (ReferenceCollector)
4. 글 생성 (AIService)
5. 내부링크 삽입 (InternalLinker)
6. 치환 처리 (SubstitutionProcessor)
6.5. 이미지 생성 (ImageGenerator) - Phase C
7. 저장 (CrawledPost + GenerationHistory)
8. 원본 제목 사용 처리 (mark_used)

설계 문서: generation_module_workplan.md - Phase 3 - 3.2.1
"""
import logging
import random
import time
from typing import Optional
from dataclasses import dataclass

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
from .image_generator import ImageGenerator

logger = logging.getLogger(__name__)

# 기본 글 생성 프롬프트
DEFAULT_CONTENT_PROMPT = (
    "다음 주제로 블로그 글을 작성해주세요.\n\n"
    "제목: {title}\n\n"
    "{reference_materials}\n\n"
    "규칙:\n"
    "- 마크다운 형식으로 작성\n"
    "- ## 소제목을 사용하여 섹션 구분\n"
    "- 자연스러운 한국어 문장\n"
    "- 1500~3000자 분량"
)


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
    error: Optional[str] = None


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
            import json
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
        content_result = await self._generate_content_with_meta(
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

        # 6.5 이미지 생성 (실패해도 글 생성은 계속)
        image_url = None
        ai_model_image = None
        section_images = None
        try:
            img_result = await self.image_generator.generate(
                blog=blog, title=working_title, module_settings=settings,
            )
            if img_result.success and img_result.image_url:
                image_url = img_result.image_url
                ai_model_image = img_result.ai_model
                section_images = img_result.section_images
                logger.info(
                    f"[GENERATOR] 이미지 생성 완료 | "
                    f"mode={img_result.image_mode} | "
                    f"sections={len(section_images) if section_images else 0}"
                )
        except Exception as e:
            logger.warning(
                f"[GENERATOR] 이미지 생성 실패 (글 생성은 계속): {e}"
            )

        # 7. GenerationHistory 저장
        elapsed = int(time.time() - start_time)
        history = GenerationHistory(
            blog_id=blog_id,
            source_title_id=source_title_id,
            prompt_module_id=prompt_module_id,
            recombined_title=working_title,
            ai_model_title=recombine_result.ai_model,
            ai_model_content=ai_content_model,
            ai_model_image=ai_model_image,
            image_url=image_url,
            reference_count=ref_result.count,
            generation_time_seconds=elapsed,
            content_length=len(final_html),
        )
        self.db.add(history)
        await self.db.flush()

        # 8. CrawledPost 저장 (source="generated")
        crawled_post = CrawledPost(
            blog_id=blog_id,
            title=working_title,
            source="generated",
            generation_history_id=history.id,
            match_status="unmatched",
            image_url=image_url,
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
        )

    async def _generate_content_with_meta(
        self,
        title: str,
        reference_injection: str,
        settings: dict,
        blog: Blog,
        category_name: str = "",
        keywords_text: str = "",
    ) -> dict:
        """
        AI로 글 생성 (블로그 AI 설정 기준)

        설정 우선순위:
        - AI 제공자/모델: Blog.ai_config.writing_ai (블로그 설정만 사용)
        - 프롬프트/세부설정: Module.settings.content_generation → 기본값

        Args:
            title: 재조합된 제목
            reference_injection: 참조자료 프롬프트 텍스트
            settings: 모듈 설정
            blog: 블로그 객체
            category_name: 카테고리 이름 (프롬프트 {category} 치환용)
            keywords_text: 키워드 텍스트 (프롬프트 {keywords} 치환용)

        Returns:
            dict: {"content": str, "model": str, "provider": str}
        """
        cg = settings.get("content_generation", {})
        ai_config = blog.ai_config or {}
        writing_ai = ai_config.get("writing_ai", {})

        # 프롬프트: 모듈 새 형식 -> 모듈 레거시 키 -> 기본값
        prompt_template = (
            cg.get("user_prompt_template")
            or settings.get("generation_prompt")
            or DEFAULT_CONTENT_PROMPT
        )
        full_prompt = prompt_template.replace(
            "{title}", title
        ).replace(
            "{reference_materials}", reference_injection
        ).replace(
            "{category}", category_name
        ).replace(
            "{keywords}", keywords_text
        )

        # AI 제공자: 블로그 ai_config.writing_ai 설정만 사용
        provider = writing_ai.get("provider")
        model = writing_ai.get("model")

        # 세부 설정: 모듈 설정 -> 기본값
        temperature = cg.get("temperature", 0.7)
        max_tokens = cg.get("max_tokens", 4000)
        system_prompt = cg.get("system_prompt") or None
        # 고급 AI 설정
        top_p = cg.get("top_p")
        top_k = cg.get("top_k")
        frequency_penalty = cg.get("frequency_penalty")
        presence_penalty = cg.get("presence_penalty")

        logger.info(
            f"[GENERATOR] AI 설정 | "
            f"provider={provider} (source=blog.writing_ai), "
            f"temp={temperature}, tokens={max_tokens}, "
            f"sys_prompt={'Y' if system_prompt else 'N'}"
        )

        # AI 호출
        result = await self.ai_service.generate(
            prompt=full_prompt,
            provider=provider,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
            top_p=top_p,
            top_k=top_k,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
        )

        if not result:
            raise RuntimeError("AI 글 생성 실패: 모든 제공자 호출 실패")

        return result

