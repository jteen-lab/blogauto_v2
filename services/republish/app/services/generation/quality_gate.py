"""발행 전 품질 게이트 — 문제 있는 글을 내보내기 전에 잡는다.

라이프인포에서 146개를 사후에 비공개했고, doooit082 계열은 105종 제목이
사이트 간 중복 게재됐다. 사후 청소로는 따라잡을 수 없어 생성 시점에 막는다.

막을 때는 반드시 사유를 남긴다. 발행이 조용히 멈추면 고장과 구분되지 않는다.

진단: docs/plans/search_visibility_all_blogs.md
순서도: docs/flowcharts/index_feedback_and_quality_gate.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...core.logger import get_logger

logger = get_logger("quality_gate", "app.log")

SETTING_KEY = "quality_gate_enabled"

# 본문 최소 길이(공백 포함). 잡학다식이 중앙값 1,588자였고 그 사이트가
# 색인 0건이다. 승인용 프롬프트도 2,000자를 요구한다.
MIN_BODY_CHARS = 1800

# 확인 불가한 사실이 글의 핵심인 유형. 라이프인포에서 걷어낸 146개가 이것이다.
# 「대한주택관리사협회 채용정보」의 연봉표가 창작이었다.
RISKY_PATTERNS = (
    (r"고객센터|전화번호|상담전화|콜센터|문의처", "연락처"),
    (r"영업시간|운영시간|진료시간|상영시간표|배차", "영업시간"),
    (r"채용공고|연봉\s*\d|급여\s*\d|시급\s*\d", "채용조건"),
    (r"현금화|상품권\s*(거래|매입|판매)", "상품권거래"),
)


@dataclass
class GateResult:
    """게이트 판정. blocked 면 발행하지 않는다."""

    blocked: bool = False
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"blocked": self.blocked, "reasons": self.reasons,
                "warnings": self.warnings}

    @property
    def message(self) -> str:
        return " / ".join(self.reasons) if self.reasons else ""


def _plain_len(markdown: str) -> int:
    """마크다운 기호를 뺀 실제 읽는 글자수."""
    text = re.sub(r"```.*?```", "", markdown or "", flags=re.S)
    text = re.sub(r"!?\[[^\]]*\]\([^)]*\)", "", text)   # 링크·이미지
    text = re.sub(r"[#*`>|_~\-]", "", text)
    return len(text.strip())


def plain_len(markdown: str) -> int:
    """게이트가 세는 것과 같은 기준의 본문 길이.

    호출자가 같은 숫자를 로그·판단에 쓸 수 있게 공개한다. 각자 따로 세면
    "1,689자로 막혔다" 와 "3,336자 생성" 이 다른 기준이 되어 비교가 안 된다.
    """
    return _plain_len(markdown)


def check_length(markdown: str, minimum: int = MIN_BODY_CHARS) -> Optional[str]:
    """본문이 너무 짧으면 사유를 돌려준다."""
    n = _plain_len(markdown)
    if n >= minimum:
        return None
    return f"본문 {n}자 (최소 {minimum}자)"


def check_risky_topic(title: str) -> Optional[str]:
    """확인 불가한 사실이 핵심인 주제인지.

    막지 않고 경고만 한다 — 같은 키워드라도 정상적인 정보 글일 수 있다
    ("우리나라 전기요금 비싼가" 는 요금이 들어가지만 정보성이다).
    """
    for pattern, label in RISKY_PATTERNS:
        if re.search(pattern, title or ""):
            return f"{label} 정보가 제목의 핵심 — 지어낸 수치가 아닌지 확인 필요"
    return None


def strip_duplicate_h1(markdown: str, title: str) -> str:
    """본문 맨 앞의 제목 반복을 제거한다.

    워드프레스·블로거 테마가 제목을 <h1> 으로 출력하는데 프롬프트가
    'H1(#) 타이틀' 을 요구해 같은 문장이 두 번 보인다. 독자에게도 거슬리고
    문서 구조도 어긋난다.
    """
    if not markdown:
        return markdown
    lines = markdown.lstrip().split("\n")
    if not lines:
        return markdown

    first = lines[0].strip()
    if not first.startswith("#"):
        return markdown

    heading = first.lstrip("#").strip()
    norm = lambda s: re.sub(r"\s+", "", s or "")  # noqa: E731
    if norm(heading) != norm(title):
        return markdown

    rest = "\n".join(lines[1:]).lstrip("\n")
    logger.info("[QUALITY_GATE] 본문 H1 중복 제거 | %s", title[:40])
    return rest


def evaluate(
    title: str, markdown: str, min_chars: int = MIN_BODY_CHARS,
) -> GateResult:
    """생성 결과를 검사한다(중복 제목 검사는 DB가 필요해 호출자가 더한다)."""
    result = GateResult()

    too_short = check_length(markdown, min_chars)
    if too_short:
        result.blocked = True
        result.reasons.append(too_short)

    risky = check_risky_topic(title)
    if risky:
        result.warnings.append(risky)

    return result


def resolve_settings(module_settings: Optional[dict]) -> Dict[str, Any]:
    """모듈 설정에서 게이트 옵션을 읽는다.

    모듈마다 성격이 달라 전역 스위치 하나로 다루기 어렵다. 예를 들어 짧은
    안내글을 의도적으로 쓰는 모듈이면 임계값을 낮춰야 한다.
    """
    gate = ((module_settings or {}).get("quality_gate") or {})
    enabled = gate.get("enabled")
    return {
        "enabled": True if enabled is None else bool(enabled),
        "min_chars": int(gate.get("min_chars") or MIN_BODY_CHARS),
    }


async def is_enabled(db) -> bool:
    """전역 스위치. 기본 켜짐."""
    from ..system_settings_service import SystemSettingsService

    raw = await SystemSettingsService.get(SETTING_KEY, db)
    if raw is None or raw == "":
        return True
    return str(raw).lower() not in ("0", "false", "off", "no")
