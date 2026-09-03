"""제목 출처 — 어디서 온 제목인지 한 곳에서 정의한다.

`temp_titles.collection_stage` 에 들어가는 값이다. 지금까지 문자열이
여기저기 흩어져 있어(`bulk_collect`·`news_collect`·`keyword_module`) 새 경로를
추가할 때마다 목록이 어긋났다.

**왜 출처를 정확히 남겨야 하는가**: 생성(L1)과 수집 중 무엇이 나은지는
추측으로 정하지 않고 실측으로 정한다(계획서 §2-6). 승격률·GSC 노출을
출처별로 비교하려면 지금부터 출처가 남아 있어야 한다. 뒤늦게 붙이면 그
사이 데이터는 비교 불가다.

계획서: docs/plans/title_tab_workplan.md §5 W1
"""
from __future__ import annotations

from typing import Dict, List

# 생성 계열
SRC_KEYWORD_MODULE = "keyword_module"   # L1 — 채택 키워드 기반 AI 생성
SRC_NEWS_GEN = "news_gen"               # L3 — 뉴스 요지 + 니치 결합

# 수집 계열
SRC_TITLE_COLLECT = "title_collect"     # ① 채택 키워드로 검색해 수집
SRC_DOMAIN_EXTRACT = "domain_extract"   # ② 저장된 도메인에서 추출

# 옛 경로(읽기 전용 — 새로 쓰지 않는다)
SRC_BULK_COLLECT = "bulk_collect"
SRC_NEWS_COLLECT = "news_collect"

GENERATED = (SRC_KEYWORD_MODULE, SRC_NEWS_GEN)
COLLECTED = (SRC_TITLE_COLLECT, SRC_DOMAIN_EXTRACT)
LEGACY = (SRC_BULK_COLLECT, SRC_NEWS_COLLECT)
ALL_SOURCES = GENERATED + COLLECTED + LEGACY

LABEL: Dict[str, str] = {
    SRC_KEYWORD_MODULE: "생성 · 키워드",
    SRC_NEWS_GEN: "생성 · 뉴스",
    SRC_TITLE_COLLECT: "수집 · 검색",
    SRC_DOMAIN_EXTRACT: "수집 · 도메인",
    SRC_BULK_COLLECT: "옛 대량수집",
    SRC_NEWS_COLLECT: "옛 뉴스수집",
}

# 화면 배지 색. 생성/수집을 한눈에 가르는 것이 목적이다.
TONE: Dict[str, str] = {
    SRC_KEYWORD_MODULE: "bg-emerald-100 text-emerald-700",
    SRC_NEWS_GEN: "bg-teal-100 text-teal-700",
    SRC_TITLE_COLLECT: "bg-blue-100 text-blue-700",
    SRC_DOMAIN_EXTRACT: "bg-indigo-100 text-indigo-700",
    SRC_BULK_COLLECT: "bg-gray-100 text-gray-500",
    SRC_NEWS_COLLECT: "bg-gray-100 text-gray-500",
}

# 화면 필터 묶음. 개별 코드를 다 노출하면 고르기 어렵다.
GROUPS: Dict[str, List[str]] = {
    "generated": list(GENERATED),
    "collected": list(COLLECTED),
    "legacy": list(LEGACY),
}
GROUP_LABEL = {
    "generated": "생성",
    "collected": "수집",
    "legacy": "옛 수집",
}


def label(code: str) -> str:
    """사람이 읽을 이름. 모르는 코드는 코드 그대로 보여 준다."""
    return LABEL.get(code, code or "-")


def tone(code: str) -> str:
    return TONE.get(code, "bg-gray-100 text-gray-500")


def is_generated(code: str) -> bool:
    return code in GENERATED


def codes_for_group(group: str) -> List[str]:
    """필터 묶음 → 실제 코드 목록. 모르는 묶음은 빈 목록."""
    return list(GROUPS.get(group, []))
