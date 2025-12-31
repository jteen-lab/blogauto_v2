"""
발행 이력 모델

Features:
- 모든 발행/재발행 시도 기록
- 상세 오류 메시지 및 응답 시간 추적
- 대시보드 조회용 필터 지원
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


class PublishLog(Base):
    """발행 이력"""
    __tablename__ = "publish_logs"

    # 기본 필드
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    blog_id = Column(Integer, ForeignKey("blogs.id"), nullable=False, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    # profile_id = Column(Integer, ForeignKey("publish_profiles.id"), nullable=True, index=True)  # 제거됨 (Flow 시스템으로 교체)
    module_id = Column(Integer, ForeignKey("modules.id"), nullable=True, index=True, comment="연관된 모듈 ID")

    # 작업 정보
    action = Column(String(20), nullable=False, comment="작업: publish/republish", index=True)
    platform = Column(String(20), nullable=False, comment="플랫폼: wordpress/blogger", index=True)

    # 결과
    status = Column(String(20), nullable=False, comment="결과: success/failed/skipped", index=True)
    error_message = Column(Text, nullable=True, comment="오류 메시지 (API 키 마스킹)")
    retry_count = Column(Integer, default=0, comment="재시도 횟수")

    # 상세 정보
    remote_id = Column(String(50), nullable=True, comment="발행된 포스트 ID")
    response_time_ms = Column(Integer, nullable=True, comment="API 응답 시간(ms)")

    # 메타
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # 관계
    user = relationship("User")
    blog = relationship("Blog")
    post = relationship("Post", back_populates="publish_logs")
    # profile = relationship("PublishProfile")  # 제거됨 (Flow 시스템으로 교체)
    module = relationship("Module")

    @property
    def is_success(self) -> bool:
        """성공 여부"""
        return self.status == "success"

    @property
    def is_failed(self) -> bool:
        """실패 여부"""
        return self.status == "failed"

    @property
    def formatted_response_time(self) -> str:
        """포맷된 응답 시간"""
        if self.response_time_ms is None:
            return "N/A"
        if self.response_time_ms < 1000:
            return f"{self.response_time_ms}ms"
        else:
            return f"{self.response_time_ms / 1000:.1f}s"

    @classmethod
    def create_success_log(
        cls,
        user_id: int,
        blog_id: int,
        post_id: int,
        action: str,
        platform: str,
        remote_id: str,
        response_time_ms: int = None,
        module_id: int = None
    ) -> "PublishLog":
        """성공 로그 생성"""
        return cls(
            user_id=user_id,
            blog_id=blog_id,
            post_id=post_id,
            module_id=module_id,
            action=action,
            platform=platform,
            status="success",
            remote_id=remote_id,
            response_time_ms=response_time_ms
        )

    @classmethod
    def create_failed_log(
        cls,
        user_id: int,
        blog_id: int,
        post_id: int,
        action: str,
        platform: str,
        error_message: str,
        retry_count: int = 0,
        module_id: int = None
    ) -> "PublishLog":
        """실패 로그 생성"""
        # API 키/토큰 마스킹
        masked_error = cls._mask_sensitive_info(error_message)

        return cls(
            user_id=user_id,
            blog_id=blog_id,
            post_id=post_id,
            module_id=module_id,
            action=action,
            platform=platform,
            status="failed",
            error_message=masked_error,
            retry_count=retry_count
        )

    @staticmethod
    def _mask_sensitive_info(message: str) -> str:
        """민감한 정보 마스킹"""
        import re

        # API 키/토큰 패턴 마스킹
        patterns = [
            (r'[A-Za-z0-9]{20,}', '***'),  # 긴 문자열 (API 키)
            (r'Bearer\s+[A-Za-z0-9._-]+', 'Bearer ***'),  # Bearer 토큰
            (r'token["\s:=]+[A-Za-z0-9._-]+', 'token: ***'),  # 토큰
            (r'password["\s:=]+[^\s"]+', 'password: ***'),  # 패스워드
        ]

        masked = message
        for pattern, replacement in patterns:
            masked = re.sub(pattern, replacement, masked, flags=re.IGNORECASE)

        return masked

    def __repr__(self) -> str:
        return f"<PublishLog(id={self.id}, action={self.action}, status={self.status}, platform={self.platform})>"