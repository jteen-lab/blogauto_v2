"""모듈 통합형 애드센스 자동 전환 (계획서 3.2).

별도 모듈을 만들지 않고 **한 모듈 안에서** 애드센스 옵션이 블로그 상태에 따라
켜지고 꺼지게 한다. `adsense_auto` 를 켠 모듈만 대상이며, 끄면 사용자가 지정한
값이 그대로 쓰인다(기본값·하위호환).

| 블로그 상태 | 니치 강제 | 정보이득 | AEO |
|---|---|---|---|
| 승인 전(none/preparing/applied) | ON | ON | ON |
| 승인(approved) | **OFF** | **OFF** | 사용자 설정 유지 |

AEO는 승인 후에도 유지한다 — 검색 노출에 계속 유효하고 애드센스 심사와 무관하다.
니치 강제는 승인 후 꺼져야 원래 카테고리 기준으로 돌아간다.
"""
from typing import Any, Dict, Optional

from ...core.logger import get_logger

logger = get_logger("adsense_auto_settings", "app.log")

AUTO_KEY = "adsense_auto"
APPROVED_STATUS = "approved"


def is_auto_enabled(module_settings: Optional[Dict[str, Any]]) -> bool:
    """이 모듈이 블로그 상태에 따라 자동 전환되도록 설정됐는지."""
    return bool((module_settings or {}).get(AUTO_KEY))


def resolve_for_blog(
    module_settings: Optional[Dict[str, Any]], blog: Any,
) -> Dict[str, Any]:
    """블로그 상태를 반영한 실행용 settings를 만든다.

    원본은 건드리지 않는다(모듈 설정은 사용자 것이고, 실행 시점 해석만 바꾼다).

    Args:
        module_settings: 프롬프트 모듈 settings
        blog: 대상 블로그(adsense_status 사용)

    Returns:
        실행에 쓸 settings dict
    """
    settings = dict(module_settings or {})
    if not is_auto_enabled(settings):
        return settings

    approved = (getattr(blog, "adsense_status", None) == APPROVED_STATUS)

    if approved:
        # 승인 완료 → 애드센스 승인용 제약 해제, 원래 카테고리 기준으로 복귀
        settings["niche_enabled"] = False
        settings["info_gain_enabled"] = False
    else:
        # 승인 전 → 승인에 유리한 설정 강제
        settings["niche_enabled"] = True
        settings["info_gain_enabled"] = True
        settings["aeo_enabled"] = True

    logger.info(
        "[ADSENSE_AUTO] 자동 전환 적용 | blog=%s | 승인=%s | 니치=%s 정보이득=%s",
        getattr(blog, "name", "?"), approved,
        settings.get("niche_enabled"), settings.get("info_gain_enabled"),
    )
    return settings
