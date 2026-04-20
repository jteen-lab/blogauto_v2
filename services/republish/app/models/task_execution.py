"""
Celery 작업 실행 상태 추적 모델

큐/워커 시스템에서 발행된 태스크의 상태를 DB에 기록합니다.
Flower 모니터링과 병행하여 비즈니스 로직 수준의 추적을 제공합니다.
"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    JSON,
    ForeignKey,
    Index,
)
from sqlalchemy.sql import func

from ..core.database import Base


class TaskExecution(Base):
    """Celery 작업 실행 상태 추적.

    각 Celery 태스크의 생명주기(pending -> running -> success/failed)를
    DB에 기록하여 이력 조회와 재시도 관리를 지원합니다.

    Attributes:
        task_id: Celery가 발급한 고유 태스크 ID
        task_name: 태스크 이름 (예: "tasks.generate_content")
        queue: 큐 이름 (예: "generation_queue")
        blog_id: 관련 블로그 ID (nullable)
        module_id: 관련 모듈 ID (nullable)
        flow_id: 관련 플로우 ID (nullable)
        status: 실행 상태 (pending/running/success/failed/retrying)
        priority: 우선순위 1-9 (9가 최고)
        params: 태스크 파라미터 (JSON)
        result: 실행 결과 (JSON)
        error_message: 에러 메시지
        retry_count: 재시도 횟수
        created_at: 생성 시각
        started_at: 실행 시작 시각
        completed_at: 완료 시각
    """

    __tablename__ = "task_executions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Celery task ID",
    )
    task_name = Column(
        String(100),
        nullable=False,
        comment="태스크 이름",
    )
    queue = Column(
        String(50),
        nullable=False,
        comment="큐 이름",
    )
    blog_id = Column(
        Integer,
        ForeignKey("blogs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="관련 블로그 ID",
    )
    module_id = Column(
        Integer,
        ForeignKey("modules.id", ondelete="SET NULL"),
        nullable=True,
        comment="관련 모듈 ID",
    )
    flow_id = Column(
        Integer,
        ForeignKey("flows.id", ondelete="SET NULL"),
        nullable=True,
        comment="관련 플로우 ID",
    )
    status = Column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
        comment="pending/running/success/failed/retrying",
    )
    priority = Column(
        Integer,
        default=5,
        comment="우선순위 1-9",
    )
    params = Column(
        JSON,
        nullable=True,
        comment="태스크 파라미터",
    )
    result = Column(
        JSON,
        nullable=True,
        comment="실행 결과",
    )
    error_message = Column(
        Text,
        nullable=True,
        comment="에러 메시지",
    )
    retry_count = Column(
        Integer,
        default=0,
        comment="재시도 횟수",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="생성 시각",
    )
    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="실행 시작 시각",
    )
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="완료 시각",
    )

    __table_args__ = (
        Index("ix_task_blog_status", "blog_id", "status"),
        Index("ix_task_created", "created_at"),
    )

    def __repr__(self) -> str:
        """문자열 표현."""
        return (
            f"<TaskExecution(id={self.id}, task_id='{self.task_id}', "
            f"task_name='{self.task_name}', status='{self.status}')>"
        )
