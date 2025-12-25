"""
일일 발행 카운터 모델

Features:
- Google 계정별 일일 발행 횟수 추적
- 블로그별 발행 제한 관리
- 발행/재발행 구분 카운팅
- 정책 준수 검증
"""
from sqlalchemy import Column, Integer, Date, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import date, datetime
from typing import Dict, Any

from ..core.database import Base


class DailyPublishCounter(Base):
    """일일 발행 카운터 모델"""

    __tablename__ = "daily_publish_counters"

    # 기본 정보
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True, comment="날짜")
    google_credential_id = Column(
        Integer,
        ForeignKey("google_credentials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Google 계정 ID"
    )
    blog_id = Column(
        Integer,
        ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="블로그 ID"
    )

    # 카운터
    publish_count = Column(
        Integer,
        default=0,
        nullable=False,
        comment="신규 발행 횟수"
    )
    republish_count = Column(
        Integer,
        default=0,
        nullable=False,
        comment="재발행 횟수"
    )

    # 제약 조건: 날짜별 블로그별로 하나의 레코드만
    __table_args__ = (
        UniqueConstraint('date', 'blog_id', name='uq_date_blog'),
    )

    # 관계 설정
    google_credential = relationship("GoogleCredential")
    blog = relationship("Blog")

    def __repr__(self) -> str:
        return (f"<DailyPublishCounter(date={self.date}, blog_id={self.blog_id}, "
                f"publish={self.publish_count}, republish={self.republish_count})>")

    def __str__(self) -> str:
        return f"Counter {self.date} Blog#{self.blog_id} ({self.total_count}회)"

    @property
    def total_count(self) -> int:
        """총 발행 횟수"""
        return self.publish_count + self.republish_count

    @property
    def is_today(self) -> bool:
        """오늘 날짜인지 확인"""
        return self.date == date.today()

    @property
    def is_weekend(self) -> bool:
        """주말인지 확인"""
        return self.date.weekday() >= 5  # 5=토요일, 6=일요일

    def increment_publish(self) -> None:
        """신규 발행 카운트 증가"""
        self.publish_count += 1

    def increment_republish(self) -> None:
        """재발행 카운트 증가"""
        self.republish_count += 1

    def reset_counts(self) -> None:
        """카운트 초기화"""
        self.publish_count = 0
        self.republish_count = 0

    def can_publish(self, max_daily_per_blog: int) -> bool:
        """블로그별 일일 제한 확인"""
        return self.total_count < max_daily_per_blog

    def can_republish(self, max_daily_per_blog: int) -> bool:
        """재발행 가능 여부 확인 (신규 발행 제한과 동일)"""
        return self.can_publish(max_daily_per_blog)

    def remaining_quota(self, max_daily_per_blog: int) -> int:
        """남은 발행 할당량"""
        return max(0, max_daily_per_blog - self.total_count)

    def get_publish_ratio(self, max_daily_per_blog: int) -> float:
        """발행 비율 (0.0 ~ 1.0)"""
        if max_daily_per_blog <= 0:
            return 0.0
        return min(1.0, self.total_count / max_daily_per_blog)

    def is_quota_exhausted(self, max_daily_per_blog: int) -> bool:
        """할당량 소진 여부"""
        return self.total_count >= max_daily_per_blog

    def is_quota_near_limit(self, max_daily_per_blog: int, threshold: float = 0.8) -> bool:
        """할당량 한계 근접 여부"""
        return self.get_publish_ratio(max_daily_per_blog) >= threshold

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "google_credential_id": self.google_credential_id,
            "blog_id": self.blog_id,
            "publish_count": self.publish_count,
            "republish_count": self.republish_count,
            "total_count": self.total_count,
            "is_today": self.is_today,
            "is_weekend": self.is_weekend
        }

    @classmethod
    def get_or_create_today(cls, session, google_credential_id: int, blog_id: int) -> "DailyPublishCounter":
        """오늘 날짜 카운터 조회 또는 생성"""
        today = date.today()
        counter = session.query(cls).filter(
            cls.date == today,
            cls.blog_id == blog_id
        ).first()

        if not counter:
            counter = cls(
                date=today,
                google_credential_id=google_credential_id,
                blog_id=blog_id,
                publish_count=0,
                republish_count=0
            )
            session.add(counter)

        return counter