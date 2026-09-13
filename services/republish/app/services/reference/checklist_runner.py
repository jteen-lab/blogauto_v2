"""체크리스트 실행 — 항목별 병렬 검색 → 판정 → 선별 재검색.

`reference_collector.py` 가 이미 465줄이라 판정 로직을 여기로 뺐다.
호출부는 `run()` 하나만 부르면 된다.

**호출 예산**: 목록 1 + 판정 1 (+ 재검색 시 판정 1) = AI 2~3회.
검색은 항목 수만큼이지만 **동시에** 던지므로 시간은 1회분이다.

계획서: docs/plans/topic_discovery_and_structure_plan.md §2-4
순서도: docs/flowcharts/topic_discovery.md §3
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...core.logger import get_logger
from . import evidence_checklist as ck

logger = get_logger("checklist_runner", "app.log")

# 항목당 가져올 검색 결과 수. 판정에 쓸 만큼만.
PER_ITEM = 12

# 판정에 넣을 자료 글자 상한. 넘기면 모델이 앞부분만 본다.
EVIDENCE_LIMIT = 6000


@dataclass
class RunResult:
    """한 제목에 대한 근거 확보 결과."""

    sheet: ck.Checklist
    results: List[Any] = field(default_factory=list)
    queries: List[tuple] = field(default_factory=list)
    ai_calls: int = 0

    @property
    def usable(self) -> bool:
        """글을 쓸 만한가. 절반은 채워져야 한다."""
        return self.sheet.coverage >= 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {"checklist": self.sheet.to_dict(),
                "results": len(self.results),
                "queries": [{"source": s, "query": q} for s, q in self.queries],
                "ai_calls": self.ai_calls, "usable": self.usable}


def _evidence_text(results: List[Any]) -> str:
    """검색 결과를 판정용 본문으로. 제목과 설명이면 판정에 충분하다."""
    lines = []
    for item in results:
        title = getattr(item, "title", "") or ""
        desc = getattr(item, "description", "") or ""
        if not title and not desc:
            continue
        lines.append(f"- {title} :: {desc}")
        if sum(len(x) for x in lines) > EVIDENCE_LIMIT:
            break
    return "\n".join(lines)


def _flatten(bundle: Dict[tuple, List[Any]]) -> List[Any]:
    """소스별 묶음을 하나로. 링크 중복은 여기서 뺀다."""
    out, seen = [], set()
    for rows in bundle.values():
        for row in rows or []:
            link = getattr(row, "link", "") or ""
            if link and link in seen:
                continue
            seen.add(link)
            out.append(row)
    return out


async def run(ai: Any, search: Any, title: str, provider: str,
              model: Optional[str] = None) -> RunResult:
    """제목 하나에 대해 근거를 확보한다.

    Args:
        ai: generate(prompt, provider, model, ...) 를 가진 서비스
        search: search_many(plan, count) 를 가진 ReferenceSearchService
        title: 확정된 제목
        provider/model: 판단 작업용 AI. 없으면 빈 결과

    Returns:
        RunResult — 목록·자료·질의·호출 수
    """
    sheet = await ck.build(ai, title, provider, model)
    out = RunResult(sheet=sheet, ai_calls=1)
    if not sheet.items:
        logger.info("[CHECKLIST_RUN] 목록이 비었다 — 기존 경로로 간다")
        return out

    plan = sheet.queries()
    out.queries = list(plan)
    bundle = await search.search_many(plan, count=PER_ITEM)
    out.results = _flatten(bundle)

    await ck.judge(ai, sheet, _evidence_text(out.results), provider, model)
    out.ai_calls += 1

    if ck.should_retry(sheet):
        retry = ck.broaden(sheet)
        logger.info("[CHECKLIST_RUN] 빈칸 %d개 — 재검색 %d건",
                    len(sheet.unfilled_items), len(retry))
        sheet.rounds += 1
        more = await search.search_many(retry, count=PER_ITEM)
        added = _flatten(more)
        known = {getattr(r, "link", "") for r in out.results}
        out.results.extend(r for r in added
                           if (getattr(r, "link", "") or "") not in known)
        out.queries.extend(retry)
        await ck.judge(ai, sheet, _evidence_text(added), provider, model)
        out.ai_calls += 1

    logger.info("[CHECKLIST_RUN] %s | 채움 %.0f%% | 자료 %d건 | AI %d회",
                title[:30], sheet.coverage * 100, len(out.results),
                out.ai_calls)
    return out


CHECKLIST_KEY = "evidence_checklist"


def is_enabled(settings: Optional[Dict[str, Any]]) -> bool:
    """참조 설정에서 체크리스트를 켰는가. 기본은 꺼짐.

    호출이 늘어나는 기능이라 기본값을 켜 두지 않는다. 근거가 중요한
    니치(법·제도·금융)부터 켜는 것이 맞다.
    """
    return bool(((settings or {}).get(CHECKLIST_KEY) or {}).get("enabled"))


async def collect_evidence(ai: Any, search: Any, query: str, title: str,
                           settings: Optional[Dict[str, Any]],
                           max_search: int = 30):
    """검색 단계를 대신한다.

    체크리스트가 꺼져 있으면 기존 단일 웹문서 검색 그대로다. 켜져 있으면
    항목별로 나눠 던지고 목록을 함께 돌려준다.

    Returns:
        (search_results, Checklist 또는 None)
    """
    if not is_enabled(settings):
        return await search.search_webdoc(query, max_search), None

    cfg = (settings or {}).get(CHECKLIST_KEY) or {}
    provider = cfg.get("ai_provider") or settings.get("ai_provider")
    model = cfg.get("ai_model") or settings.get("ai_model")
    if not provider:
        logger.info("[CHECKLIST_RUN] AI 미지정 — 기존 검색으로 간다")
        return await search.search_webdoc(query, max_search), None

    got = await run(ai, search, title or query, provider, model)
    if not got.sheet.items:
        return await search.search_webdoc(query, max_search), None

    # 체크리스트가 자료를 거의 못 채웠으면 기존 검색으로 보충한다.
    if not got.usable:
        logger.info("[CHECKLIST_RUN] 채움 %.0f%% — 기존 검색으로 보충",
                    got.sheet.coverage * 100)
        extra = await search.search_webdoc(query, max_search)
        known = {getattr(r, "link", "") for r in got.results}
        got.results.extend(r for r in extra
                           if (getattr(r, "link", "") or "") not in known)
    return got.results, got.sheet
