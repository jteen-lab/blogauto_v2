"""AI 모델 카탈로그 — 제공자 목록 API 로 갱신되는 모델과 요금.

모델 목록이 화면마다 하드코딩돼 있어, 제공자가 모델을 내리면 죽은 선택지가
그대로 남았다(구글 선택지 10개 중 5개가 이미 없었다). 목록을 여기 한 곳에
모으고 화면은 받아 쓴다.

요금은 어느 제공자도 API 로 주지 않아 별도 테이블에 우리가 관리한다.
"""
from sqlalchemy import (
    Boolean, Column, DateTime, Float, Index, Integer, String, Text,
    UniqueConstraint, func,
)

from ..core.database import Base

# 용도 — 화면에서 목적에 맞는 모델만 고르게 한다
CAP_TEXT = "text"
CAP_IMAGE = "image"
CAP_EMBEDDING = "embedding"
CAP_OTHER = "other"

# 추천 배지 — 제공자별로 각 1개만 둔다(여러 개면 배지 의미가 없어진다)
TIER_FLAGSHIP = "flagship"   # 최고 성능
TIER_VALUE = "value"         # 가성비


class AIModel(Base):
    """제공자에서 제공하는 모델 하나."""

    __tablename__ = "ai_models"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False, index=True)
    model_id = Column(String(200), nullable=False)
    display_name = Column(String(200), nullable=True)

    capability = Column(
        String(20), default=CAP_TEXT, nullable=False,
        comment="text|image|embedding|other — 화면 필터용",
    )
    # 사라진 모델도 행은 남긴다. 지우면 그 설정이 무엇을 가리켰는지
    # 알 수 없게 되고 '지원 종료' 표시와 경고를 할 수 없다.
    is_available = Column(Boolean, default=True, nullable=False, index=True)
    shutdown_date = Column(
        String(40), nullable=True,
        comment="제공자가 공지한 종료일(OpenAI 가 제공)",
    )
    tier = Column(
        String(20), nullable=True,
        comment="flagship|value — 추천 배지. 사람이 지정한다",
    )
    note = Column(Text, nullable=True)

    first_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "model_id", name="uq_ai_model"),
        Index("ix_ai_models_provider_cap", "provider", "capability"),
    )

    def __repr__(self) -> str:
        return f"<AIModel({self.provider}/{self.model_id})>"


class AIModelPrice(Base):
    """모델 요금(100만 토큰당). 제공자가 API 로 주지 않아 수동 관리한다."""

    __tablename__ = "ai_model_prices"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False, index=True)
    model_id = Column(String(200), nullable=False)

    input_per_1m = Column(Float, nullable=True)
    output_per_1m = Column(Float, nullable=True)
    cached_input_per_1m = Column(Float, nullable=True)
    currency = Column(String(10), default="USD", nullable=False)
    # 딥시크처럼 시간대별 요금이 있으면 비피크 기준으로 적고 여기에 적는다
    note = Column(Text, nullable=True)

    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("provider", "model_id", name="uq_ai_model_price"),
    )

    def __repr__(self) -> str:
        return f"<AIModelPrice({self.provider}/{self.model_id})>"
