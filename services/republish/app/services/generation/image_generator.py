"""
이미지 생성 총괄 서비스

Blog.image_mode에 따라 AI/템플릿 이미지를 생성합니다.
모드: template, openai/ai, both, none
오버레이 로직은 image_overlay_helper.py에 분리.
"""
import logging
import re
import time
from typing import Optional, List
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.blog import Blog
from .ai_image_service import AIImageService
from .template_image_service import TemplateImageService
from .image_param_converter import (
    normalize_provider, convert_to_provider_params,
    migrate_legacy_image_settings,
)
from .image_overlay_helper import overlay_title_on_image

logger = logging.getLogger(__name__)

# 섹션 헤딩 파싱용 패턴
_H2_PATTERN = re.compile(r'<h2[^>]*>(.*?)</h2>', re.IGNORECASE | re.DOTALL)
_HTML_TAG_PATTERN = re.compile(r'<[^>]+>')


@dataclass
class ImageResult:
    """이미지 생성 결과"""
    success: bool
    image_url: Optional[str] = None
    image_mode: Optional[str] = None
    provider: Optional[str] = None
    ai_model: Optional[str] = None
    generation_time_seconds: int = 0
    error: Optional[str] = None
    section_images: Optional[List[dict]] = field(default=None)
    final_html: Optional[str] = None


class ImageGenerator:
    """
    이미지 생성 총괄 서비스

    Blog.image_mode에 따라 적절한 서비스로 라우팅합니다.
    - "openai" / "ai": AI 이미지만 시도 (title_overlay 옵션)
    - "template": 항상 템플릿 이미지 생성 (enabled 체크 안 함)
    - "both": cover_source/section_source로 대표/섹션 이미지 소스 결정
    - None / "none": 이미지 생성 안 함
    """

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.ai_image = AIImageService(db, user_id)
        self.template_image = TemplateImageService()

    async def generate(
        self, blog: Blog, title: str, module_settings: dict,
        final_html: Optional[str] = None, keywords: str = "",
    ) -> ImageResult:
        """
        블로그 설정에 따라 이미지 생성

        Args:
            blog: Blog 객체
            title: 포스트 제목
            module_settings: 모듈 설정
            final_html: 생성된 글 HTML (both 모드에서 섹션 이미지 삽입용)
            keywords: 키워드 텍스트 ({keywords} 플레이스홀더 치환용)

        Returns:
            ImageResult (both 모드: final_html에 섹션 이미지 삽입됨)
        """
        start_time = time.time()
        image_mode = getattr(blog, "image_mode", None) or "template"
        img_settings = module_settings.get("image_generation", {})
        # 레거시 dalle{}/nanobanana{} 구조 자동 변환
        img_settings = migrate_legacy_image_settings(img_settings)

        # template/ai/openai 모드: blog.image_mode로 이미 결정됨 → 항상 생성
        # both 모드: blog.image_mode로 결정됨 → 항상 생성
        # none 모드: _dispatch에서 건너뜀
        # enabled 플래그는 image_mode 미설정 시 폴백용으로만 사용
        if image_mode not in ("template", "openai", "ai", "both"):
            if not img_settings.get("enabled", False):
                logger.debug("[IMAGE_GEN] 이미지 생성 비활성화 - 건너뜀")
                return ImageResult(success=True)

        logger.info(
            f"[IMAGE_GEN] 시작 | mode={image_mode} | title={title[:30]}"
        )

        try:
            result = await self._dispatch(
                blog, title, img_settings, image_mode, final_html,
                keywords,
            )
            result.generation_time_seconds = int(time.time() - start_time)
            if result.success and result.image_url:
                logger.info(
                    f"[IMAGE_GEN] 완료 | mode={result.image_mode} | "
                    f"provider={result.provider} | "
                    f"time={result.generation_time_seconds}s"
                )
            return result
        except Exception as e:
            elapsed = int(time.time() - start_time)
            logger.error(f"[IMAGE_GEN] 실패: {e}")
            return ImageResult(
                success=False,
                generation_time_seconds=elapsed,
                error=str(e),
            )

    async def _dispatch(
        self,
        blog: Blog,
        title: str,
        img_settings: dict,
        image_mode: str,
        final_html: Optional[str] = None,
        keywords: str = "",
    ) -> ImageResult:
        """image_mode에 따라 적절한 서비스로 라우팅"""
        if image_mode == "template":
            return await self._generate_template(blog, title)

        if image_mode in ("openai", "ai"):
            return await self._generate_ai_with_overlay(
                blog, title, img_settings, keywords,
            )

        if image_mode == "both":
            return await self._generate_both(
                blog, title, img_settings, final_html, keywords,
            )

        logger.debug(
            f"[IMAGE_GEN] image_mode='{image_mode}' - 이미지 불필요"
        )
        return ImageResult(success=True)

    async def _generate_ai_with_overlay(
        self, blog: Blog, title: str, img_settings: dict,
        keywords: str = "",
    ) -> ImageResult:
        """AI 이미지 생성 + title_overlay 옵션 처리"""
        result = await self._generate_ai(blog, title, img_settings, keywords)
        if not result.success or not result.image_url:
            return result

        if not img_settings.get("title_overlay", False):
            return result

        overlay_config = getattr(blog, "overlay_config", None)
        if not overlay_config:
            logger.error(
                "[IMAGE_GEN] title_overlay=True이지만 "
                "blog.overlay_config 없음"
            )
            return ImageResult(
                success=False, image_mode="ai",
                error="title_overlay 사용 시 blog.overlay_config 필수",
            )

        overlaid_path = await overlay_title_on_image(
            template_image_svc=self.template_image,
            image_path=result.image_url,
            title=title,
            overlay_config=overlay_config,
        )
        if overlaid_path:
            result.image_url = overlaid_path
            logger.info("[IMAGE_GEN] AI 이미지에 제목 오버레이 완료")
        else:
            logger.error("[IMAGE_GEN] 오버레이 처리 실패")
            return ImageResult(
                success=False, image_mode="ai",
                error="제목 오버레이 처리 실패 - 블로그 이미지 설정을 확인하세요",
            )

        return result

    async def _generate_both(
        self, blog: Blog, title: str, img_settings: dict,
        final_html: Optional[str] = None, keywords: str = "",
    ) -> ImageResult:
        """
        both 모드: 대표이미지 + 섹션별 이미지 자동 생성

        final_html에서 <h2> 태그를 파싱하여 섹션 수만큼
        이미지를 생성하고, HTML에 <img> 태그를 삽입합니다.
        """
        overlay = getattr(blog, "overlay_config", None) or {}
        cover_source = overlay.get("cover_source", "ai")
        section_source = overlay.get("section_source", "template")

        # 1) 대표이미지 생성
        cover_result = await self._generate_by_source(
            blog, title, img_settings, cover_source,
            fallback=True, keywords=keywords,
        )

        # 2) 섹션 파싱 → 섹션별 이미지 생성 → HTML 삽입
        section_images = []
        result_html = final_html
        if final_html:
            sections = self._parse_sections(final_html)
            logger.info(
                f"[IMAGE_GEN] both 모드 | cover={cover_source}, "
                f"section={section_source}, 섹션 수={len(sections)}"
            )
            if sections:
                section_images = await self._generate_section_images(
                    blog, sections, img_settings, section_source,
                    keywords=keywords,
                )
                result_html = self._insert_section_images(
                    final_html, section_images,
                )
        else:
            logger.info(
                f"[IMAGE_GEN] both 모드 | cover={cover_source}, "
                f"section={section_source} (final_html 없음 - 섹션 이미지 생략)"
            )

        cover_result.image_mode = "both"
        cover_result.section_images = section_images or None
        cover_result.final_html = result_html
        return cover_result

    async def _generate_by_source(
        self, blog: Blog, title: str, img_settings: dict,
        source: str, fallback: bool = False, keywords: str = "",
    ) -> ImageResult:
        """source 타입에 따라 이미지 생성 (fallback=True 시 템플릿 폴백)"""
        if source == "ai":
            result = await self._generate_ai_with_overlay(
                blog, title, img_settings, keywords,
            )
            if fallback and (not result.success or not result.image_url):
                logger.info("[IMAGE_GEN] AI 실패 → 템플릿 폴백")
                return await self._generate_template(blog, title)
            return result
        return await self._generate_template(blog, title)

    def _parse_sections(self, final_html: str) -> List[dict]:
        """
        final_html에서 <h2> 태그를 파싱하여 섹션 목록 반환

        Returns:
            [{"heading": str, "end_position": int}, ...]
        """
        sections = []
        for match in _H2_PATTERN.finditer(final_html):
            heading_text = _HTML_TAG_PATTERN.sub("", match.group(1)).strip()
            if heading_text:
                sections.append({
                    "heading": heading_text,
                    "end_position": match.end(),
                })
        return sections

    async def _generate_section_images(
        self, blog: Blog, sections: List[dict], img_settings: dict,
        section_source: str, keywords: str = "",
    ) -> List[dict]:
        """섹션별 이미지 생성 (섹션 전용 설정 적용)"""
        section_settings = self._resolve_section_settings(img_settings)
        section_images: List[dict] = []
        for section in sections:
            heading = section["heading"]
            try:
                if section_source == "ai":
                    sec = await self._generate_ai(
                        blog, heading, section_settings, keywords,
                    )
                else:
                    sec = await self._generate_template(blog, heading)
                if sec.success and sec.image_url:
                    section_images.append({
                        "heading": heading,
                        "image_url": sec.image_url,
                        "source": section_source,
                        "end_position": section["end_position"],
                    })
                else:
                    logger.warning(
                        f"[IMAGE_GEN] 섹션 이미지 실패: {heading[:30]}"
                    )
            except Exception as e:
                logger.warning(
                    f"[IMAGE_GEN] 섹션 이미지 오류: {heading[:30]} - {e}"
                )
        logger.info(
            f"[IMAGE_GEN] 섹션 이미지 생성 완료: "
            f"{len(section_images)}/{len(sections)}장"
        )
        return section_images

    def _insert_section_images(
        self, final_html: str, section_images: List[dict],
    ) -> str:
        """
        섹션 이미지를 final_html의 각 <h2> 뒤에 삽입

        end_position 역순으로 삽입하여 위치 이동 방지
        """
        if not section_images:
            return final_html
        sorted_imgs = sorted(
            section_images,
            key=lambda x: x.get("end_position", 0),
            reverse=True,
        )
        for img in sorted_imgs:
            if not img.get("image_url"):
                continue
            pos = img["end_position"]
            heading = img.get("heading", "")
            img_tag = (
                f'\n<div class="section-image">'
                f'<img src="{img["image_url"]}" '
                f'alt="{heading}" loading="lazy" />'
                f'</div>\n'
            )
            final_html = final_html[:pos] + img_tag + final_html[pos:]
        return final_html

    async def _generate_ai(
        self, blog: Blog, title: str, img_settings: dict,
        keywords: str = "",
    ) -> ImageResult:
        """
        AI 이미지 서비스로 생성

        블로그의 ai_config.image_ai에서 provider/model을 가져오고,
        모듈의 통합 파라미터(aspect_ratio, style, quality)를
        변환 레이어로 provider별 파라미터로 변환합니다.
        """
        ai_config = blog.ai_config or {}
        image_ai = ai_config.get("image_ai", {})

        # provider 결정: 블로그 설정 우선
        raw_provider = image_ai.get("provider", "dalle")
        provider = normalize_provider(raw_provider)
        model = image_ai.get("model")

        logger.info(
            f"[IMAGE_GEN] AI 파라미터 변환 | "
            f"provider={provider}, model={model or '기본값'}"
        )

        # 통합 파라미터 → provider별 파라미터 변환
        provider_params = convert_to_provider_params(
            unified_settings=img_settings,
            provider=provider,
            model=model,
        )

        # 프롬프트 템플릿 전달
        prompt_template = img_settings.get("prompt_template", "")

        result = await self.ai_image.generate(
            title=title,
            provider=provider,
            provider_params=provider_params,
            prompt_template=prompt_template,
            blog_id=blog.id,
            keywords=keywords,
        )

        if result:
            return ImageResult(
                success=True,
                image_url=result["image_url"],
                image_mode="ai",
                provider=result.get("provider"),
                ai_model=result.get("model"),
            )

        return ImageResult(
            success=False,
            image_mode="ai",
            error="AI 이미지 생성 실패",
        )

    async def _generate_template(
        self, blog: Blog, title: str,
    ) -> ImageResult:
        """템플릿 이미지 서비스로 생성"""
        result = await self.template_image.generate(
            title=title, blog=blog, blog_id=blog.id,
        )

        if result:
            return ImageResult(
                success=True,
                image_url=result["image_url"],
                image_mode="template",
                provider="template",
            )

        return ImageResult(
            success=False,
            image_mode="template",
            error="템플릿 이미지 생성 실패",
        )

    @staticmethod
    def _resolve_section_settings(img_settings: dict) -> dict:
        """
        섹션 이미지 설정 결정

        section_custom=True: 사용자가 설정한 섹션 전용 값 사용
        section_custom=False: 대표 이미지 설정 기반 자동 최적화
        """
        if img_settings.get("section_custom"):
            return {
                "prompt_template": img_settings.get(
                    "section_prompt_template", ""
                ),
                "aspect_ratio": img_settings.get(
                    "section_aspect_ratio", "1:1"
                ),
                "style": img_settings.get(
                    "section_style", "minimal"
                ),
                "quality": img_settings.get(
                    "section_quality", "standard"
                ),
            }

        # 자동 설정: 대표 이미지와 차별화
        hero_prompt = img_settings.get("prompt_template", "")
        return {
            "prompt_template": ImageGenerator._auto_section_prompt(
                hero_prompt
            ),
            "aspect_ratio": "1:1",
            "style": img_settings.get("style", "realistic"),
            "quality": "standard",
        }

    @staticmethod
    def _auto_section_prompt(hero_prompt: str) -> str:
        """
        대표 이미지 프롬프트를 섹션 이미지에 맞게 자동 변환

        대표/섹션 모두 AI 생성 시에도 다른 이미지가
        나오도록 프롬프트 맥락을 변경합니다.
        """
        if not hero_prompt:
            return (
                "{title} 주제의 블로그 섹션 일러스트. "
                "심플하고 집중적인 디자인."
            )

        # 대표 이미지 키워드 → 섹션 맥락으로 변환
        replacements = {
            "대표 이미지": "섹션 이미지",
            "헤더 이미지": "섹션 일러스트",
            "블로그 헤더": "블로그 섹션",
            "header image": "section illustration",
            "blog header": "blog section",
            "professional blog": "focused blog section",
            "전문적인 블로그": "블로그 섹션",
            "전문 블로그": "블로그 섹션",
        }

        section_prompt = hero_prompt
        for old, new in replacements.items():
            section_prompt = section_prompt.replace(old, new)

        # 변환이 적용되지 않았으면 접두어 추가
        if section_prompt == hero_prompt:
            section_prompt = f"블로그 섹션 이미지: {hero_prompt}"

        return section_prompt

