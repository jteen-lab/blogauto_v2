"""
이미지 파라미터 변환 레이어

모듈의 통합 파라미터(aspect_ratio, style, quality)를
블로그의 AI provider에 맞게 자동 변환합니다.

설계 문서: image_generation_unified_settings_plan.md - Phase 3
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Provider 정규화 매핑
PROVIDER_NORMALIZE = {
    "openai": "dalle",
    "dall-e": "dalle",
    "dalle": "dalle",
    "nanobanana": "nanobanana",
    "gemini": "nanobanana",
}

# 통합 aspect_ratio → DALL-E size 매핑
DALLE_SIZE_MAP = {
    "16:9": "1792x1024",
    "9:16": "1024x1792",
    "1:1": "1024x1024",
    "4:3": "1024x1024",   # 근사 매핑
    "3:4": "1024x1792",   # 근사 매핑
}

# 통합 style → DALL-E style 매핑
DALLE_STYLE_MAP = {
    "realistic": "natural",
    "vivid": "vivid",
    "artistic": "vivid",
    "cartoon": "vivid",    # 근사 매핑
    "minimal": "natural",  # 근사 매핑
}

# 통합 style → Nanobanana style 매핑 (대부분 직접 전달)
NANO_STYLE_MAP = {
    "realistic": "realistic",
    "vivid": "artistic",
    "artistic": "artistic",
    "cartoon": "cartoon",
    "minimal": "minimal",
}


def normalize_provider(provider: str) -> str:
    """
    Provider 이름 정규화

    Args:
        provider: 원본 provider 이름 (openai, dalle, nanobanana 등)

    Returns:
        정규화된 provider 이름 (dalle 또는 nanobanana)
    """
    normalized = PROVIDER_NORMALIZE.get(provider, provider)
    if normalized not in ("dalle", "nanobanana"):
        logger.warning(
            f"[PARAM_CONV] 알 수 없는 provider: {provider} → "
            f"기본값 dalle 사용"
        )
        return "dalle"
    return normalized


def convert_to_provider_params(
    unified_settings: dict,
    provider: str,
    model: Optional[str] = None,
) -> dict:
    """
    통합 파라미터를 provider별 파라미터로 변환

    Args:
        unified_settings: 모듈의 image_generation 설정
            - aspect_ratio: "16:9" | "9:16" | "1:1" | "4:3" | "3:4"
            - style: "realistic" | "vivid" | "artistic" | "cartoon" | "minimal"
            - quality: "standard" | "hd"
        provider: 정규화된 provider 이름 (dalle/nanobanana)
        model: AI 모델 이름 (블로그 설정에서 오버라이드)

    Returns:
        provider별 파라미터 dict
    """
    provider = normalize_provider(provider)
    aspect_ratio = unified_settings.get("aspect_ratio", "16:9")
    style = unified_settings.get("style", "realistic")
    quality = unified_settings.get("quality", "standard")

    if provider == "dalle":
        params = _convert_to_dalle(aspect_ratio, style, quality, model)
    else:
        params = _convert_to_nanobanana(aspect_ratio, style, model)

    logger.info(
        f"[PARAM_CONV] 변환 완료 | provider={provider} | "
        f"입력: ratio={aspect_ratio}, style={style}, quality={quality} | "
        f"출력: {params}"
    )
    return params


def _convert_to_dalle(
    aspect_ratio: str,
    style: str,
    quality: str,
    model: Optional[str],
) -> dict:
    """
    통합 파라미터 → DALL-E 파라미터 변환

    Returns:
        {"size": str, "quality": str, "style": str, "model": str}
    """
    return {
        "size": DALLE_SIZE_MAP.get(aspect_ratio, "1024x1024"),
        "quality": quality if quality in ("standard", "hd") else "standard",
        "style": DALLE_STYLE_MAP.get(style, "natural"),
        "model": model or "dall-e-3",
    }


def _convert_to_nanobanana(
    aspect_ratio: str,
    style: str,
    model: Optional[str],
) -> dict:
    """
    통합 파라미터 → Nanobanana 파라미터 변환

    Returns:
        {"aspect_ratio": str, "style": str, "model": str}
    """
    return {
        "aspect_ratio": aspect_ratio,
        "style": NANO_STYLE_MAP.get(style, "realistic"),
        "model": model or "gemini-2.0-flash-exp",
    }


# DALL-E size → 통합 aspect_ratio 역변환
_DALLE_SIZE_REVERSE = {
    "1792x1024": "16:9",
    "1024x1792": "9:16",
    "1024x1024": "1:1",
}

# DALL-E style → 통합 style 역변환
_DALLE_STYLE_REVERSE = {
    "natural": "realistic",
    "vivid": "vivid",
}


def migrate_legacy_image_settings(settings: dict) -> dict:
    """
    레거시 dalle{}/nanobanana{} 구조를 통합 키로 변환

    Phase 2 이전에 저장된 모듈 데이터를 자동 변환합니다.
    이미 통합 형식이면 그대로 반환합니다.

    Args:
        settings: image_generation 설정 dict

    Returns:
        통합 형식의 settings dict (원본 수정 안 함)
    """
    # 이미 통합 형식이면 그대로 반환
    if "aspect_ratio" in settings:
        return settings

    # dalle{} 또는 nanobanana{} 없으면 변환 불필요
    dalle = settings.get("dalle")
    nanobanana = settings.get("nanobanana")
    if not dalle and not nanobanana:
        return settings

    result = {k: v for k, v in settings.items()
              if k not in ("dalle", "nanobanana", "provider",
                           "images_per_post", "cover_source",
                           "section_source")}

    if dalle:
        size = dalle.get("size", "1024x1024")
        result["aspect_ratio"] = _DALLE_SIZE_REVERSE.get(size, "1:1")
        style = dalle.get("style", "natural")
        result["style"] = _DALLE_STYLE_REVERSE.get(style, "realistic")
        result["quality"] = dalle.get("quality", "standard")
    elif nanobanana:
        result["aspect_ratio"] = nanobanana.get(
            "aspectRatio", nanobanana.get("aspect_ratio", "16:9"),
        )
        result["style"] = nanobanana.get("style", "realistic")
        result["quality"] = "standard"

    logger.info(
        f"[PARAM_CONV] 레거시 마이그레이션 완료 | "
        f"ratio={result.get('aspect_ratio')}, "
        f"style={result.get('style')}, "
        f"quality={result.get('quality')}"
    )
    return result
