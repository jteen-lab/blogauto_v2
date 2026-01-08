"""
오토런 실행 로그 모델

Features:
- 플로우 실행 기록 (시작/완료/실패/일시정지)
- 상태 변경 추적
- 실행 통계 조회
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


class AutorunLog(Base):
    """오토런 실행 로그"""
    __tablename__ = "autorun_logs"

    # 기본 필드
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    flow_id = Column(Integer, ForeignKey("flows.id"), nullable=False, index=True)

    # 액션 정보
    action = Column(
        String(30),
        nullable=False,
        comment="액션: started/completed/failed/paused/resumed/stopped/added/removed",
        index=True
    )

    # 결과 정보
    status = Column(
        String(20),
        nullable=False,
        comment="결과: success/failed/warning",
        index=True
    )
    message = Column(Text, nullable=True, comment="상세 메시지")

    # 실행 정보 (플로우 실행 시)
    execution_duration_ms = Column(Integer, nullable=True, comment="실행 시간(ms)")
    posts_processed = Column(Integer, nullable=True, comment="처리된 포스트 수")
    posts_success = Column(Integer, nullable=True, comment="성공한 포스트 수")
    posts_failed = Column(Integer, nullable=True, comment="실패한 포스트 수")

    # 메타
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # 관계
    user = relationship("User")
    flow = relationship("Flow")

    @property
    def is_success(self) -> bool:
        """성공 여부"""
        return self.status == "success"

    @property
    def formatted_duration(self) -> str:
        """포맷된 실행 시간"""
        if self.execution_duration_ms is None:
            return "-"
        if self.execution_duration_ms < 1000:
            return f"{self.execution_duration_ms}ms"
        elif self.execution_duration_ms < 60000:
            return f"{self.execution_duration_ms / 1000:.1f}초"
        else:
            minutes = self.execution_duration_ms // 60000
            seconds = (self.execution_duration_ms % 60000) // 1000
            return f"{minutes}분 {seconds}초"

    @property
    def action_display(self) -> str:
        """액션 표시 문자열"""
        action_map = {
            "started": "🚀 실행 시작",
            "completed": "✅ 실행 완료",
            "failed": "❌ 실행 실패",
            "paused": "⏸️ 일시정지",
            "resumed": "▶️ 재개",
            "stopped": "⏹️ 중지",
            "added": "➕ 추가됨",
            "removed": "➖ 제외됨"
        }
        return action_map.get(self.action, self.action)

    @property
    def status_display(self) -> str:
        """상태 표시 문자열"""
        status_map = {
            "success": "성공",
            "failed": "실패",
            "warning": "경고"
        }
        return status_map.get(self.status, self.status)

    @classmethod
    def create_action_log(
        cls,
        user_id: int,
        flow_id: int,
        action: str,
        status: str = "success",
        message: str = None
    ) -> "AutorunLog":
        """액션 로그 생성"""
        return cls(
            user_id=user_id,
            flow_id=flow_id,
            action=action,
            status=status,
            message=message
        )

    @classmethod
    def create_execution_log(
        cls,
        user_id: int,
        flow_id: int,
        status: str,
        duration_ms: int = None,
        posts_processed: int = None,
        posts_success: int = None,
        posts_failed: int = None,
        message: str = None
    ) -> "AutorunLog":
        """실행 완료 로그 생성"""
        action = "completed" if status == "success" else "failed"
        return cls(
            user_id=user_id,
            flow_id=flow_id,
            action=action,
            status=status,
            message=message,
            execution_duration_ms=duration_ms,
            posts_processed=posts_processed,
            posts_success=posts_success,
            posts_failed=posts_failed
        )

    def __repr__(self) -> str:
        return f"<AutorunLog(id={self.id}, flow_id={self.flow_id}, action={self.action}, status={self.status})>"
