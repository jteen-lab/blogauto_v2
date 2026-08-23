"""
글 생성 AI 호출 헬퍼 - ContentGenerator에서 분리

설정 우선순위:
- AI 제공자/모델: Blog.ai_config.writing_ai (블로그 설정만 사용)
- 프롬프트/세부설정: Module.settings.content_generation -> 기본값
"""
import logging
from typing import Optional

from ...models.blog import Blog
from ..ai.ai_service import AIService
from ..prompt_builder.blocks import adsense_gain_directive, aeo_directive

logger = logging.getLogger(__name__)

# 기본 글 생성 프롬프트
DEFAULT_CONTENT_PROMPT = (
    "다음 주제로 블로그 글을 작성해주세요.\n\n"
    "제목: {title}\n\n"
    "{reference_materials}\n\n"
    "규칙:\n"
    "- 마크다운 형식으로 작성\n"
    "- ## 소제목을 사용하여 섹션 구분\n"
    "- 자연스러운 한국어 문장\n"
    "- 1500~3000자 분량"
)


async def generate_content_with_meta(
    ai_service: AIService,
    title: str,
    reference_injection: str,
    settings: dict,
    blog: Blog,
    category_name: str = "",
    keywords_text: str = "",
    prompt_override: str = "",
    extra_instruction: str = "",
    existing_content: str = "",
) -> dict:
    """AI로 글 생성 (블로그 AI 설정 기준)

    Args:
        ai_service: AI 서비스 인스턴스
        title: 재조합된 제목
        reference_injection: 참조자료 프롬프트 텍스트
        settings: 모듈 설정
        blog: 블로그 객체
        category_name: 카테고리 이름 ({category} 치환용)
        keywords_text: 키워드 텍스트 ({keywords} 치환용)
        prompt_override: 비어있지 않으면 모듈 프롬프트 대신 사용(리뉴얼 새 프롬프트)
        extra_instruction: 프롬프트 말미에 덧붙일 추가 지침(리뉴얼 추가 프롬프트)
        existing_content: {existing_content} 치환용 기존 글 본문(리뉴얼 확장)

    Returns:
        dict: {"content": str, "model": str, "provider": str}

    Raises:
        RuntimeError: AI 글 생성 실패 시
    """
    cg = settings.get("content_generation", {})
    ai_config = blog.ai_config or {}
    writing_ai = ai_config.get("writing_ai", {})

    # 프롬프트: 리뉴얼 새 프롬프트(override) -> 모듈 새 형식 -> 레거시 -> 기본값
    prompt_template = (
        prompt_override
        or cg.get("user_prompt_template")
        or settings.get("generation_prompt")
        or DEFAULT_CONTENT_PROMPT
    )
    full_prompt = (
        prompt_template
        .replace("{title}", title)
        .replace("{reference_materials}", reference_injection)
        .replace("{category}", category_name)
        .replace("{keywords}", keywords_text)
        .replace("{existing_content}", existing_content)
    )
    # 리뉴얼 추가 지침을 프롬프트 말미에 결합
    if extra_instruction:
        full_prompt = f"{full_prompt}\n\n{extra_instruction}"

    # F7: 프롬프트 모듈 '정보이득 강화' 토글 시 지시문 주입(옵트인·중복 가드).
    if settings.get("info_gain_enabled"):
        directive = adsense_gain_directive()
        if directive and directive[:20] not in full_prompt:
            full_prompt = f"{full_prompt}\n\n{directive}"
            logger.info("[GENERATOR] F7 정보이득 지시문 주입 | blog=%s", blog.name)

    # AEO/GEO: 'AI 답변 인용 대비' 토글 시 지시문 주입(옵트인·중복 가드).
    # 정보이득과 축이 달라 함께 켜도 충돌하지 않는다
    # (정보이득=무엇을 쓸지, AEO=어떤 형태로 쓸지).
    if settings.get("aeo_enabled"):
        aeo = aeo_directive()
        if aeo and aeo[:20] not in full_prompt:
            full_prompt = f"{full_prompt}\n\n{aeo}"
            logger.info("[GENERATOR] AEO 지시문 주입 | blog=%s", blog.name)

    # AI 제공자: 블로그 ai_config.writing_ai 설정만 사용
    provider = writing_ai.get("provider")
    model = writing_ai.get("model")

    # 세부 설정: 모듈 설정 -> 기본값
    temperature = cg.get("temperature", 0.7)
    max_tokens = cg.get("max_tokens", 4000)
    system_prompt = cg.get("system_prompt") or None
    top_p = cg.get("top_p")
    top_k = cg.get("top_k")
    frequency_penalty = cg.get("frequency_penalty")
    presence_penalty = cg.get("presence_penalty")

    logger.info(
        f"[GENERATOR] AI 설정 | provider={provider} (source=blog.writing_ai), "
        f"temp={temperature}, tokens={max_tokens}, "
        f"sys_prompt={'Y' if system_prompt else 'N'}"
    )

    result = await ai_service.generate(
        prompt=full_prompt,
        provider=provider,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system_prompt=system_prompt,
        top_p=top_p,
        top_k=top_k,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
    )

    if not result:
        raise RuntimeError("AI 글 생성 실패: 모든 제공자 호출 실패")

    return result
