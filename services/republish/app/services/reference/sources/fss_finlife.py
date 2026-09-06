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
}
OPTION_LABELS = {
    "mrtg_type_nm": "담보 유형",
    "rpay_type_nm": "상환 방식",
    "lend_rate_type_nm": "금리 유형",
    "lend_rate_min": "최저 금리(%)",
    "lend_rate_max": "최고 금리(%)",
    "lend_rate_avg": "전월 평균 금리(%)",
    "intr_rate_type_nm": "저축 금리 유형",
    "intr_rate": "저축 금리(%)",
    "intr_rate2": "최고 우대금리(%)",
    "save_trm": "저축 기간(개월)",
}


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
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(source.endpoint, params=params)
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


def _match_products(base_list: List[dict], query: str,
                    entities: List[str]) -> List[dict]:
    """상품명이 개체와 맞는 것만.

    개체가 없으면 아무것도 고르지 않는다 — 목록 첫 상품을 주면 그게 곧
    엉뚱한 상품이다.
    """
    from ..relevance import matches

    targets = [e for e in (entities or []) if e]
    if not targets:
        targets = [w for w in (query or "").split() if len(w) >= 2]
    if not targets:
        return []

    # 좁은 것부터: 첫 개체(가장 고유) → 전체 개체
    for scope in (targets[:1], targets):
        hit = [
            item for item in base_list
            if matches(f"{item.get('fin_prdt_nm', '')} "
                       f"{item.get('kor_co_nm', '')}", scope)
        ]
        if hit:
            return hit
    return []


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
        raw = row.get("lend_rate_min") or row.get("intr_rate")
        try:
            rated.append((float(raw), row))
        except (TypeError, ValueError):
            continue
    if rated:
        return min(rated, key=lambda pair: pair[0])[1]
    return options[0]
