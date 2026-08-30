"""
참조자료 요약 서비스

수집된 문서를 AI 또는 텍스트 알고리즘으로 요약합니다.

Features:
- AI 요약: OpenAI / Anthropic / Google 사용자 선택
- 알고리즘 요약: TextRank / 빈도 기반 / 위치 기반 (비용 없음)
- 요약 스타일: 간결형 / 서술형 / 보고서형 / 핵심 요점형
- AI 실패 시 알고리즘 폴백
"""
import random
import logging
from typing import List, Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.ai_api_key import AIProvider
from ..schemas.reference_collection import CrawledDocument, DocumentSummary
from .ai_key_manager import AIKeyManager
from .text_summarizer import TextSummarizer

logger = logging.getLogger(__name__)

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import google.generativeai as genai
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False


# 스타일별 AI 요약 프롬프트 (글자수는 동적으로 삽입)
SUMMARY_PROMPTS: Dict[str, str] = {
    "concise": (
        "다음 웹 문서 내용을 {max_length}자 이내로 요약해주세요. "
        "핵심 정보와 주요 내용만 간결하게 정리해주세요.\n\n"
        "[문서 내용]\n{content}\n\n[요약]"
    ),
    "narrative": (
        "다음 웹 문서 내용을 {max_length}자 이내의 자연스러운 서술형으로 요약해주세요. "
        "글의 흐름을 유지하면서 핵심 내용을 전달해주세요. "
        "문단 구분을 사용하여 읽기 쉽게 작성해주세요.\n\n"
        "[문서 내용]\n{content}\n\n[서술형 요약]"
    ),
    "report": (
        "다음 웹 문서 내용을 {max_length}자 이내의 보고서 형식으로 요약해주세요.\n"
        "구조: 1) 핵심 주제 2) 주요 내용 3) 결론/시사점\n"
        "각 항목을 명확히 구분하여 작성해주세요.\n\n"
        "[문서 내용]\n{content}\n\n[보고서형 요약]"
    ),
    "bullet": (
        "다음 웹 문서 내용의 핵심 요점을 {max_length}자 이내로 정리해주세요.\n"
        "- 형태의 불릿 포인트 목록으로 작성\n"
        "- 각 항목은 한 문장으로 핵심만 전달\n"
        "- 5-8개 항목으로 구성\n\n"
        "[문서 내용]\n{content}\n\n[핵심 요점]"
    ),
}

# AI 입력 최대 길이
MAX_INPUT_LENGTH = 3000


class ReferenceSummaryService:
    """참조자료 요약 서비스"""

    def __init__(
        self,
        db_session: AsyncSession,
        user_id: int = 1,
        select_count: int = 3,
        summary_method: str = "ai",
        ai_provider: str = "openai",
        ai_model: str = "gpt-4.1-mini",
        summary_style: str = "concise",
        algorithm_type: str = "textrank",
        max_length: int = 500
    ):
        """
        Args:
            db_session: DB 세션
            user_id: 사용자 ID
            select_count: 요약할 문서 선택 수
            summary_method: 요약 방법 (ai / algorithm)
            ai_provider: AI 제공자 (openai / anthropic / google)
            ai_model: AI 모델명 (gpt-4o-mini, claude-3-haiku 등)
            summary_style: 요약 스타일 (concise / narrative / report / bullet)
            algorithm_type: 알고리즘 유형 (textrank / frequency / position)
            max_length: 요약 최대 글자수
        """
        self.db = db_session
        self.key_manager = AIKeyManager(db_session, user_id)
        self.select_count = max(1, select_count)
        self.summary_method = summary_method
        self.ai_provider = ai_provider
        self.ai_model = ai_model
        self.summary_style = summary_style
        self.algorithm_type = algorithm_type
        self.max_length = max(200, min(2000, max_length))

    def select_random_documents(
        self,
        documents: List[CrawledDocument],
        count: int = 3
    ) -> List[CrawledDocument]:
        """랜덤으로 문서 선택"""
        if len(documents) <= count:
            return documents
        return random.sample(documents, count)

    async def summarize_documents(
        self,
        documents: List[CrawledDocument]
    ) -> List[DocumentSummary]:
        """선택된 문서들 요약"""
        selected = self.select_random_documents(documents, self.select_count)
        logger.info(
            f"[SUMMARY] 시작 | 문서: {len(selected)}개 | "
            f"방법: {self.summary_method} | 스타일: {self.summary_style}"
        )

        summaries = []
        for doc in selected:
            summary = await self._summarize_single(doc)
            summaries.append(summary)

        ai_count = sum(1 for s in summaries if s.is_ai_summary)
        logger.info(f"[SUMMARY] 완료 | AI: {ai_count} | 알고리즘: {len(summaries) - ai_count}")
        return summaries

    async def _summarize_single(self, doc: CrawledDocument) -> DocumentSummary:
        """단일 문서 요약"""
        content = doc.content[:MAX_INPUT_LENGTH]

        if self.summary_method == "algorithm":
            summary_text = self._summarize_with_algorithm(content)
            is_ai = False
        else:
            summary_text = await self._call_ai_summary(content)
            is_ai = True
            if not summary_text:
                # AI 실패 시 알고리즘 폴백
                summary_text = self._summarize_with_algorithm(content)
                is_ai = False

        return DocumentSummary(
            url=doc.url,
            title=doc.title,
            original_length=doc.content_length,
            summary=summary_text[:self.max_length],
            summary_length=len(summary_text),
            is_ai_summary=is_ai
        )

    def _summarize_with_algorithm(self, content: str) -> str:
        """텍스트 알고리즘으로 요약"""
        summarizer = TextSummarizer(max_summary_length=self.max_length)
        return summarizer.summarize(content, method=self.algorithm_type)

    def _get_prompt(self, content: str) -> str:
        """스타일에 맞는 프롬프트 생성"""
        template = SUMMARY_PROMPTS.get(self.summary_style, SUMMARY_PROMPTS["concise"])
        return template.format(content=content, max_length=self.max_length)

    async def _call_ai_summary(self, content: str) -> Optional[str]:
        """사용자 선택 AI provider로 요약"""
        prompt = self._get_prompt(content)

        # 선택된 provider 우선 시도
        result = await self._try_provider(self.ai_provider, prompt)
        if result:
            return result

        # 선택 provider 실패 시 다른 provider 시도
        fallback_order = ["openai", "anthropic", "google", "deepseek"]
        for provider in fallback_order:
            if provider == self.ai_provider:
                continue
            result = await self._try_provider(provider, prompt)
            if result:
                return result

        return None

    async def _try_provider(self, provider: str, prompt: str) -> Optional[str]:
        """특정 AI provider로 요약 시도"""
        provider_map = {
            "openai": (HAS_OPENAI, AIProvider.OPENAI, self._call_openai),
            "anthropic": (HAS_ANTHROPIC, AIProvider.ANTHROPIC, self._call_anthropic),
            "google": (HAS_GOOGLE, AIProvider.GOOGLE, self._call_google),
            # 딥시크는 OpenAI 호환이라 openai 라이브러리를 그대로 쓴다
            "deepseek": (HAS_OPENAI, AIProvider.DEEPSEEK, self._call_deepseek),
        }

        config = provider_map.get(provider)
        if not config:
            return None

        has_lib, ai_provider_enum, call_fn = config
        if not has_lib:
            return None

        key = await self.key_manager.get_available_key(ai_provider_enum)
        if not key:
            return None

        result = await call_fn(key.api_key, prompt)
        if result:
            await self.key_manager.mark_key_used(key.id)
        return result

    def _get_model_for_provider(self, provider: str) -> str:
        """provider별 사용할 모델명 반환"""
        defaults = {
            "openai": "gpt-4.1-mini",
            "anthropic": "claude-haiku-4-5-20251001",
            "google": "gemini-2.5-flash",
            "deepseek": "deepseek-v4-flash",
        }
        valid = {
            "openai": {
                "gpt-4.1-nano", "gpt-4.1-mini", "gpt-4.1",
                "gpt-4o-mini", "gpt-4o",
                "gpt-5-nano", "gpt-5-mini", "gpt-5", "gpt-5.2",
            },
            "anthropic": {
                "claude-3-haiku-20240307",
                "claude-haiku-4-5-20251001",
                "claude-sonnet-4-20250514",
                "claude-sonnet-4-5-20250929",
                "claude-opus-4-5-20251101",
                "claude-opus-4-6",
            },
            "google": {
                "gemini-2.5-flash-lite", "gemini-2.5-flash",
                "gemini-2.5-pro",
                "gemini-3-flash-preview", "gemini-3-pro-preview",
            },
            "deepseek": {
                "deepseek-v4-flash", "deepseek-v4-pro",
                "deepseek-v4-flash-vision-exp",
            },
        }
        if provider == self.ai_provider and self.ai_model in valid.get(provider, set()):
            return self.ai_model
        return defaults.get(provider, "gpt-4.1-mini")

    async def _call_openai(self, api_key: str, prompt: str) -> Optional[str]:
        """OpenAI API 호출"""
        try:
            model_name = self._get_model_for_provider("openai")
            client = openai.AsyncOpenAI(api_key=api_key)
            response = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[SUMMARY] OpenAI 실패: {e}")
            return None

    async def _call_deepseek(self, api_key: str, prompt: str) -> Optional[str]:
        """딥시크 API 호출 (OpenAI 호환 — base_url 만 다르다)"""
        from .ai.deepseek_pricing import BASE_URL, EXTRA_PARAMS

        try:
            model_name = self._get_model_for_provider("deepseek")
            client = openai.AsyncOpenAI(api_key=api_key, base_url=BASE_URL)
            # 사고 모드를 끈다 — max_tokens=800 을 사고가 먹으면 요약이 빈다
            response = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.3,
                **EXTRA_PARAMS,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[SUMMARY] DeepSeek 실패: {e}")
            return None

    async def _call_anthropic(self, api_key: str, prompt: str) -> Optional[str]:
        """Anthropic API 호출"""
        try:
            model_name = self._get_model_for_provider("anthropic")
            client = anthropic.AsyncAnthropic(api_key=api_key)
            response = await client.messages.create(
                model=model_name,
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning(f"[SUMMARY] Anthropic 실패: {e}")
            return None

    async def _call_google(self, api_key: str, prompt: str) -> Optional[str]:
        """Google Gemini API 호출"""
        try:
            model_name = self._get_model_for_provider("google")
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            response = await model.generate_content_async(prompt)
            return response.text.strip()
        except Exception as e:
            logger.warning(f"[SUMMARY] Google 실패: {e}")
            return None
