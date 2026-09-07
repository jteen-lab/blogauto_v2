"""등록 프리셋 — 주소·응답 경로를 사람이 타이핑하지 않게 한다.

레지스트리는 `options` 에 `items_path`·`field_map` 같은 값을 받는다. 그걸
화면에서 손으로 적게 하면 아무도 못 쓴다. 자주 쓰는 API 는 여기에 미리
적어 두고, 사용자는 **인증키만** 넣는다.

프리셋에 없는 API 도 등록할 수 있다 — 그때만 주소와 옵션을 직접 적는다.

순서도: docs/flowcharts/reference_accuracy.md
"""
from __future__ import annotations

from typing import Any, Dict, List

from ....models.external_source import (
    ADAPTER_DATA_GO_KR, ADAPTER_FSS_FINLIFE,
)

# 금감원은 8종이 주소만 다르다. 같은 어댑터·같은 인증키를 쓴다.
_FSS = "https://finlife.fss.or.kr/finlifeapi/{op}.json"

PRESETS: List[Dict[str, Any]] = [
    {
        # **권장.** 주소의 {op} 를 어댑터가 제목에 맞춰 채운다. 대출 니치는
        # 주담대·전세·신용대출을 다 다루므로, 종류마다 따로 등록하면
        # 같은 인증키를 세 번 넣게 된다.
        "code": "fss_all",
        "name": "금감원 금융상품 공시 (자동 선택 · 권장)",
        "adapter": ADAPTER_FSS_FINLIFE,
        "endpoint": _FSS.format(op="{op}"),
        "options": {"top_fin_grp_no": "020000", "max_facts": 2},
        "match_topics": ["금융/대출", "재테크/돈관리", "부동산",
                         "시니어/노후"],
        "match_keywords": ["대출", "금리", "예금", "적금", "연금", "한도",
                           "전세", "주담대", "아파트론"],
        "key_hint": "금감원 오픈API 인증키 (finlife.fss.or.kr 에서 신청)",
    },
    {
        "code": "fss_mortgage",
        "name": "금감원 주택담보대출 공시 (이 종류만)",
        "adapter": ADAPTER_FSS_FINLIFE,
        "endpoint": _FSS.format(op="mortgageLoanProductsSearch"),
        "options": {"top_fin_grp_no": "020000", "max_facts": 2},
        "match_topics": ["금융/대출", "부동산"],
        "match_keywords": ["주택담보", "아파트론", "주담대", "담보대출"],
        "key_hint": "금감원 오픈API 인증키 (finlife.fss.or.kr 에서 신청)",
    },
    {
        "code": "fss_rent",
        "name": "금감원 전세자금대출 공시 (이 종류만)",
        "adapter": ADAPTER_FSS_FINLIFE,
        "endpoint": _FSS.format(op="rentHouseLoanProductsSearch"),
        "options": {"top_fin_grp_no": "020000", "max_facts": 2},
        "match_topics": ["금융/대출", "부동산"],
        "match_keywords": ["전세자금", "전세대출", "전세보증"],
        "key_hint": "금감원 오픈API 인증키",
    },
    {
        "code": "fss_credit",
        "name": "금감원 개인신용대출 공시 (이 종류만)",
        "adapter": ADAPTER_FSS_FINLIFE,
        "endpoint": _FSS.format(op="creditLoanProductsSearch"),
        "options": {"top_fin_grp_no": "020000", "max_facts": 2},
        "match_topics": ["금융/대출"],
        "match_keywords": ["신용대출", "마이너스통장", "비상금대출"],
        "key_hint": "금감원 오픈API 인증키",
    },
    {
        "code": "fss_deposit",
        "name": "금감원 정기예금 공시 (이 종류만)",
        "adapter": ADAPTER_FSS_FINLIFE,
        "endpoint": _FSS.format(op="depositProductsSearch"),
        "options": {"top_fin_grp_no": "020000", "max_facts": 2},
        "match_topics": ["재테크/돈관리", "금융/대출"],
        "match_keywords": ["정기예금", "예금금리", "예치"],
        "key_hint": "금감원 오픈API 인증키",
    },
    {
        "code": "fss_saving",
        "name": "금감원 적금 공시 (이 종류만)",
        "adapter": ADAPTER_FSS_FINLIFE,
        "endpoint": _FSS.format(op="savingProductsSearch"),
        "options": {"top_fin_grp_no": "020000", "max_facts": 2},
        "match_topics": ["재테크/돈관리"],
        "match_keywords": ["적금", "청약", "저축"],
        "key_hint": "금감원 오픈API 인증키",
    },
    {
        # 실호출로 확정한 규격(2026-09-07). 짐작으로 적었다가 두 번 틀렸다.
        #   주소   .../policyNewsService2/policyNewsList2
        #   필수   startDate·endDate (YYYYMMDD)
        #   제약   범위 최대 3일 — 넘기면 THREE_DAYS_OVER_ERROR
        #   응답   XML, 항목은 <NewsItem>
        # v1(policyNewsService/policyNewsList)은 같은 키로 안 된다.
        "code": "policy_briefing",
        "name": "정책브리핑 정책뉴스·보도자료",
        "adapter": ADAPTER_DATA_GO_KR,
        "endpoint": ("https://apis.data.go.kr/1371000/policyNewsService2/"
                     "policyNewsList2"),
        "options": {
            "items_path": ["response", "body", "NewsItem"],
            "title_field": "Title",
            "date_field": "ApproveDate",
            "field_map": {
                "제목": "Title",
                "부제": "SubTitle1",
                "내용": "DataContents",
                "승인일": "ApproveDate",
            },
            # 날짜가 필수이고 범위가 3일을 넘으면 거절한다
            "date_range_days": 3,
            "date_params": {"start": "startDate", "end": "endDate"},
            "rows": 20, "max_facts": 3,
        },
        "match_topics": ["정부지원금/복지", "시니어/노후", "세금/절세"],
        "match_keywords": ["정책", "지원금", "제도", "개편", "시행"],
        "key_hint": "공공데이터포털 일반 인증키",
    },
]

_BY_CODE = {p["code"]: p for p in PRESETS}

# 어댑터를 고르면 채워 줄 기본 주소. 직접 입력에서 주소를 몰라
# "주소를 입력하세요" 로 막히던 자리다.
ADAPTER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    ADAPTER_FSS_FINLIFE: {
        "endpoint": _FSS.format(op="{op}"),
        "options": {"top_fin_grp_no": "020000", "max_facts": 2},
        "hint": "{op} 자리는 제목에 맞는 상품 종류로 자동 치환됩니다",
    },
    ADAPTER_DATA_GO_KR: {
        "endpoint": "",
        "options": {"items_path": ["response", "body", "items", "item"],
                    "rows": 10, "max_facts": 3},
        "hint": "공공데이터포털에서 받은 요청 주소를 붙여넣으세요",
    },
}


def adapter_default(adapter: str) -> Dict[str, Any]:
    """어댑터 기본값. 모르는 어댑터면 빈 dict."""
    return dict(ADAPTER_DEFAULTS.get(adapter) or {})


def get(code: str) -> Dict[str, Any]:
    """프리셋 하나. 없으면 빈 dict."""
    return dict(_BY_CODE.get(code) or {})


def listing() -> List[Dict[str, Any]]:
    """화면에 뿌릴 목록. 인증키는 프리셋에 없다."""
    return [
        {"code": p["code"], "name": p["name"], "adapter": p["adapter"],
         "match_topics": p["match_topics"],
         "match_keywords": p["match_keywords"],
         "key_hint": p.get("key_hint", ""),
         # 주소를 확정하지 못했거나 오퍼레이션이 API 마다 다른 프리셋은
         # 사용자가 화면에서 고칠 수 있어야 한다
         "needs_endpoint": (not p.get("endpoint")
                            or bool(p.get("editable_endpoint"))),
         # 고칠 수 있는 주소는 미리 채워 준다
         "default_endpoint": (p.get("endpoint", "")
                              if p.get("editable_endpoint") else "")}
        for p in PRESETS
    ]
