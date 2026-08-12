"""F4 — 니치(주제) 강제 판정 순수 로직.

인벤토리 선택 시 애드센스 준비 블로그를 단일 니치 topic으로 제한(옵트인 차단).
DB 의존 없는 순수 함수만 두어 단위테스트가 쉽고, inventory_trigger 크기를
줄인다.
"""
from typing import List, Optional

# 니치 강제 대상 상태(옵트인 차단). preparing 블로그만 니치 topic으로 제한한다.
ADSENSE_NICHE_STATUSES = ("preparing",)


def resolve_adsense_niche(adsense_status, niche_topic_ids) -> Optional[List[int]]:
    """니치 강제가 적용되는 경우 허용 topic_id 목록 반환, 아니면 None.

    preparing 상태 + niche_topic_ids 값이 있을 때만 강제(옵트인 차단).
    그 외(none/applied/approved/rejected, 니치 미설정)는 None → 기존 동작.
    """
    if adsense_status not in ADSENSE_NICHE_STATUSES:
        return None
    ids = [int(x) for x in (niche_topic_ids or []) if x is not None]
    return ids or None
