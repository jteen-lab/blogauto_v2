"""
블로그 모델 정의

Features:
- WordPress/Blogger/기타 플랫폼 지원
- API 키 암호화 저장
- 자동/수동 발행 설정
- 소프트 딜리트 패턴
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any

from ..core.database import Base


class BlogPlatform(str, Enum):
    """블로그 플랫폼"""
    WORDPRESS = "wordpress"
    BLOGGER = "blogger"
    OTHER = "other"


class Blog(Base):
    """블로그 모델"""

    __tablename__ = "blogs"

    # 기본 정보
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 블로그 정보
    name = Column(String(100), nullable=False, comment="블로그 이름")
    url = Column(String(255), nullable=False, comment="블로그 URL")
    platform = Column(SQLEnum(BlogPlatform), nullable=False, comment="플랫폼 타입")

    # 상태
    is_active = Column(Boolean, default=True, nullable=False, comment="활성 상태")
    is_auto_supported = Column(Boolean, default=True, nullable=False, comment="자동화 지원 여부")

    # API 정보 (암호화 저장)
    api_key_encrypted = Column(Text, nullable=True, comment="암호화된 API 키")
    api_secret_encrypted = Column(Text, nullable=True, comment="암호화된 API 시크릿")
    oauth_token_encrypted = Column(Text, nullable=True, comment="암호화된 OAuth 토큰")

    # 발행 설정
    auto_publish = Column(Boolean, default=False, nullable=False, comment="자동 발행 여부")
    republish_interval_hours = Column(Integer, default=24, nullable=False, comment="재발행 간격(시간)")
    daily_limit = Column(Integer, default=10, nullable=False, comment="일일 발행 제한")

    # 콘텐츠 설정
    editor_type = Column(String(50), default="classic", nullable=False, comment="에디터 타입")
    css_classes = Column(JSON, nullable=True, comment="CSS 클래스 치환 규칙")

    # 소프트 딜리트
    is_deleted = Column(Boolean, default=False, nullable=False)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 관계 설정
    user = relationship("User", back_populates="blogs")
    profile_links = relationship("BlogProfileLink", back_populates="blog")
    group_links = relationship("BlogGroupLink", back_populates="blog", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Blog(id={self.id}, name={self.name}, platform={self.platform.value})>"

    def __str__(self) -> str:
        return f"Blog #{self.id} ({self.name})"

    @property
    def is_wordpress(self) -> bool:
        """WordPress 블로그 여부"""
        return self.platform == BlogPlatform.WORDPRESS

    @property
    def is_blogger(self) -> bool:
        """Blogger 블로그 여부"""
        return self.platform == BlogPlatform.BLOGGER

    @property
    def is_other(self) -> bool:
        """기타 플랫폼 여부"""
        return self.platform == BlogPlatform.OTHER

    @property
    def has_api_credentials(self) -> bool:
        """API 인증 정보 보유 여부"""
        return bool(self.api_key_encrypted or self.oauth_token_encrypted)

    @property
    def masked_api_key(self) -> str:
        """마스킹된 API 키 (로그용)"""
        if not self.api_key_encrypted:
            return "없음"
        return "****" + str(self.api_key_encrypted)[-4:] if len(str(self.api_key_encrypted)) > 4 else "****"

    def activate(self) -> None:
        """블로그 활성화"""
        self.is_active = True

    def deactivate(self) -> None:
        """블로그 비활성화"""
        self.is_active = False

    def enable_auto_publish(self) -> None:
        """자동 발행 활성화"""
        if self.is_auto_supported:
            self.auto_publish = True

    def disable_auto_publish(self) -> None:
        """자동 발행 비활성화"""
        self.auto_publish = False

    def soft_delete(self) -> None:
        """소프트 딜리트"""
        self.is_deleted = True
        self.is_active = False

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환 (민감 정보 제외)"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "url": self.url,
            "platform": self.platform.value,
            "is_active": self.is_active,
            "is_auto_supported": self.is_auto_supported,
            "has_api_credentials": self.has_api_credentials,
            "auto_publish": self.auto_publish,
            "republish_interval_hours": self.republish_interval_hours,
            "daily_limit": self.daily_limit,
            "editor_type": self.editor_type,
            "css_classes": self.css_classes,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }