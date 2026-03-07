"""
이미지 생성 총괄 서비스

Blog.image_mode에 따라 AI 이미지 또는 템플릿 이미지를 생성합니다.

아키텍처:
  ImageGenerator (총괄)
    +-- AIImageService (DALL-E, Nanobanana 등)
    +-- TemplateImageService (배경 + 텍스트 합성)

설계 문서: generation_pipeline_enhancement_plan.md - Phase C - 5.3
"""
import logging
import time
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.blog import Blog
from .ai_image_service import AIImageService
from .template_image_service import TemplateImageService

logger = logging.getLogger(__name__)


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


class ImageGenerator:
    """
    이미지 생성 총괄 서비스

    Blog.image_mode에 따라 적절한 서비스로 라우팅합니다.
    - "openai" / "ai": AI 이미지만 시도
    - "template": 템플릿 이미지만 시도
    - "both": AI 시도 → 실패 시 템플릿 폴백
    - None / "none": 이미지 생성 안 함
    """

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.ai_image = AIImageService(db, user_id)
        self.template_image = TemplateImageService()

    async def generate(
        self, blog: Blog, title: str, module_settings: dict,
    ) -> ImageResult:
        """
        블로그 설정에 따라 이미지 생성

        Args:
            blog: Blog 객체
            title: 재조합된 포스트 제목
            module_settings: 프롬프트 모듈 전체 settings

        Returns:
            ImageResult
        """
        start_time = time.time()

        img_settings = module_settings.get("image_generation", {})
        if not img_settings.get("enabled", False):
            logger.debug("[IMAGE_GEN] 이미지 생성 비활성화 - 건너뜀")
            return ImageResult(success=True)

        image_mode = getattr(blog, "image_mode", None) or "template"
        logger.info(
            f"[IMAGE_GEN] 시작 | mode={image_mode} | title={title[:30]}"
        )

        try:
            result = await self._dispatch(
                blog, title, img_settings, image_mode,
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
    ) -> ImageResult:
        """image_mode에 따라 적절한 서비스로 라우팅"""
        if image_mode in ("openai", "ai"):
            return await self._generate_ai(blog, title, img_settings)
        elif image_mode == "template":
            return await self._generate_template(blog, title)
        elif image_mode == "both":
            result = await self._generate_ai(blog, title, img_settings)
            if not result.success or not result.image_url:
                logger.info("[IMAGE_GEN] AI 실패 → 템플릿 폴백")
                return await self._generate_template(blog, title)
            return result
        else:
            logger.debug(
                f"[IMAGE_GEN] image_mode='{image_mode}' - 이미지 불필요"
            )
            return ImageResult(success=True)

    async def _generate_ai(
        self, blog: Blog, title: str, img_settings: dict,
    ) -> ImageResult:
        """AI 이미지 서비스로 생성 (블로그 image_ai 설정 우선)"""
        # 블로그 ai_config.image_ai provider가 있으면 모듈 설정을 오버라이드
        ai_config = blog.ai_config or {}
        image_ai = ai_config.get("image_ai", {})
        if image_ai.get("provider"):
            effective_settings = img_settings.copy()
            effective_settings["provider"] = image_ai["provider"]
            logger.info(
                f"[IMAGE_GEN] AI provider 오버라이드: "
                f"blog.image_ai.provider={image_ai['provider']}"
            )
        else:
            effective_settings = img_settings

        result = await self.ai_image.generate(
            title=title, settings=effective_settings, blog_id=blog.id,
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
