"""
제목 재조합 서비스

정식 제목을 AI로 재조합하는 서비스.
프롬프트 모듈(생성 타입 Module)의 title_prompt를 사용합니다.

설계 문서: generation_module_workplan.md - Phase 2 - 2.2.1
"""
import logging
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ..ai.ai_service import AIService
from ...models.module import Module

logger = logging.getLogger(__name__)

# 기본 프롬프트 (Module에 title_prompt가 없을 때)
DEFAULT_TITLE_PROMPT = (
    "다음 블로그 제목을 SEO에 최적화된 형태로 재조합해주세요.\n"
    "원본 제목: {title}\n\n"
    "규칙:\n"
    "- 원본의 핵심 키워드를 유지\n"
    "- 자연스러운 한국어 문장\n"
    "- 검색엔진 최적화를 고려\n"
    "- 제목만 출력 (부가 설명 없이)"
)


@dataclass
class RecombineResult:
    """제목 재조합 결과"""
    original_title: str
    recombined_title: str
    ai_model: str
    ai_provider: str
    is_modified: bool


class TitleRecombiner:
    """
    정식 제목을 AI로 재조합하는 서비스

    연동:
    - Module.settings의 "title_prompt" 사용
    - AIService로 AI 호출
    """

    def __init__(self, db: AsyncSession, user_id: int = 1):
        self.db = db
        self.user_id = user_id
        self.ai_service = AIService(db, user_id)

    async def recombine(
        self,
        original_title: str,
        module_id: int,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> RecombineResult:
        """
        제목 재조합 실행

        Args:
            original_title: 원본 정식 제목
            module_id: 생성 모듈 ID (settings에서 prompt 로드)
            provider: AI 제공자 (None이면 자동)
            model: AI 모델 (None이면 기본값)

        Returns:
            RecombineResult: 재조합 결과

        Raises:
            ValueError: 모듈을 찾을 수 없는 경우
        """
        logger.info(
            f"[RECOMBINE] 시작 | title='{original_title[:30]}...' "
            f"| module_id={module_id}"
        )

        # 1. 모듈에서 설정 로드
        module = await self.db.get(Module, module_id)
        if not module:
            raise ValueError(f"모듈을 찾을 수 없습니다: id={module_id}")

        settings = module.settings or {}

        # 제목 재조합 활성화 여부 확인 (새/구 형식 호환)
        title_enabled = False
        title_prompt_text = None

        if "title_recombine" in settings:
            # 새 형식 (프롬프트 모듈: settings.title_recombine)
            tr = settings["title_recombine"]
            title_enabled = tr.get("enabled", False)
            title_prompt_text = tr.get("custom_prompt")
        else:
            # 구 형식 (생성 모듈: settings.enable_title_prompt)
            title_enabled = settings.get("enable_title_prompt", False)
            title_prompt_text = settings.get("title_prompt")

        if not title_enabled:
            logger.info("[RECOMBINE] 제목 재조합 비활성화 → 원본 제목 반환")
            return RecombineResult(
                original_title=original_title,
                recombined_title=original_title,
                ai_model="none",
                ai_provider="none",
                is_modified=False,
            )

        # 2. 프롬프트 구성
        title_prompt = title_prompt_text or DEFAULT_TITLE_PROMPT
        full_prompt = title_prompt.replace("{title}", original_title)

        # 3. AI 호출
        result = await self.ai_service.generate(
            prompt=full_prompt,
            provider=provider,
            model=model,
            max_tokens=200,
            temperature=0.7,
        )

        if not result:
            logger.warning("[RECOMBINE] AI 호출 실패 → 원본 제목 반환")
            return RecombineResult(
                original_title=original_title,
                recombined_title=original_title,
                ai_model="failed",
                ai_provider="failed",
                is_modified=False,
            )

        # 4. 결과 정리 (줄바꿈, 따옴표 제거)
        recombined = self._clean_title(result["content"])

        logger.info(
            f"[RECOMBINE] 완료 | 원본: '{original_title[:30]}' "
            f"→ 재조합: '{recombined[:30]}' "
            f"| model={result['model']}"
        )

        return RecombineResult(
            original_title=original_title,
            recombined_title=recombined,
            ai_model=result["model"],
            ai_provider=result["provider"],
            is_modified=True,
        )

    def _clean_title(self, raw_title: str) -> str:
        """AI 출력에서 제목만 추출 및 정리"""
        title = raw_title.strip()

        # 여러 줄이면 첫 번째 줄만
        if "\n" in title:
            title = title.split("\n")[0].strip()

        # 따옴표 제거
        for quote in ['"', "'", "「", "」", "『", "』"]:
            title = title.strip(quote)

        # 불필요한 접두사 제거
        prefixes = ["제목:", "재조합:", "결과:", "Title:"]
        for prefix in prefixes:
            if title.startswith(prefix):
                title = title[len(prefix):].strip()

        return title.strip()
