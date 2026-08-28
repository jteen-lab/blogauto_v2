"""A5 — 본문의 FAQ 블록에서 FAQPage JSON-LD 를 만든다.

핵심 제약: **JSON-LD 내용은 화면에 보이는 텍스트와 같아야 한다.**
마크업에만 있고 페이지에 없는 FAQ 는 스팸 판정 대상이므로, 스키마를 따로 생성하지
않고 이미 렌더된 본문에서 문자열을 그대로 추출한다.

구글은 2026-05-07 FAQ 리치결과를 폐지했다. 목적은 리치결과가 아니라 검색·RAG
엔진의 내용 이해와 답변 발췌를 돕는 것이다.

설계: docs/flowcharts/aeo_a5_faq_schema.md
"""
from __future__ import annotations

import html
import json
import re
from typing import List, Optional, Tuple

from ...core.logger import get_logger

logger = get_logger("faq_schema", "app.log")

# FAQ 블록을 여는 제목
HEADING_RE = re.compile(r"<h([1-4])[^>]*>(.*?)</h\1>", re.I | re.S)
FAQ_HEADING_WORDS = ("자주 묻는 질문", "자주묻는질문", "faq")
# 블록을 닫는 경계
BOUNDARY_RE = re.compile(r"<h[1-4][^>]*>|<hr\s*/?>", re.I)
# 문단
PARAGRAPH_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.I | re.S)
# 질문 문단 안의 강조
STRONG_RE = re.compile(r"<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>", re.I | re.S)
# 라벨 접두어 — 번호 표식일 뿐이므로 제거해도 본문에 남는 문자열은 동일하다
LABEL_RE = re.compile(r"^(?:Q|A|질문|답변)\s*\d*\s*[:.）)]\s*", re.I)

MIN_PAIRS = 2
MAX_PAIRS = 10


def _text(fragment: str) -> str:
    """HTML 조각에서 보이는 텍스트만 남긴다."""
    plain = re.sub(r"<[^>]+>", "", fragment or "")
    plain = html.unescape(plain)
    return re.sub(r"\s+", " ", plain).strip()


def _strip_label(text: str) -> str:
    """`Q1:` `A1.` `질문 1:` 같은 번호 표식을 뗀다."""
    return LABEL_RE.sub("", text).strip()


def _find_block(body_html: str) -> Optional[str]:
    """FAQ 제목 다음부터 다음 제목/구분선 앞까지를 잘라낸다."""
    for match in HEADING_RE.finditer(body_html):
        heading = _text(match.group(2)).lower()
        if not any(word in heading for word in FAQ_HEADING_WORDS):
            continue

        rest = body_html[match.end():]
        boundary = BOUNDARY_RE.search(rest)
        return rest[: boundary.start()] if boundary else rest
    return None


def extract_pairs(body_html: str) -> List[Tuple[str, str]]:
    """본문에서 (질문, 답변) 쌍을 뽑는다.

    질문은 문단 안의 강조 텍스트, 답변은 바로 다음 문단이다.

    Args:
        body_html: 발행 직전 본문 HTML

    Returns:
        (질문, 답변) 목록. FAQ 블록이 없으면 빈 목록.
    """
    block = _find_block(body_html)
    if not block:
        return []

    paragraphs = PARAGRAPH_RE.findall(block)
    pairs: List[Tuple[str, str]] = []
    index = 0
    while index < len(paragraphs) - 1 and len(pairs) < MAX_PAIRS:
        strong = STRONG_RE.search(paragraphs[index])
        if not strong:
            index += 1
            continue

        question = _strip_label(_text(strong.group(1)))
        answer = _strip_label(_text(paragraphs[index + 1]))
        # 답변 문단이 또 질문이면(강조로 시작) 쌍이 아니다.
        if question and answer and not STRONG_RE.search(paragraphs[index + 1]):
            pairs.append((question, answer))
            index += 2
        else:
            index += 1

    return pairs


def build_jsonld(pairs: List[Tuple[str, str]]) -> Optional[str]:
    """FAQPage JSON-LD 문자열을 만든다. 쌍이 부족하면 None."""
    if len(pairs) < MIN_PAIRS:
        return None

    payload = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            }
            for question, answer in pairs
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def inject(body_html: str) -> str:
    """본문에 FAQPage JSON-LD 를 덧붙인다.

    FAQ 블록이 없거나 쌍이 부족하면 원본을 그대로 돌려준다.
    어떤 이유로든 실패해도 발행을 막지 않는다.
    """
    if not body_html or "application/ld+json" in body_html:
        return body_html

    try:
        pairs = extract_pairs(body_html)
        jsonld = build_jsonld(pairs)
        if not jsonld:
            return body_html

        logger.info("[FAQ_SCHEMA] FAQPage 삽입 | 질문 %d개", len(pairs))
        return (
            f'{body_html}\n'
            f'<script type="application/ld+json">{jsonld}</script>'
        )
    except Exception as exc:  # noqa: BLE001 — 발행을 막지 않는다
        logger.warning("[FAQ_SCHEMA] 생성 실패(무시): %s", exc)
        return body_html
