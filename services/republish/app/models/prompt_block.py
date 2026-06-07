"""프롬프트 빌더 옵션 블록 모델.

프롬프트 빌더의 4축 옵션(페르소나·독자수준·섹션패턴·시작톤)을 DB에 저장한다.
기존에는 `services/prompt_builder/blocks.py` 에 하드코딩돼 있어 옵션 추가/수정이
1회성이었으나, 본 테이블로 옮겨 영구 저장·추가·수정이 가능해진다.

- 기본 제공 블록은 `is_builtin=True` 로 시드된다(기존 blocks.py 값과 동일).
- 운영자가 추가/수정한 블록은 `is_builtin=False`.
- UNIQUE(block_type, code) 로 같은 축 안에서 코드 중복을 막는다.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Integer, String, Boolean, Text, DateTime, UniqueConstraint, Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class PromptBlock(Base):
    """프롬프트 빌더 옵션 블록 (페르소나/독자/패턴/톤)."""

    __tablename__ = "prompt_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    block_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="블록 축: persona|reader|pattern|tone",
    )
    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="축 내 고유 코드 (예: P-Expert, P4, T-Numbers)",
    )
    label: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="UI 표시 라벨",
    )
    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="프롬프트에 삽입되는 블록 본문 텍스트",
    )
    cluster: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="그룹 식별(톤 S1~S5 등, 없으면 빈 값)",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="축 내 정렬 순서",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="활성 여부(비활성 시 빌더 옵션에서 숨김)",
    )
    is_builtin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="기본 제공 블록 여부(시드값)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "block_type", "code", name="uq_prompt_block_type_code",
        ),
        Index("ix_prompt_blocks_type_active", "block_type", "is_active"),
    )

    def to_block_dict(self) -> dict:
        """빌더 JS가 기대하는 StyleBlock 형태로 변환(편집/삭제용 id 포함)."""
        return {
            "id": self.id,
            "code": self.code,
            "label": self.label,
            "cluster": self.cluster or "",
            "body": self.body,
        }

    def __repr__(self) -> str:
        return (
            f"<PromptBlock(type={self.block_type}, code={self.code}, "
            f"builtin={self.is_builtin})>"
        )
