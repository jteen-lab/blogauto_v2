# Growth Profile - Phase A 구현 프롬프트

> **Phase**: A (기반 구조 - 코어)
> **설계 문서**: growth_stage_strategy_plan.md v3.1
> **작성일**: 2026-02-20
> **상태**: 구현 대기

---

## 개요

Phase A는 Growth Profile 모듈의 핵심 데이터 구조와 로직을 구현합니다.
이 Phase에서 만들어진 코드는 Phase B 이후에서 Flow 실행에 주입됩니다.

**Phase A에서는 DB 변경이 없습니다.** Module.settings JSONB에 저장하므로 Alembic 마이그레이션 불필요.

---

## 생성/수정 파일 목록

| # | 파일 경로 | 타입 | 예상 줄 수 | 설명 |
|---|----------|------|-----------|------|
| 1 | `app/models/module_type.py` | 수정 | +6줄 | growth_profile 타입 seed 추가 |
| 2 | `app/services/generation/flow_execution_context.py` | 신규 | ~120줄 | 데이터클래스 3종 |
| 3 | `app/services/generation/growth_profile_defaults.py` | 신규 | ~120줄 | 기본 프로파일 3종 |
| 4 | `app/services/generation/growth_profile_resolver.py` | 신규 | ~180줄 | 핵심 로직 |
| 5 | `app/services/generation/__init__.py` | 수정 | +10줄 | Phase A export 추가 |
| 6 | `tests/integration/test_growth_profile_resolver.py` | 신규 | ~300줄 | 테스트 30개 |

---

## 파일 1: module_type.py 수정

### 경로: `app/models/module_type.py`

### 변경 내용

`get_default_types()` 메서드(35줄)의 반환 리스트 **맨 앞**에 growth_profile 추가.
`display_order: 0`으로 가장 먼저 표시.

### 추가할 코드

```python
# get_default_types() 반환 리스트의 첫 번째 항목으로 추가
{
    "code": "growth_profile",
    "name": "성장 프로파일",
    "icon": "📈",
    "display_order": 0
},
```

### 동작 원리

`main.py`의 `seed_module_types()` 함수가 앱 시작 시 `get_default_types()`를 호출하여 DB에 없는 타입을 자동 삽입합니다. 별도 SQL 실행 불필요.

---

## 파일 2: flow_execution_context.py (신규)

### 경로: `app/services/generation/flow_execution_context.py`
### 예상 줄 수: ~120줄

### 설계 출처: 작업계획서 Section 6-2, Section 8-3

### 전체 구조

```python
"""
Growth Profile 실행 컨텍스트

Flow 실행 시 메모리에서만 사용되는 임시 객체.
DB에 저장하지 않으며, Flow 실행이 끝나면 폐기됨.

설계 문서: growth_stage_strategy_plan.md - Section 6-2, 8-3
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)
```

### 데이터클래스 1: ModuleIntervalParams

```python
@dataclass
class ModuleIntervalParams:
    """
    개별 모듈(generate/publish/republish)의 간격 파라미터

    Attributes:
        enabled: 이 구간에서 모듈 활성화 여부
        interval_mode: "manual" 또는 "auto" (enabled=false면 None)
        interval_minutes: manual 모드 시 분 단위 간격
        daily_count: auto 모드 시 하루 목표 횟수
        computed_interval: 최종 계산된 간격(분). auto면 시스템이 계산
        min_inventory: generate 전용. 최소 보유 포스트 수
    """
    enabled: bool
    interval_mode: Optional[str] = None
    interval_minutes: Optional[int] = None
    daily_count: Optional[int] = None
    computed_interval: Optional[int] = None
    min_inventory: Optional[int] = None

    @classmethod
    def from_stage_dict(
        cls,
        module_dict: dict,
        active_hours: int = 16
    ) -> "ModuleIntervalParams":
        """
        stages[n].generate/publish/republish dict에서 생성

        Args:
            module_dict: {"enabled": true, "interval_mode": "auto", ...}
            active_hours: schedule_matrix에서 계산된 오늘 활성 시간 수

        Returns:
            ModuleIntervalParams 인스턴스 (computed_interval 계산 완료)
        """
        enabled = module_dict.get("enabled", False)

        if not enabled:
            return cls(enabled=False)

        interval_mode = module_dict.get("interval_mode")
        interval_minutes = module_dict.get("interval_minutes")
        daily_count = module_dict.get("daily_count")
        min_inventory = module_dict.get("min_inventory")

        # computed_interval 계산
        computed_interval = None
        if interval_mode == "manual" and interval_minutes:
            computed_interval = interval_minutes
        elif interval_mode == "auto" and daily_count:
            active_minutes = active_hours * 60
            computed_interval = max(5, int(active_minutes / daily_count))

        return cls(
            enabled=True,
            interval_mode=interval_mode,
            interval_minutes=interval_minutes,
            daily_count=daily_count,
            computed_interval=computed_interval,
            min_inventory=min_inventory,
        )
```

**핵심 포인트:**
- `computed_interval` 계산 시 `active_hours * 60 / daily_count` 사용 (24시간 고정 금지)
- `enabled=false`면 나머지 필드 모두 무시 (None 반환)
- `max(5, ...)`: 최소 5분 보장 (daily_count가 극단적으로 큰 경우)

### 데이터클래스 2: StageParams

```python
@dataclass
class StageParams:
    """
    블로그에 적용된 성장 단계 파라미터

    Attributes:
        stage_name: 스테이지 고유 이름 (예: "rapid_growth")
        stage_label: 사용자 표시용 (예: "급성장기")
        generate: 생성 모듈 간격 파라미터
        publish: 발행 모듈 간격 파라미터
        republish: 재발행 모듈 간격 파라미터
    """
    stage_name: str
    stage_label: str
    generate: ModuleIntervalParams
    publish: ModuleIntervalParams
    republish: ModuleIntervalParams

    @classmethod
    def from_stage_dict(
        cls,
        stage_dict: dict,
        active_hours: int = 16
    ) -> "StageParams":
        """
        stages 배열의 단일 항목에서 생성

        Args:
            stage_dict: stages[n] 전체 dict
            active_hours: 오늘 활성 시간 수 (auto 간격 계산용)
        """
        return cls(
            stage_name=stage_dict["name"],
            stage_label=stage_dict["label"],
            generate=ModuleIntervalParams.from_stage_dict(
                stage_dict.get("generate", {"enabled": False}),
                active_hours
            ),
            publish=ModuleIntervalParams.from_stage_dict(
                stage_dict.get("publish", {"enabled": False}),
                active_hours
            ),
            republish=ModuleIntervalParams.from_stage_dict(
                stage_dict.get("republish", {"enabled": False}),
                active_hours
            ),
        )
```

### 데이터클래스 3: FlowExecutionContext

```python
@dataclass
class FlowExecutionContext:
    """
    Flow 실행 시 공유되는 컨텍스트 (메모리 전용, DB 저장 없음)

    Attributes:
        flow_id: Flow ID
        growth_profile: Growth Profile 모듈의 settings 원본 dict
        schedule_matrix: 7x24 활성 시간대 매트릭스
        jitter: 지터 설정 dict {"enabled": bool, "min_percent": int, "max_percent": int}
        blog_stages: {blog_id: StageParams} 매핑
    """
    flow_id: int
    growth_profile: Optional[dict] = None
    schedule_matrix: Optional[list] = None
    jitter: Optional[dict] = None
    blog_stages: Dict[int, StageParams] = field(default_factory=dict)

    def get_stage_for_blog(self, blog_id: int) -> Optional[StageParams]:
        """블로그 ID에 해당하는 스테이지 파라미터 반환"""
        return self.blog_stages.get(blog_id)

    def has_growth_profile(self) -> bool:
        """Growth Profile이 설정되어 있는지 확인"""
        return self.growth_profile is not None

    def is_active_time(self, weekday: int, hour: int) -> bool:
        """
        현재 시간이 활성 시간대인지 확인

        Args:
            weekday: 0=월요일, 6=일요일
            hour: 0~23

        Returns:
            True=활성, False=비활성
            schedule_matrix 미설정 시 항상 True (기본 활성)
        """
        if self.schedule_matrix is None:
            return True
        if not isinstance(self.schedule_matrix, list) or len(self.schedule_matrix) != 7:
            return True
        day_schedule = self.schedule_matrix[weekday]
        if not isinstance(day_schedule, list) or len(day_schedule) != 24:
            return True
        return day_schedule[hour]
```

---

## 파일 3: growth_profile_defaults.py (신규)

### 경로: `app/services/generation/growth_profile_defaults.py`
### 예상 줄 수: ~120줄

### 설계 출처: 작업계획서 Section 5-1, 5-4, 8-4

### 전체 구조

```python
"""
Growth Profile 시스템 기본 프로파일 3종

코드에서 직접 관리 (DB 저장 아님).
사용자가 Growth Profile 생성 시 이 프로파일 중 하나를 선택하여 시작.

설계 문서: growth_stage_strategy_plan.md - Section 5-4, 8-4
"""
from typing import Dict, Any
```

### 공통 schedule_matrix 생성 헬퍼

```python
def _make_schedule_matrix(
    weekday_start: int = 6,
    weekday_end: int = 21,
    weekend_start: int = 7,
    weekend_end: int = 20,
) -> list:
    """
    7x24 schedule_matrix 생성 헬퍼

    Args:
        weekday_start/end: 평일 활성 시작/종료 시간
        weekend_start/end: 주말 활성 시작/종료 시간

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
```

### DEFAULT_PROFILES 딕셔너리

3종의 프로파일을 정의합니다. 각 프로파일은 Module.settings에 저장될 완전한 JSON 구조입니다.

```python
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
```

---

## 파일 4: growth_profile_resolver.py (신규)

### 경로: `app/services/generation/growth_profile_resolver.py`
### 예상 줄 수: ~180줄

### 설계 출처: 작업계획서 Section 6-1, 6-2, 6-3, 6-4, Phase A 완료 기준

### 기존 코드 재사용 참조

| 기존 코드 | 위치 | Phase A에서의 사용 |
|----------|------|------------------|
| `FlowExecutionState.calculate_next_execution()` | `flow_execution_state.py:139-184` | jitter 적용 + schedule_matrix 보정. GrowthProfileResolver에서 직접 호출 |
| `FlowExecutionState.is_in_active_window()` | `flow_execution_state.py:235-251` | 현재 시간 활성 여부 체크. 동일 로직을 FlowExecutionContext.is_active_time()으로 위임 |
| `FlowExecutionState._adjust_to_active_window()` | `flow_execution_state.py:186-233` | 비활성→다음 활성 슬롯 보정 |
| `form.js calculateFromDailyCount()` | `form.js:359-368` | auto 간격 = active_hours * 60 / daily_count (올바른 구현 참조) |

> **중요**: GrowthProfileResolver는 위 기존 로직의 **상위 조율자**입니다. jitter/schedule_matrix 처리를 중복 구현하지 않고, FlowExecutionState 메서드를 활용합니다.

### 전체 구조

```python
"""
Growth Profile Resolver

블로그 포스트 수 → 성장 단계 매핑, 모듈별 간격 계산, 활성 시간 체크.
Phase B에서 Flow 실행 시 Step 0으로 호출됨.

설계 문서: growth_stage_strategy_plan.md - Section 6
"""
import logging
from datetime import datetime
from typing import Optional, List, Tuple

from .flow_execution_context import (
    FlowExecutionContext,
    StageParams,
    ModuleIntervalParams,
)

logger = logging.getLogger(__name__)
```

### 메서드 1: validate_stages

```python
@staticmethod
def validate_stages(stages: list) -> Tuple[bool, Optional[str]]:
    """
    stages 배열의 유효성 검증

    검증 항목:
    1. stages가 비어있지 않은지
    2. 각 stage에 필수 필드(name, label, post_count_min)가 있는지
    3. post_count_min이 오름차순인지
    4. 연속성: 이전 stage의 post_count_max + 1 == 다음 stage의 post_count_min
    5. 겹침 없음: 이전 max < 다음 min
    6. 마지막 stage의 post_count_max는 None(무제한) 허용

    Args:
        stages: settings["stages"] 배열

    Returns:
        (True, None) 또는 (False, "에러 메시지")
    """
    if not stages:
        return False, "stages 배열이 비어있습니다"

    required_fields = ["name", "label", "post_count_min"]

    for i, stage in enumerate(stages):
        # 필수 필드 체크
        for field in required_fields:
            if field not in stage:
                return False, f"stage[{i}]에 '{field}' 필드가 없습니다"

        # 첫 번째 stage 검증
        if i == 0:
            if stage["post_count_min"] != 0:
                return False, f"첫 번째 stage의 post_count_min은 0이어야 합니다 (현재: {stage['post_count_min']})"

        # 연속성 검증 (두 번째 stage부터)
        if i > 0:
            prev_max = stages[i - 1].get("post_count_max")
            curr_min = stage["post_count_min"]

            if prev_max is None:
                return False, f"stage[{i-1}]의 post_count_max가 None인데 다음 stage가 존재합니다"

            expected_min = prev_max + 1
            if curr_min != expected_min:
                return False, (
                    f"stage[{i}]의 post_count_min({curr_min})이 "
                    f"이전 stage의 post_count_max({prev_max}) + 1 = {expected_min}과 다릅니다"
                )

    return True, None
```

### 메서드 2: count_active_hours

```python
@staticmethod
def count_active_hours(schedule_matrix: Optional[list], weekday: int = None) -> int:
    """
    schedule_matrix에서 특정 요일(또는 오늘)의 활성 시간 수 계산

    Args:
        schedule_matrix: 7x24 bool 배열
        weekday: 0=월~6=일. None이면 오늘 요일 사용

    Returns:
        활성 시간 수 (0~24). schedule_matrix가 None이면 24 반환
    """
    if schedule_matrix is None:
        return 24

    if weekday is None:
        weekday = datetime.now().weekday()

    if (
        not isinstance(schedule_matrix, list)
        or len(schedule_matrix) != 7
        or not isinstance(schedule_matrix[weekday], list)
        or len(schedule_matrix[weekday]) != 24
    ):
        return 24

    return sum(1 for h in schedule_matrix[weekday] if h)
```

### 메서드 3: resolve_stage_for_blog

```python
@staticmethod
def resolve_stage_for_blog(
    post_count: int,
    stages: list,
) -> Optional[dict]:
    """
    블로그의 포스트 수로 적절한 성장 단계(stage) 결정

    경계값 규칙 (작업계획서 Q3):
        post_count_max는 inclusive.
        50글 = 해당 스테이지, 51글 = 다음 스테이지.

    Args:
        post_count: 블로그의 현재 누적 포스트 수
        stages: settings["stages"] 배열

    Returns:
        매칭된 stage dict. 매칭 실패 시 마지막 stage 반환.

    예시:
        stages = [{min:0, max:50}, {min:51, max:150}, {min:151, max:None}]
        post_count=50  -> stages[0] (inclusive)
        post_count=51  -> stages[1]
        post_count=999 -> stages[2] (max=None이므로)
    """
    if not stages:
        return None

    for stage in stages:
        stage_min = stage.get("post_count_min", 0)
        stage_max = stage.get("post_count_max")

        if stage_max is None:
            # 마지막 구간 (무제한)
            if post_count >= stage_min:
                return stage
        else:
            # post_count_max inclusive
            if stage_min <= post_count <= stage_max:
                return stage

    # 어떤 구간에도 매칭되지 않으면 마지막 구간 적용
    logger.warning(
        f"[GP_RESOLVE] post_count={post_count}가 어떤 구간에도 매칭되지 않음. "
        f"마지막 구간 적용"
    )
    return stages[-1]
```

### 메서드 4: build_execution_context

```python
@classmethod
def build_execution_context(
    cls,
    flow_id: int,
    gp_settings: dict,
    blog_post_counts: dict,
) -> FlowExecutionContext:
    """
    Flow 실행 시 FlowExecutionContext 생성 (Phase B의 Step 0에서 호출)

    Args:
        flow_id: Flow ID
        gp_settings: Growth Profile 모듈의 settings dict
        blog_post_counts: {blog_id: post_count} 매핑

    Returns:
        FlowExecutionContext (blog_stages 매핑 완료)

    사용 예:
        context = GrowthProfileResolver.build_execution_context(
            flow_id=1,
            gp_settings=module.settings,
            blog_post_counts={10: 30, 20: 100, 30: 200}
        )
    """
    schedule_matrix = gp_settings.get("schedule_matrix")
    jitter = gp_settings.get("jitter")
    stages = gp_settings.get("stages", [])

    # stages 유효성 검증
    valid, error = cls.validate_stages(stages)
    if not valid:
        logger.error(f"[GP_RESOLVE] stages 검증 실패: {error}")
        raise ValueError(f"Growth Profile stages 검증 실패: {error}")

    # 오늘의 활성 시간 수 계산
    active_hours = cls.count_active_hours(schedule_matrix)

    # 각 블로그에 대해 스테이지 매핑
    blog_stages = {}
    for blog_id, post_count in blog_post_counts.items():
        stage_dict = cls.resolve_stage_for_blog(post_count, stages)
        if stage_dict:
            blog_stages[blog_id] = StageParams.from_stage_dict(
                stage_dict, active_hours
            )
            logger.info(
                f"[GP_RESOLVE] blog_id={blog_id} | posts={post_count} "
                f"| stage={stage_dict['name']} "
                f"| gen={blog_stages[blog_id].generate.computed_interval}min "
                f"| pub={blog_stages[blog_id].publish.computed_interval}min "
                f"| rep={blog_stages[blog_id].republish.computed_interval}min"
            )

    context = FlowExecutionContext(
        flow_id=flow_id,
        growth_profile=gp_settings,
        schedule_matrix=schedule_matrix,
        jitter=jitter,
        blog_stages=blog_stages,
    )

    logger.info(
        f"[GP_RESOLVE] context 생성 완료 | flow_id={flow_id} "
        f"| blogs={len(blog_stages)} | active_hours={active_hours}"
    )

    return context
```

---

## 파일 5: __init__.py 수정

### 경로: `app/services/generation/__init__.py`

### 추가할 내용

```python
# 기존 import 아래에 추가

# Growth Profile (Phase A)
from .flow_execution_context import (
    FlowExecutionContext,
    StageParams,
    ModuleIntervalParams,
)
from .growth_profile_resolver import GrowthProfileResolver
from .growth_profile_defaults import (
    DEFAULT_PROFILES,
    get_default_profile,
    get_available_profiles,
)

# __all__에 추가
__all__ = [
    # ... 기존 유지 ...
    # Growth Profile (Phase A)
    "FlowExecutionContext",
    "StageParams",
    "ModuleIntervalParams",
    "GrowthProfileResolver",
    "DEFAULT_PROFILES",
    "get_default_profile",
    "get_available_profiles",
]
```

---

## 파일 6: 테스트

### 경로: `tests/integration/test_growth_profile_resolver.py`
### 예상 줄 수: ~250줄

### 테스트 목록 (30개)

#### 클래스 1: TestResolveStageForBlog (스테이지 매핑)

| ID | 메서드명 | 시나리오 | 입력 | 기대 |
|----|---------|---------|------|------|
| T01 | `test_rapid_growth_stage` | 급성장기 매핑 | post_count=30, stages=[0~50, 51~150, 151~null] | stage_name="rapid_growth" |
| T02 | `test_growth_stage` | 성장기 매핑 | post_count=100 | stage_name="growth" |
| T03 | `test_stable_stage` | 안정기 매핑 | post_count=200 | stage_name="stable" |
| T04 | `test_boundary_inclusive_max` | 경계값 max inclusive | post_count=50, max=50 | stage_name="rapid_growth" |
| T05 | `test_boundary_next_stage` | 경계값 전환 | post_count=51, 다음 min=51 | stage_name="growth" |
| T06 | `test_last_stage_null_max` | 마지막 null max | post_count=9999, max=null | 마지막 스테이지 |
| T07 | `test_zero_posts` | 포스트 0건 | post_count=0, min=0 | 첫 스테이지 |
| T08 | `test_single_stage` | 단일 구간 | post_count=100, stages=[0~null] | 해당 스테이지 |

#### 클래스 2: TestComputeInterval (간격 계산)

| ID | 메서드명 | 시나리오 | 입력 | 기대 |
|----|---------|---------|------|------|
| T09 | `test_manual_mode` | manual 간격 | mode="manual", interval_minutes=120 | computed=120 |
| T10 | `test_auto_mode_active_hours` | auto 활성시간 기반 | mode="auto", daily_count=5, active_hours=16 | computed=192 |
| T11 | `test_auto_mode_different_hours` | auto 다른 활성시간 | mode="auto", daily_count=3, active_hours=12 | computed=240 |
| T12 | `test_auto_mode_minimum_5min` | auto 최소값 보장 | mode="auto", daily_count=200, active_hours=16 | computed=5 (max(5, 4.8)) |
| T13 | `test_disabled_module` | enabled=false 무시 | enabled=false | computed=None |

#### 클래스 3: TestActiveHours (활성 시간 체크)

| ID | 메서드명 | 시나리오 | 입력 | 기대 |
|----|---------|---------|------|------|
| T14 | `test_active_hour_true` | 활성 시간 | matrix[0][10]=true, weekday=0, hour=10 | True |
| T15 | `test_inactive_hour_false` | 비활성 시간 | matrix[0][3]=false, weekday=0, hour=3 | False |
| T16 | `test_no_matrix_always_active` | matrix=None | matrix=None | True |
| T17 | `test_count_active_hours` | 활성 시간 수 | 6~21시 활성 (16시간) | 16 |

#### 클래스 4: TestValidateStages (연속성 검증)

| ID | 메서드명 | 시나리오 | 입력 | 기대 |
|----|---------|---------|------|------|
| T18 | `test_valid_continuous_stages` | 정상 연속 | [0~50, 51~150, 151~null] | (True, None) |
| T19 | `test_gap_detection` | 빈 범위 감지 | [0~50, 52~150] | (False, 에러) |
| T20 | `test_overlap_detection` | 겹침 감지 | [0~50, 50~150] | (False, 에러) |
| T21 | `test_empty_stages` | 빈 배열 | [] | (False, 에러) |
| T22 | `test_single_stage_valid` | 단일 구간 | [0~null] | (True, None) |

#### 클래스 5: TestDefaultProfiles (기본 프로파일)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T23 | `test_all_profiles_exist` | 3종 존재 확인 | aggressive, balanced, conservative 키 존재 |
| T24 | `test_profiles_stages_valid` | 각 프로파일 stages 연속성 | validate_stages 통과 |
| T25 | `test_profiles_schedule_matrix_shape` | matrix 형태 검증 | 7x24 배열 |

#### 클래스 6: TestBuildExecutionContext (통합 테스트)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T26 | `test_build_context_multiple_blogs` | 블로그 3개 (30글, 100글, 200글) | blog_stages에 3개 StageParams, 각각 올바른 스테이지 |
| T27 | `test_build_context_invalid_stages` | stages 배열 빈 구간 | ValueError 발생 |

#### 클래스 7: TestHelperFunctions (유틸리티 함수)

| ID | 메서드명 | 시나리오 | 기대 |
|----|---------|---------|------|
| T28 | `test_get_default_profile_invalid_key` | 존재하지 않는 프로파일 키 | KeyError 발생 |
| T29 | `test_count_active_hours_no_matrix` | schedule_matrix=None | 24 반환 |
| T30 | `test_validate_stages_first_min_not_zero` | 첫 stage의 min=5 (0이 아님) | (False, 에러) |

### 테스트 실행 명령

```bash
cd /home/jteen/blogauto_v2/services/republish
python3 -m pytest tests/integration/test_growth_profile_resolver.py -v
```

---

## 기존 코드 버그 수정 (Phase A 범위)

### Module.calculated_interval_minutes 버그

- **파일**: `app/models/module.py:84-88`
- **현재 코드**: `return max(5, int(1440 / self.auto_daily_count))` (24시간 = 1440분 고정)
- **문제**: 활성 시간대를 무시하고 24시간 기준으로 계산
- **Phase A 결정**: 이 버그는 Phase A에서 수정하지 않음. 이유:
  - GrowthProfileResolver는 자체적으로 `active_hours * 60 / daily_count`로 계산
  - 기존 모듈(republish 등)은 아직 Module.calculated_interval_minutes를 사용 중
  - Phase C에서 개별 모듈 스케줄러 제거 시 함께 수정

---

## 구현 순서

```
1. flow_execution_context.py    (의존성 없음, 독립 구현)
2. growth_profile_defaults.py   (의존성 없음, 독립 구현)
3. growth_profile_resolver.py   (1, 2에 의존)
4. module_type.py 수정           (독립)
5. __init__.py 수정              (1, 2, 3 완료 후)
6. 테스트 작성 및 실행           (1~5 완료 후)
```

**1, 2, 4는 병렬 구현 가능.**

---

## 완료 기준 체크리스트

- [ ] `flow_execution_context.py` 생성 완료 (~120줄)
- [ ] `growth_profile_defaults.py` 생성 완료 (~120줄)
- [ ] `growth_profile_resolver.py` 생성 완료 (~180줄)
- [ ] `module_type.py`에 growth_profile 타입 추가
- [ ] `__init__.py`에 Phase A export 추가
- [ ] 테스트 30개 작성 및 전체 통과
- [ ] 각 파일 500줄 미만 확인
- [ ] 각 함수 50줄 미만 확인
- [ ] 타입 힌트 전수 적용
- [ ] Docstring 전수 작성
- [ ] 로깅 `[GP_RESOLVE]` 프리픽스 적용
