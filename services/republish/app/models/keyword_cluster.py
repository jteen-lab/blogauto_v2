"""키워드 클러스터 — 생산 단위를 키워드에서 **묶음**으로 올린다.

키워드 1개 = 제목 1개는 대량 발행에 맞지 않는다. 업계 표준은 비슷한 키워드를
묶어 **대표 글(필러) 1편 + 곁가지 글 N편**을 쓰는 것이다(토픽 클러스터).
그래야 키워드 1개에서 글 여러 편이 나오고, 주제 권위도 쌓인다.

권장 규모: 클러스터당 키워드 8~10개.

계획서: docs/plans/keyword_module_redesign_plan.md §2 B4
"""
from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.sql import func

from ..core.database import Base

# 상태
CLUSTER_NEW = "new"          # 아직 제목을 안 만듦
CLUSTER_TITLED = "titled"    # 제목을 만들었음


class KeywordCluster(Base):
    """비슷한 의도·주제의 키워드 묶음."""

    __tablename__ = "keyword_clusters"
    __table_args__ = (
        UniqueConstraint("user_id", "blog_id", "name",
                         name="uq_keyword_cluster"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False,
                     index=True)
    blog_id = Column(Integer, ForeignKey("blogs.id"), nullable=True,
                     index=True)

    # 대표 키워드(검색량이 가장 큰 것). 필러 글의 축이 된다.
    name = Column(String(200), nullable=False)
    topic_id = Column(Integer, nullable=True, index=True)
    subtopic_id = Column(Integer, nullable=True, index=True)

    # 묶음 전체를 대표하는 검색 의도
    intent = Column(String(20), nullable=True, index=True)

    size = Column(Integer, nullable=False, default=0)
    total_volume = Column(Integer, nullable=True)

    status = Column(String(20), nullable=False, default=CLUSTER_NEW,
                    index=True)
    titles_made = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return (f"<KeywordCluster {self.name} size={self.size} "
                f"intent={self.intent}>")
