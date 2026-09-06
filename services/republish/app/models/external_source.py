"""외부 자료원 등록표 — 어떤 API 를 언제 부를지 **데이터로** 정한다.

니치마다 `if 금융: 금감원 호출` 을 코드에 박으면 API 가 늘 때마다 코드를
고쳐야 한다. 여기에 등록해 두면 글 생성 때 제목·니치를 보고 알아서 고른다.

    match_topics    이 주제(니치)일 때만 후보
    match_keywords  제목에 이 말이 있을 때만 후보
    adapter         응답을 우리 형태로 바꾸는 코드의 이름

**어댑터는 코드다.** 공공데이터포털처럼 인증·응답이 표준화된 곳은 어댑터
하나로 여러 API 를 받지만(등록만 하면 끝), 금감원처럼 자체 규격은 전용
어댑터가 필요하다. 그래서 `adapter` 는 화면에서 고르는 값이다.

순서도: docs/flowcharts/reference_accuracy.md
"""
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, JSON, String, Text,
)
from sqlalchemy.sql import func

from ..core.database import Base

# 어댑터 코드. 새 어댑터를 만들면 여기에 더한다.
ADAPTER_DATA_GO_KR = "data_go_kr"   # 공공데이터포털 표준(다수 API 공용)
ADAPTER_FSS_FINLIFE = "fss_finlife"  # 금감원 금융상품한눈에(자체 규격)

ADAPTERS = (ADAPTER_DATA_GO_KR, ADAPTER_FSS_FINLIFE)


class ExternalSource(Base):
    """1차 출처 API 한 개."""

    __tablename__ = "external_sources"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True,
                  comment="식별자 (예: fss_loan_mortgage)")
    name = Column(String(200), nullable=False, comment="화면에 보일 이름")
    adapter = Column(String(50), nullable=False,
                     comment="응답을 해석할 어댑터 코드")

    endpoint = Column(String(500), nullable=False, comment="호출 주소")
    # 인증키는 암호화해 둔다. 공공데이터포털은 serviceKey, 금감원은 auth 다.
    auth_key_encrypted = Column(Text, nullable=True)
    # 어댑터별 추가 값 (금감원 topFinGrpNo, 포털 응답 경로 등)
    options = Column(JSON, nullable=True, default=dict)

    # 언제 이 소스를 쓰나 — 둘 다 비면 "아무 때나" 가 아니라 "안 쓴다"
    match_topics = Column(JSON, nullable=True, default=list,
                          comment="주제명 목록 (예: 금융/대출)")
    match_keywords = Column(JSON, nullable=True, default=list,
                            comment="제목에 있으면 후보 (예: 대출, 금리)")

    enabled = Column(Boolean, nullable=False, default=True)
    # 하루 호출 한도. 공공데이터포털 개발계정은 보통 1,000회다.
    daily_limit = Column(Integer, nullable=False, default=1000)

    note = Column(Text, nullable=True, comment="발급처·신청 방법 메모")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ExternalSource({self.code}, adapter={self.adapter})>"
