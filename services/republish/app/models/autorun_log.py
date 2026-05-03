"""
오토런 실행 로그 모델

Features:
- 플로우 실행 기록 (시작/완료/실패/일시정지)
- 상태 변경 추적
- 실행 통계 조회
- 간결한 로그 포맷: [플로우명][모듈명]-[포스트제목][실행시간][결과]
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
    flow_id = Column(Integer, ForeignKey("flows.id"), nullable=True, index=True)

    # 액션 정보
    action = Column(
        String(30),
        nullable=False,
        comment="액션: republish/publish/generate/paused/resumed/stopped/added/removed",
        index=True
    )

    # 결과 정보
    status = Column(
        String(20),
        nullable=False,
        comment="결과: success/failed/warning/hold/skipped",
        index=True
    )

    # 상세 정보 (새 필드)
    flow_name = Column(String(100), nullable=True, comment="플로우명")
    module_name = Column(String(100), nullable=True, comment="모듈명")
    blog_name = Column(String(100), nullable=True, comment="블로그명")
    post_title = Column(String(200), nullable=True, comment="포스트 제목")
    action_time = Column(String(50), nullable=True, comment="액션 시간 (재발행 시간 등)")

    # 기존 필드 (호환성)
    message = Column(Text, nullable=True, comment="상세 메시지 (에러 등)")
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
        """액션 표시 문자열 - 간결한 포맷"""
        action_map = {
            "republish": "재발행",
            "publish": "발행",
            "generate": "생성",
            "paused": "일시정지",
            "resumed": "재개",
            "stopped": "중지",
            "added": "추가",
            "removed": "제외",
            # 이전 호환성
            "started": "실행 시작",
            "completed": "실행 완료",
            "failed": "실행 실패"
        }
        return action_map.get(self.action, self.action)

    @property
    def status_display(self) -> str:
        """상태 표시 문자열"""
        status_map = {
            "success": "성공",
            "failed": "실패",
            "warning": "경고",
            "hold": "보류",
            "skipped": "스킵",
        }
        return status_map.get(self.status, self.status)

    @property
    def module_type_name(self) -> str:
        """모듈 타입명 (액션 기반)"""
        type_map = {
            "republish": "재발행",
            "publish": "발행",
            "generate": "생성",
            "prompt": "프롬프트"
        }
        return type_map.get(self.action, self.action)

    @property
    def compact_display(self) -> str:
        """간결한 로그 표시 - 새 포맷"""
        # 형식: 재발행 모듈[모듈명]
        #       (블로그명)📄 포스트 제목
        #       🕐 년/월/일/시간 ⏱️ 시간 작업종류 결과
        lines = []

        # 1줄: 모듈 타입과 모듈명
        module_type = self.module_type_name
        module_name = self.module_name or ""
        lines.append(f"{module_type} 모듈[{module_name}]")

        # 2줄: 블로그명과 포스트 제목 (전체 출력)
        blog_part = f"({self.blog_name})" if self.blog_name else ""
        title_part = f"📄 {self.post_title}" if self.post_title else ""
        if blog_part or title_part:
            lines.append(f"{blog_part}{title_part}")

        # 3줄: 시간, 작업시간, 작업종류, 결과
        time_parts = []
        if self.action_time:
            time_parts.append(f"🕐 {self.action_time}")
        if self.execution_duration_ms is not None:
            # m/s 포맷
            duration_sec = self.execution_duration_ms / 1000
            time_parts.append(f"⏱️ {duration_sec:.1f}s")
        # 작업 종류와 결과
        status_text = self.status_display
        time_parts.append(f"{module_type} {status_text}")

        if time_parts:
            lines.append(" ".join(time_parts))

        return "\n".join(lines)

    @classmethod
    def create_action_log(
        cls,
        user_id: int,
        flow_id: int,
        action: str,
        status: str = "success",
        message: str = None,
        flow_name: str = None,
        module_name: str = None,
        blog_name: str = None,
        post_title: str = None,
        action_time: str = None
    ) -> "AutorunLog":
        """액션 로그 생성 (새 간결한 포맷)"""
        return cls(
            user_id=user_id,
            flow_id=flow_id,
            action=action,
            status=status,
            message=message,
            flow_name=flow_name,
            module_name=module_name,
            blog_name=blog_name,
            post_title=post_title,
            action_time=action_time
        )

    @classmethod
    def create_execution_log(
        cls,
        user_id: int,
        flow_id: int,
        action: str,
        status: str,
        flow_name: str = None,
        module_name: str = None,
        blog_name: str = None,
        post_title: str = None,
        action_time: str = None,
        duration_ms: int = None,
        message: str = None
    ) -> "AutorunLog":
        """실행 완료 로그 생성 (새 간결한 포맷)"""
        return cls(
            user_id=user_id,
            flow_id=flow_id,
            action=action,
            status=status,
            flow_name=flow_name,
            module_name=module_name,
            blog_name=blog_name,
            post_title=post_title,
            action_time=action_time,
            execution_duration_ms=duration_ms,
            message=message
        )

    def __repr__(self) -> str:
        return f"<AutorunLog(id={self.id}, flow_id={self.flow_id}, action={self.action}, status={self.status})>"
