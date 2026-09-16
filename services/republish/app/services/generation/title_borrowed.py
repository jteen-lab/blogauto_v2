"""남의 수치가 섞인 제목을 걸러낸다.

스타일 지시에 적어 둔 **예시의 숫자가 제목으로 옮겨 붙는 일**이 있었다.
「월세 계약만료 1개월전 갱신청구권 12평 78만원」 — 원본 제목에는 평수도
금액도 없는데 지시문 예시("12평 … 78만원")가 그대로 따라왔다.

프롬프트로 막는 것만으로는 부족하다. 결과를 우리가 한 번 본다.

**개수는 막지 않는다.** 「확인할 7가지」처럼 원본에 없는 숫자를 붙이는
것은 제목을 낫게 만든다. 금액·평수처럼 **사실을 주장하는 단위**만 본다.

순서도: docs/flowcharts/title_recombine_rotation.md
"""
from __future__ import annotations

import re
from typing import List

from ...core.logger import get_logger

logger = get_logger("title_borrowed", "app.log")

#: 사실을 주장하는 단위 — 원본에 없으면 지어낸 것이다
FACT_UNITS = (
    "만원", "천원", "원", "억", "만",
    "평", "㎡", "제곱미터",
    "km", "킬로", "m", "시간", "분", "일", "개월", "년", "주", "차",
    "인", "명", "kg", "리터", "도",
)

#: 숫자 + 단위. 단위가 긴 것부터 맞춰야 "만원" 이 "만" 으로 잘리지 않는다
_PATTERN = re.compile(
    r"(\d[\d,\.]*)\s*(" + "|".join(sorted(FACT_UNITS, key=len, reverse=True)) + r")"
)


def _facts(text: str) -> List[str]:
    """이 글에 적힌 '수치+단위' 목록. 쉼표·공백 차이는 무시한다."""
    out = []
    for num, unit in _PATTERN.findall(text or ""):
        token = num.replace(",", "").rstrip(".") + unit
        if token not in out:
            out.append(token)
    return out


def borrowed(original: str, recombined: str) -> List[str]:
    """재조합 제목에만 있는 수치. 비어 있으면 깨끗하다."""
    source = set(_facts(original))
    return [f for f in _facts(recombined) if f not in source]


def is_clean(original: str, recombined: str) -> bool:
    """원본에 없는 수치가 붙지 않았는가."""
    return not borrowed(original, recombined)


def strip_borrowed(original: str, recombined: str) -> str:
    """빌려 온 수치를 덜어낸 제목. 덜어낼 게 없으면 그대로.

    다시 청하는 것이 낫지만, 두 번째도 같은 수치를 들고 오면 마지막에
    이걸 쓴다. 제목이 안 나오는 것보다 낫다.
    """
    taken = borrowed(original, recombined)
    if not taken:
        return recombined

    out = recombined
    for token in taken:
        num = re.escape(token[:-len(_unit_of(token))])
        unit = re.escape(_unit_of(token))
        out = re.sub(num.replace(r"\,", r"[,]?") + r"\s*" + unit, "", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" -·,")
    logger.info("[TITLE_BORROWED] 남의 수치 제거 | %s → %s | 뺀 것=%s",
                recombined, out, taken)
    return out or recombined


def _unit_of(token: str) -> str:
    """토큰 끝에 붙은 단위."""
    for unit in sorted(FACT_UNITS, key=len, reverse=True):
        if token.endswith(unit):
            return unit
    return ""
