"""
Growth Profile 시스템 기본 프로파일 3종

코드에서 직접 관리 (DB 저장 아님).
사용자가 Growth Profile 생성 시 이 프로파일 중 하나를 선택하여 시작.

설계 문서: growth_stage_strategy_plan.md - Section 5-4, 8-4
"""
from typing import Dict, Any


def _make_schedule_matrix(
    weekday_start: int = 6,
    weekday_end: int = 21,
    weekend_start: int = 7,
    weekend_end: int = 20,
) -> list:
    """
    7x24 schedule_matrix 생성 헬퍼

    Args:
        weekday_start: 평일 활성 시작 시간
        weekday_end: 평일 활성 종료 시간
        weekend_start: 주말 활성 시작 시간
        weekend_end: 주말 활성 종료 시간

    Returns:
        bool[7][24] 배열 (월~일 x 0~23시)
    """
    matrix = []
    for day in range(7):
        if day < 5:  # 평일 (월~금)
            start, end = weekday_start, weekday_end
        else:  # 주말 (토~일)
            start, end = weekend_start, weekend_end
        row = [start <= h <= end for h in range(24)]
        matrix.append(row)
    return matrix


DEFAULT_PROFILES: Dict[str, Dict[str, Any]] = {
    "aggressive": {
        # 공격적 성장: 급성장기에 발행 빈도 극대화, 재고 넉넉하게 유지
        "schedule_matrix": _make_schedule_matrix(6, 22, 7, 21),
        "jitter": {"enabled": True, "min_percent": -15, "max_percent": 25},
        "stages": [
            {
                "name": "rapid_growth",
                "label": "급성장기",
                "post_count_min": 0,
                "post_count_max": 100,
                "generate": {
                    "enabled": True,
                    "min_inventory": 15,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 8,
                },
                "publish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 8,
                },
                "republish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 3,
                },
                "description": "빠른 콘텐츠 축적, 발행 빈도 극대화",
            },
            {
                "name": "growth",
                "label": "성장기",
                "post_count_min": 101,
                "post_count_max": 300,
                "generate": {
                    "enabled": True,
                    "min_inventory": 10,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 5,
                },
                "publish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 5,
                },
                "republish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 5,
                },
                "description": "꾸준한 성장, 발행과 재발행 균형",
            },
            {
                "name": "stable",
                "label": "안정기",
                "post_count_min": 301,
                "post_count_max": None,
                "generate": {
                    "enabled": True,
                    "min_inventory": 5,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 3,
                },
                "publish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 2,
                },
                "republish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 5,
                },
                "description": "유지보수, 재발행 비중 확대",
            },
        ],
        "warmup": {
            "enabled": True,
            "warmup_days": 14,
            "initial_daily_posts": 1,
            "max_daily_posts": 5,
            "ramp_rate": 0.5,
            "description": "신규 블로그 빠른 워밍업",
        },
    },

    "balanced": {
        # 균형 성장: 기본값. 작업계획서 Section 5-1의 JSON 구조 그대로
        "schedule_matrix": _make_schedule_matrix(6, 21, 7, 20),
        "jitter": {"enabled": True, "min_percent": -20, "max_percent": 30},
        "stages": [
            {
                "name": "rapid_growth",
                "label": "급성장기",
                "post_count_min": 0,
                "post_count_max": 50,
                "generate": {
                    "enabled": True,
                    "min_inventory": 10,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 5,
                },
                "publish": {
                    "enabled": True,
                    "interval_mode": "manual",
                    "interval_minutes": 120,
                    "daily_count": None,
                },
                "republish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 3,
                },
                "description": "빠른 콘텐츠 축적, 검색 노출 기반 구축",
            },
            {
                "name": "growth",
                "label": "성장기",
                "post_count_min": 51,
                "post_count_max": 150,
                "generate": {
                    "enabled": True,
                    "min_inventory": 5,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 3,
                },
                "publish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 2,
                },
                "republish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 3,
                },
                "description": "안정적 성장, 기존 글 최적화 병행",
            },
            {
                "name": "stable",
                "label": "안정기",
                "post_count_min": 151,
                "post_count_max": None,
                "generate": {
                    "enabled": True,
                    "min_inventory": 3,
                    "interval_mode": "manual",
                    "interval_minutes": 360,
                    "daily_count": None,
                },
                "publish": {
                    "enabled": False,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": None,
                },
                "republish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 2,
                },
                "description": "유지보수, 기존 콘텐츠 가치 극대화",
            },
        ],
        "warmup": {
            "enabled": True,
            "warmup_days": 14,
            "initial_daily_posts": 1,
            "max_daily_posts": 3,
            "ramp_rate": 0.5,
            "description": "신규 블로그 등록 후 워밍업 기간",
        },
    },

    "conservative": {
        # 보수적 운영: 안정적 운영 위주, 느린 생성
        "schedule_matrix": _make_schedule_matrix(8, 20, 9, 18),
        "jitter": {"enabled": True, "min_percent": -10, "max_percent": 20},
        "stages": [
            {
                "name": "rapid_growth",
                "label": "급성장기",
                "post_count_min": 0,
                "post_count_max": 50,
                "generate": {
                    "enabled": True,
                    "min_inventory": 5,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 2,
                },
                "publish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 2,
                },
                "republish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 2,
                },
                "description": "안정적 초기 성장",
            },
            {
                "name": "growth",
                "label": "성장기",
                "post_count_min": 51,
                "post_count_max": 200,
                "generate": {
                    "enabled": True,
                    "min_inventory": 3,
                    "interval_mode": "manual",
                    "interval_minutes": 360,
                    "daily_count": None,
                },
                "publish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 1,
                },
                "republish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 2,
                },
                "description": "보수적 성장, 재발행 비중 높임",
            },
            {
                "name": "stable",
                "label": "안정기",
                "post_count_min": 201,
                "post_count_max": None,
                "generate": {
                    "enabled": True,
                    "min_inventory": 2,
                    "interval_mode": "manual",
                    "interval_minutes": 480,
                    "daily_count": None,
                },
                "publish": {
                    "enabled": False,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": None,
                },
                "republish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 2,
                },
                "description": "유지보수 전용, 재발행 중심",
            },
        ],
        "warmup": {"enabled": False},
    },

    "adsense": {
        # 애드센스 승인용(F7): 승인 전 1일1포 저속 발행 + 재발행 억제.
        # 정보이득 지시문(Q-AdsenseGain)은 blog.adsense_status=preparing 시
        # 생성 단계에서 자동 주입됨(content_generator_helper). 승인 후엔
        # 운영자가 다른 프리셋(balanced 등)으로 전환한다.
        "schedule_matrix": _make_schedule_matrix(8, 20, 9, 18),
        "jitter": {"enabled": True, "min_percent": -10, "max_percent": 20},
        "stages": [
            {
                "name": "adsense_prep",
                "label": "애드센스 준비기",
                "post_count_min": 0,
                "post_count_max": None,
                "generate": {
                    "enabled": True,
                    "min_inventory": 3,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 1,
                },
                "publish": {
                    "enabled": True,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": 1,
                },
                "republish": {
                    "enabled": False,
                    "interval_mode": "auto",
                    "interval_minutes": None,
                    "daily_count": None,
                },
                "description": "승인 전 1일1포·재발행 억제(scaled content abuse 회피)",
            },
        ],
        "warmup": {"enabled": False},
    },
}


def get_default_profile(profile_key: str = "balanced") -> dict:
    """
    기본 프로파일 반환

    Args:
        profile_key: "aggressive" | "balanced" | "conservative"

    Returns:
        Module.settings에 저장할 완전한 dict

    Raises:
        KeyError: 존재하지 않는 프로파일 키
    """
    if profile_key not in DEFAULT_PROFILES:
        raise KeyError(
            f"Unknown profile: '{profile_key}'. "
            f"Available: {list(DEFAULT_PROFILES.keys())}"
        )
    import copy
    return copy.deepcopy(DEFAULT_PROFILES[profile_key])


def get_available_profiles() -> list:
    """
    사용 가능한 프로파일 목록 반환 (UI 선택용)

    Returns:
        [{"key": "aggressive", "name": "공격적 성장", "description": "..."}, ...]
    """
    descriptions = {
        "aggressive": ("공격적 성장", "급성장기에 발행 빈도 극대화, 재고 넉넉하게 유지"),
        "balanced": ("균형 성장", "균형 잡힌 기본 설정, 단계별 최적화"),
        "conservative": ("보수적 운영", "안정적 운영 위주, 느린 생성"),
        "adsense": ("애드센스 승인용", "승인 전 1일1포·재발행 억제 + 정보이득 프롬프트"),
    }
    return [
        {
            "key": key,
            "name": descriptions[key][0],
            "description": descriptions[key][1],
            "stages_count": len(profile["stages"]),
        }
        for key, profile in DEFAULT_PROFILES.items()
    ]
