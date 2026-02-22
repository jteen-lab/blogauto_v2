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
