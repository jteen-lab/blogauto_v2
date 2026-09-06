"""금융감독원 금융상품한눈에 — 대출·예금 금리의 **1차 출처**.

공공데이터포털 밖 자체 규격이라 전용 어댑터가 필요하다. 대신 한 번
만들면 8종을 다 쓴다(주담대·전세·신용대출·개인사업자·예금·적금·연금·회사).

    https://finlife.fss.or.kr/finlifeapi/{op}.json
      ?auth=키&topFinGrpNo=020000&pageNo=1

응답은 상품 기본정보(baseList)와 금리 옵션(optionList)이 **따로** 온다.
`fin_prdt_cd` 로 이어 붙여야 "이 상품의 금리" 가 된다.

**상품명이 안 맞으면 빈손으로 돌아온다.** 비슷한 상품을 대신 주지 않는다 —
"우리아파트론" 자리에 다른 주담대 조건이 들어가면 사실이 아닌 글이 된다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from ....core.logger import get_logger
from .base import SourceAdapter, SourceFact, SourceResult, decrypt_key

logger = get_logger("source_fss", "app.log")

TIMEOUT = 20.0

# 권역 코드. 은행만 볼지 저축은행까지 볼지는 등록표 options 에서 정한다.
GRP_BANK = "020000"

# 상품 종류별 조회 이름. **주소가 종류마다 다르다.**
#
# 대출 니치는 주담대·전세·신용대출을 다 다룬다. 종류마다 소스를 따로
# 등록하게 하면 인증키가 같은데도 세 번 등록해야 한다. 제목을 보고
# 알아서 고른다 — 등록은 하나로 끝난다.
OPS = {
    "mortgage": "mortgageLoanProductsSearch",
    "rent": "rentHouseLoanProductsSearch",
    "credit": "creditLoanProductsSearch",
    "deposit": "depositProductsSearch",
    "saving": "savingProductsSearch",
    "annuity": "annuitySavingProductsSearch",
}

# 제목에 이 말이 있으면 그 종류다. 위에서부터 먼저 맞는 것을 쓴다 —
# "전세자금대출" 은 '전세' 와 '대출' 에 다 걸리므로 순서가 중요하다.
OP_HINTS = [
    ("rent", ("전세", "임차", "보증금")),
    ("mortgage", ("주택담보", "주담대", "아파트론", "담보대출", "부동산담보")),
    ("annuity", ("연금저축", "연금")),
    ("saving", ("적금", "청약", "부금")),
    ("deposit", ("예금", "예치", "정기예")),
    ("credit", ("신용대출", "마이너스", "비상금", "직장인대출", "대출")),
]

# 어느 것에도 안 걸릴 때. 대출 니치가 대부분이라 신용대출을 기본으로 둔다.
DEFAULT_OP = "credit"

# 응답 항목 → 사람이 읽을 이름
BASE_LABELS = {
    "kor_co_nm": "금융회사",
    "fin_prdt_nm": "상품명",
    "join_way": "가입 방법",
    "loan_inci_expn": "대출 부대비용",
    "erly_rpay_fee": "중도상환수수료",
    "dly_rate": "연체 이자율",
    "loan_lmt": "대출 한도",
    "mtrt_int": "만기 후 이자율",
    "spcl_cnd": "우대조건",
    # 개인신용대출
    "crdt_prdt_type_nm": "대출 종류",
    "cb_name": "신용평가사",
}
OPTION_LABELS = {
    # 담보·전세 대출
    "mrtg_type_nm": "담보 유형",
    "rpay_type_nm": "상환 방식",
    "lend_rate_type_nm": "금리 유형",
    "lend_rate_min": "최저 금리(%)",
    "lend_rate_max": "최고 금리(%)",
    "lend_rate_avg": "전월 평균 금리(%)",
    # 예금·적금·연금
    "intr_rate_type_nm": "저축 금리 유형",
    "intr_rate": "저축 금리(%)",
    "intr_rate2": "최고 우대금리(%)",
    "save_trm": "저축 기간(개월)",
    # 개인신용대출 — 항목 이름이 위와 **완전히 다르다.**
    # 이걸 안 넣어서 신용대출 조회에 금리가 하나도 안 나왔다.
    "crdt_lend_rate_type_nm": "금리 구분",
    "crdt_grad_avg": "평균 금리(%)",
    "crdt_grad_1": "신용점수 900 초과 금리(%)",
    "crdt_grad_4": "신용점수 801~900 금리(%)",
    "crdt_grad_5": "신용점수 701~800 금리(%)",
    "crdt_grad_6": "신용점수 601~700 금리(%)",
    "crdt_grad_10": "신용점수 501~600 금리(%)",
    "crdt_grad_11": "신용점수 401~500 금리(%)",
    "crdt_grad_12": "신용점수 301~400 금리(%)",
    "crdt_grad_13": "신용점수 300 이하 금리(%)",
}

# 값이 있는데 이름을 모르는 항목까지 버리면, 상품 종류가 바뀔 때마다
# 금리가 통째로 사라진다. 아래 것들만 빼고 나머지는 원래 키로 붙인다.
SKIP_KEYS = {
    "dcls_month", "fin_co_no", "fin_prdt_cd", "crdt_prdt_type",
    "dcls_strt_day", "dcls_end_day", "fin_co_subm_day",
}


def pick_op(text: str) -> str:
    """제목·질의를 보고 어느 상품 종류인지 고른다.

    등록은 하나로 하고, 부를 때 종류를 정한다. 그래서 대출 니치에서
    주담대 글과 전세 글이 각각 맞는 공시를 본다.
    """
    haystack = (text or "").replace(" ", "")
    for op, hints in OP_HINTS:
        if any(hint in haystack for hint in hints):
            return op
    return DEFAULT_OP


def resolve_endpoint(endpoint: str, query: str,
                     entities: List[str]) -> str:
    """주소에 `{op}` 가 있으면 상품 종류를 채운다.

    `{op}` 가 없으면 종류를 고정한 소스다(옛 프리셋). 그대로 쓴다.
    """
    if "{op}" not in (endpoint or ""):
        return endpoint
    op = pick_op(" ".join([query, *(entities or [])]))
    resolved = endpoint.replace("{op}", OPS.get(op, OPS[DEFAULT_OP]))
    logger.info("[FSS] 상품 종류 자동 선택 | %s | %s", op, resolved)
    return resolved


class FssFinlifeAdapter(SourceAdapter):
    """금감원 금융상품통합비교공시."""

    code = "fss_finlife"

    async def fetch(self, source: Any, query: str,
                    entities: List[str]) -> SourceResult:
        name = getattr(source, "name", "") or "금융감독원 금융상품한눈에"
        key = decrypt_key(source)
        if not key:
            return SourceResult(code=source.code, name=name,
                                error="인증키가 없습니다")

        options: Dict[str, Any] = getattr(source, "options", None) or {}
        params = {
            "auth": key,
            "topFinGrpNo": options.get("top_fin_grp_no", GRP_BANK),
            "pageNo": 1,
        }
        endpoint = resolve_endpoint(source.endpoint, query, entities)
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(endpoint, params=params)
        except Exception as e:  # noqa: BLE001
            return SourceResult(code=source.code, name=name,
                                error=f"호출 실패: {e}")

        if response.status_code != 200:
            return SourceResult(
                code=source.code, name=name,
                error=f"HTTP {response.status_code}: {response.text[:120]}")
        try:
            body = (response.json() or {}).get("result") or {}
        except Exception:  # noqa: BLE001
            return SourceResult(code=source.code, name=name,
                                error="JSON 이 아닌 응답")

        base_list = body.get("baseList") or []
        option_list = body.get("optionList") or []
        if not base_list:
            return SourceResult(code=source.code, name=name,
                                error="공시 목록이 비어 있습니다")

        picked = _match_products(base_list, query, entities)
        if not picked:
            # 억지로 비슷한 상품을 주지 않는다. 없는 게 낫다.
            logger.info("[FSS] 상품 미일치 — 빈손 반환 | query='%s' | 개체=%s",
                        query, entities)
            return SourceResult(code=source.code, name=name)

        by_code = _group_options(option_list)
        limit = int(options.get("max_facts", 2))
        facts = [
            _to_fact(product, by_code.get(product.get("fin_prdt_cd"), []),
                     name, str(body.get("prdt_div") or ""))
            for product in picked[:limit]
        ]
        return SourceResult(code=source.code, name=name, facts=facts)


# 금융회사 이름의 꼬리. 제목에서 기관을 알아보는 데 쓴다.
# 인터넷은행은 "뱅크" 로 끝난다(케이뱅크·카카오뱅크·토스뱅크). "은행" 만
# 보면 이들이 회사로 인식되지 않아, 회사 제약이 통째로 풀린다.
_COMPANY_TAILS = ("은행", "뱅크", "캐피탈", "저축은행", "카드", "증권",
                  "생명", "화재", "금고", "조합", "파이낸셜", "대부")


def _company_of(words: List[str]) -> Optional[str]:
    """제목에서 금융회사 이름을 찾는다. 없으면 None."""
    for word in words:
        if any(word.endswith(tail) for tail in _COMPANY_TAILS):
            return word
    return None


def _same_company(title_name: str, listed: str) -> bool:
    """같은 회사인가.

    제목은 "NH농협은행", 공시는 "농협은행" 처럼 접두어가 다르다. 영문
    접두어를 떼고 서로 포함하는지 본다.
    """
    import re as _re

    def norm(text: str) -> str:
        cut = _re.sub(r"^[A-Za-z]+", "", (text or "").replace(" ", ""))
        return cut or (text or "").replace(" ", "")

    left, right = norm(title_name), norm(listed)
    if not left or not right:
        return False
    return left in right or right in left


def _match_products(base_list: List[dict], query: str,
                    entities: List[str]) -> List[dict]:
    """상품명이 개체와 맞는 것만.

    **회사가 제목에 있으면 그 회사 상품만 본다.** 예전에는 개체를 넓히는
    과정에서 "전세대출" 같은 일반어가 걸려, "NH농협은행 전세대출" 글에
    중소기업은행 IBK전세대출이 붙었다(2026-09-06 실측). 다른 은행의
    금리를 이 은행 것처럼 쓰면 사실이 아닌 글이 된다.

    개체가 없으면 아무것도 고르지 않는다 — 목록 첫 상품을 주면 그게 곧
    엉뚱한 상품이다.
    """
    from ..relevance import matches

    targets = [e for e in (entities or []) if e]
    if not targets:
        targets = [w for w in (query or "").split() if len(w) >= 2]
    if not targets:
        return []

    pool = base_list
    company = _company_of(targets)
    if company:
        pool = [item for item in base_list
                if _same_company(company, item.get("kor_co_nm", ""))]
        if not pool:
            logger.info("[FSS] 회사 미일치 — 빈손 | 제목회사='%s'", company)
            return []
        # 회사를 좁혔으면 상품명만 남는다. 회사명 자체는 빼고 비교한다.
        targets = [t for t in targets if t != company] or [company]

    # 좁은 것부터: 첫 개체(가장 고유) → 전체 개체
    for scope in (targets[:1], targets):
        hit = [
            item for item in pool
            if matches(f"{item.get('fin_prdt_nm', '')} "
                       f"{item.get('kor_co_nm', '')}", scope)
        ]
        if hit:
            return _dedupe(hit)

    # 회사는 맞는데 상품명이 안 맞으면 그 회사 상품을 준다. 다른 회사를
    # 주는 것과 달리, 적어도 이 은행의 조건이라 사실이 어긋나지 않는다.
    if company and pool:
        logger.info("[FSS] 상품명 미일치 — 회사 상품으로 대체 | '%s'", company)
        return _dedupe(pool)
    return []


def _dedupe(items: List[dict]) -> List[dict]:
    """같은 상품을 한 번만. 공시는 월·회사별로 같은 상품을 여러 줄로 준다.

    중복을 안 걸러 "우리은행 신용대출상품" 이 두 번 실렸다(사용자 보고).
    """
    seen, out = set(), []
    for item in items:
        key = (item.get("fin_co_no"), item.get("fin_prdt_cd"),
               item.get("fin_prdt_nm"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _group_options(option_list: List[dict]) -> Dict[str, List[dict]]:
    """금리 옵션을 상품 코드로 묶는다."""
    out: Dict[str, List[dict]] = {}
    for row in option_list:
        code = row.get("fin_prdt_cd")
        if code:
            out.setdefault(code, []).append(row)
    return out


def _to_fact(product: dict, options: List[dict], source_name: str,
             div: str) -> SourceFact:
    """상품 하나를 사실로. 옵션은 대표 한 줄만 붙인다.

    옵션을 전부 붙이면 프롬프트가 표로 뒤덮여, 정작 설명해야 할 내용이
    밀린다. 금리가 가장 낮은 옵션 하나면 기준으로 충분하다.
    """
    fields: Dict[str, Any] = {}
    for key, label in BASE_LABELS.items():
        if product.get(key):
            fields[label] = product[key]

    best = _cheapest(options)
    if best:
        for key, label in OPTION_LABELS.items():
            if best.get(key):
                fields[label] = best[key]
        # 이름을 모르는 항목도 값이 있으면 살린다. 상품 종류가 바뀔 때마다
        # 금리가 통째로 사라지는 것보다 낫다.
        for key, value in best.items():
            if key in SKIP_KEYS or key in OPTION_LABELS:
                continue
            if value not in (None, "", "-") and not isinstance(
                    value, (dict, list)):
                fields.setdefault(key, value)

    title = (f"{product.get('kor_co_nm', '')} "
             f"{product.get('fin_prdt_nm', '')}").strip()
    return SourceFact(
        title=title or source_name, fields=fields, source_name=source_name,
        url="https://finlife.fss.or.kr/",
        published=str(product.get("dcls_month") or ""),
    )


def _cheapest(options: List[dict]) -> Optional[dict]:
    """금리가 가장 낮은 옵션. 숫자가 없으면 첫 번째."""
    if not options:
        return None
    rated = []
    for row in options:
        raw = (row.get("lend_rate_min") or row.get("intr_rate")
               or row.get("crdt_grad_avg") or row.get("crdt_grad_1"))
        try:
            rated.append((float(raw), row))
        except (TypeError, ValueError):
            continue
    if rated:
        return min(rated, key=lambda pair: pair[0])[1]
    return options[0]
