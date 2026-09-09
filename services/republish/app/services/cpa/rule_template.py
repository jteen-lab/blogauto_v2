"""정형 규칙 항목 — 무엇이 비었는지 보이게 한다.

규칙을 유형별로만 늘어놓으면 **무엇을 못 뽑았는지 알 수 없다.** 오퍼마다
요구가 달라 "이 오퍼엔 원래 없는 것"과 "AI 가 놓친 것"이 구분되지 않는다.

그래서 **요구가 가장 많은 오퍼**를 기준으로 칸을 미리 만든다. 부산ㅎr늘안과
의료광고 가이드라인(규칙 22건·13유형)이 그 기준이다. 추출 결과를 이 칸에
넣고, 빈 칸은 빈 채로 둔다. 칸에 없는 규칙은 따로 모아 사람이 확인한다.

**칸을 늘리는 것은 안전하다.** 빈 칸은 그냥 비어 있을 뿐이다. 반대로 칸이
없으면 그 요구는 조용히 사라진다.

순서도: docs/flowcharts/cpa_offer.md
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ...core.logger import get_logger

logger = get_logger("cpa_rule_template", "app.log")

# 정형 항목. (키, 이름, 받는 규칙 유형, 없으면 위험한가, 설명)
#
# `critical` 은 비면 글을 내보내면 안 되는 항목이다. 대가성 문구가 없으면
# 공정위 위반이고, 업종에 따라 주체 명시가 없으면 유인알선이 된다.
SLOTS: List[Dict[str, Any]] = [
    {"key": "ftc_notice", "label": "공정위 대가성 문구",
     "types": ["must_include"], "critical": True,
     "hint": "표시하지 않으면 위법입니다"},
    {"key": "notice_position", "label": "문구 위치",
     "types": ["position"], "critical": True,
     "hint": "2024-12-01 개정으로 끝부분 게재 불가"},
    {"key": "subject_notice", "label": "광고 주체 명시",
     "types": ["must_include"], "critical": False,
     "hint": "의료·법률은 주체를 밝히지 않으면 위반"},
    {"key": "brand_form", "label": "브랜드 표기 규칙",
     "types": ["replace", "must_not_include"], "critical": False,
     "hint": "풀네임 금지·난독화 표기 등"},
    {"key": "confusable", "label": "혼동 브랜드 금지",
     "types": ["must_not_include"], "critical": False,
     "hint": "다른 지점·유사 상호"},
    {"key": "banned_words", "label": "금지 낱말",
     "types": ["must_not_include"], "critical": False,
     "hint": "최상급·확신 표현 등"},
    {"key": "banned_topics", "label": "금지 주제",
     "types": ["forbidden_topic"], "critical": False,
     "hint": "후기·비용 공개·할인 소구 등"},
    {"key": "banned_patterns", "label": "금지 형태(수치·연락처)",
     "types": ["pattern"], "critical": False,
     "hint": "할인율·건수·전화번호"},
    {"key": "softening", "label": "순화 대체 문구",
     "types": ["replace"], "critical": False,
     "hint": "무료 → 지원해드립니다 등"},
    {"key": "absent_items", "label": "취급하지 않는 항목",
     "types": ["must_not_include"], "critical": False,
     "hint": "본원에 없는 시술·상품"},
    {"key": "conditional", "label": "조건부 필수",
     "types": ["conditional"], "critical": False,
     "hint": "X 를 쓰면 Y 도 반드시"},
    {"key": "channels", "label": "매체 허용·금지",
     "types": ["channel"], "critical": False,
     "hint": "검색광고·SNS·카페 등"},
    {"key": "assets", "label": "사용 가능한 자료",
     "types": ["asset"], "critical": False,
     "hint": "심의 배너·제공 이미지"},
    {"key": "link_policy", "label": "링크 제약",
     "types": ["link_policy"], "critical": False,
     "hint": "타사 링크 금지 등"},
    {"key": "targeting", "label": "대상·전환 조건",
     "types": ["conversion"], "critical": False,
     "hint": "미승인 사유·접수 항목·지역·나이"},
    {"key": "required_topics", "label": "반드시 다룰 내용",
     "types": ["required_topic"], "critical": False,
     "hint": "대출 목적이 아님을 명시 등"},
    {"key": "keywords", "label": "추천 키워드",
     "types": ["content_axis"], "critical": False,
     "hint": "제목·글 소재의 출발점"},
    {"key": "facts", "label": "사실 정보",
     "types": ["content_source"], "critical": False,
     "hint": "여기 있는 것만 사실로 쓴다"},
    {"key": "advisory", "label": "사람이 볼 항목",
     "types": ["advisory"], "critical": False,
     "hint": "기계가 검사할 수 없는 당부"},
]

# 유형별 기본 칸. 힌트에 안 걸리면 여기로 간다.
# 이게 없으면 "유형을 받는 첫 칸" 으로 다 몰린다 — 최상급 금지어가
# 브랜드 표기 칸에 들어가는 식이다(실측으로 잡음).
_DEFAULT: Dict[str, str] = {
    "must_include": "subject_notice",
    "must_not_include": "banned_words",
    "forbidden_topic": "banned_topics",
    "pattern": "banned_patterns",
    "replace": "softening",
    "position": "notice_position",
    "conditional": "conditional",
    "channel": "channels",
    "asset": "assets",
    "link_policy": "link_policy",
    "conversion": "targeting",
    "required_topic": "required_topics",
    "content_axis": "keywords",
    "content_source": "facts",
    "advisory": "advisory",
}

# 기본 칸이 아닌 곳으로 보낼 낱말. 규칙 어디에든 있으면 그 칸으로 간다.
_HINTS: List[tuple] = [
    ("ftc_notice", ("애드릭스 수익", "애드릭스 커미션", "애드릭스 포인트",
                    "대가성", "경제적 대가")),
    ("subject_notice", ("주최", "광고책임변호사", "홍보성 내용")),
    ("confusable", ("서울점", "강남점", "부산점", "타사", "타 법", "지점")),
    ("brand_form", ("풀네임", "안과명", "상호명", "표기")),
    ("absent_items", ("본원에 없", "진행하지 않", "미보유", "취급하지 않")),
]


def _slot_for(rule: Dict[str, Any]) -> Optional[str]:
    """이 규칙이 들어갈 칸. 없으면 None(= 칸 밖 규칙)."""
    kind = (rule or {}).get("type")
    blob = f"{rule.get('value') or ''} {rule.get('target') or ''} " \
           f"{rule.get('source_quote') or ''}"

    # ① 값으로 먼저 가른다 — 같은 유형이 여러 칸에 걸리기 때문이다
    for key, words in _HINTS:
        slot = next((s for s in SLOTS if s["key"] == key), None)
        if not slot or kind not in slot["types"]:
            continue
        if any(word in blob for word in words):
            return key

    # ② 유형별 기본 칸
    return _DEFAULT.get(kind)


def assign(rules: Sequence[dict],
           ftc_notice: str = "") -> Dict[str, Any]:
    """추출된 규칙을 정형 칸에 넣는다.

    Args:
        rules: 추출·수기 추가된 규칙
        ftc_notice: 고정 서식에서 뽑은 대가성 문구(있으면 그 칸을 채운다)

    Returns:
        {"slots": [...], "extras": [...], "missing": [...], "filled": n}
        `extras` 는 칸에 없는 규칙이다 — 버리지 않고 사람이 확인한다.
        `missing` 은 빈 칸이다 — 원래 없는 것인지 놓친 것인지 사람이 본다.
    """
    buckets: Dict[str, List[dict]] = {s["key"]: [] for s in SLOTS}
    extras: List[dict] = []

    for rule in rules or []:
        key = _slot_for(rule)
        if key:
            buckets[key].append(rule)
        else:
            extras.append(rule)

    if ftc_notice and not buckets["ftc_notice"]:
        buckets["ftc_notice"].append({
            "type": "must_include", "scope": "all", "target": "대가성 문구",
            "value": ftc_notice, "severity": "block",
            "source_quote": "[고정 서식] 대가성 문구 표시",
        })

    slots = [{**s, "rules": buckets[s["key"]], "count": len(buckets[s["key"]])}
             for s in SLOTS]
    missing = [s["key"] for s in slots if not s["count"]]
    filled = len(SLOTS) - len(missing)

    logger.info("[CPA_TEMPLATE] 채워진 칸 %d/%d · 칸 밖 규칙 %d건",
                filled, len(SLOTS), len(extras))
    return {"slots": slots, "extras": extras, "missing": missing,
            "filled": filled, "total": len(SLOTS)}


def critical_missing(result: Dict[str, Any]) -> List[str]:
    """비면 글을 내보내면 안 되는 칸 중 빈 것."""
    return [s["label"] for s in result.get("slots", [])
            if s.get("critical") and not s.get("count")]
