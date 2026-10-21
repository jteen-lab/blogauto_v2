"""L1. '어디서 확인하나' 기관 이름에 공식 주소 링크를 붙인다.

슈마즈 첫 글(5230, 2026-10-21)의 끝 '어디서 확인하나'에 예금보험공사·금감원
이름만 있고 링크가 0개였다. 돈 주제 글은 공식 사이트 링크가 신뢰 근거다.

주소는 아래 정해진 목록에서만 가져온다(지어낸 주소 없음). 목록 주소도
F1 허용 도메인 밖이면 붙이지 않는다. 이미 링크가 있는 줄은 건드리지 않는다.

순서도: docs/flowcharts/shoemaz_fact_gate.md (L1)
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

from . import url_allowlist as f1

# 긴 이름부터 맞춘다(예: '금융감독원 금융상품통합비교공시' 가 '금융감독원' 보다 먼저)
DEFAULT_LINKS: Tuple[Tuple[str, str], ...] = (
    ("금융감독원 금융상품통합비교공시", "https://finlife.fss.or.kr"),
    ("금융상품통합비교공시", "https://finlife.fss.or.kr"),
    ("금융상품 한눈에", "https://finlife.fss.or.kr"),
    ("금융소비자 정보포털 파인(FINE)", "https://fine.fss.or.kr"),
    ("금융소비자 정보포털 파인", "https://fine.fss.or.kr"),
    ("금융소비자 정보포털", "https://fine.fss.or.kr"),
    ("통합연금포털", "https://100lifeplan.fss.or.kr"),
    ("예금보험공사", "https://www.kdic.or.kr"),
    ("금융감독원", "https://www.fss.or.kr"),
    ("금융위원회", "https://www.fsc.go.kr"),
    ("국세청 홈택스", "https://www.hometax.go.kr"),
    ("홈택스", "https://www.hometax.go.kr"),
    ("국세청", "https://www.nts.go.kr"),
    ("국민연금공단", "https://www.nps.or.kr"),
    ("신협중앙회", "https://www.cu.co.kr"),
    ("우체국", "https://www.epost.go.kr"),
    ("금융투자협회", "https://www.kofia.or.kr"),
    ("한국거래소", "https://www.krx.co.kr"),
    ("한국은행", "https://www.bok.or.kr"),
    ("국가법령정보센터", "https://www.law.go.kr"),
)
DEFAULT_HEADINGS = ("어디서 확인",)

_HEAD = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
_ITEM = re.compile(r"^(\s*(?:[-*+]|\d+\.)\s+)(.*)$")
_HAS_LINK = re.compile(r"\]\(|https?://|<a\s", re.I)


def _allowed(links: Iterable[Tuple[str, str]],
             domains: Optional[Iterable[str]]) -> List[Tuple[str, str]]:
    """허용 도메인 안 주소만, 긴 이름부터."""
    doms = tuple(domains or f1.DEFAULT_DOMAINS)
    ok = [(n, u) for n, u in links
          if any(f1.host_of(u) == d or f1.host_of(u).endswith("." + d)
                 for d in doms)]
    return sorted(ok, key=lambda x: -len(x[0]))


def _link_item(text: str, table: List[Tuple[str, str]]) -> str:
    """목록 한 줄에서 처음 나오는 기관 이름 하나를 링크로 바꾼다."""
    if _HAS_LINK.search(text):
        return text
    best = None
    for name, url in table:
        i = text.find(name)
        if i >= 0 and (best is None or i < best[0]):
            best = (i, name, url)
    if not best:
        return text
    i, name, url = best
    bold = text[max(0, i - 2):i] == "**" and text[i + len(name):i + len(name) + 2] == "**"
    if bold:
        i, name = i - 2, f"**{name}**"
    return f"{text[:i]}[{name}]({url}){text[i + len(name):]}"


def apply(markdown: str, cfg: dict, domains: Optional[Iterable[str]] = None
          ) -> Tuple[str, int]:
    """'어디서 확인' 소제목 아래 목록 줄에 링크를 붙인다. (본문, 붙인 수)."""
    heads = tuple(cfg.get("headings") or DEFAULT_HEADINGS)
    extra = [(str(x.get("name")), str(x.get("url")))
             for x in (cfg.get("links") or []) if isinstance(x, dict)]
    table = _allowed(extra + list(DEFAULT_LINKS), domains)
    out, inside, added = [], False, 0
    for line in (markdown or "").split("\n"):
        h = _HEAD.match(line)
        if h:
            inside = any(k in h.group(2) for k in heads)
        elif inside:
            m = _ITEM.match(line)
            if m:
                new = _link_item(m.group(2), table)
                if new != m.group(2):
                    added += 1
                    line = m.group(1) + new
        out.append(line)
    return "\n".join(out), added
