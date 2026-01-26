"""
동작 로그 모델

시스템에서 발생하는 각종 동작을 기록합니다.
- 크롤링, 매칭, 발행 등의 작업 로그
- INFO, WARN, ERROR, SUCCESS 레벨
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from ..core.database import Base


class ActionLog(Base):
    """동작 로그 테이블"""

    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 로그 레벨 (INFO, WARN, ERROR, SUCCESS)
    level = Column(String(20), nullable=False, default="INFO")

    # 로그 메시지
    message = Column(Text, nullable=False)

    # 로그 카테고리 (crawl, match, publish, system 등)
    category = Column(String(50), nullable=True)

    # 관련 리소스 정보 (선택적)
    resource_type = Column(String(50), nullable=True)  # blog, title, flow 등
    resource_id = Column(Integer, nullable=True)

    # 생성 시간
    timestamp = Column(DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f"<ActionLog [{self.level}] {self.message[:50]}>"
