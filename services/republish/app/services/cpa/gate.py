"""발행 전 검증 — 프롬프트를 어겨도 여기서 잡는다.

**게이트는 업종을 모른다.** 규칙 유형만 안다. 의료가 오든 대부업이 오든
코드는 그대로고 규칙 데이터만 바뀐다. 실제 오퍼 7건(의료·법률·생활·통신·
금융·교육) 80건을 분해해 얻은 유형 체계다.

막을 때는 **어느 규칙에 걸렸는지, 그 규칙이 원문 어느 문장에서 왔는지**까지
남긴다. 조용히 멈추면 고장과 구분되지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ...core.logger import get_logger

logger = get_logger("cpa_gate", "app.log")

# 대가성 문구가 "앞부분" 인지 볼 범위(글자)
NOTICE_HEAD = 400


@dataclass
class Violation:
    """규칙 하나를 어긴 사실."""

    rule_type: str
    scope: str
    value: str
    reason: str
    severity: str = "block"
    source_quote: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.rule_type, "scope": self.scope,
                "value": self.value, "reason": self.reason,
                "severity": self.severity, "source_quote": self.source_quote}


@dataclass
class GateResult:
    """검증 결과."""

    violations: List[Violation] = field(default_factory=list)
    reviews: List[Violation] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(v.severity == "block" for v in self.violations)

    def summary(self) -> str:
        blocks = [v for v in self.violations if v.severity == "block"]
        if not blocks:
            return "통과"
        head = blocks[0]
        more = f" 외 {len(blocks) - 1}건" if len(blocks) > 1 else ""
        return f"{head.reason}{more}"

    def to_dict(self) -> Dict[str, Any]:
        return {"blocked": self.blocked,
                "violations": [v.to_dict() for v in self.violations],
                "reviews": [v.to_dict() for v in self.reviews],
                "summary": self.summary()}


def _text_for(scope: str, title: str, body: str) -> str:
    """규칙 범위에 맞는 검사 대상.

    스탁론은 '금리' 를 금지키워드로 두면서 본문에 "월 0.4%대" 를 쓴다.
    범위를 구분하지 않으면 광고주가 준 문구를 우리가 막는다.
    """
    if scope == "title":
        return title or ""
    if scope == "keywords":
        return title or ""
    if scope == "body":
        return body or ""
    return f"{title or ''}\n{body or ''}"


def _check_not_include(rule: dict, title: str, body: str) -> Optional[Violation]:
    value = str(rule.get("value") or "").strip()
    if len(value) < 2:
        return None
    scope = rule.get("scope") or "all"
    if value in _text_for(scope, title, body):
        return Violation(
            "must_not_include", scope, value,
            f"금지 낱말 '{value}' 사용",
            rule.get("severity") or "block",
            str(rule.get("source_quote") or ""))
    return None


def _check_include(rule: dict, title: str, body: str) -> Optional[Violation]:
    value = str(rule.get("value") or "").strip()
    if len(value) < 2:
        return None
    if value not in f"{title}\n{body}":
        return Violation(
            "must_include", rule.get("scope") or "all", value,
            f"필수 문구 누락: '{value[:40]}'",
            rule.get("severity") or "block",
            str(rule.get("source_quote") or ""))
    return None


def _check_pattern(rule: dict, title: str, body: str) -> Optional[Violation]:
    value = str(rule.get("value") or "").strip()
    if not value:
        return None
    try:
        found = re.search(value, _text_for(rule.get("scope") or "all",
                                           title, body))
    except re.error:
        # 정규식이 아니면 문자열로 본다
        return _check_not_include(rule, title, body)
    if found:
        return Violation(
            "pattern", rule.get("scope") or "all", value,
            f"금지 형태 '{found.group(0)[:30]}' 사용",
            rule.get("severity") or "block",
            str(rule.get("source_quote") or ""))
    return None


def _check_replace(rule: dict, title: str, body: str) -> Optional[Violation]:
    """순화 대상 표현이 남아 있나. 대체어가 아니라 원표현을 본다."""
    target = str(rule.get("target") or "").strip()
    if len(target) < 2:
        return None
    if target in f"{title}\n{body}":
        return Violation(
            "replace", rule.get("scope") or "all", target,
            f"'{target}' 은(는) '{rule.get('value')}' 로 바꿔야 합니다",
            rule.get("severity") or "block",
            str(rule.get("source_quote") or ""))
    return None


def _check_conditional(rule: dict, title: str, body: str) -> Optional[Violation]:
    """X 를 썼으면 Y 도 있어야 한다."""
    trigger = str(rule.get("target") or "").strip()
    needed = str(rule.get("value") or "").strip()
    if len(trigger) < 2 or len(needed) < 2:
        return None
    text = f"{title}\n{body}"
    if trigger in text and needed not in text:
        return Violation(
            "conditional", rule.get("scope") or "all", needed,
            f"'{trigger}' 을(를) 썼으면 '{needed[:30]}' 도 있어야 합니다",
            rule.get("severity") or "block",
            str(rule.get("source_quote") or ""))
    return None


def _check_link_policy(rule: dict, body: str,
                       other_landings: Sequence[str]) -> Optional[Violation]:
    """같은 글에 다른 오퍼의 링크가 있나."""
    for url in other_landings or []:
        if url and url in (body or ""):
            return Violation(
                "link_policy", "body", url,
                "같은 글에 다른 오퍼의 링크가 있습니다",
                rule.get("severity") or "block",
                str(rule.get("source_quote") or ""))
    return None


def _check_notice(offer: Any, title: str, body: str) -> Optional[Violation]:
    """공정위 대가성 문구. 2024-12-01 개정으로 끝부분 게재가 막혔다."""
    notice = (offer.ftc_notice or "").strip()
    if not notice:
        return Violation(
            "must_include", "all", "대가성 문구",
            "공정거래위원회 대가성 문구가 오퍼에 없습니다", "block", "")
    text = f"{title}\n{body}"
    if notice not in text:
        return Violation(
            "must_include", "all", notice,
            "대가성 문구 누락 — 표시하지 않으면 위법입니다", "block", "")
    head = f"{title}\n{body[:NOTICE_HEAD]}"
    if notice not in head and "[광고]" not in (title or ""):
        return Violation(
            "position", "all", notice,
            "대가성 문구가 앞부분에 없습니다 (2024-12-01 개정: 끝부분 불가)",
            "block", "")
    return None


_CHECKS = {
    "must_not_include": _check_not_include,
    "must_include": _check_include,
    "pattern": _check_pattern,
    "replace": _check_replace,
    "conditional": _check_conditional,
}


def check(offer: Any, title: str, body: str,
          other_landings: Sequence[str] = ()) -> GateResult:
    """이 글을 내보내도 되나.

    Args:
        offer: CpaOffer
        title: 글 제목
        body: 본문
        other_landings: 다른 오퍼의 랜딩 URL 목록

    Returns:
        GateResult. blocked 면 발행하지 않는다.
    """
    result = GateResult()

    notice = _check_notice(offer, title, body)
    if notice:
        result.violations.append(notice)

    for rule in offer.rules or []:
        kind = (rule or {}).get("type")
        found = None
        if kind in _CHECKS:
            found = _CHECKS[kind](rule, title, body)
        elif kind == "link_policy":
            found = _check_link_policy(rule, body, other_landings)
        elif kind in ("required_topic", "advisory", "asset", "channel",
                      "format"):
            # 기계가 판정할 수 없다. 사람이 볼 목록에 올린다.
            result.reviews.append(Violation(
                kind, rule.get("scope") or "all",
                str(rule.get("value") or rule.get("target") or ""),
                "사람 확인 필요", "review",
                str(rule.get("source_quote") or "")))
            continue

        if found:
            if found.severity == "review":
                result.reviews.append(found)
            else:
                result.violations.append(found)

    if result.blocked:
        logger.warning("[CPA_GATE] 차단 | '%s' | %s",
                       (title or "")[:40], result.summary())
    return result
