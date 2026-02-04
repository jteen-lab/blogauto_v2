"""
참조자료 요약 서비스

수집된 문서를 AI를 사용하여 요약합니다.
AI 호출 실패 시 원본 앞부분을 사용합니다.
"""
import random
import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.ai_api_key import AIProvider
from ..schemas.reference_collection import CrawledDocument, DocumentSummary
from .ai_key_manager import AIKeyManager

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


class ReferenceSummaryService:
    """참조자료 요약 서비스"""

    SELECT_COUNT = 3
    MAX_INPUT_LENGTH = 3000
    MAX_SUMMARY_LENGTH = 500

    PROMPT = "다음 웹 문서 내용을 500자 이내로 요약해주세요. 핵심 정보와 주요 내용만 간결하게 정리해주세요.\n\n[문서 내용]\n{content}\n\n[요약]"

    def __init__(self, db_session: AsyncSession, user_id: int = 1):
        self.db = db_session
        self.key_manager = AIKeyManager(db_session, user_id)

    def select_random_documents(self, documents: List[CrawledDocument], count: int = 3) -> List[CrawledDocument]:
        """랜덤으로 문서 선택"""
        return documents if len(documents) <= count else random.sample(documents, count)

    async def summarize_documents(self, documents: List[CrawledDocument]) -> List[DocumentSummary]:
        """선택된 문서들 요약"""
        selected = self.select_random_documents(documents, self.SELECT_COUNT)
        logger.info(f"[SUMMARY] 요약 시작 | 문서 수: {len(selected)}")

        summaries = [await self._summarize_single(doc) for doc in selected]
        logger.info(f"[SUMMARY] 요약 완료 | AI: {sum(1 for s in summaries if s.is_ai_summary)}")
        return summaries

    async def _summarize_single(self, doc: CrawledDocument) -> DocumentSummary:
        """단일 문서 요약"""
        content = doc.content[:self.MAX_INPUT_LENGTH]
        summary_text, is_ai = await self._call_ai_summary(content), True

        if not summary_text:
            summary_text = content[:self.MAX_SUMMARY_LENGTH] + ("..." if len(content) > self.MAX_SUMMARY_LENGTH else "")
            is_ai = False

        return DocumentSummary(
            url=doc.url, title=doc.title, original_length=doc.content_length,
            summary=summary_text[:self.MAX_SUMMARY_LENGTH], summary_length=len(summary_text), is_ai_summary=is_ai
        )

    async def _call_ai_summary(self, content: str) -> Optional[str]:
        """AI API 호출하여 요약"""
        if HAS_OPENAI:
            key = await self.key_manager.get_available_key(AIProvider.OPENAI)
            if key and (result := await self._call_openai(key.api_key, content)):
                await self.key_manager.mark_key_used(key.id)
                return result

        if HAS_ANTHROPIC:
            key = await self.key_manager.get_available_key(AIProvider.ANTHROPIC)
            if key and (result := await self._call_anthropic(key.api_key, content)):
                await self.key_manager.mark_key_used(key.id)
                return result
        return None

    async def _call_openai(self, api_key: str, content: str) -> Optional[str]:
        """OpenAI API 호출"""
        try:
            client = openai.AsyncOpenAI(api_key=api_key)
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": self.PROMPT.format(content=content)}],
                max_tokens=600, temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[SUMMARY] OpenAI 실패: {e}")
            return None

    async def _call_anthropic(self, api_key: str, content: str) -> Optional[str]:
        """Anthropic API 호출"""
        try:
            client = anthropic.AsyncAnthropic(api_key=api_key)
            response = await client.messages.create(
                model="claude-3-haiku-20240307", max_tokens=600,
                messages=[{"role": "user", "content": self.PROMPT.format(content=content)}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning(f"[SUMMARY] Anthropic 실패: {e}")
            return None
