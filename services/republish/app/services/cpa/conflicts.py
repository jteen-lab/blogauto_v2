"""충돌 감지 — 자동으로 한쪽을 고르면 사고가 난다.

실제 오퍼에서 확인한 두 가지다.

    법무법인 중정   금지 키워드 '전문'  ↔  자기 소개문 "전문화된 법률서비스로"
    야호스탁론      금지 키워드 '금리'  ↔  자기 홍보문구 "월 0.4%대", "업계 최저금리"

광고주 소개문을 그대로 쓰면 광고주가 금지한 낱말을 쓴 글이 되고, 금지어를
문서 전체에 적용하면 광고주가 준 문구를 우리가 막는다. **어느 쪽도 시스템이
고를 수 없다.** 찾아서 보여주기만 한다.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ...core.logger import get_logger

logger = get_logger("cpa_conflicts", "app.log")

# 금지어가 원문에 이만큼 자주 나오면 광고주가 쓰는 말로 본다
_MIN_HITS = 1


def _banned_words(rules: List[dict]) -> List[dict]:
    return [r for r in rules or []
            if (r or {}).get("type") == "must_not_include" and r.get("value")]


def _sources(rules: List[dict]) -> str:
    """content_source 로 뽑힌 사실 원천을 한 덩어리로."""
    return "\n".join(str((r or {}).get("value") or "")
                     for r in rules or []
                     if (r or {}).get("type") == "content_source")


def detect(raw_text: str, rules: List[dict]) -> List[Dict[str, Any]]:
    """오퍼 내부 모순을 찾는다.

    Args:
        raw_text: 프로모션 원문
        rules: 추출된 규칙

    Returns:
        [{"kind", "word", "rule_quote", "text_quote", "hint"}]
    """
    body = raw_text or ""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    out: List[Dict[str, Any]] = []

    for rule in _banned_words(rules):
        word = str(rule.get("value") or "").strip()
        if len(word) < 2:
            continue
        # 금지 규칙을 만든 그 줄은 당연히 그 낱말을 담고 있다. 제외한다.
        quote = str(rule.get("source_quote") or "")
        hits = [line for line in lines
                if word in line and line != quote and "금지" not in line
                and "지양" not in line and "불가" not in line]
        if len(hits) >= _MIN_HITS:
            out.append({
                "kind": "self_contradiction",
                "word": word,
                "rule_quote": quote[:200],
                "text_quote": hits[0][:200],
                "hint": (f"'{word}' 을(를) 금지하면서 안내문에서 "
                         f"{len(hits)}번 쓰고 있습니다. 금지 범위가 제목·"
                         f"키워드인지 본문까지인지 확인이 필요합니다."),
            })

    if out:
        logger.info("[CPA_CONFLICT] %d건 | %s", len(out),
                    ", ".join(c["word"] for c in out[:5]))
    return out


def legal_vs_offer(rules: List[dict]) -> List[Dict[str, Any]]:
    """법정 사전이 광고주가 준 사실 원천과 부딪히는가.

    현금사은품 오퍼는 금지사항이 없는데 소개문에 "전국 최대 현금지급 센터",
    "최저요금" 이 있다. 표시광고법 쪽에서 걸릴 수 있다.
    """
    source = _sources(rules)
    if not source:
        return []
    out = []
    for rule in rules or []:
        if not str((rule or {}).get("source_quote") or "").startswith("[법정]"):
            continue
        word = str(rule.get("value") or "")
        if word and word in source:
            out.append({
                "kind": "legal_vs_source",
                "word": word,
                "rule_quote": str(rule.get("source_quote"))[:200],
                "text_quote": "",
                "hint": (f"법정 금지어 '{word}' 가 광고주 소개문에 있습니다. "
                         f"그대로 옮기면 위험합니다."),
            })
    return out
