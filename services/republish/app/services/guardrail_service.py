"""
섹션 기반 가드레일 서비스

Features:
- 섹션 위계 정의 (collect → utility → control → deploy)
- 섹션 간 순서 변경 제한
- 섹션 내 순서 변경 허용
- 엔진 실행 시 순서 검증
"""
from typing import Optional


# 섹션 위계 정의 (순서: 낮은 값이 먼저 실행)
SECTION_HIERARCHY = {
    "collect": 1,      # 데이터 수집
    "utility": 2,      # 유틸리티 (가공)
    "control": 3,      # 실행 제어
    "deploy": 4,       # 배포 및 기록
    "template": 99,    # 템플릿 (UI용, 실행 대상 아님)
}

# 섹션 한글 이름
SECTION_NAMES = {
    "collect": "수집",
    "utility": "유틸리티",
    "control": "제어",
    "deploy": "배포",
    "template": "템플릿",
}


def get_section_order(category: str) -> int:
    """섹션의 위계 순서 반환"""
    return SECTION_HIERARCHY.get(category, 50)


def get_section_name(category: str) -> str:
    """섹션의 한글 이름 반환"""
    return SECTION_NAMES.get(category, category)


def can_move_module(
    moving_category: str,
    target_position_category: Optional[str],
    direction: str  # "up" or "down"
) -> tuple[bool, str]:
    """
    모듈 이동 가능 여부 확인

    Args:
        moving_category: 이동하려는 모듈의 카테고리
        target_position_category: 이동 후 위치할 자리의 인접 모듈 카테고리
        direction: 이동 방향 ("up" or "down")

    Returns:
        (이동 가능 여부, 메시지)
    """
    if target_position_category is None:
        return True, ""

    moving_order = get_section_order(moving_category)
    target_order = get_section_order(target_position_category)

    # 같은 섹션 내 이동은 항상 허용
    if moving_category == target_position_category:
        return True, ""

    # 위로 이동 시: 더 높은 위계(낮은 번호) 섹션 위로 갈 수 없음
    if direction == "up":
        if moving_order > target_order:
            return False, (
                f"'{get_section_name(moving_category)}' 모듈은 "
                f"'{get_section_name(target_position_category)}' 섹션 위로 이동할 수 없습니다."
            )

    # 아래로 이동 시: 더 낮은 위계(높은 번호) 섹션 아래로 갈 수 없음
    if direction == "down":
        if moving_order < target_order:
            return False, (
                f"'{get_section_name(moving_category)}' 모듈은 "
                f"'{get_section_name(target_position_category)}' 섹션 아래로 이동할 수 없습니다."
            )

    return True, ""


def validate_module_order(modules: list[dict]) -> tuple[bool, list[str]]:
    """
    모듈 순서의 섹션 위계 준수 여부 검증

    Args:
        modules: [{"category": str, "execution_order": int, "name": str}, ...]

    Returns:
        (유효 여부, 경고 메시지 목록)
    """
    warnings = []

    if not modules:
        return True, warnings

    # 실행 순서대로 정렬
    sorted_modules = sorted(modules, key=lambda m: m.get("execution_order", 0))

    prev_section_order = 0
    prev_category = None

    for module in sorted_modules:
        category = module.get("category", "")
        current_order = get_section_order(category)

        # 섹션 위계가 역전되는 경우 경고
        if current_order < prev_section_order and prev_category != category:
            warnings.append(
                f"'{get_section_name(category)}' 모듈({module.get('name', '')})이 "
                f"'{get_section_name(prev_category)}' 모듈보다 먼저 실행됩니다. "
                f"권장 순서: {get_section_name(prev_category)} → {get_section_name(category)}"
            )

        prev_section_order = current_order
        prev_category = category

    return len(warnings) == 0, warnings


def get_recommended_insertion_order(
    existing_modules: list[dict],
    new_module_category: str
) -> int:
    """
    새 모듈의 권장 삽입 위치 계산

    Args:
        existing_modules: 기존 모듈 목록
        new_module_category: 새 모듈의 카테고리

    Returns:
        권장 execution_order 값
    """
    if not existing_modules:
        return 1

    new_section_order = get_section_order(new_module_category)

    # 같은 섹션 또는 더 낮은 위계 섹션의 마지막 모듈 찾기
    insert_after = 0

    for module in sorted(existing_modules, key=lambda m: m.get("execution_order", 0)):
        module_section_order = get_section_order(module.get("category", ""))

        if module_section_order <= new_section_order:
            insert_after = module.get("execution_order", 0)

    return insert_after + 1


def sort_modules_by_section(modules: list[dict]) -> list[dict]:
    """
    모듈을 섹션 위계 및 execution_order에 따라 정렬

    섹션 위계 우선, 같은 섹션 내에서는 execution_order 순서 유지

    Args:
        modules: 정렬할 모듈 목록

    Returns:
        정렬된 모듈 목록
    """
    return sorted(
        modules,
        key=lambda m: (
            get_section_order(m.get("category", "")),
            m.get("execution_order", 0)
        )
    )
