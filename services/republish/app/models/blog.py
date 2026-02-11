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

    # Google 계정 연결 (Blogger용)
    google_credential_id = Column(
        Integer,
        ForeignKey("google_credentials.id"),
        nullable=True,
        comment="Google 계정 ID (Blogger용)"
    )

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

    # 이미지 설정
    image_mode = Column(
        String(20),
        default="template",
        nullable=False,
        comment="이미지 모드: template, openai, both"
    )
    overlay_config = Column(
        JSON,
        default=dict,
        nullable=True,
        comment="이미지 오버레이 설정"
    )

    # 치환자 설정
    placeholders = Column(
        JSON,
        default=dict,
        nullable=True,
        comment="치환자 설정: html_tags, css_classes, text_replace"
    )

    # 스타일 설정
    style_config = Column(
        JSON,
        default=dict,
        nullable=True,
        comment="CSS 스타일 설정"
    )

    # AI 설정
    ai_config = Column(
        JSON,
        default=dict,
        nullable=True,
        comment="AI 서비스 설정: writing_ai, title_ai, image_ai"
    )

    # 유사도 매칭 설정 (Phase 3)
    matching_config = Column(
        JSON,
        default=dict,
        nullable=True,
        comment="유사도 매칭 설정: allow_duplicate_similar_posts, matching_threshold, use_waiting_category, waiting_threshold_min"
    )

    # 포스트 통계 (재발행 모듈 적용 구간 필터링용)
    total_post_count = Column(Integer, nullable=True, comment="누적 포스트 수")
    post_count_updated_at = Column(DateTime(timezone=True), nullable=True, comment="포스트 수 업데이트 시점")

    # 크롤링/매칭 상태 (Phase M-1: 유사도 매칭 워크플로우)
    is_new_blog = Column(Boolean, default=True, nullable=False, comment="신규 블로그 여부 (포스트 없음)")
    crawl_status = Column(String(20), default="never", nullable=False, comment="크롤링 상태: never | crawling | matching | synced | error")
    last_crawled_at = Column(DateTime(timezone=True), nullable=True, comment="마지막 크롤링 시간")
    last_matched_at = Column(DateTime(timezone=True), nullable=True, comment="마지막 매칭 완료 시간")
    crawled_count = Column(Integer, default=0, nullable=False, comment="크롤링된 포스트 수")
    matched_count = Column(Integer, default=0, nullable=False, comment="매칭된 포스트 수")

    # 소프트 딜리트
    is_deleted = Column(Boolean, default=False, nullable=False)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 관계 설정
    user = relationship("User", back_populates="blogs")
    google_credential = relationship("GoogleCredential", back_populates="blogs")
    # profile_links는 제거됨 (새로운 Flow 시스템으로 교체)
    # group_links = relationship("BlogGroupLink", back_populates="blog", cascade="all, delete-orphan")  # 제거됨 (Flow 시스템으로 교체)
    flow_links = relationship("FlowBlog", back_populates="blog", cascade="all, delete-orphan")
    crawled_posts = relationship("CrawledPost", back_populates="blog", cascade="all, delete-orphan")

    # Phase G-1: 생성 모듈 관계
    generation_histories = relationship(
        "GenerationHistory",
        back_populates="blog",
        cascade="all, delete-orphan",
    )
    growth_setting = relationship(
        "BlogGrowthSetting",
        back_populates="blog",
        uselist=False,
        cascade="all, delete-orphan",
    )

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
        if self.is_blogger and not (self.api_key_encrypted or self.oauth_token_encrypted):
            return bool(self.google_credential_id)
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
        """
        딕셔너리로 변환 (민감 정보 제외)

        Returns:
            Dict[str, Any]: 블로그 정보 딕셔너리
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "google_credential_id": self.google_credential_id,
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
            # 이미지 설정
            "image_mode": self.image_mode,
            "overlay_config": self.overlay_config or {},
            # 치환자 설정
            "placeholders": self.placeholders or {},
            # 스타일 설정
            "style_config": self.style_config or {},
            # AI 설정
            "ai_config": self.ai_config or {},
            # 유사도 매칭 설정 (Phase 3)
            "matching_config": self.matching_config or {},
            # 크롤링/매칭 상태 (Phase M-1)
            "is_new_blog": self.is_new_blog,
            "crawl_status": self.crawl_status,
            "last_crawled_at": self.last_crawled_at,
            "last_matched_at": self.last_matched_at,
            "crawled_count": self.crawled_count,
            "matched_count": self.matched_count,
            # 타임스탬프
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    def to_dict_with_credentials(self, decrypt_func) -> Dict[str, Any]:
        """딕셔너리로 변환 (복호화된 인증정보 포함)"""
        result = self.to_dict()

        # 복호화된 인증정보 추가
        result["api_key"] = ""
        result["api_secret"] = ""
        result["oauth_token"] = ""

        try:
            if self.api_key_encrypted:
                result["api_key"] = decrypt_func(self.api_key_encrypted)
        except Exception:
            result["api_key"] = ""

        try:
            if self.api_secret_encrypted:
                result["api_secret"] = decrypt_func(self.api_secret_encrypted)
        except Exception:
            result["api_secret"] = ""

        try:
            if self.oauth_token_encrypted:
                result["oauth_token"] = decrypt_func(self.oauth_token_encrypted)
        except Exception:
            result["oauth_token"] = ""

        return result