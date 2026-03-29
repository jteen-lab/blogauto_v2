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

# Timezone 설정
KST = pytz.timezone('Asia/Seoul')


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

    def record_execution(self, success: bool) -> None:
        """실행 기록 (timezone aware)"""
        self.last_executed_at = datetime.now(KST)
        self.total_executions += 1
        if success:
            self.successful_executions += 1
        else:
            self.failed_executions += 1

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
        """다음 실행 시간 계산 (timezone aware)"""
        from datetime import timedelta
        import random

        # timezone aware datetime 사용
        now = datetime.now(KST)

        # base_time 설정 (timezone aware로 변환)
        if self.last_executed_at:
            if self.last_executed_at.tzinfo is None:
                base_time = KST.localize(self.last_executed_at)
            else:
                base_time = self.last_executed_at
        else:
            base_time = now

        # 기본 간격 적용
        interval_seconds = interval_minutes * 60

        # Jitter 적용 (선택적)
        if jitter_enabled:
            min_factor = 1 + (jitter_min_percent / 100)
            max_factor = 1 + (jitter_max_percent / 100)
            jitter_factor = random.uniform(min_factor, max_factor)
            interval_seconds = int(interval_seconds * jitter_factor)

        next_time = base_time + timedelta(seconds=interval_seconds)

        # 이미 지난 시간이면 현재 시간 기준으로 재계산
        if next_time <= now:
            next_time = now + timedelta(seconds=interval_seconds)

        # schedule_matrix 기반 활성화 시간대 체크
        if schedule_matrix:
            next_time = self._adjust_to_active_window(next_time, schedule_matrix)

        self.next_execution_at = next_time
        return next_time

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
