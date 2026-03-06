"""
제목 재조합 서비스

정식 제목을 AI로 재조합하는 서비스.
프롬프트 모듈(생성 타입 Module)의 title_prompt를 사용합니다.
스타일별 재조합을 지원합니다 (emotional, practical, question, viral, minimal).

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

# 스타일별 AI 프롬프트 설명
STYLE_PROMPTS: dict[str, str] = {
    "emotional": "감성적이고 따뜻한 느낌으로, 독자의 감정에 호소하는 스타일",
    "practical": "실용적이고 구체적인 정보를 강조하는 스타일",
    "question": "독자의 궁금증을 자극하는 질문형 스타일",
    "viral": "클릭을 유도하는 임팩트 있는 바이럴 스타일",
    "minimal": "간결하고 핵심만 담은 심플한 스타일",
}

# 스타일 한국어 라벨
STYLE_LABELS: dict[str, str] = {
    "emotional": "감성형",
    "practical": "실용형",
    "question": "질문형",
    "viral": "바이럴",
    "minimal": "심플",
}


@dataclass
class RecombineResult:
    """제목 재조합 결과"""
    original_title: str
    recombined_title: str
    ai_model: str
    ai_provider: str
    is_modified: bool
    error_detail: str = ""


@dataclass
class RecombineStyleResult:
    """스타일별 제목 재조합 결과"""
    style: str
    style_label: str
    original_title: str
    recombined_title: str
    ai_model: str
    ai_provider: str
    is_modified: bool
    error_detail: str = ""


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
        style: Optional[str] = None,
    ) -> RecombineResult:
        """
        제목 재조합 실행

        Args:
            original_title: 원본 정식 제목
            module_id: 생성 모듈 ID (settings에서 prompt 로드)
            provider: AI 제공자 (None이면 자동)
            model: AI 모델 (None이면 기본값)
            style: 제목 스타일 (emotional, practical, question, viral, minimal)

        Returns:
            RecombineResult: 재조합 결과

        Raises:
            ValueError: 모듈을 찾을 수 없는 경우
        """
        style_label = STYLE_LABELS.get(style, "") if style else ""
        logger.info(
            f"[RECOMBINE] 시작 | title='{original_title[:30]}...' "
            f"| module_id={module_id}"
            f"{f' | style={style}({style_label})' if style else ''}"
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

        # 2. 프롬프트 구성 (기본 프롬프트 + 추가 지시사항)
        full_prompt = DEFAULT_TITLE_PROMPT.replace("{title}", original_title)

        # 추가 지시사항이 있으면 기본 프롬프트 뒤에 추가
        if title_prompt_text and title_prompt_text.strip():
            extra = title_prompt_text.strip().replace("{title}", original_title)
            full_prompt += f"\n\n추가 지시사항:\n{extra}"

        # 스타일이 지정된 경우 프롬프트에 스타일 지시 추가
        if style and style in STYLE_PROMPTS:
            style_instruction = (
                f"\n\n스타일: {STYLE_PROMPTS[style]}"
            )
            full_prompt += style_instruction
            logger.debug(
                f"[RECOMBINE] 스타일 적용 | style={style}"
            )

        # 3. AI 호출
        logger.info(
            f"[RECOMBINE] AI 호출 시도 | provider={provider} | model={model}"
        )
        if not provider:
            error_msg = "provider가 None - 모듈/블로그 설정에서 AI 제공자 미지정"
            logger.error(f"[RECOMBINE] {error_msg}")
            return RecombineResult(
                original_title=original_title,
                recombined_title=original_title,
                ai_model="none",
                ai_provider="none",
                is_modified=False,
                error_detail=error_msg,
            )

        result = await self.ai_service.generate(
            prompt=full_prompt,
            provider=provider,
            model=model,
            max_tokens=200,
            temperature=0.7,
        )

        if not result:
            error_msg = (
                f"AI 호출 실패 (provider={provider}, model={model}) - "
                f"API 키 미등록/비활성/오류 상태일 가능성"
            )
            logger.warning(f"[RECOMBINE] {error_msg}")
            return RecombineResult(
                original_title=original_title,
                recombined_title=original_title,
                ai_model="failed",
                ai_provider="failed",
                is_modified=False,
                error_detail=error_msg,
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

    async def recombine_with_styles(
        self,
        original_title: str,
        module_id: int,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        override_styles: Optional[list[str]] = None,
    ) -> list[RecombineStyleResult]:
        """
        모듈 설정의 스타일별로 제목을 재조합

        Module.settings.title_recombine.styles 리스트에 있는
        각 스타일에 대해 recombine()을 호출하여 스타일별 결과를 반환합니다.
        스타일 미설정 시 기본 recombine 1회 실행.

        Args:
            original_title: 원본 정식 제목
            module_id: 생성 모듈 ID
            provider: AI 제공자 (None이면 자동)
            model: AI 모델 (None이면 기본값)
            override_styles: UI에서 전달된 스타일 목록 (None이면 DB 설정 사용)

        Returns:
            RecombineStyleResult 리스트 (스타일별 1개씩)

        Raises:
            ValueError: 모듈을 찾을 수 없는 경우
        """
        module = await self.db.get(Module, module_id)
        if not module:
            raise ValueError(f"모듈을 찾을 수 없습니다: id={module_id}")

        # override_styles가 전달되면 우선 사용, 없으면 DB 설정 사용
        if override_styles is not None:
            styles = override_styles
        else:
            settings = module.settings or {}
            tr = settings.get("title_recombine", {})
            styles = tr.get("styles", [])

        if not styles:
            # 스타일 미설정 → 기본 recombine 1회
            logger.info(
                "[RECOMBINE_STYLES] 스타일 미설정 → 기본 모드 1회 실행"
            )
            result = await self.recombine(
                original_title=original_title,
                module_id=module_id,
                provider=provider,
                model=model,
            )
            return [RecombineStyleResult(
                style="default",
                style_label="기본",
                original_title=result.original_title,
                recombined_title=result.recombined_title,
                ai_model=result.ai_model,
                ai_provider=result.ai_provider,
                is_modified=result.is_modified,
                error_detail=result.error_detail,
            )]

        logger.info(
            f"[RECOMBINE_STYLES] {len(styles)}개 스타일 실행 | "
            f"styles={styles}"
        )
        results: list[RecombineStyleResult] = []
        for style in styles:
            result = await self.recombine(
                original_title=original_title,
                module_id=module_id,
                provider=provider,
                model=model,
                style=style,
            )
            results.append(RecombineStyleResult(
                style=style,
                style_label=STYLE_LABELS.get(style, style),
                original_title=result.original_title,
                recombined_title=result.recombined_title,
                ai_model=result.ai_model,
                ai_provider=result.ai_provider,
                is_modified=result.is_modified,
                error_detail=result.error_detail,
            ))

        return results

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
