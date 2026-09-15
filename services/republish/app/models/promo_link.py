"""홍보 링크 모델.

글 끝에 붙일 버튼 하나를 담는다. CPA 오퍼(광고 심의 규칙 관리)와 달리
주소·문구·고지문만 있으면 바로 쓸 수 있다.

수작업에서는 이사 견적용과 청소용 주소를 주제에 따라 바꿔 넣었다. 그
선택을 화면에서 하도록 목록으로 만든다.
"""
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, func,
)

from ..core.database import Base

#: 고지문 기본값 — 애드릭스 표시 문구
DEFAULT_NOTICE = "이 포스팅은 애드릭스 수익을 위해 작성되었습니다."


class PromoLink(Base):
    """글에 붙일 홍보 버튼 하나."""

    __tablename__ = "promo_links"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False,
                  comment="목록에서 고를 때 보이는 이름")
    url = Column(String(500), nullable=False, comment="버튼이 여는 주소")
    button_text = Column(String(200), nullable=False,
                         comment="버튼에 찍히는 문구")
    notice = Column(String(300), nullable=True, default=DEFAULT_NOTICE,
                    comment="맨 앞에 붙는 고지문. 비우면 고지문 없음")

    blog_id = Column(Integer, ForeignKey("blogs.id", ondelete="CASCADE"),
                     nullable=True, index=True,
                     comment="이 블로그 전용. 비우면 모든 블로그 공용")
    cpa_offer_id = Column(Integer,
                          ForeignKey("cpa_offers.id", ondelete="SET NULL"),
                          nullable=True, index=True,
                          comment="이으면 어느 글에서 눌렸는지 추적된다")

    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    def to_dict(self) -> dict:
        """화면이 쓰는 모양."""
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "button_text": self.button_text,
            "notice": self.notice or "",
            "blog_id": self.blog_id,
            "cpa_offer_id": self.cpa_offer_id,
            "is_active": self.is_active,
        }
