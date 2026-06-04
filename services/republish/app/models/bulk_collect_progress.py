"""
대량 수집 진행 상태 모델 정의

Phase A-041: 대량 수집(bulk_collect) 모듈의 블로그(도메인) 단위
진행 상태를 영구 보관한다.

저장 단위:
    (module_id, blog_domain) 쌍 = UNIQUE
    같은 모듈이 같은 도메인을 반복 처리할 때마다 갱신된다.

용도:
    - 마지막으로 본 sitemap lastmod 시각 보관 → 다음 사이클에서 신규/변경 글만 처리
    - 한 사이클이 얼마나 걸렸는지, 몇 개 처리/실패했는지 메트릭 보관

비고:
    - blog_domain 은 Blog 테이블과 직접 FK 가 아니다.
      대량 수집은 등록되지 않은 외부 도메인도 처리 대상이기 때문이다.
    - module_id 는 modules.id 와 FK, ondelete=CASCADE.
      모듈이 삭제되면 진행 상태도 함께 정리된다.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..core.database import Base

logger = logging.getLogger(__name__)


class BulkCollectProgress(Base):
    """
    대량 수집 모듈별, 블로그 도메인별 진행 상태

    각 (module_id, blog_domain) 쌍에 대해 직전 사이클 정보를 1 row 로 유지한다.
    다음 사이클 진입 시 last_seen_lastmod 를 기준으로 신규 변경만 수집한다.
    """
    __tablename__ = "bulk_collect_progress"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        comment="PK"
    )

    # 모듈 FK (modules.id, ondelete=CASCADE)
    module_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="대량 수집 모듈 ID"
    )

    # 블로그 도메인 (Blog FK 아님 — 외부 도메인도 추적 대상)
    blog_domain: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        comment="블로그 도메인 (예: example.tistory.com)"
    )

    # 직전 사이클에서 마지막으로 확인한 sitemap lastmod
    last_seen_lastmod: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="마지막으로 처리한 sitemap entry 의 lastmod 시각"
    )

    # 직전 사이클 메트릭
    last_cycle_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="가장 최근 사이클 종료 시각"
    )
    last_cycle_duration_sec: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="가장 최근 사이클 소요 시간(초)"
    )
    last_cycle_processed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="가장 최근 사이클 처리 성공 건수"
    )
    last_cycle_failed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="가장 최근 사이클 실패 건수"
    )

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="최초 등록 시각"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="마지막 갱신 시각"
    )

    # (module_id, blog_domain) 쌍은 유니크
    __table_args__ = (
        UniqueConstraint(
            "module_id",
            "blog_domain",
            name="uq_bulk_collect_progress_module_domain",
        ),
    )

    def __repr__(self) -> str:
        return (
            "<BulkCollectProgress("
            f"id={self.id}, module_id={self.module_id}, "
            f"domain='{self.blog_domain}', "
            f"last_seen_lastmod={self.last_seen_lastmod})>"
        )
