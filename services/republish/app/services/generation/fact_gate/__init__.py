"""사실 관문 — 글을 다 쓴 뒤 저장 전에 F1 주소·F3 말투·F2 사실을 본다.

모듈 설정 ``settings.fact_gate`` 가 있을 때만 동작한다. 키가 없으면 아무것도
하지 않는다 — 다른 블로그는 지금과 같다(official_hold 와 같은 방식).
``fact_gate`` 는 최상위 키라 화면 저장에도 지워지지 않는다(settings_merge).

    "fact_gate": {
      "url_allowlist": {"enabled": true, "domains": [...], "check_alive": true},
      "polite_tone":   {"enabled": true, "max_ratio": 0.2},
      "fact_check":    {"enabled": true, "provider": "anthropic",
                        "model": "claude-haiku-4-5", "facts": ["확정 사실", ...],
                        "hold_on_error": true},  # B2 검사 실패면 보류
      "journal": true,                       # B4 logs/fact_gate.jsonl
      "official_api_counts": true,          # O1 (official_hold)
      "official_seeds": [{"keywords": [...], "urls": [...]}],   # O2
      "next_title_on_hold": {"enabled": true, "max_attempts": 3}  # O3
    }

2026-10-20 마케팅 지시(형 승인) — 슈마즈(블로그 15·모듈 177).
순서도: docs/flowcharts/shoemaz_fact_gate.md
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional

from ....core.logger import get_logger
from . import fact_check as f2
from . import journal
from . import polite_tone as f3
from . import url_allowlist as f1

logger = get_logger("fact_gate", "app.log")

DEFAULT_CHECK = ("anthropic", "claude-haiku-4-5")
CHECK_FAILED = "사실 검사 — 검사 호출·해석 실패(검사 없이 내보내지 않음)"


@dataclass
class GateOutcome:
    """관문 결과. hold_reason 이 있으면 저장하지 않고 보류한다."""

    markdown: str
    hold_reason: Optional[str] = None
    record: dict = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


def config(settings: Optional[dict]) -> dict:
    """모듈의 fact_gate 블록(없으면 빈 dict)."""
    cfg = (settings or {}).get("fact_gate")
    return cfg if isinstance(cfg, dict) else {}


def _on(cfg: dict, key: str) -> dict:
    """하위 스위치가 켜졌으면 그 블록, 아니면 빈 dict."""
    sub = cfg.get(key)
    return sub if isinstance(sub, dict) and sub.get("enabled") is True else {}


def with_prompt(settings: dict) -> dict:
    """F3 가 켜졌으면 system_prompt 에 말투 한 줄을 붙인 사본."""
    if not _on(config(settings), "polite_tone"):
        return settings
    cg = dict(settings.get("content_generation") or {})
    cg["system_prompt"] = f3.with_directive(cg.get("system_prompt"))
    return {**settings, "content_generation": cg}


def _writer(blog: Any, settings: dict) -> tuple:
    """글쓰기 모델(provider, model, max_tokens) — 블로그 writing_ai."""
    w = (getattr(blog, "ai_config", None) or {}).get("writing_ai") or {}
    cg = settings.get("content_generation") or {}
    return w.get("provider"), w.get("model"), int(cg.get("max_tokens") or 4000)


def ref_urls(ref_result: Any) -> List[str]:
    """참고 자료에 실제로 있던 주소(요약 문서 + 통합 요약 출처)."""
    from ..official_hold import reference_urls

    return reference_urls(ref_result)


def _refs_text(ref_result: Any) -> str:
    try:
        return ref_result.to_prompt_injection()
    except Exception:  # noqa: BLE001
        return getattr(ref_result, "digest", "") or ""


async def _run_f2(ai: Any, md: str, refs: str, cfg: dict, writer: tuple,
                  rec: dict) -> tuple:
    """사실 검사 → '높음' 문장 고치기 → 재검사. (본문, 보류 사유)."""
    prov = cfg.get("provider") or DEFAULT_CHECK[0]
    model = cfg.get("model") or DEFAULT_CHECK[1]
    facts = cfg.get("facts") or []  # 확정 사실 — 검사 모델의 옛 기억을 누른다
    strict = cfg.get("hold_on_error") is True  # B2 승인 심사 기간엔 보류
    items = await f2.check(ai, md, refs, prov, model, facts)
    rec["f2_items"] = items
    if items is None:
        rec["f2_error"] = ("검사 호출 실패 — 보류" if strict
                           else "검사 호출 실패 — 검사 없이 계속")
        return md, (CHECK_FAILED if strict else None)
    bad = f2.high(items)
    if not bad:
        return md, None
    fixes = await f2.fix(ai, bad, refs, writer[0], writer[1], facts)
    given = {str(f.get("sentence") or "").strip() for f in fixes}
    # 답에 빠진 문장은 고칠 수 없는 것으로 보고 지운다
    fixes += [{"sentence": b["sentence"], "replacement": ""}
              for b in bad if str(b["sentence"]).strip() not in given]
    md, applied = f2.apply_fixes(md, fixes)
    rec["f2_fixes"] = applied
    again = await f2.check(ai, md, refs, prov, model, facts)
    rec["f2_recheck"] = again
    if again is None and strict:
        rec["f2_error"] = "재검사 호출 실패 — 보류"
        return md, CHECK_FAILED
    left = f2.high(again)
    if left:
        return md, (f"사실 검사 — 고친 뒤에도 틀린 문장 {len(left)}개: "
                    f"{left[0].get('sentence', '')[:40]}")
    return md, None


async def run(ai_service: Any, markdown: str, ref_result: Any,
              settings: dict, blog: Any, title: str) -> GateOutcome:
    """F1 → F3 → F2 순서로 본다(꺼진 스위치는 건너뜀)."""
    cfg = config(settings)
    out = GateOutcome(markdown=markdown)
    if not cfg:
        return out
    writer = _writer(blog, settings)
    rec = out.record
    c1 = _on(cfg, "url_allowlist")
    if c1:
        out.markdown, removed = await f1.scrub(
            out.markdown, ref_urls(ref_result), c1.get("domains"),
            c1.get("check_alive", True) is not False)
        rec["f1_removed"] = removed
        if removed:
            out.notes.append(f"F1 주소 {len(removed)}개 삭제")
    c3 = _on(cfg, "polite_tone")
    if c3:
        out.markdown, reason, rec["f3"] = await f3.enforce(
            ai_service, out.markdown, writer[0], writer[1], writer[2],
            float(c3.get("max_ratio", f3.DEFAULT_MAX_RATIO)))
        out.hold_reason = reason
    c2 = _on(cfg, "fact_check")
    if c2 and not out.hold_reason:
        out.markdown, out.hold_reason = await _run_f2(
            ai_service, out.markdown, _refs_text(ref_result), c2, writer, rec)
        n = len(f2.high(rec.get("f2_items")))
        if n:
            out.notes.append(f"F2 틀린 문장 {n}개 고침")
    logger.info("[FACT_GATE] '%s' | 보류=%s | %s", (title or "")[:40],
                out.hold_reason or "-",
                json.dumps(rec, ensure_ascii=False, default=str)[:3000])
    if cfg.get("journal") is True:
        journal.write(blog, title, out.hold_reason, rec)
    return out


async def record_hold(db: Any, source_title: Any, reason: str,
                      title: str) -> None:
    """보류를 제목에 기록한다(지우지 않고 hold_count 를 올린다)."""
    source_title.hold_count = (source_title.hold_count or 0) + 1
    source_title.last_held_at = datetime.now()
    source_title.hold_reason = reason[:500]
    await db.commit()
    logger.warning("[FACT_GATE] 보류 %d회 | '%s' | %s",
                   source_title.hold_count, (title or "")[:40], reason)
