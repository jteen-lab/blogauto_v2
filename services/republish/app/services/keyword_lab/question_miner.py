"""질문 발굴 — 커뮤니티 질문의 *상황*에서 주제를 캔다.

**옛 경로와 무엇이 다른가**

    [키워드]  채택 키워드 → AI 제목        — 니치 안에서만 돈다
    [수집]    남의 제목 → 재조합           — 원본 표현만 바뀐다
    [발굴]    사람의 질문 → 상황 → 제목    — **니치를 넓힌다**

「이사 견적」 하나에서 글 11편이 나온 경로가 이것이다. 주제를 가른 건
니치가 아니라 조건이었다. 2층→3층, 엘베 없음, 장롱 3짝, 합가 경유,
워시타워만 남음. 전부 사람이 질문에 써 넣은 말이다.

**재조합을 거치지 않는다.** 원본 제목이 없기 때문이다. 재조합은 있는
제목의 표현을 바꾸는 도구고, 여기서는 상황에서 제목을 새로 짓는다.

**지문으로 중복을 막는다.** 같은 니치를 계속 긁으면 같은 상황이 반복된다.
이미 쓴 지문은 호출부가 넘겨주고, 이번 회차 지문을 돌려받아 저장한다.

계획서: docs/plans/topic_discovery_and_structure_plan.md §2-2
순서도: docs/flowcharts/topic_discovery.md §2
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from . import situation as sit
from .sources import community
from .sources.base import SRC_NAVER_CAFE, SRC_NAVER_KIN
from .title_gate import TitleGate

logger = get_logger("question_miner", "app.log")

DEFAULT_SOURCES = (SRC_NAVER_KIN, SRC_NAVER_CAFE)

# 한 회차에 AI 에게 보여 줄 질문 수. 많이 넣으면 상황이 뭉개진다.
QUESTIONS_PER_BATCH = 12

# 질문 묶음 하나에서 받을 제목 수
TITLES_PER_BATCH = 5

PROMPT = """다음은 「{niche}」에 대해 사람들이 실제로 올린 질문입니다.
각 질문에는 구체적인 상황이 들어 있습니다.

{questions}

이 질문들을 바탕으로 블로그 글 제목을 {count}개 지어 주세요.

지켜야 할 것
- 질문에 담긴 **상황(조건·수치·제약)**을 제목에 살립니다.
  예: "같은 건물 위층 이사", "장롱이 계단을 못 지날 때"
- 질문을 그대로 옮기지 말고 **글의 주제**로 바꿉니다.
- {count}개가 **서로 다른 상황**을 다뤄야 합니다.
- 지명·상호·개인을 특정할 수 있는 말은 쓰지 않습니다.
- 낚시성 표현("충격", "이것만 알면")과 과장을 쓰지 않습니다.
- 25~45자.
- 번호·따옴표·군더더기 없이 제목만 한 줄에 하나씩 출력하세요."""


@dataclass
class MineResult:
    """한 회차 결과."""

    collected: int = 0
    concrete: int = 0
    fresh: int = 0
    titles: List[str] = field(default_factory=list)
    fingerprints: List[str] = field(default_factory=list)
    signals: Dict[str, int] = field(default_factory=dict)
    admitted: int = 0
    preview: List[dict] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "collected": self.collected, "concrete": self.concrete,
            "fresh": self.fresh, "titles": self.titles,
            "fingerprints": self.fingerprints, "signals": self.signals,
            "admitted": self.admitted, "preview": self.preview,
            "error": self.error,
        }


class QuestionMiner:
    """질문 → 상황 → 제목."""

    def __init__(self, db: AsyncSession, ai_service: Any, user_id: int = 1):
        self.db = db
        self.ai = ai_service
        self.user_id = user_id

    async def run(self, user_settings: Any, seeds: List[str], row: Any,
                  niche: str, known: Sequence[str] = (),
                  sources: Sequence[str] = DEFAULT_SOURCES,
                  provider: Optional[str] = None,
                  model: Optional[str] = None,
                  dry_run: bool = False) -> MineResult:
        """한 회차를 돈다.

        Args:
            user_settings: 네이버 검색 자격증명 보유 객체
            seeds: 질문을 긁을 시드(채택 키워드)
            row: 분류 폴백용 KeywordCandidate
            niche: 프롬프트에 넣을 주제군 이름
            known: 이미 쓴 상황 지문
            sources: 커뮤니티 소스 코드
            provider/model: AI 지정. 없으면 생성하지 않고 상황만 돌려준다.
            dry_run: 저장 없이 판정만

        Returns:
            MineResult
        """
        result = MineResult()
        questions = await self._collect(user_settings, seeds, sources)
        result.collected = len(questions)
        if not questions:
            result.error = "질문을 찾지 못했습니다 — 시드나 API 키를 확인하세요"
            return result

        paired = [(q, sit.extract(q.text)) for q in questions]
        concrete = [(q, s) for q, s in paired if s.is_concrete]
        result.concrete = len(concrete)

        kept = sit.dedupe([s for _, s in concrete], known=known)
        marks = {s.fingerprint() for s in kept}
        fresh = [(q, s) for q, s in concrete if s.fingerprint() in marks]
        result.fresh = len(fresh)
        result.fingerprints = sorted(marks)
        result.signals = sit.summarize([s for _, s in fresh])

        if not fresh:
            result.error = "새로운 상황이 없습니다 — 이미 다룬 주제들입니다"
            return result
        if not provider:
            # 상황만 보고 싶을 때. 호출을 태우지 않는다.
            return result

        result.titles = await self._make_titles(
            fresh[:QUESTIONS_PER_BATCH], niche, provider, model)
        if not result.titles:
            result.error = "제목 생성에 실패했습니다"
            return result

        outcome = await self._admit(result.titles, row, dry_run)
        result.admitted = outcome.get("admitted", 0)
        result.preview = outcome.get("preview", [])
        return result

    async def _collect(self, user_settings: Any, seeds: List[str],
                       sources: Sequence[str]) -> List[Any]:
        """소스별로 질문을 긁는다. 하나가 죽어도 나머지는 쓴다."""
        out: List[Any] = []
        for code in sources:
            try:
                out.extend(await community.collect_questions(
                    user_settings, seeds, code))
            except Exception as e:  # noqa: BLE001
                logger.warning("[QUESTION_MINER] %s 실패 | %s", code, e)
        return out

    async def _make_titles(self, pairs: List[tuple], niche: str,
                           provider: str, model: Optional[str]) -> List[str]:
        """질문 묶음에서 제목을 받는다."""
        lines = []
        for idx, (q, s) in enumerate(pairs, 1):
            tags = ", ".join(s.signals[:5]) or "-"
            lines.append(f"{idx}. {q.title}\n   상황: {tags}")
        prompt = PROMPT.format(niche=niche or "이 주제",
                               questions="\n".join(lines),
                               count=TITLES_PER_BATCH)
        try:
            got = await self.ai.generate(
                prompt=prompt, provider=provider, model=model,
                max_tokens=600, temperature=0.9)
        except Exception as e:  # noqa: BLE001
            logger.warning("[QUESTION_MINER] AI 호출 실패 | %s", e)
            return []
        return parse_titles((got or {}).get("content") or "", TITLES_PER_BATCH)

    async def _admit(self, titles: List[str], row: Any,
                     dry_run: bool) -> Dict[str, Any]:
        """기존 관문을 그대로 태운다. 새 경로라고 따로 두지 않는다."""
        gate = TitleGate(self.db, self.user_id)
        try:
            return await gate.admit(titles, row, dry_run=dry_run)
        except Exception as e:  # noqa: BLE001
            logger.warning("[QUESTION_MINER] 관문 실패 | %s", e)
            return {"admitted": 0, "preview": []}


def parse_titles(text: str, count: int) -> List[str]:
    """모델이 붙이는 번호·따옴표·군더더기를 걷어낸다."""
    out: List[str] = []
    seen = set()
    for line in (text or "").splitlines():
        item = line.strip()
        item = re.sub(r"^[-*•]\s*", "", item)
        item = re.sub(r"^\d+[.)]\s*", "", item)
        item = item.strip(" \"'“”‘’")
        if len(item) < 8 or len(item) > 120 or item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= count:
            break
    return out
