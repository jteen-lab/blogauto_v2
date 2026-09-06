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
    skip_length_directive: bool = False,
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
        skip_length_directive: True 면 분량 지시문을 붙이지 않는다
            (이어쓰기는 자체 지시문을 쓰므로 중복 주입을 막는다)

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
    # 자리표시자가 없는 프롬프트에도 자료가 들어가게 한다.
    #
    # 프롬프트 빌더 화면은 {title}·{category}·{keywords} 만 안내한다.
    # {reference_materials} 는 어디에도 없어서, 화면으로 만든 모듈은
    # **전부** 이 자리표시자가 빠져 있었다. 검색·크롤링·요약을 다 하고
    # 결과를 버린 셈이다(2026-09-06 실측: 14개 중 12개, 최근 30일 글의 95%).
    #
    # 분량·정보이득 지시문보다 **앞에** 붙인다. 그것들이 마지막에 읽혀야
    # "위의 다른 분량 언급보다 우선" 같은 문장이 뜻을 갖는다.
    if reference_injection and "{reference_materials}" not in prompt_template:
        full_prompt = f"{full_prompt}\n\n{reference_injection}"
        logger.info(
            "[GENERATOR] 참조 자리표시자 없음 — 말미에 붙임 | blog=%s",
            blog.name,
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

    # 분량 지시문 — 게이트 임계값에서 유도해 주입한다.
    # 이 지시가 없으면 모델은 모듈 프롬프트의 목표치를 소프트하게 받아
    # 중앙 1,883자·하위10% 1,484자로 흩어진다(400편 실측). 게이트가 보는
    # 숫자와 모델이 듣는 숫자를 한 곳에서 묶는다.
    if not skip_length_directive:
        from .quality_gate import resolve_settings as _gate_cfg
        from .length_directive import build as _length_directive

        gate_cfg = _gate_cfg(settings)
        if gate_cfg["enabled"]:
            directive = _length_directive(gate_cfg["min_chars"], settings)
            if directive and "■ 분량 기준" not in full_prompt:
                full_prompt = f"{full_prompt}\n\n{directive}"
                logger.info(
                    "[GENERATOR] 분량 지시문 주입 | blog=%s | 최소=%s",
                    blog.name, gate_cfg["min_chars"],
                )

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


async def extend_content(
    ai_service: AIService,
    title: str,
    draft: str,
    current_chars: int,
    min_chars: int,
    settings: dict,
    blog: Blog,
) -> str:
    """짧은 초안에 이어쓰기 1회. 실패하면 초안을 그대로 돌려준다.

    버리고 다시 만들지 않는 이유: 재생성은 참조 수집(검색 30·크롤 10)과
    제목 재조합까지 되풀이하면서도 모델에게 "짧았다" 는 사실을 전하지
    않는다. 같은 분포에서 다시 뽑을 뿐이다.

    한 번만 한다. 두 번 세 번 이어 붙이면 글이 늘어지고 비용도 는다.
    """
    from .length_directive import continuation_prompt

    cg = settings.get("content_generation", {})
    writing_ai = (blog.ai_config or {}).get("writing_ai", {})

    prompt = continuation_prompt(
        title, draft, current_chars, min_chars, settings)

    logger.info(
        "[GENERATOR] 이어쓰기 시도 | blog=%s | %s | 현재 %d자",
        blog.name, title[:30], current_chars,
    )

    try:
        result = await ai_service.generate(
            prompt=prompt,
            provider=writing_ai.get("provider"),
            model=writing_ai.get("model"),
            max_tokens=cg.get("max_tokens", 4000),
            temperature=cg.get("temperature", 0.7),
            system_prompt=cg.get("system_prompt") or None,
        )
    except Exception as e:  # noqa: BLE001
        # 이어쓰기 실패로 생성을 죽이지 않는다. 초안은 그대로 두고
        # 게이트가 최종 판단한다.
        logger.warning("[GENERATOR] 이어쓰기 호출 실패(무시) | %s", e)
        return draft

    addition = ((result or {}).get("content") or "").strip()
    if not addition:
        logger.warning("[GENERATOR] 이어쓰기 결과 비어 있음 | %s", title[:30])
        return draft

    # 모델이 안내 문구를 붙이는 경우가 있어 첫 줄만 걸러낸다.
    lines = addition.split("\n")
    if lines and lines[0].strip().startswith(("이어서", "다음은", "추가로")):
        addition = "\n".join(lines[1:]).lstrip()

    return f"{draft.rstrip()}\n\n{addition}"
