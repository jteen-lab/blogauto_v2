"""근거 체크리스트 — 검색 **전에** 무엇을 알아야 하는지 정한다.

**왜 이게 필요한가**: 지금 파이프라인은 제목에서 질의 하나를 뽑아 한 번
검색하고 끝난다. 자료가 부실해도 그대로 글 생성으로 넘어간다. 되돌아갈
경로가 없는 게 아니라, **되돌아가야 하는지 판정할 기준이 없다.**

사람이 쓸 때는 순서가 이렇다.

    1. 이 사람이 진짜 막힌 지점을 찾는다
    2. 그걸 답하려면 무엇을 알아야 하는지 [목록]을 만든다   ← 검색 전
    3. 목록의 각 항목을 별도 질의로 던진다
    4. 결과를 [목록]에 대조한다 — 빈칸이 있나
    5. 빈칸만 다시 검색
    6. 채워진 목록 순서로 구조를 짜고 쓴다

2번이 전부다. 「원룸 퇴거 청소비」 글의 목록은 이랬다.

    원상회복 의무의 법적 근거는 무엇인가      [law]
    통상손모는 누구 책임인가                  [law]
    계약서 특약이 있으면 달라지는가           [web]
    보증금 임의공제 대응 절차는               [news]

**항목마다 찾을 곳이 다르다.** 이게 "검색 기준이 디테일하다"의 실체다.
법 근거를 웹문서에서 찾으면 블로그 글이 근거가 된다.

**재검색은 목적이 아니라 부속이다.** 목록이 있어야 빈칸이 보이고, 빈칸이
보여야 재검색할 이유가 생긴다. 상한을 둬 무한 루프를 막는다.

계획서: docs/plans/topic_discovery_and_structure_plan.md §2-4
순서도: docs/flowcharts/topic_discovery.md §3
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ...core.logger import get_logger

logger = get_logger("evidence_checklist", "app.log")

# 항목이 지정할 수 있는 소스. ReferenceSearchService.ENDPOINTS 와 맞춘다.
SOURCES = ("web", "news", "kin", "cafe", "encyc", "law")
DEFAULT_SOURCE = "web"

# 항목 수 상한. 늘리면 호출이 선형으로 늘어난다.
MIN_ITEMS = 2
MAX_ITEMS = 5

# 재검색 상한. **코드에 박는다** — 설정으로 빼면 비용이 통제되지 않는다.
MAX_RETRY_ROUNDS = 1

BUILD_PROMPT = """제목: {title}

이 제목으로 글을 쓰려면 무엇을 알아야 하는지 항목으로 적어 주세요.
독자가 진짜 막혀 있는 지점에 답하는 데 필요한 것만 적습니다.

지켜야 할 것
- {min_items}~{max_items}개
- 각 항목은 "무엇을 알아야 하는가"를 한 문장으로 (질문형 아님)
- 항목 끝에 찾을 곳을 대괄호로 표시합니다
  [law] 법령·판례·제도 근거   [news] 최근 변화·시의성
  [kin] 실제 겪은 사례·후기    [encyc] 용어 정의
  [web] 일반 설명·시세
- 제목에 없는 말이라도 답에 필요하면 넣습니다
- 형식: - 항목 내용 [소스]
- 다른 설명 없이 목록만 출력하세요"""

JUDGE_PROMPT = """아래 자료가 각 항목에 답을 주는지 판정해 주세요.

[항목]
{items}

[자료]
{evidence}

각 항목에 대해 한 줄씩, 아래 형식으로만 답하세요.
번호. 채움 또는 빈칸

"채움"은 자료에 그 항목의 답이 실제로 들어 있을 때만 씁니다.
관련은 있지만 답이 없으면 "빈칸"입니다."""


@dataclass
class ChecklistItem:
    """알아야 할 것 하나."""

    ask: str
    source: str = DEFAULT_SOURCE
    filled: bool = False
    tried: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"ask": self.ask, "source": self.source,
                "filled": self.filled, "tried": self.tried}


@dataclass
class Checklist:
    """제목 하나에 딸린 목록."""

    title: str
    items: List[ChecklistItem] = field(default_factory=list)
    rounds: int = 0

    @property
    def filled_items(self) -> List[ChecklistItem]:
        return [i for i in self.items if i.filled]

    @property
    def unfilled_items(self) -> List[ChecklistItem]:
        return [i for i in self.items if not i.filled]

    @property
    def is_complete(self) -> bool:
        return bool(self.items) and not self.unfilled_items

    @property
    def coverage(self) -> float:
        """채움 비율. 화면과 로그가 이 숫자로 말한다."""
        return len(self.filled_items) / len(self.items) if self.items else 0.0

    def queries(self, only_unfilled: bool = False) -> List[Tuple[str, str]]:
        """검색 계획. `search_many()` 에 그대로 넣는다."""
        picked = self.unfilled_items if only_unfilled else self.items
        return [(i.source, _to_query(self.title, i.ask)) for i in picked]

    def outline(self) -> List[str]:
        """채워진 항목이 소제목 순서가 된다.

        항목이 다르면 구조가 다르다. 퇴거 청소와 경유 이사의 구조가
        달랐던 이유가 이것이다.
        """
        return [i.ask for i in self.filled_items]

    def to_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "rounds": self.rounds,
                "coverage": round(self.coverage, 2),
                "items": [i.to_dict() for i in self.items]}


def _to_query(title: str, ask: str) -> str:
    """항목을 검색어로. 제목을 통째로 넣으면 검색이 안 된다."""
    text = re.sub(r"[^\w가-힣\s]", " ", ask or "")
    words = [w for w in text.split() if len(w) > 1]
    return " ".join(words[:8]) or (title or "")[:30]


def parse(text: str) -> List[ChecklistItem]:
    """모델 응답을 항목으로. 대괄호 소스를 읽고, 없으면 web 으로 둔다."""
    out: List[ChecklistItem] = []
    seen = set()
    for line in (text or "").splitlines():
        row = line.strip()
        row = re.sub(r"^[-*•]\s*", "", row)
        row = re.sub(r"^\d+[.)]\s*", "", row).strip()
        if len(row) < 4:
            continue
        source = DEFAULT_SOURCE
        found = re.search(r"\[([a-z]+)\]", row)
        if found:
            code = found.group(1).lower()
            if code in SOURCES:
                source = code
            row = row[:found.start()].strip()
        row = row.strip(" -–—:·")
        if len(row) < 4 or row in seen:
            continue
        seen.add(row)
        out.append(ChecklistItem(ask=row, source=source))
        if len(out) >= MAX_ITEMS:
            break
    return out


def parse_verdicts(text: str, count: int) -> List[bool]:
    """판정 응답을 불린 목록으로. 못 읽은 줄은 빈칸으로 본다."""
    marks: List[bool] = []
    for line in (text or "").splitlines():
        row = line.strip()
        if not row:
            continue
        if "채움" in row or "충족" in row:
            marks.append(True)
        elif "빈칸" in row or "부족" in row or "없음" in row:
            marks.append(False)
        if len(marks) >= count:
            break
    while len(marks) < count:
        marks.append(False)
    return marks


async def build(ai: Any, title: str, provider: str,
                model: Optional[str] = None) -> Checklist:
    """제목에서 목록을 만든다. 실패하면 빈 목록 — 호출부가 기존 경로로 간다."""
    sheet = Checklist(title=title)
    if not provider or not title:
        return sheet
    prompt = BUILD_PROMPT.format(title=title, min_items=MIN_ITEMS,
                                 max_items=MAX_ITEMS)
    try:
        got = await ai.generate(prompt=prompt, provider=provider, model=model,
                                max_tokens=400, temperature=0.4)
    except Exception as e:  # noqa: BLE001
        logger.warning("[CHECKLIST] 생성 실패 | %s", e)
        return sheet

    sheet.items = parse((got or {}).get("content") or "")
    logger.info("[CHECKLIST] %s | 항목 %d개 | %s", title[:30], len(sheet.items),
                [i.source for i in sheet.items])
    return sheet


async def judge(ai: Any, sheet: Checklist, evidence: str, provider: str,
                model: Optional[str] = None) -> Checklist:
    """자료가 각 항목에 답을 주는지 판정한다.

    판정은 **판단 작업**이라 생성보다 중요한 자리다. 여기서 틀리면 재검색이
    헛돌거나 부실한 자료로 글을 쓴다.
    """
    targets = sheet.unfilled_items
    if not targets or not provider or not evidence:
        return sheet

    listed = "\n".join(f"{n}. {i.ask}" for n, i in enumerate(targets, 1))
    prompt = JUDGE_PROMPT.format(items=listed, evidence=evidence[:6000])
    try:
        got = await ai.generate(prompt=prompt, provider=provider, model=model,
                                max_tokens=200, temperature=0.0)
    except Exception as e:  # noqa: BLE001
        logger.warning("[CHECKLIST] 판정 실패 | %s", e)
        return sheet

    marks = parse_verdicts((got or {}).get("content") or "", len(targets))
    for item, ok in zip(targets, marks):
        item.tried += 1
        item.filled = ok
    logger.info("[CHECKLIST] 판정 | 채움 %d/%d (%.0f%%)",
                len(sheet.filled_items), len(sheet.items),
                sheet.coverage * 100)
    return sheet


def should_retry(sheet: Checklist) -> bool:
    """재검색할 이유가 있는가. 상한을 넘기면 더 돌지 않는다."""
    return bool(sheet.unfilled_items) and sheet.rounds < MAX_RETRY_ROUNDS


def broaden(sheet: Checklist) -> List[Tuple[str, str]]:
    """미충족 항목의 질의를 다시 짠다.

    같은 말로 다시 던지면 같은 결과가 온다. 소스를 넓히고(전용 → web)
    질의를 짧게 줄인다.
    """
    plan: List[Tuple[str, str]] = []
    for item in sheet.unfilled_items:
        source = DEFAULT_SOURCE if item.source != DEFAULT_SOURCE else "kin"
        words = _to_query(sheet.title, item.ask).split()
        plan.append((source, " ".join(words[:4]) or sheet.title[:20]))
    return plan


def to_prompt_injection(sheet: Checklist) -> str:
    """구조 지시문. 채워진 항목이 소제목 뼈대가 된다."""
    lines = sheet.outline()
    if not lines:
        return ""
    body = "\n".join(f"- {t}" for t in lines)
    return ("\n\n[글의 뼈대]\n"
            "아래 항목을 순서대로 다룹니다. 각 항목을 소제목 하나로 풉니다.\n"
            f"{body}\n"
            "자료에 없는 항목은 지어내지 말고 건너뜁니다.\n")


def summarize(sheets: Sequence[Checklist]) -> Dict[str, Any]:
    """여러 회차 통계. 판정이 제대로 도는지 화면이 말하게 한다."""
    if not sheets:
        return {"count": 0, "avg_coverage": 0.0, "retried": 0}
    return {
        "count": len(sheets),
        "avg_coverage": round(
            sum(s.coverage for s in sheets) / len(sheets), 2),
        "retried": sum(1 for s in sheets if s.rounds > 0),
    }
