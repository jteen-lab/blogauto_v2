"""근거 등급 — 확인된 것과 확인 안 된 것을 섞지 않는다.

"이 금리가 맞다" 를 **증명할 수는 없다.** 웹에 값이 있어도 출처가 블로그면
다른 블로그를 베낀 것일 수 있고, 10년 전 정보가 지금도 돌아다닌다.
검색을 붙인 도구들도 인용 정확도에서 상당한 오류율을 보인다.

할 수 있는 것은 셋을 구분하는 것이다.

    회사가 실재하는가       확인 가능 (금융회사 조회)
    상품이 공시 대상인가     확인 가능 (금감원 공시)
    이 수치가 맞는가        **확인 불가** — 1차 출처가 없으면

그래서 값을 쓸지 말지를 등급으로 정한다.

    A 확인됨      공식 API 에 이 상품이 있다 → 공시 수치를 쓴다
    B 부분 확인   공식 도메인 자료가 있거나 여러 자료가 겹친다
                  → 수치는 "공식 안내 확인", 회사·절차 정보는 쓴다
    C 확인 불가   근거가 없다 → 발행 보류

순서도: docs/flowcharts/evidence_hold.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlsplit

from ...core.logger import get_logger

logger = get_logger("reference_evidence", "app.log")

# 등급
GRADE_A = "A"        # 공식 API 적중
GRADE_B = "B"        # 부분 확인
GRADE_C = "C"        # 확인 불가 — 보류
GRADE_NONE = "-"     # YMYL 이 아니라 등급을 매기지 않음

# 수치가 곧 사실인 주제. 여기서만 등급을 매긴다.
# 요리·여행 글까지 보류하면 아무것도 못 쓴다.
YMYL_TOPICS = (
    "금융/대출", "보험", "세금/절세", "재테크/돈관리", "부동산",
    "건강/의학", "정부지원금/복지", "시니어/노후",
)

# 제목에 이 말이 있으면 수치가 핵심이다(니치가 안 붙은 제목 대비).
YMYL_HINTS = (
    "대출", "금리", "이자", "보험", "연금", "세금", "공제", "환급",
    "한도", "수수료", "적금", "예금", "지원금", "보조금", "급여",
)

# 1차에 준하는 출처. 기관·공공이 직접 낸 문서다.
OFFICIAL_SUFFIXES = (".go.kr", ".or.kr", ".re.kr")

# 은행·카드사 등 사업자 공식 도메인. 자기 상품 설명은 1차 출처다.
OFFICIAL_HINTS = (
    "bank", "card", "capital", "insurance", "life", "securities",
    "fss.or.kr", "fsc.go.kr", "kinfa.or.kr", "korea.kr",
)

# 자료가 이보다 오래되면 최신성을 인정하지 않는다.
FRESH_DAYS = 365

# B 등급 최소 자료 수. 한 곳만 있으면 그 글의 오류를 그대로 받는다.
MIN_SOURCES = 2


@dataclass
class Evidence:
    """이 제목에 대해 무엇이 확인됐나."""

    grade: str = GRADE_NONE
    official_hit: bool = False       # 공식 API 적중
    official_docs: int = 0           # 공식 도메인 자료 수
    total_docs: int = 0              # 관련 자료 수
    fresh_docs: int = 0              # 12개월 이내 자료 수
    reasons: List[str] = field(default_factory=list)

    @property
    def hold(self) -> bool:
        """발행을 보류해야 하는가."""
        return self.grade == GRADE_C

    @property
    def allow_numbers(self) -> bool:
        """수치를 써도 되는가. A 만 허용한다."""
        return self.grade == GRADE_A

    def to_dict(self) -> Dict[str, Any]:
        return {"grade": self.grade, "official_hit": self.official_hit,
                "official_docs": self.official_docs,
                "total_docs": self.total_docs, "fresh_docs": self.fresh_docs,
                "reasons": self.reasons}

    def summary(self) -> str:
        """보류 사유로 남길 한 줄."""
        return " / ".join(self.reasons) if self.reasons else self.grade


def is_ymyl(topics: Sequence[str], title: str = "") -> bool:
    """수치가 곧 사실인 주제인가.

    니치가 안 붙은 제목도 있어 제목 낱말로 한 번 더 본다.
    """
    for topic in topics or ():
        if topic and any(y in topic for y in YMYL_TOPICS):
            return True
    text = (title or "").replace(" ", "")
    return any(hint in text for hint in YMYL_HINTS)


def is_official(url: str) -> bool:
    """1차에 준하는 출처인가.

    기관 도메인이거나, 금융사 공식 도메인으로 보이는 곳.
    블로그·카페 플랫폼은 아무리 내용이 좋아도 1차가 아니다.
    """
    host = (urlsplit(url or "").hostname or "").lower()
    if not host:
        return False
    if any(host.endswith(suffix) for suffix in OFFICIAL_SUFFIXES):
        return True
    # 플랫폼은 제외 — 도메인에 bank 가 들어가도 남의 글이다
    if any(bad in host for bad in ("blog.", "cafe.", "tistory", "naver.com",
                                   "brunch", "medium", "wordpress")):
        return False
    return any(hint in host for hint in OFFICIAL_HINTS)


def _is_fresh(raw: Any) -> bool:
    """12개월 이내인가. 날짜를 못 읽으면 판단하지 않는다(False)."""
    text = str(raw or "").strip()
    if not text:
        return False
    for pattern in ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S", "%Y.%m.%d"):
        try:
            when = datetime.strptime(text[:len(text)], pattern).date()
        except ValueError:
            continue
        return when >= date.today() - timedelta(days=FRESH_DAYS)
    # 본문에서 연도만 찾는다
    years = re.findall(r"20\d{2}", text)
    if years:
        return int(years[-1]) >= date.today().year - 1
    return False


def evaluate(
    topics: Sequence[str],
    title: str,
    official_hit: bool,
    documents: Sequence[Any],
) -> Evidence:
    """근거를 모아 등급을 매긴다.

    Args:
        topics: 이 글의 주제·하위주제 이름
        title: 제목
        official_hit: 공식 API 가 이 상품을 찾았나
        documents: 관련성 관문을 통과한 자료(url·postdate 를 본다)

    Returns:
        Evidence
    """
    if not is_ymyl(topics, title):
        return Evidence(grade=GRADE_NONE,
                        reasons=["수치가 핵심이 아닌 주제"])

    docs = list(documents or [])
    official_docs = sum(
        1 for d in docs if is_official(getattr(d, "url", "") or ""))
    fresh_docs = sum(
        1 for d in docs
        if _is_fresh(getattr(d, "postdate", None)
                     or getattr(d, "published", None)))

    found = Evidence(official_hit=official_hit, official_docs=official_docs,
                     total_docs=len(docs), fresh_docs=fresh_docs)

    if official_hit:
        found.grade = GRADE_A
        found.reasons.append("공식 공시에서 이 상품을 찾음")
        return found

    if official_docs >= 1:
        found.grade = GRADE_B
        found.reasons.append(f"공식 도메인 자료 {official_docs}건")
        return found

    if len(docs) >= MIN_SOURCES and fresh_docs >= 1:
        found.grade = GRADE_B
        found.reasons.append(
            f"자료 {len(docs)}건(최근 {fresh_docs}건) — 수치는 쓰지 않음")
        return found

    found.grade = GRADE_C
    if not docs:
        found.reasons.append("관련 자료를 찾지 못함")
    else:
        if len(docs) < MIN_SOURCES:
            found.reasons.append(f"자료가 {len(docs)}건뿐")
        if not fresh_docs:
            found.reasons.append("최근 1년 자료가 없음")
        found.reasons.append("공식 출처 없음")
    logger.info("[EVIDENCE] C 등급 | '%s' | %s", title[:40], found.summary())
    return found


def directive(found: Evidence) -> str:
    """등급에 맞는 프롬프트 지시문.

    A 는 수치를 쓰게 하고, B 는 확인처로 돌린다. 같은 프롬프트로 두 경우를
    다루면 자료가 없을 때 AI 가 빈칸을 상상으로 채운다.
    """
    if found.grade == GRADE_A:
        return (
            "■ 수치 사용\n"
            "- 위 공식 자료의 값만 씁니다. 기관 공시 기준임을 밝히세요.\n"
            "- 공식 자료에 없는 항목은 \"공식 안내 확인\" 으로 두세요.")
    if found.grade == GRADE_B:
        return (
            "■ 수치 사용 (중요)\n"
            "- 이 상품은 **공식 공시에서 확인되지 않았습니다.**\n"
            "- 금리·한도·수수료 같은 숫자를 쓰지 마세요. 참고자료에 있어도\n"
            "  출처가 확인되지 않은 값이므로 쓰지 않습니다.\n"
            "- 대신 무엇을 어디서 확인해야 하는지 알려 주세요\n"
            "  (해당 금융사 공식 홈페이지, 금융감독원 금융상품통합비교공시,\n"
            "   금융소비자 정보포털 파인의 제도권 금융회사 조회).\n"
            "- 상품의 존재나 조건을 단정하지 말고 \"확인이 필요하다\" 로 씁니다.")
    return ""
