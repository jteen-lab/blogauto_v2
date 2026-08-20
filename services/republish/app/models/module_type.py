"""
모듈 타입 마스터 테이블

Features:
- 모듈의 타입을 정의하는 마스터 테이블
- 프롬프트, 생성, 수집, 데이터 등의 타입 관리
- UI에서 사용할 아이콘 및 정렬 순서 포함
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


class ModuleType(Base):
    """모듈 타입 마스터"""
    __tablename__ = "module_types"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, comment="모듈 타입 코드")
    name = Column(String(100), nullable=False, comment="모듈 타입 이름")
    icon = Column(String(50), nullable=True, comment="이모지 또는 아이콘 클래스")
    display_order = Column(Integer, default=0, comment="화면 표시 순서")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 관계
    modules = relationship("Module", back_populates="module_type")

    def __repr__(self) -> str:
        return f"<ModuleType(code='{self.code}', name='{self.name}')>"

    @classmethod
    def get_default_types(cls) -> list[dict]:
        """기본 모듈 타입 목록 반환"""
        return [
            {
                "code": "growth_profile",
                "name": "성장 프로파일",
                "icon": "📈",
                "display_order": 0
            },
            {
                "code": "prompt",
                "name": "프롬프트/생성",
                "icon": "💭",
                "display_order": 1
            },
            {
                "code": "generate",
                "name": "생성",
                "icon": "🤖",
                "display_order": 2
            },
            {
                "code": "collect",
                "name": "수집",
                "icon": "🔍",
                "display_order": 3
            },
            {
                "code": "data",
                "name": "데이터",
                "icon": "📊",
                "display_order": 4
            },
            {
                "code": "contact_form",
                "name": "애드센스 필수구성",
                "icon": "📋",
                "display_order": 5
            }
        ]