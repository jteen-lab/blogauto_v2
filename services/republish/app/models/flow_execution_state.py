"""
플로우 실행 상태 모델

Features:
- 플로우별/액션별 실행 상태 추적
- 마지막 실행 시간 및 다음 실행 예정 시간
- 일시정지 시 남은 시간 보존
- 활성화 시간대 내 실행 제어

action_type 값:
- "generate": 글 생성
- "publish": 발행
- "republish": 재발행
- "collect": 수집
- "data": 데이터
"""
from datetime import datetime
from typing import Optional
import pytz
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base
from ..core.logger import get_logger

logger = get_logger("flow_execution_state", "republish.log")

# Timezone 설정
KST = pytz.timezone('Asia/Seoul')

# 좀비 실행 판정 기준 (분)
ZOMBIE_TIMEOUT_MINUTES = 30

# 스케줄 안전 상수
MIN_EXECUTION_GAP = 60          # 최소 실행 간격 (초)
MIN_CHECK_INTERVAL = 600        # 재고 부족 시 재체크 간격 (초, 10분)
MAX_SCHEDULE_SEARCH_DAYS = 14   # 활성 시간대 탐색 최대 일수


class FlowExecutionState(Base):
    """플로우 실행 상태 - 액션 타입별 실행 추적"""
    __tablename__ = "flow_execution_states"
    __table_args__ = (
        Index(
            'ix_fes_flow_action_blog',
            'flow_id', 'action_type', 'blog_id',
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    flow_id = Column(
        Integer,
        ForeignKey("flows.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    action_type = Column(
        String(30),
        nullable=False,
        index=True,
        comment="액션 타입 (generate/publish/republish/collect/data)"
    )
    blog_id = Column(
        Integer,
        ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="블로그별 간격 추적용 (nullable: 블로그 무관 액션)"
    )

    # 실행 상태 추적
    last_executed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="마지막 실행 시간"
    )
    last_success_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="마지막 성공 시점"
    )
    next_execution_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="다음 예정 실행 시간"
    )

    # 일시정지 관련
    is_paused = Column(
        Boolean,
        default=False,
        comment="일시정지 상태"
    )
    paused_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="일시정지 시작 시간"
    )
    remaining_seconds = Column(
        Integer,
        nullable=True,
        comment="일시정지 시 남은 시간(초)"
    )

    # 실행 통계
    total_executions = Column(
        Integer,
        default=0,
        comment="총 실행 횟수"
    )
    successful_executions = Column(
        Integer,
        default=0,
        comment="성공 횟수"
    )
    failed_executions = Column(
        Integer,
        default=0,
        comment="실패 횟수"
    )
    consecutive_failures = Column(
        Integer,
        default=0,
        comment="연속 실패 횟수 (성공 시 0으로 리셋)"
    )

    # 동시 실행 가드
    is_running = Column(
        Boolean,
        default=False,
        comment="현재 실행 중 여부"
    )
    last_execution_started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="마지막 실행 시작 시간"
    )

    # 메타
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # 관계
    flow = relationship("Flow", backref="execution_states")
    blog = relationship("Blog")

    def acquire_execution_lock(self) -> bool:
        """실행 잠금 획득. 이미 실행 중이면 False 반환.

        좀비 상태(ZOMBIE_TIMEOUT_MINUTES 이상 경과)이면
        강제 해제 후 잠금을 재획득합니다.

        Returns:
            True: 잠금 획득 성공 (실행 가능)
            False: 이미 실행 중 (스킵 필요)
        """
        if self.is_running:
            if self.last_execution_started_at:
                started = self.last_execution_started_at
                if started.tzinfo is None:
                    started = KST.localize(started)
                elapsed = (
                    datetime.now(KST) - started
                ).total_seconds()
                if elapsed > ZOMBIE_TIMEOUT_MINUTES * 60:
                    logger.warning(
                        f"[EXEC_GUARD] 좀비 실행 감지 "
                        f"({elapsed / 60:.0f}분 경과) → 강제 해제 | "
                        f"flow_id={self.flow_id} | "
                        f"action_type={self.action_type}"
                    )
                else:
                    return False  # 정상 실행 중
            else:
                return False

        self.is_running = True
        self.last_execution_started_at = datetime.now(KST)
        return True

    def release_execution_lock(self) -> None:
        """실행 잠금 해제"""
        self.is_running = False

    def record_execution(self, success: bool) -> None:
        """실행 기록. 성공/실패 모두 last_executed_at 갱신 (스케줄 진행 보장).

        실패 시에도 last_executed_at을 갱신하여 스케줄이 항상 전진합니다.
        마지막 성공 시점은 last_success_at으로 별도 추적합니다.
        """
        now = datetime.now(KST)
        self.total_executions += 1
        self.last_executed_at = now  # 항상 갱신 (무한 루프 방지)
        if success:
            self.last_success_at = now
            self.successful_executions += 1
            self.consecutive_failures = 0
        else:
            self.failed_executions += 1
            self.consecutive_failures = (self.consecutive_failures or 0) + 1

    def pause(self, remaining_seconds: int = None) -> None:
        """일시정지 (timezone aware)"""
        self.is_paused = True
        self.paused_at = datetime.now(KST)
        if remaining_seconds is not None:
            self.remaining_seconds = remaining_seconds
        elif self.next_execution_at:
            # 다음 실행까지 남은 시간 계산 (timezone aware)
            now = datetime.now(KST)
            next_exec = self.next_execution_at
            if next_exec.tzinfo is None:
                next_exec = KST.localize(next_exec)
            delta = next_exec - now
            self.remaining_seconds = max(0, int(delta.total_seconds()))

    def resume(self) -> Optional[datetime]:
        """재개 - 다음 실행 시간 반환 (timezone aware)"""
        if not self.is_paused:
            return self.next_execution_at

        self.is_paused = False
        self.paused_at = None

        # 남은 시간이 있으면 그 시간 후로 설정
        if self.remaining_seconds and self.remaining_seconds > 0:
            from datetime import timedelta
            self.next_execution_at = datetime.now(KST) + timedelta(seconds=self.remaining_seconds)
        self.remaining_seconds = None

        return self.next_execution_at

    def calculate_next_execution(
        self,
        interval_minutes: int,
        schedule_matrix: list = None,
        jitter_enabled: bool = False,
        jitter_min_percent: int = -20,
        jitter_max_percent: int = 30
    ) -> Optional[datetime]:
        """다음 실행 시간 계산 (활성 시간대 기준 간격 소비 방식)."""
        from datetime import timedelta
        import random

        now = datetime.now(KST)

        if self.last_executed_at:
            if self.last_executed_at.tzinfo is None:
                base_time = KST.localize(self.last_executed_at)
            else:
                base_time = self.last_executed_at.astimezone(KST)
        else:
            base_time = now

        interval_seconds = interval_minutes * 60
        if jitter_enabled:
            min_factor = 1 + (jitter_min_percent / 100)
            max_factor = 1 + (jitter_max_percent / 100)
            interval_seconds = int(interval_seconds * random.uniform(min_factor, max_factor))

        if schedule_matrix:
            next_time = self._calc_active_time_schedule(
                base_time, interval_seconds, schedule_matrix, now
            )
        else:
            next_time = base_time + timedelta(seconds=interval_seconds)
            if next_time <= now:
                next_time = now + timedelta(seconds=MIN_EXECUTION_GAP)

        self.next_execution_at = next_time
        return next_time

    def _calc_active_time_schedule(
        self,
        base_time: datetime,
        interval_seconds: int,
        schedule_matrix: list,
        now: datetime,
    ) -> datetime:
        """활성 시간대만 카운트하여 다음 실행 시간 계산.

        base_time부터 활성 시간만 누적하여 interval_seconds를 소비합니다.
        결과가 과거이면 MIN_EXECUTION_GAP(60초) 후로 설정하여
        무한 루프를 방지합니다.
        """
        from datetime import timedelta

        remaining = interval_seconds
        cursor = base_time

        for _ in range(MAX_SCHEDULE_SEARCH_DAYS * 24):
            dow = cursor.weekday()
            hour = cursor.hour

            if not self._is_hour_active(schedule_matrix, dow, hour):
                cursor = self._next_active_hour(cursor, schedule_matrix)
                if cursor is None:
                    return now + timedelta(seconds=MIN_EXECUTION_GAP)
                continue

            end_of_hour = cursor.replace(minute=0, second=0) + timedelta(hours=1)
            seconds_in_hour = (end_of_hour - cursor).total_seconds()

            if remaining <= seconds_in_hour:
                result = cursor + timedelta(seconds=remaining)
                if result <= now:
                    # 밀린 스케줄: 즉시 실행 허용 (최소 60초 간격)
                    return now + timedelta(seconds=MIN_EXECUTION_GAP)
                return result

            remaining -= seconds_in_hour
            cursor = end_of_hour

        return now + timedelta(seconds=MIN_EXECUTION_GAP)

    @staticmethod
    def _is_hour_active(matrix: list, dow: int, hour: int) -> bool:
        """schedule_matrix에서 특정 요일/시간이 활성인지 확인."""
        if not matrix or len(matrix) != 7:
            return True
        day = matrix[dow]
        if not day or len(day) != 24:
            return True
        return bool(day[hour])

    @staticmethod
    def _next_active_hour(from_time: datetime, matrix: list) -> 'Optional[datetime]':
        """from_time 이후 가장 가까운 활성 시간의 시작을 반환."""
        from datetime import timedelta

        cursor = from_time.replace(minute=0, second=0) + timedelta(hours=1)
        for _ in range(24 * 7):
            dow = cursor.weekday()
            hour = cursor.hour
            if FlowExecutionState._is_hour_active(matrix, dow, hour):
                return cursor
            cursor += timedelta(hours=1)
        return None

    def _adjust_to_active_window(
        self,
        proposed_time: datetime,
        schedule_matrix: list
    ) -> datetime:
        """활성화 시간대로 조정"""
        from datetime import timedelta

        # 최대 7일까지만 탐색
        for day_offset in range(7):
            check_time = proposed_time + timedelta(days=day_offset)
            day_of_week = check_time.weekday()
            hour = check_time.hour

            # schedule_matrix 유효성 검사
            if not isinstance(schedule_matrix, list) or len(schedule_matrix) != 7:
                return proposed_time

            day_schedule = schedule_matrix[day_of_week]
            if not isinstance(day_schedule, list) or len(day_schedule) != 24:
                return proposed_time

            # 해당 시간이 활성화되어 있으면 반환
            if day_schedule[hour]:
                return check_time

            # 같은 날 남은 시간 중 활성화된 시간 찾기
            for next_hour in range(hour + 1, 24):
                if day_schedule[next_hour]:
                    return check_time.replace(hour=next_hour, minute=0, second=0)

            # 다음 날부터 활성화된 시간 찾기
            for future_day_offset in range(1, 7):
                future_date = check_time + timedelta(days=future_day_offset)
                future_day_of_week = future_date.weekday()
                future_day_schedule = schedule_matrix[future_day_of_week]

                if isinstance(future_day_schedule, list):
                    for future_hour in range(24):
                        if future_day_schedule[future_hour]:
                            return future_date.replace(
                                hour=future_hour,
                                minute=0,
                                second=0
                            )

        # 활성화된 시간대를 찾지 못하면 원래 시간 반환
        return proposed_time

    def is_in_active_window(self, schedule_matrix: list = None) -> bool:
        """현재 시간이 활성화 시간대인지 확인 (timezone aware)"""
        if not schedule_matrix:
            return True

        now = datetime.now(KST)
        day_of_week = now.weekday()
        hour = now.hour

        if not isinstance(schedule_matrix, list) or len(schedule_matrix) != 7:
            return True

        day_schedule = schedule_matrix[day_of_week]
        if not isinstance(day_schedule, list) or len(day_schedule) != 24:
            return True

        return day_schedule[hour]

    @property
    def success_rate(self) -> float:
        """성공률"""
        if self.total_executions == 0:
            return 0.0
        return (self.successful_executions / self.total_executions) * 100

    def __repr__(self) -> str:
        return (
            f"<FlowExecutionState(flow_id={self.flow_id}, "
            f"action_type='{self.action_type}', blog_id={self.blog_id}, "
            f"paused={self.is_paused})>"
        )
