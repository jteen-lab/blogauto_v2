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
from .title_length import (
    fits as fits_length, parse_range as parse_length,
    retry_hint as length_retry_hint,
)

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

# 스타일별 지시. **분위기가 아니라 형태**를 말한다.
#
# "감성적이고 따뜻한 느낌" 같은 설명으로는 AI 가 스타일을 구분하지 못한다.
# 실제로 다섯 스타일이 거의 같은 제목으로 수렴했다. 무엇을 넣고 무엇을
# 빼야 하는지 문장 구조로 지시해야 갈린다.
#
# 모듈 설정(`title_recombine.style_prompts`)으로 덮어쓸 수 있다.
STYLE_PROMPTS: dict[str, str] = {
    "emotional": ("독자를 '당신'으로 부르고 감정 어휘를 하나 넣을 것. "
                  "예: 지금도 손실 중인 당신이 확인해야 할 매매 원칙"),
    "practical": "숫자나 절차를 넣을 것. 예: 3단계로 끝내는 매매 원칙과 5가지 확인 조건",
    "question": "의문사로 시작할 것. 예: 왜 지금 사야 하고 얼마나 나눠 담아야 하는가",
    "viral": ("역설이나 반전을 넣을 것. "
              "예: 아무도 말하지 않는 오히려 손해인 분할매수 구간"),
    "minimal": "명사로 끝낼 것. 수식어 금지. 예: 라오어 무한매수법 실전 매매 원칙 총정리",
}

# 스타일 한국어 라벨
STYLE_LABELS: dict[str, str] = {
    "emotional": "감성형",
    "practical": "실용형",
    "question": "질문형",
    "viral": "바이럴",
    "minimal": "심플",
}


def build_base_prompt(original_title: str,
                      extra_text: Optional[str] = None,
                      keywords: Optional[list] = None,
                      length: Optional[tuple] = None) -> str:
    """스타일 지시를 뺀 공통 프롬프트.

    단일 호출과 배치 호출이 **같은 본문**을 쓴다. 따로 만들면 한쪽만
    고쳐져 결과가 갈린다.

    길이 지시는 **맨 앞**에 둔다. 뒤에 두면 스타일 지시에 묻힌다 —
    추가 지시사항에 "25자 이내" 를 적어도 안 지켜지던 이유가 그것이다.
    """
    from .title_length import instruction as length_instruction

    prompt = ""
    if length:
        note = length_instruction(*length)
        if note:
            prompt = note + "\n\n"
    prompt += DEFAULT_TITLE_PROMPT.replace("{title}", original_title)

    # 핵심어를 명시한다. 이게 없으면 재조합이 검색되는 말을 흘린다.
    picked = [k for k in (keywords or []) if k and str(k).strip()][:5]
    if picked:
        prompt += ("\n\n반드시 유지할 핵심어: "
                   + ", ".join(str(k) for k in picked)
                   + "\n이 말들이 제목에서 빠지면 검색에 잡히지 않습니다.")

    if extra_text and extra_text.strip():
        extra = extra_text.strip().replace("{title}", original_title)
        prompt += f"\n\n추가 지시사항:\n{extra}"
    return prompt


def style_instruction(style: Optional[str],
                      overrides: Optional[dict] = None) -> Optional[str]:
    """이 스타일의 지시문. 모듈 설정이 있으면 그것을 쓴다.

    비어 있거나 공백뿐인 값은 덮어쓰기로 보지 않는다 — 화면에서 지우면
    기본값으로 돌아가야 한다.
    """
    if not style:
        return None
    custom = (overrides or {}).get(style)
    if custom and str(custom).strip():
        return str(custom).strip()
    return STYLE_PROMPTS.get(style)


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
        keywords: Optional[list] = None,
    ) -> RecombineResult:
        """
        제목 재조합 실행

        Args:
            original_title: 원본 정식 제목
            module_id: 생성 모듈 ID (settings에서 prompt 로드)
            provider: AI 제공자 (None이면 자동)
            model: AI 모델 (None이면 기본값)
            style: 제목 스타일 (emotional, practical, question, viral, minimal)
            keywords: 지켜야 할 핵심어. 재조합이 원본 문자열만 보면 검색
                되는 말이 빠질 수 있다(계획서 §4-5 B)

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

        style_overrides: dict = {}
        if "title_recombine" in settings:
            # 새 형식 (프롬프트 모듈: settings.title_recombine)
            tr = settings["title_recombine"]
            title_enabled = tr.get("enabled", False)
            title_prompt_text = tr.get("custom_prompt")
            # 스타일 지시를 화면에서 고칠 수 있다. 비운 것은 기본값을 쓴다.
            style_overrides = tr.get("style_prompts") or {}
            length_range = parse_length(tr)
        else:
            # 구 형식 (생성 모듈: settings.enable_title_prompt)
            title_enabled = settings.get("enable_title_prompt", False)
            title_prompt_text = settings.get("title_prompt")
            length_range = (0, 0)

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
        full_prompt = build_base_prompt(
            original_title, title_prompt_text, keywords, length_range)

        # 스타일 지시. **이 스타일 것만** 넣는다 — 다섯 개를 다 넣으면
        # AI 가 전부 지키려 해서 결과가 같아진다(실제로 그랬다).
        instruction = style_instruction(style, style_overrides)
        if instruction:
            full_prompt += (
                f"\n\n[스타일: {STYLE_LABELS.get(style, style)}] {instruction}"
                "\n위 규칙과 충돌하면 스타일을 우선하세요.")
            logger.debug(f"[RECOMBINE] 스타일 적용 | style={style}")

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

        # **AI 는 글자수를 세지 못한다.** 우리가 세고, 벗어나면 실제 길이를
        # 알려 주며 한 번 다시 청한다. 두 번은 하지 않는다 — 호출이
        # 통제를 벗어난다.
        recombined = await self._fit_length(
            recombined, full_prompt, length_range, provider, model)

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
        # 한 번에 만들어 본다. 스타일마다 따로 부르면 서로를 몰라서
        # 비슷한 답이 나온다(실제로 다섯이 거의 같았다).
        batched = await self._batch_styles(module, styles, original_title,
                                           provider, model)
        if batched:
            return batched

        logger.info("[RECOMBINE_STYLES] 배치 실패 → 스타일별 개별 호출")
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

    async def _fit_length(self, title: str, base_prompt: str,
                          length: tuple, provider: Optional[str],
                          model: Optional[str]) -> str:
        """길이가 안 맞으면 한 번 다시 만든다. 실패하면 원래 것을 쓴다."""
        low, high = length or (0, 0)
        if not (low or high) or fits_length(title, low, high):
            return title

        hint = length_retry_hint(title, low, high)
        logger.info(f"[RECOMBINE] 길이 재시도 | {hint}")
        try:
            result = await self.ai_service.generate(
                prompt=f"{base_prompt}\n\n{hint}\n제목만 출력하세요.",
                provider=provider, model=model,
                max_tokens=200, temperature=0.7)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[RECOMBINE] 길이 재시도 실패: {e}")
            return title
        if not result:
            return title

        retried = self._clean_title(result.get("content") or "")
        # 다시 만든 것도 안 맞으면 더 시도하지 않는다. 둘 중 가까운 쪽을 쓴다.
        if retried and fits_length(retried, low, high):
            return retried
        return retried or title

    async def _batch_styles(self, module, styles: list, original_title: str,
                            provider: Optional[str], model: Optional[str],
                            ) -> Optional[list]:
        """스타일 전체를 한 번에 만든다. 실패하면 None(개별 호출로)."""
        from .title_style_batch import (
            MAX_STYLES, build_prompt, is_complete, parse,
        )

        picked = [s for s in styles if s][:MAX_STYLES]
        if not picked:
            return None

        settings = module.settings or {}
        tr = settings.get("title_recombine", {})
        overrides = tr.get("style_prompts") or {}

        length = parse_length(tr)
        base = build_base_prompt(
            original_title, tr.get("custom_prompt"), None, length)
        prompt = build_prompt(
            base, picked, STYLE_LABELS,
            {code: style_instruction(code, overrides) for code in picked})

        try:
            result = await self.ai_service.generate(
                prompt=prompt, provider=provider, model=model,
                # 스타일 수만큼 받아야 하니 단일 호출보다 넉넉히
                max_tokens=200 + 120 * len(picked),
                temperature=0.8)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[RECOMBINE_STYLES] 배치 호출 실패: {e}")
            return None
        if not result:
            return None

        parsed = parse(result.get("content") or "", picked)
        # 길이가 어긋난 것은 개별 호출로 돌린다. 거기서 한 번 더 청한다 —
        # 배치를 통째로 다시 부르면 맞았던 제목까지 바뀐다.
        low, high = length
        if low or high:
            parsed = {code: title for code, title in parsed.items()
                      if fits_length(self._clean_title(title), low, high)}
        if not is_complete(parsed, picked):
            # 일부만 오면 빈칸이 생긴다. 개별 호출로 돌아가는 편이 낫다.
            logger.info("[RECOMBINE_STYLES] 응답 부족 | %d/%d",
                        len(parsed), len(picked))
            return None

        return [RecombineStyleResult(
            style=code,
            style_label=STYLE_LABELS.get(code, code),
            original_title=original_title,
            recombined_title=self._clean_title(parsed[code]),
            ai_model=result.get("model", "unknown"),
            ai_provider=result.get("provider", provider or "unknown"),
            is_modified=self._clean_title(parsed[code]) != original_title,
        ) for code in picked]

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
