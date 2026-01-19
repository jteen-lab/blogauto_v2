"""
사용자 설정 모델

Features:
- AI 서비스 API 키 관리
- Google Blogger 시간당 발행 제한 설정
- 네이버 검색광고 API 설정
- 사용자별 1:1 설정 테이블
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from typing import Optional

from ..core.database import Base


class UserSettings(Base):
    """사용자 설정 모델"""

    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint(
            'blogger_hourly_limit BETWEEN 1 AND 4',
            name='check_blogger_hourly_limit_range'
        ),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # user_id는 단일 사용자 환경에서 기본값 1 사용 (FK 제거로 독립 동작)
    user_id = Column(
        Integer,
        default=1,
        nullable=False,
        index=True
    )

    # AI 서비스 설정
    openai_api_key = Column(String(255), nullable=True)
    claude_api_key = Column(String(255), nullable=True)
    default_ai_model = Column(String(50), default="gpt-4", nullable=False)

    # API 설정
    blogger_hourly_limit = Column(Integer, default=2, nullable=False)

    # 네이버 검색광고 API 설정
    naver_ads_api_key = Column(String(255), nullable=True)
    naver_ads_secret_key = Column(String(255), nullable=True)
    naver_ads_customer_id = Column(String(50), nullable=True)

    # 네이버 데이터랩 API 설정 (검색어 트렌드)
    naver_datalab_client_id = Column(String(255), nullable=True)
    naver_datalab_client_secret = Column(String(255), nullable=True)

    # 네이버 검색 API 설정 (블로그 검색 결과 수집)
    naver_search_client_id = Column(String(255), nullable=True)
    naver_search_client_secret = Column(String(255), nullable=True)

    # Google Keyword Planner API 설정
    google_ads_developer_token = Column(String(255), nullable=True)
    google_ads_client_id = Column(String(255), nullable=True)
    google_ads_client_secret = Column(String(255), nullable=True)
    google_ads_refresh_token = Column(String(512), nullable=True)
    google_ads_customer_id = Column(String(50), nullable=True)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # 관계 설정 (FK 제거로 relationship도 제거)
    # user = relationship("User", backref="settings", uselist=False)

    def __repr__(self) -> str:
        return f"<UserSettings(user_id={self.user_id}, model={self.default_ai_model})>"

    @property
    def has_openai_key(self) -> bool:
        """OpenAI API 키 설정 여부"""
        return bool(self.openai_api_key)

    @property
    def has_claude_key(self) -> bool:
        """Claude API 키 설정 여부"""
        return bool(self.claude_api_key)

    @property
    def masked_openai_key(self) -> Optional[str]:
        """마스킹된 OpenAI API 키 (앞 4자 + **** + 뒤 4자)"""
        if not self.openai_api_key:
            return None
        if len(self.openai_api_key) <= 8:
            return "****"
        return f"{self.openai_api_key[:4]}****{self.openai_api_key[-4:]}"

    @property
    def masked_claude_key(self) -> Optional[str]:
        """마스킹된 Claude API 키"""
        if not self.claude_api_key:
            return None
        if len(self.claude_api_key) <= 8:
            return "****"
        return f"{self.claude_api_key[:4]}****{self.claude_api_key[-4:]}"

    @property
    def has_naver_ads_api(self) -> bool:
        """네이버 검색광고 API 설정 여부"""
        return bool(
            self.naver_ads_api_key and
            self.naver_ads_secret_key and
            self.naver_ads_customer_id
        )

    @property
    def masked_naver_ads_api_key(self) -> Optional[str]:
        """마스킹된 네이버 검색광고 API 키"""
        if not self.naver_ads_api_key:
            return None
        if len(self.naver_ads_api_key) <= 8:
            return "****"
        return f"{self.naver_ads_api_key[:4]}****{self.naver_ads_api_key[-4:]}"

    @property
    def masked_naver_ads_secret_key(self) -> Optional[str]:
        """마스킹된 네이버 검색광고 Secret 키"""
        if not self.naver_ads_secret_key:
            return None
        if len(self.naver_ads_secret_key) <= 8:
            return "****"
        return f"{self.naver_ads_secret_key[:4]}****{self.naver_ads_secret_key[-4:]}"

    @property
    def has_naver_datalab_api(self) -> bool:
        """네이버 데이터랩 API 설정 여부"""
        return bool(
            self.naver_datalab_client_id and
            self.naver_datalab_client_secret
        )

    @property
    def masked_naver_datalab_client_id(self) -> Optional[str]:
        """마스킹된 네이버 데이터랩 Client ID"""
        if not self.naver_datalab_client_id:
            return None
        if len(self.naver_datalab_client_id) <= 8:
            return "****"
        return f"{self.naver_datalab_client_id[:4]}****{self.naver_datalab_client_id[-4:]}"

    @property
    def masked_naver_datalab_client_secret(self) -> Optional[str]:
        """마스킹된 네이버 데이터랩 Client Secret"""
        if not self.naver_datalab_client_secret:
            return None
        if len(self.naver_datalab_client_secret) <= 8:
            return "****"
        return f"{self.naver_datalab_client_secret[:4]}****{self.naver_datalab_client_secret[-4:]}"

    @property
    def has_naver_search_api(self) -> bool:
        """네이버 검색 API 설정 여부"""
        return bool(
            self.naver_search_client_id and
            self.naver_search_client_secret
        )

    @property
    def masked_naver_search_client_id(self) -> Optional[str]:
        """마스킹된 네이버 검색 Client ID"""
        if not self.naver_search_client_id:
            return None
        if len(self.naver_search_client_id) <= 8:
            return "****"
        return f"{self.naver_search_client_id[:4]}****{self.naver_search_client_id[-4:]}"

    @property
    def masked_naver_search_client_secret(self) -> Optional[str]:
        """마스킹된 네이버 검색 Client Secret"""
        if not self.naver_search_client_secret:
            return None
        if len(self.naver_search_client_secret) <= 8:
            return "****"
        return f"{self.naver_search_client_secret[:4]}****{self.naver_search_client_secret[-4:]}"

    @property
    def has_google_keyword_planner_api(self) -> bool:
        """Google Keyword Planner API 설정 여부"""
        return bool(
            self.google_ads_developer_token and
            self.google_ads_client_id and
            self.google_ads_client_secret and
            self.google_ads_refresh_token and
            self.google_ads_customer_id
        )

    @property
    def masked_google_ads_developer_token(self) -> Optional[str]:
        """마스킹된 Google Ads Developer Token"""
        if not self.google_ads_developer_token:
            return None
        if len(self.google_ads_developer_token) <= 8:
            return "****"
        return f"{self.google_ads_developer_token[:4]}****{self.google_ads_developer_token[-4:]}"

    @property
    def masked_google_ads_client_id(self) -> Optional[str]:
        """마스킹된 Google Ads Client ID"""
        if not self.google_ads_client_id:
            return None
        if len(self.google_ads_client_id) <= 8:
            return "****"
        return f"{self.google_ads_client_id[:4]}****{self.google_ads_client_id[-4:]}"

    @property
    def masked_google_ads_client_secret(self) -> Optional[str]:
        """마스킹된 Google Ads Client Secret"""
        if not self.google_ads_client_secret:
            return None
        if len(self.google_ads_client_secret) <= 8:
            return "****"
        return f"{self.google_ads_client_secret[:4]}****{self.google_ads_client_secret[-4:]}"

    @property
    def masked_google_ads_refresh_token(self) -> Optional[str]:
        """마스킹된 Google Ads Refresh Token"""
        if not self.google_ads_refresh_token:
            return None
        if len(self.google_ads_refresh_token) <= 8:
            return "****"
        return f"{self.google_ads_refresh_token[:4]}****{self.google_ads_refresh_token[-4:]}"

    def to_dict(self) -> dict:
        """딕셔너리 변환 (API 키 마스킹)"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "openai_api_key": self.masked_openai_key,
            "claude_api_key": self.masked_claude_key,
            "default_ai_model": self.default_ai_model,
            "blogger_hourly_limit": self.blogger_hourly_limit,
            "has_openai_key": self.has_openai_key,
            "has_claude_key": self.has_claude_key,
            # 네이버 검색광고 API
            "naver_ads_api_key": self.masked_naver_ads_api_key,
            "naver_ads_secret_key": self.masked_naver_ads_secret_key,
            "naver_ads_customer_id": self.naver_ads_customer_id,
            "has_naver_ads_api": self.has_naver_ads_api,
            # 네이버 데이터랩 API
            "naver_datalab_client_id": self.masked_naver_datalab_client_id,
            "naver_datalab_client_secret": self.masked_naver_datalab_client_secret,
            "has_naver_datalab_api": self.has_naver_datalab_api,
            # 네이버 검색 API
            "naver_search_client_id": self.masked_naver_search_client_id,
            "naver_search_client_secret": self.masked_naver_search_client_secret,
            "has_naver_search_api": self.has_naver_search_api,
            # Google Keyword Planner API
            "google_ads_developer_token": self.masked_google_ads_developer_token,
            "google_ads_client_id": self.masked_google_ads_client_id,
            "google_ads_client_secret": self.masked_google_ads_client_secret,
            "google_ads_refresh_token": self.masked_google_ads_refresh_token,
            "google_ads_customer_id": self.google_ads_customer_id,
            "has_google_keyword_planner_api": self.has_google_keyword_planner_api,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
