"""F4 — 니치(주제) 강제 판정 순수 로직.

인벤토리 선택 시 프롬프트 모듈을 단일 니치 topic으로 제한(옵트인 차단).
DB 의존 없는 순수 함수만 두어 단위테스트가 쉽고, inventory_trigger 크기를
줄인다.

2026-08-16: 블로그 단위(`Blog.adsense_status`/`niche_topic_ids`)에서 **모듈
단위**(프롬프트 모듈 `settings`)로 이전. 애드센스 승인용 모듈과 일반 모듈을
같은 블로그에서 통합/분리 사용하기 위함. 순서도
`docs/flowcharts/adsense_module_ui_migration.md`.
"""
from typing import Any, Dict, List, Optional


def resolve_module_niche(module_settings: Optional[Dict[str, Any]]) -> Optional[List[int]]:
    """프롬프트 모듈 settings 기준 니치 강제 topic 목록 반환, 아니면 None.

    ``niche_enabled`` 토글이 켜지고 ``niche_topic_ids``가 있을 때만 강제한다
    (옵트인 차단). 그 외(토글 꺼짐·미설정)는 None → 기존 카테고리 필터 유지.

    Args:
        module_settings: 프롬프트 모듈 settings dict (없으면 None)

    Returns:
        강제 시 허용 topic_id 목록(int 정규화, None 제거), 아니면 None
    """
    if not module_settings:
        return None
    if not module_settings.get("niche_enabled"):
        return None
    ids = [int(x) for x in (module_settings.get("niche_topic_ids") or []) if x is not None]
    return ids or None
