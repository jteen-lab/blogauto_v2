"""회사가 실재하는가 — 금감원 공시 참여 금융회사 조회.

"AK론 대출 금리" 글에 우리은행 신용대출 정보가 붙었다. 상품이 안 맞은
것도 문제지만, 그 전에 **AK론이라는 회사를 확인한 적이 없다.**

금감원 금융상품한눈에는 회사 목록을 따로 준다.

    https://finlife.fss.or.kr/finlifeapi/companySearch.json
      ?auth=키&topFinGrpNo=020000&pageNo=1

2026-09-07 실측: 은행 18 · 여신전문 48 · 저축은행 80 · 보험 20 ·
금융투자 7 = 173곳.

**이 목록은 제도권 전체가 아니다.** 공시에 참여하는 회사만 있다.
목록에 없다고 불법업체가 아니다 — 대부업·중개업일 수 있다. 그래서
"확인됨" 과 "확인 안 됨" 만 구분하고, 없는 회사를 나쁘다고 말하지 않는다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import httpx

from ...core.logger import get_logger

logger = get_logger("reference_company", "app.log")

ENDPOINT = "https://finlife.fss.or.kr/finlifeapi/companySearch.json"
TIMEOUT = 15.0

# 권역. 대출 글은 은행·여신전문·저축은행에서 대부분 걸린다.
GROUPS = ("020000", "030200", "030300", "050000", "060000")

# 목록은 자주 바뀌지 않는다. 글 한 편마다 5번 부르지 않는다.
CACHE_TTL = 6 * 60 * 60

_cache: Dict[str, Any] = {"at": 0.0, "names": []}


@dataclass
class CompanyCheck:
    """제목에 나온 회사를 확인했나."""

    name: Optional[str] = None      # 제목에서 찾은 회사 이름
    known: Optional[bool] = None    # True 확인됨 / False 목록에 없음 / None 모름
    matched: Optional[str] = None   # 목록에서 맞은 이름
    reason: str = ""

    @property
    def unverified(self) -> bool:
        """회사 이름은 있는데 확인이 안 된 경우."""
        return self.known is False


# 같은 회사가 목록에는 한글, 제목에는 영문으로 적힌다.
# 실측: 목록에 "오케이캐피탈 ㈜" 와 "OK저축은행" 이 함께 있다.
_INITIALS = {
    "OK": "오케이", "KB": "케이비", "NH": "엔에이치", "IBK": "아이비케이",
    "DB": "디비", "BNK": "비엔케이", "JB": "제이비", "MG": "엠지",
    "HB": "에이치비", "SBI": "에스비아이", "JT": "제이티", "MS": "엠에스",
    "DH": "디에이치", "CK": "씨케이", "OSB": "오에스비", "SC": "에스씨",
    "IM": "아이엠", "BMW": "비엠더블유", "SK": "에스케이", "LG": "엘지",
}


def _forms(text: str) -> set:
    """비교에 쓸 표기들. 영문 머리글자를 한글로도, 그 반대로도 편다."""
    import re

    base = _norm(text)
    out = {base}
    head = re.match(r"^[A-Za-z]+", base)
    if head:
        letters = head.group(0)
        tail = base[len(letters):]
        out.add(tail)                                   # 머리글자를 뗀 형태
        korean = _INITIALS.get(letters.upper())
        if korean:
            out.add(korean + tail)                      # 영문 → 한글
    for letters, korean in _INITIALS.items():
        if base.startswith(korean):
            out.add(letters + base[len(korean):])       # 한글 → 영문
    return {form for form in out if len(form) > 2}


def _strip_prefix(text: str) -> str:
    """앞에 붙은 영문·숫자를 뗀다. "NH농협은행" → "농협은행"."""
    import re

    cut = re.sub(r"^[A-Za-z0-9]+", "", text or "")
    return cut or (text or "")


def _norm(text: str) -> str:
    """비교용 정규화. 공백과 법인 표기를 뗀다."""
    out = (text or "").replace(" ", "")
    for junk in ("주식회사", "㈜", "(주)"):
        out = out.replace(junk, "")
    return out


def same_company(left: str, right: str) -> bool:
    """같은 회사로 볼 수 있나.

    제목은 "NH농협은행", 공시는 "농협은행주식회사" 처럼 앞뒤가 다르다.
    영문 접두어와 법인 표기를 떼고 **같아야** 한다.

    한글 접두어가 더 붙은 것은 다른 회사다 — "행복드림저축은행" 은
    "드림저축은행" 이 아니다. 그냥 포함 관계로 보면 이 둘이 같아진다.
    """
    lefts, rights = _forms(left), _forms(right)
    if not lefts or not rights:
        return False
    for a in lefts:
        for b in rights:
            # "우리은행" 과 "우리은행주식회사" 처럼 뒤에만 더 붙은 경우까지
            if a == b or a.startswith(b) or b.startswith(a):
                return True
    return False


async def _load_names(key: str) -> List[str]:
    """권역별 회사 이름을 모은다. 캐시가 살아 있으면 그대로 쓴다."""
    now = time.time()
    if _cache["names"] and now - _cache["at"] < CACHE_TTL:
        return _cache["names"]

    names: List[str] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for group in GROUPS:
            try:
                response = await client.get(
                    ENDPOINT,
                    params={"auth": key, "topFinGrpNo": group, "pageNo": 1})
                body = (response.json() or {}).get("result") or {}
            except Exception as e:  # noqa: BLE001 — 한 권역 실패로 멈추지 않는다
                logger.warning("[COMPANY] %s 권역 조회 실패: %s", group, e)
                continue
            if body.get("err_cd") not in ("000", None):
                logger.warning("[COMPANY] %s 권역 err_cd=%s",
                               group, body.get("err_cd"))
                continue
            names.extend(
                row.get("kor_co_nm") or ""
                for row in (body.get("baseList") or []))

    names = [n for n in names if n]
    if names:
        _cache["names"], _cache["at"] = names, now
        logger.info("[COMPANY] 공시 참여 회사 %d곳 적재", len(names))
    return names


async def verify(key: str, title_company: Optional[str]) -> CompanyCheck:
    """제목에서 찾은 회사가 공시 목록에 있나.

    Args:
        key: 금감원 인증키(복호화된 값)
        title_company: 제목에서 뽑은 회사 이름. 없으면 None

    Returns:
        CompanyCheck. 회사명이 없거나 조회에 실패하면 known=None(모름)
    """
    if not title_company:
        return CompanyCheck(reason="제목에 회사 이름이 없음")
    if not key:
        return CompanyCheck(name=title_company, reason="인증키 없음")

    try:
        names = await _load_names(key)
    except Exception as e:  # noqa: BLE001 — 조회 실패로 글을 막지 않는다
        logger.warning("[COMPANY] 목록 조회 실패: %s", e)
        return CompanyCheck(name=title_company, reason=f"조회 실패: {e}")

    if not names:
        return CompanyCheck(name=title_company, reason="목록을 받지 못함")

    for listed in names:
        if same_company(title_company, listed):
            return CompanyCheck(name=title_company, known=True, matched=listed,
                                reason=f"공시 참여 회사 확인({listed})")

    logger.info("[COMPANY] 미확인 회사 | %s", title_company)
    return CompanyCheck(name=title_company, known=False,
                        reason=f"'{title_company}' 은(는) 금감원 공시 참여 "
                               f"회사 목록에 없음")


def company_in(title: str, words: Optional[Sequence[str]] = None
               ) -> Optional[str]:
    """제목에서 금융회사 이름을 뽑는다. 없으면 None."""
    from .sources.fss_finlife import _company_of

    picked = list(words or []) or (title or "").split()
    return _company_of(picked)
