"""성장 프로파일 ↔ 애드센스 프리셋 전환 (계획서 3.3).

블로그가 애드센스 준비 단계에 들어가면 성장 프로파일을 `adsense` 프리셋
(1일 1생성·1발행, 재발행 중단)으로 바꾸고, 승인 후에는 **원래 쓰던 설정으로
되돌린다**. 되돌릴 수 있으려면 전환 전 설정을 보관해 두어야 한다.

프리셋 식별자는 이미 `settings.selectedPreset` 에 저장되고 있다
(aggressive/balanced/conservative/adsense/custom_*). 여기서 추가하는 것은
**원본 스냅샷**(`settings.adsense_base_profile`)이다.

계획서: docs/plans/adsense_status_automation_plan.md
"""
import copy
from typing import Any, Dict, Optional

from ...core.logger import get_logger
from .growth_profile_defaults import get_default_profile

logger = get_logger("growth_profile_adsense", "app.log")

ADSENSE_PRESET_KEY = "adsense"
BASE_SNAPSHOT_KEY = "adsense_base_profile"
AUTO_SWITCH_KEY = "adsense_auto"

# 스냅샷에 담을 프로파일 본체 키(사용자가 만든 커스텀 프로파일 목록도 보존)
_PROFILE_KEYS = (
    "selectedPreset", "schedule_matrix", "jitter", "stages", "warmup",
    "custom_profiles",
)


def is_adsense_auto(settings: Optional[Dict[str, Any]]) -> bool:
    """이 성장 프로파일이 애드센스 상태에 따라 자동 전환되도록 설정됐는지."""
    return bool((settings or {}).get(AUTO_SWITCH_KEY))


def is_on_adsense_preset(settings: Optional[Dict[str, Any]]) -> bool:
    """현재 애드센스 프리셋이 적용된 상태인지."""
    return (settings or {}).get("selectedPreset") == ADSENSE_PRESET_KEY


def _snapshot(settings: Dict[str, Any]) -> Dict[str, Any]:
    """되돌릴 대상 키만 복사해 스냅샷을 만든다."""
    return {k: copy.deepcopy(settings[k]) for k in _PROFILE_KEYS if k in settings}


def apply_adsense_preset(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """애드센스 프리셋을 적용한다(원본은 스냅샷으로 보관).

    이미 애드센스 프리셋이면 **스냅샷을 덮어쓰지 않는다** — 두 번 호출해도
    원본이 애드센스 설정으로 바뀌어 복원이 불가능해지는 것을 막는다.

    Returns:
        새 settings dict (입력은 변경하지 않음)
    """
    current = dict(settings or {})

    if is_on_adsense_preset(current):
        return current

    snapshot = _snapshot(current)
    preset = get_default_profile(ADSENSE_PRESET_KEY)

    new_settings = dict(current)
    for key in _PROFILE_KEYS:
        new_settings.pop(key, None)
    new_settings.update(preset)
    new_settings["selectedPreset"] = ADSENSE_PRESET_KEY
    if snapshot:
        new_settings[BASE_SNAPSHOT_KEY] = snapshot

    logger.info(
        "[GP_ADSENSE] 애드센스 프리셋 적용 | 이전=%s | 스냅샷=%s",
        current.get("selectedPreset"), "보관" if snapshot else "없음",
    )
    return new_settings


def restore_base_profile(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """보관해 둔 원본 설정으로 되돌린다.

    스냅샷이 없으면 **아무것도 하지 않는다**(임의의 기본값으로 덮어쓰면
    사용자가 손으로 맞춘 설정이 사라진다).

    Returns:
        새 settings dict (입력은 변경하지 않음)
    """
    current = dict(settings or {})
    snapshot = current.get(BASE_SNAPSHOT_KEY)

    if not snapshot:
        logger.info("[GP_ADSENSE] 복원할 스냅샷 없음 — 현재 설정 유지")
        return current

    new_settings = dict(current)
    for key in _PROFILE_KEYS:
        new_settings.pop(key, None)
    new_settings.update(copy.deepcopy(snapshot))
    new_settings.pop(BASE_SNAPSHOT_KEY, None)

    logger.info(
        "[GP_ADSENSE] 원본 프로파일 복원 | 복원된 프리셋=%s",
        new_settings.get("selectedPreset"),
    )
    return new_settings
