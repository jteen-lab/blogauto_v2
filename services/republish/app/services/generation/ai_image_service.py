"""
AI 이미지 생성 서비스 (DALL-E, Nanobanana)

프롬프트 모듈의 image_generation 설정을 기반으로
AI API를 호출하여 이미지를 생성합니다.

설계 문서: generation_pipeline_enhancement_plan.md - Phase C - 5.4
"""
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..ai_key_manager import AIKeyManager
from ...schemas.ai_api_key import AIProvider
from ...core.config import settings

logger = logging.getLogger(__name__)

# 이미지 저장 경로 (config 기반)
IMAGE_DIR = Path(settings.image_storage_dir)
IMAGE_URL_PREFIX = settings.image_url_prefix

# 기본 이미지 프롬프트 (한글)
DEFAULT_PROMPT_TEMPLATE = (
    "{title} 주제의 전문적인 블로그 대표 이미지, "
    "{keywords} 포함, 현대적인 디자인, 깔끔한 구성"
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
        self, title: str, provider: str, provider_params: dict,
        prompt_template: str, blog_id: int,
        keywords: str = "",
    ) -> Optional[dict]:
        """
        AI로 이미지 생성 (변환된 provider별 파라미터 수신)

        Args:
            title: 이미지 프롬프트에 사용할 제목
            provider: 정규화된 provider (dalle/nanobanana)
            provider_params: 변환 레이어에서 생성된 provider별 파라미터
            prompt_template: 이미지 프롬프트 템플릿
            blog_id: 블로그 ID (파일명에 사용)
            keywords: 키워드 문자열 ({keywords} 치환용)

        Returns:
            dict: {"image_url": str, "provider": str, "model": str}
            또는 None (실패 시)
        """
        effective_template = prompt_template or DEFAULT_PROMPT_TEMPLATE
        prompt = effective_template.replace("{title}", title)
        # {keywords} 치환: 데이터 없으면 플레이스홀더 제거
        if keywords:
            prompt = prompt.replace("{keywords}", keywords)
        else:
            prompt = prompt.replace("{keywords}", "").strip()
            # 잔여 구문 정리 (", 포함" → "" 등)
            prompt = re.sub(r',\s*포함\s*,', ',', prompt)
            prompt = re.sub(r',\s*featuring\s*,', ',', prompt)
            prompt = re.sub(r',\s*,', ',', prompt)
            prompt = re.sub(r'\s{2,}', ' ', prompt).strip()

        logger.info(
            f"[AI_IMAGE] 이미지 생성 시작 | "
            f"provider={provider} | title={title[:30]}"
        )

        if provider == "dalle":
            return await self._generate_with_dalle(
                prompt, provider_params, blog_id,
            )
        elif provider == "nanobanana":
            return await self._generate_with_nanobanana(
                prompt, provider_params, blog_id,
            )
        else:
            logger.warning(
                f"[AI_IMAGE] 알 수 없는 provider: {provider}"
            )
            return None

    async def _generate_with_dalle(
        self, prompt: str, params: dict, blog_id: int,
    ) -> Optional[dict]:
        """
        DALL-E API로 이미지 생성 (b64_json 모드)

        Args:
            prompt: 이미지 생성 프롬프트
            params: 변환된 DALL-E 파라미터
                - size: "1024x1024" | "1792x1024" | "1024x1792"
                - quality: "standard" | "hd"
                - style: "natural" | "vivid"
                - model: "dall-e-3" 등
            blog_id: 블로그 ID
        """
        key = await self.key_manager.get_available_key(AIProvider.OPENAI)
        if not key:
            logger.error("[AI_IMAGE] OpenAI API 키 없음 - DALL-E 사용 불가")
            return None

        size = params.get("size", "1024x1024")
        quality = params.get("quality", "standard")
        style = params.get("style", "natural")
        model = params.get("model", "dall-e-3")

        try:
            image_bytes = await self._call_dalle_api(
                api_key=key.api_key, prompt=prompt, model=model,
                size=size, quality=quality, style=style,
            )
            if not image_bytes:
                return None

            local_path = await self._save_image_bytes(image_bytes, blog_id)
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
        self, api_key: str, prompt: str, model: str,
        size: str, quality: str, style: str,
    ) -> Optional[bytes]:
        """
        OpenAI DALL-E API 호출 (b64_json 모드)

        base64 이미지 데이터를 직접 수신하여 SAS URL 다운로드 문제를 우회합니다.

        Returns:
            생성된 이미지의 바이트 데이터 또는 None
        """
        import openai
        import base64

        client = openai.AsyncOpenAI(api_key=api_key)
        resp = await client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            style=style,
            response_format="b64_json",
            n=1,
        )

        if resp.data and resp.data[0].b64_json:
            logger.info("[AI_IMAGE] DALL-E: 이미지 데이터 수신 완료")
            return base64.b64decode(resp.data[0].b64_json)
        return None

    async def _generate_with_nanobanana(
        self, prompt: str, params: dict, blog_id: int,
    ) -> Optional[dict]:
        """
        Nanobanana (Google Gemini) API로 이미지 생성

        Args:
            prompt: 이미지 생성 프롬프트
            params: 변환된 Nanobanana 파라미터
                - aspect_ratio: "16:9" | "9:16" | "1:1" | "4:3" | "3:4"
                - style: "realistic" | "artistic" | "cartoon" | "minimal"
                - model: "gemini-2.0-flash-exp" 등
            blog_id: 블로그 ID
        """
        key = await self.key_manager.get_available_key(AIProvider.GOOGLE)
        if not key:
            logger.error("[AI_IMAGE] Google API 키 없음 - Nanobanana 불가")
            return None

        model = params.get("model", "gemini-2.0-flash-exp")
        aspect_ratio = params.get("aspect_ratio", "16:9")
        style = params.get("style", "realistic")

        try:
            image_bytes = await self._call_gemini_image_api(
                api_key=key.api_key, prompt=prompt, model=model,
                aspect_ratio=aspect_ratio, style=style,
            )
            if not image_bytes:
                return None

            local_path = await self._save_image_bytes(image_bytes, blog_id)
            if not local_path:
                return None

            await self.key_manager.mark_key_used(key.id)
            return {
                "image_url": local_path,
                "provider": "nanobanana",
                "model": model,
            }
        except Exception as e:
            error_msg = str(e)
            await self.key_manager.mark_key_error(key.id, error_msg[:200])
            logger.error(f"[AI_IMAGE] Nanobanana 실패: {error_msg[:100]}")
            return None

    async def _call_gemini_image_api(
        self, api_key: str, prompt: str, model: str,
        aspect_ratio: str, style: str,
    ) -> Optional[bytes]:
        """Google Gemini REST API로 이미지 생성 요청"""
        import httpx

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": (
                f"{prompt} Style: {style}, aspect ratio: {aspect_ratio}"
            )}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE", "TEXT"],
            },
        }

        logger.info(
            f"[AI_IMAGE] Gemini 호출 | model={model} | "
            f"aspect={aspect_ratio} | style={style}"
        )

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        return self._extract_image_from_gemini(data)

    def _extract_image_from_gemini(
        self, data: dict,
    ) -> Optional[bytes]:
        """Gemini API 응답에서 이미지 바이트 추출"""
        import base64

        candidates = data.get("candidates", [])
        if not candidates:
            logger.error("[AI_IMAGE] Gemini: candidates 없음")
            return None

        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            inline_data = part.get("inlineData")
            if inline_data and inline_data.get("data"):
                logger.info("[AI_IMAGE] Gemini: 이미지 데이터 수신 완료")
                return base64.b64decode(inline_data["data"])

        logger.error("[AI_IMAGE] Gemini: 이미지 데이터 없음")
        return None

    async def _save_image_bytes(
        self, image_bytes: bytes, blog_id: int,
    ) -> Optional[str]:
        """
        바이트 데이터를 이미지 파일로 로컬 저장

        Returns:
            저장된 이미지의 상대 URL
        """
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)

        filename = (
            f"{blog_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
        )
        filepath = IMAGE_DIR / filename

        try:
            filepath.write_bytes(image_bytes)
            relative_url = f"{IMAGE_URL_PREFIX}/{filename}"
            logger.info(
                f"[AI_IMAGE] 이미지 저장 완료: {relative_url}"
            )
            return relative_url

        except Exception as e:
            logger.error(f"[AI_IMAGE] 이미지 저장 실패: {e}")
            return None

