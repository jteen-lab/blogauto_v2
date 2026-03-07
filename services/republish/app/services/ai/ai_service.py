"""
AI 호출 공통 서비스

OpenAI, Anthropic, Google 등 다양한 AI API를 통합 호출하는 서비스.
AIKeyManager를 사용하여 키 관리 및 자동 전환을 지원합니다.

설계 문서: generation_module_workplan.md - Phase 2 - 2.2.3
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..ai_key_manager import AIKeyManager
from ...schemas.ai_api_key import AIProvider

logger = logging.getLogger(__name__)


class AIService:
    """AI API 통합 호출 서비스"""

    def __init__(self, db: AsyncSession, user_id: int = 1):
        self.db = db
        self.user_id = user_id
        self.key_manager = AIKeyManager(db, user_id)

    async def generate(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> Optional[dict]:
        """
        텍스트 생성 (제목 재조합, 글 생성 등)

        Args:
            prompt: 생성 프롬프트
            provider: AI 제공자 ("openai", "anthropic", "google")
            model: 모델명 (None이면 기본값)
            max_tokens: 최대 토큰 수
            temperature: 생성 온도
            system_prompt: 시스템 프롬프트 (있으면 AI에 전달)

        Returns:
            dict: {"content": str, "model": str, "provider": str}
            또는 None (실패 시)
        """
        logger.info(
            f"[AI_SERVICE] generate 호출 | provider={provider} | "
            f"model={model} | max_tokens={max_tokens}"
        )
        providers = self._get_provider_order(provider)

        for prov in providers:
            result = await self._try_provider(
                prov, prompt, model, max_tokens, temperature,
                system_prompt,
            )
            if result:
                return result

        if not providers:
            logger.error(
                f"[AI_SERVICE] AI 제공자가 지정되지 않아 생성 불가 "
                f"(입력 provider={provider!r})"
            )
        else:
            logger.error(
                f"[AI_SERVICE] 선택된 제공자 {[p.value for p in providers]} "
                f"호출 실패 - API 키 상태 확인 필요"
            )
        return None

    async def summarize(
        self,
        text: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        max_length: int = 500,
    ) -> Optional[str]:
        """
        텍스트 요약

        Args:
            text: 요약할 텍스트
            provider: AI 제공자
            model: 모델명
            max_length: 요약 최대 길이

        Returns:
            요약된 텍스트 또는 None
        """
        prompt = (
            f"다음 글을 {max_length}자 이내로 핵심만 요약해주세요.\n\n{text}"
        )
        result = await self.generate(
            prompt=prompt,
            provider=provider,
            model=model,
            max_tokens=1000,
            temperature=0.3,
        )
        return result["content"] if result else None

    def _get_provider_order(self, preferred: Optional[str]) -> list:
        """
        사용자가 선택한 제공자만 반환 (폴백 없음)

        사용자가 프롬프트 설정에서 선택한 AI 서비스만 시도합니다.
        선택하지 않은 서비스로 자동 전환하지 않습니다.
        """
        preferred_map = {
            "openai": AIProvider.OPENAI,
            "anthropic": AIProvider.ANTHROPIC,
            "google": AIProvider.GOOGLE,
        }

        if not preferred:
            logger.warning("[AI_SERVICE] AI 제공자가 지정되지 않음 - 호출 불가")
            return []

        prov = preferred_map.get(preferred.lower())
        if prov:
            logger.info(f"[AI_SERVICE] 사용자 선택 제공자: {prov.value}")
            return [prov]

        logger.warning(f"[AI_SERVICE] 알 수 없는 제공자: {preferred}")
        return []

    async def _try_provider(
        self,
        provider: AIProvider,
        prompt: str,
        model: Optional[str],
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str] = None,
    ) -> Optional[dict]:
        """특정 제공자로 생성 시도"""
        key = await self.key_manager.get_available_key(provider)
        if not key:
            # 키 미사용 원인 상세 로깅
            all_keys = await self.key_manager.get_keys_by_provider(provider)
            if not all_keys:
                logger.error(
                    f"[AI_SERVICE] {provider.value}: 등록된 API 키 없음"
                )
            else:
                for k in all_keys:
                    logger.warning(
                        f"[AI_SERVICE] {provider.value} 키 상태: "
                        f"id={k.id}, label={k.label}, status={k.status}, "
                        f"is_active={k.is_active}, "
                        f"last_error={k.last_error_message or 'N/A'}"
                    )
            return None

        try:
            if provider == AIProvider.OPENAI:
                content = await self._call_openai(
                    key.api_key, prompt, model or "gpt-4o-mini",
                    max_tokens, temperature, system_prompt,
                )
                used_model = model or "gpt-4o-mini"
            elif provider == AIProvider.ANTHROPIC:
                content = await self._call_anthropic(
                    key.api_key, prompt, model or "claude-3-haiku-20240307",
                    max_tokens, temperature, system_prompt,
                )
                used_model = model or "claude-3-haiku-20240307"
            elif provider == AIProvider.GOOGLE:
                content = await self._call_google(
                    key.api_key, prompt, model or "gemini-2.0-flash",
                    max_tokens, temperature, system_prompt,
                )
                used_model = model or "gemini-2.0-flash"
            else:
                return None

            if content:
                await self.key_manager.mark_key_used(key.id)
                return {
                    "content": content,
                    "model": used_model,
                    "provider": provider.value,
                }

            return None

        except Exception as e:
            error_msg = str(e)
            if "rate" in error_msg.lower() or "429" in error_msg:
                next_key = await self.key_manager.mark_key_rate_limited(key.id)
                if next_key:
                    logger.info(f"[AI_SERVICE] Rate limit → 다음 키 시도")
                    return await self._try_provider(
                        provider, prompt, model, max_tokens, temperature,
                        system_prompt,
                    )
            else:
                await self.key_manager.mark_key_error(key.id, error_msg[:200])
            logger.warning(f"[AI_SERVICE] {provider.value} 실패: {error_msg[:100]}")
            return None

    async def _call_openai(
        self,
        api_key: str,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str] = None,
    ) -> Optional[str]:
        """OpenAI API 호출"""
        import openai

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        client = openai.AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()

    async def _call_anthropic(
        self,
        api_key: str,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str] = None,
    ) -> Optional[str]:
        """Anthropic API 호출"""
        import anthropic

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(**kwargs)
        return resp.content[0].text.strip()

    async def _call_google(
        self,
        api_key: str,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str] = None,
    ) -> Optional[str]:
        """Google Gemini API 호출"""
        import httpx

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "").strip()
        return None
