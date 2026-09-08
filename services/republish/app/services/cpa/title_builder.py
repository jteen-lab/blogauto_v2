"""오퍼 → 제목 재고.

가이드라인이 친절하면 **주제 × 키워드 + 내용 포인트**를 통째로 준다.
부산ㅎr늘안과는 주제 9개에 키워드 40여 개, 야호스탁론은 키워드 23개다.
이걸 제목으로 펴면 오퍼 하나에서 글 수십 편이 나온다. 자동화의 이득은
여기서 나온다.

**오퍼가 금지한 축은 만들지 않는다.** 안과는 후기가 의료법 위반이라
"후기" 꼴 제목을 만들면 그 자체로 위반이다.

**축이 없는 오퍼가 더 흔하다.** 이사스토리·카바딜러는 추천 키워드가 없다.
그때는 오퍼 이름과 전환 항목에서 만든다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from ...core.logger import get_logger

logger = get_logger("cpa_title_builder", "app.log")

# 키워드 하나를 여러 각도로 편다. 구매 직전 의도가 앞에 온다.
# CPA 는 검색량이 아니라 의도로 이긴다 — 정확히 겨냥한 1,000명이
# 무작위 50,000명을 이긴다.
PATTERNS = (
    "{kw} 조건과 신청 방법",
    "{kw} 자격 요건 정리",
    "{kw} 신청 절차 한눈에",
    "{kw} 준비 서류와 확인할 점",
    "{kw} 알아보기 전에 확인할 것",
)

# 오퍼가 금지하지 않아도 위험한 꼴. 후기·경험담은 여러 업종에서 막힌다.
RISKY_PATTERNS = ("후기", "경험담", "실제 사용", "직접 해봤")

_SPLIT = re.compile(r"[,\n·|/]+")


def _keywords_from_rules(rules: Sequence[dict]) -> List[str]:
    """content_axis 규칙에서 키워드를 모은다."""
    out: List[str] = []
    for rule in rules or []:
        if (rule or {}).get("type") != "content_axis":
            continue
        blob = f"{rule.get('value') or ''} {rule.get('source_quote') or ''}"
        for part in _SPLIT.split(blob):
            word = part.strip(" .·-*0123456789)(")
            if 2 <= len(word) <= 30 and word not in out:
                out.append(word)
    return out


def _forbidden_words(rules: Sequence[dict]) -> List[str]:
    """제목에 쓰면 안 되는 낱말. 범위가 title·keywords·all 인 것만."""
    out = []
    for rule in rules or []:
        if (rule or {}).get("type") != "must_not_include":
            continue
        if (rule.get("scope") or "all") not in ("title", "keywords", "all"):
            continue
        value = str(rule.get("value") or "").strip()
        if value:
            out.append(value)
    return out


def _forbidden_topics(rules: Sequence[dict]) -> List[str]:
    return [str((r or {}).get("value") or "").strip()
            for r in rules or []
            if (r or {}).get("type") == "forbidden_topic"]


def _safe(title: str, banned: Sequence[str], topics: Sequence[str]) -> bool:
    """이 제목을 만들어도 되나."""
    for word in banned:
        if word and word in title:
            return False
    for word in RISKY_PATTERNS:
        if word in title:
            return False
    for topic in topics:
        # 금지 주제의 낱말이 제목에 그대로 들어가면 만들지 않는다
        for part in _SPLIT.split(topic):
            token = part.strip()
            if len(token) >= 3 and token in title:
                return False
    return True


def build(offer: Any, limit: int = 40) -> Dict[str, Any]:
    """오퍼에서 제목 후보를 만든다.

    Args:
        offer: CpaOffer
        limit: 최대 개수

    Returns:
        {"titles": [...], "keywords": [...], "skipped": [...]}
        `skipped` 는 규칙에 걸려 버린 후보다 — 왜 적게 나왔는지 보여준다.
    """
    rules = offer.rules or []
    keywords = _keywords_from_rules(rules)
    if not keywords:
        # 축이 없는 오퍼. 이름에서 만든다.
        name = re.sub(r"\[[^\]]*\]", "", offer.name or "").strip()
        keywords = [name] if name else []

    banned = _forbidden_words(rules)
    topics = _forbidden_topics(rules)

    titles: List[str] = []
    skipped: List[str] = []
    for keyword in keywords:
        for pattern in PATTERNS:
            if len(titles) >= limit:
                break
            candidate = pattern.format(kw=keyword)
            if candidate in titles:
                continue
            if _safe(candidate, banned, topics):
                titles.append(candidate)
            elif len(skipped) < 20:
                skipped.append(candidate)

    logger.info("[CPA_TITLE] '%s' | 키워드 %d → 제목 %d (규칙에 걸림 %d)",
                (offer.name or "")[:30], len(keywords), len(titles),
                len(skipped))
    return {"titles": titles, "keywords": keywords, "skipped": skipped}
