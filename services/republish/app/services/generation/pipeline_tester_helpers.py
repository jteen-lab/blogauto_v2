"""pipeline_tester.py 헬퍼 함수 모듈

PipelineTester에서 self를 사용하지 않는 순수 함수들을 분리합니다.
"""
from ..ai.ai_service import AIService
from .generator import DEFAULT_CONTENT_PROMPT


def build_image_result(
    result, elapsed: int, img_settings: dict,
    blog_image_mode: str, settings_source: str = "db",
) -> dict:
    """이미지 테스트 결과 딕셔너리 생성"""
    both_info = {}
    if blog_image_mode == "both":
        both_info = {
            "cover_source": img_settings.get("cover_source", "ai"),
            "section_source": img_settings.get(
                "section_source", "template"
            ),
        }
    return {
        "step": "generate_image",
        "success": result.success,
        "result": {
            "image_url": result.image_url,
            "image_mode": result.image_mode,
            "provider": result.provider,
            "ai_model": result.ai_model,
            "generation_time_seconds": elapsed,
            "blog_image_mode": blog_image_mode,
            "enabled": img_settings.get("enabled", False),
            "title_overlay": img_settings.get("title_overlay", False),
            "section_images": result.section_images,
            "settings_used": {
                "source": settings_source,
                "aspect_ratio": img_settings.get("aspect_ratio"),
                "style": img_settings.get("style"),
                "quality": img_settings.get("quality"),
                "prompt_template": img_settings.get("prompt_template"),
            },
            **both_info,
        },
        **({"error": result.error} if result.error else {}),
    }


async def call_ai_generate(
    ai_service: AIService, title: str, ref_injection: str,
    settings: dict, blog,
    category_name: str = "", keywords_text: str = "",
) -> tuple:
    """AI 글 생성 호출 (generator.py 로직 재현)

    Args:
        ai_service: AIService 인스턴스
        title: 제목
        ref_injection: 참조자료 텍스트
        settings: 모듈 설정
        blog: Blog 인스턴스
        category_name: 카테고리명
        keywords_text: 키워드 텍스트

    Returns:
        (result_dict, settings_info) 튜플
    """
    cg = settings.get("content_generation", {})
    writing_ai = (blog.ai_config or {}).get("writing_ai", {})
    prompt_template = (
        cg.get("user_prompt_template")
        or settings.get("generation_prompt") or DEFAULT_CONTENT_PROMPT
    )
    full_prompt = prompt_template.replace(
        "{title}", title
    ).replace(
        "{reference_materials}", ref_injection
    ).replace(
        "{category}", category_name or ""
    ).replace(
        "{keywords}", keywords_text or ""
    )
    provider = writing_ai.get("provider")
    model = writing_ai.get("model")
    temperature = cg.get("temperature", 0.7)
    max_tokens = cg.get("max_tokens", 4000)
    system_prompt = cg.get("system_prompt") or None
    top_p = cg.get("top_p")
    top_k = cg.get("top_k")
    frequency_penalty = cg.get("frequency_penalty")
    presence_penalty = cg.get("presence_penalty")
    settings_info = {
        "provider_source": "blog.writing_ai",
        "temperature": temperature, "max_tokens": max_tokens,
        "has_system_prompt": system_prompt is not None,
        "prompt_source": get_prompt_source(cg, settings),
        "top_p": top_p, "top_k": top_k,
        "frequency_penalty": frequency_penalty,
        "presence_penalty": presence_penalty,
    }
    result = await ai_service.generate(
        prompt=full_prompt, provider=provider, model=model,
        max_tokens=max_tokens, temperature=temperature,
        system_prompt=system_prompt,
        top_p=top_p, top_k=top_k,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
    )
    return result, settings_info


def get_prompt_source(cg: dict, settings: dict) -> str:
    """사용된 프롬프트 소스 판별"""
    if cg.get("user_prompt_template"):
        return "content_generation.user_prompt_template"
    if settings.get("generation_prompt"):
        return "generation_prompt (legacy)"
    return "DEFAULT_CONTENT_PROMPT"


def make_error(step: str, message: str) -> dict:
    """에러 응답 생성"""
    return {"step": step, "success": False, "error": message}
