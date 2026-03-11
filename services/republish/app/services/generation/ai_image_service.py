"""
AI 이미지 생성 서비스 (DALL-E, Nanobanana)

프롬프트 모듈의 image_generation 설정을 기반으로
AI API를 호출하여 이미지를 생성합니다.

설계 문서: generation_pipeline_enhancement_plan.md - Phase C - 5.4
"""
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..ai_key_manager import AIKeyManager
from ...schemas.ai_api_key import AIProvider

logger = logging.getLogger(__name__)

# 이미지 저장 경로
IMAGE_DIR = Path(__file__).parent.parent.parent / "static" / "generated" / "images"

# 기본 이미지 프롬프트
DEFAULT_PROMPT_TEMPLATE = (
    "A clean, professional blog header image for: {title}. "
    "Modern design, suitable for a Korean blog post."
)


class AIImageService:
    """
    AI API를 사용한 이미지 생성 서비스

    DALL-E 또는 Nanobanana API를 호출하여 이미지를 생성하고
    로컬 파일로 저장합니다.
    """

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id
        self.key_manager = AIKeyManager(db, user_id)

    async def generate(
        self, title: str, settings: dict, blog_id: int,
    ) -> Optional[dict]:
        """
        AI로 이미지 생성

        Args:
            title: 이미지 프롬프트에 사용할 제목
            settings: image_generation 설정
            blog_id: 블로그 ID (파일명에 사용)

        Returns:
            dict: {"image_url": str, "provider": str, "model": str}
            또는 None (실패 시)
        """
        provider_name = settings.get("provider", "dalle")
        prompt_template = (
            settings.get("prompt_template") or DEFAULT_PROMPT_TEMPLATE
        )
        prompt = prompt_template.replace("{title}", title)

        logger.info(
            f"[AI_IMAGE] 이미지 생성 시작 | "
            f"provider={provider_name} | title={title[:30]}"
        )

        if provider_name == "dalle":
            return await self._generate_with_dalle(
                prompt, settings, blog_id,
            )
        elif provider_name == "nanobanana":
            logger.warning("[AI_IMAGE] Nanobanana 미구현 - 건너뜀")
            return None
        else:
            logger.warning(
                f"[AI_IMAGE] 알 수 없는 provider: {provider_name}"
            )
            return None

    async def _generate_with_dalle(
        self, prompt: str, settings: dict, blog_id: int,
    ) -> Optional[dict]:
        """DALL-E API로 이미지 생성"""
        key = await self.key_manager.get_available_key(AIProvider.OPENAI)
        if not key:
            logger.error("[AI_IMAGE] OpenAI API 키 없음 - DALL-E 사용 불가")
            return None

        dalle_settings = settings.get("dalle", {})
        size = dalle_settings.get("size", "1024x1024")
        quality = dalle_settings.get("quality", "standard")
        style = dalle_settings.get("style", "natural")
        model = dalle_settings.get("model", "dall-e-3")

        try:
            remote_url = await self._call_dalle_api(
                api_key=key.api_key,
                prompt=prompt,
                model=model,
                size=size,
                quality=quality,
                style=style,
            )
            if not remote_url:
                return None

            local_path = await self._save_image_from_url(
                remote_url, blog_id,
            )
            if not local_path:
                return None

            await self.key_manager.mark_key_used(key.id)
            return {
                "image_url": local_path,
                "provider": "dalle",
                "model": model,
            }

        except Exception as e:
            error_msg = str(e)
            await self.key_manager.mark_key_error(key.id, error_msg[:200])
            logger.error(f"[AI_IMAGE] DALL-E 실패: {error_msg[:100]}")
            return None

    async def _call_dalle_api(
        self,
        api_key: str,
        prompt: str,
        model: str,
        size: str,
        quality: str,
        style: str,
    ) -> Optional[str]:
        """
        OpenAI DALL-E API 호출

        Returns:
            생성된 이미지의 원격 URL 또는 None
        """
        import openai

        client = openai.AsyncOpenAI(api_key=api_key)
        resp = await client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            style=style,
            n=1,
        )

        if resp.data and resp.data[0].url:
            return resp.data[0].url
        return None

    async def _save_image_from_url(
        self, url: str, blog_id: int,
    ) -> Optional[str]:
        """
        원격 URL에서 이미지 다운로드 후 로컬 저장

        Returns:
            저장된 이미지의 상대 URL (예: /static/generated/images/1_xxx.png)
        """
        import httpx

        IMAGE_DIR.mkdir(parents=True, exist_ok=True)

        filename = (
            f"{blog_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
        )
        filepath = IMAGE_DIR / filename

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                filepath.write_bytes(resp.content)

            relative_url = f"/static/generated/images/{filename}"
            logger.info(f"[AI_IMAGE] 이미지 저장 완료: {relative_url}")
            return relative_url

        except Exception as e:
            logger.error(f"[AI_IMAGE] 이미지 다운로드/저장 실패: {e}")
            return None
