"""건강형 주제의 '공식 출처 우선' — 추가 질의·도메인 가산·인용 규칙.

건강·의학·음식 효능·출산/육아 글은 네이버 웹문서만 뒤지면 블로그·카페
글이 근거가 된다. 그래서
  1) 공식 기관 이름을 붙인 추가 질의를 던지고,
  2) 공식 도메인(화이트리스트) 결과를 앞으로 올리고,
  3) 글 끝 '참고 자료' 에는 공식 출처만 적게 한다.

순서도: docs/flowcharts/health_official_sources.md
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 건강형 주제 판정 — 주제/하위주제 이름에 이 낱말이 있으면 건강형이다.
# (수작남: 건강/의학=topic1, 비만/다이어트=sub18, 음식 효능=sub53,
#  출산 준비=sub32, 육아팁=sub51). 목록을 바꾸려면 여기만 고친다.
HEALTH_TOPIC_KEYWORDS: tuple = (
    "건강", "의학", "다이어트", "비만", "효능", "출산", "임신", "육아", "영양",
)

# 공식 출처를 겨냥한 추가 질의 꼬리말
OFFICIAL_QUERY_SUFFIXES: tuple = ("질병관리청", "국가건강정보포털", "식약처")

# 공식 출처 도메인 → 기관명. 하위 도메인까지 인정한다(예: health.kdca.go.kr).
TRUSTED_HEALTH_DOMAINS: Dict[str, str] = {
    "kdca.go.kr": "질병관리청",
    "health.kdca.go.kr": "국가건강정보포털(질병관리청)",
    "mfds.go.kr": "식품의약품안전처",
    "nedrug.mfds.go.kr": "의약품안전나라(식약처)",
    "foodsafetykorea.go.kr": "식품안전나라(식약처)",
    "hira.or.kr": "건강보험심사평가원",
    "nhis.or.kr": "국민건강보험공단",
    "korea.kr": "대한민국 정책브리핑",
    "mohw.go.kr": "보건복지부",
    "amc.seoul.kr": "서울아산병원",
    "snuh.org": "서울대학교병원",
    "severance.healthcare": "세브란스병원",
    "sev.iseverance.com": "세브란스병원",
    "samsunghospital.com": "삼성서울병원",
    "kams.or.kr": "대한의학회",
    "diabetes.or.kr": "대한당뇨병학회",
    "kosso.or.kr": "대한비만학회",
    "pediatrics.or.kr": "대한소아청소년과학회",
    "ksog.org": "대한산부인과학회",
}

OFFICIAL_PER_QUERY = 10
EXTRA_CAP = 10


def is_health_topic(topic_names: Iterable[str], title: str = "") -> bool:
    """주제·하위주제 이름(없으면 제목)에 건강형 낱말이 있나."""
    names = [n for n in (topic_names or []) if n]
    text = " ".join(names) if names else (title or "")
    return any(k in text for k in HEALTH_TOPIC_KEYWORDS)


def official_org(url: str) -> Optional[str]:
    """공식 도메인이면 기관명, 아니면 None. 가장 긴(구체적) 도메인 우선."""
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    best = ""
    for dom in TRUSTED_HEALTH_DOMAINS:
        if (host == dom or host.endswith("." + dom)) and len(dom) > len(best):
            best = dom
    return TRUSTED_HEALTH_DOMAINS[best] if best else None


def is_official(url: str) -> bool:
    """공식 도메인 URL 인가."""
    return official_org(url) is not None


def _url_of(item: Any) -> str:
    return getattr(item, "link", "") or getattr(item, "url", "") or ""


def boost_official(items: Sequence[Any]) -> List[Any]:
    """공식 도메인을 앞으로(안정 정렬 — 나머지 순서는 그대로)."""
    return sorted(items, key=lambda it: 0 if is_official(_url_of(it)) else 1)


async def official_search(search_service: Any, query: str) -> List[Any]:
    """공식 기관 이름을 붙여 추가 검색. 공식 도메인 결과만 남긴다."""
    found: List[Any] = []
    for suffix in OFFICIAL_QUERY_SUFFIXES:
        try:
            rows = await search_service.search_webdoc(
                f"{query} {suffix}", count=OFFICIAL_PER_QUERY)
        except Exception as e:  # noqa: BLE001 — 추가 검색 실패로 막지 않는다
            logger.warning("[HEALTH_SRC] 추가 검색 실패 | %s | %s", suffix, e)
            continue
        found.extend(r for r in (rows or []) if is_official(_url_of(r)))
    return found[:EXTRA_CAP]


async def augment(search_service: Any, query: str, results: List[Any],
                  health: bool) -> List[Any]:
    """건강형이면 공식 결과를 붙이고(중복 제거) 공식을 앞으로 올린다."""
    if not health:
        return results
    extra = await official_search(search_service, query)
    seen = {_url_of(r).rstrip("/") for r in results}
    merged = list(results)
    for r in extra:
        key = _url_of(r).rstrip("/")
        if key not in seen:
            seen.add(key)
            merged.append(r)
    logger.info("[HEALTH_SRC] 공식 추가 %d건", len(merged) - len(results))
    return boost_official(merged)


def official_refs(documents: Sequence[Any]) -> List[Dict[str, Any]]:
    """인용 후보 — 공식 도메인 문서만 {org,title,url,is_official}."""
    refs = []
    for doc in documents:
        url = _url_of(doc)
        org = official_org(url)
        if org:
            refs.append({"org": org, "title": getattr(doc, "title", "") or "",
                         "url": url, "is_official": True})
    return refs


def citation_block(refs: Sequence[Dict[str, Any]], health: bool) -> str:
    """글 끝 '참고 자료'·수치·면책 지시문. 비건강형은 공식 출처가 있을 때만."""
    lines: List[str] = []
    if refs:
        lines += ["[인용 가능한 공식 출처]"]
        lines += [f"- {r['org']} | {r['title'] or '(제목 없음)'} | {r['url']}"
                  for r in refs]
        lines += ["글 맨 끝에 '참고 자료' 소제목을 두고, 위 목록 중 본문에서 "
                  "실제로 쓴 것만 '기관명 - 페이지 제목' 형태로 링크를 걸어 "
                  "적으세요. 블로그·카페·지식iN 등 일반 문서는 절대 출처로 "
                  "적지 마세요."]
    elif health:
        lines += ["[출처 규칙]", "공식 기관 자료가 없으므로 '참고 자료' 목록을 "
                  "만들지 마세요. 블로그·카페·지식iN 은 출처로 적지 마세요."]
    if health:
        lines += ["[건강 정보 규칙]",
                  "수치·용량·효과는 위 공식 출처에 있는 것만 쓰고, 없으면 "
                  "정성적으로(예: '도움이 될 수 있다') 설명하세요.",
                  "글의 마지막 줄에 한 줄 면책 문구를 넣으세요: '이 글은 일반 "
                  "정보이며 의사의 진단·치료를 대신하지 않습니다.'"]
    return "\n".join(lines)
