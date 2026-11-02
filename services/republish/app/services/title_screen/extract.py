"""3단계 검색어 뽑기 — gpt-4o-mini 에 제목 50개씩 묶어 '사람들이 실제로 치는 말' 후보 2~3개와 칸 번호.

같은 주제여도 말에 따라 검색량이 수천 배 차이 난다(국민연금 수령시기 10 ↔ 수령나이 56,260).
그래서 후보를 2~3개 받아 4단계에서 전부 잰다. 칸(하위주제) 이름표도 같은 호출에서 받는다.
검색어 칸 붙이기(정리 때 칸 없는 채택 검색어)도 같은 칸 목록으로 여기서 묻는다.

순서도: docs/flowcharts/title_screen_d.md (3)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger

logger = get_logger("title_screen", "app.log")

PROVIDER = "openai"
MODEL = "gpt-4o-mini"
BATCH = 50
KW_BATCH = 100

TITLE_PROMPT = """아래 블로그 제목마다, 이 글을 찾는 사람이 네이버 검색창에 실제로 칠 검색어 후보 2~3개와 맞는 칸 번호를 고르세요.

검색어 규칙
- 2~4낱말의 짧은 말. 띄어쓰기는 사람들이 치는 대로.
- 같은 뜻의 다른 말을 섞어 후보를 만듭니다(예: 국민연금 수령시기 / 국민연금 수령나이).
- 블로그 이름·지역 가게 이름·상품 모델명은 빼고, 주제 말 중심으로.
칸 규칙
- 아래 칸 목록에서 가장 가까운 칸 번호 하나. 제목 주제가 목록의 어느 주제에 들어가면 0을 쓰지 말고
  그 주제 안에서 가장 가까운 칸을 고릅니다(예: 상속세 → 상속·증여, 기저귀 지원사업 → 육아·가족 지원).
- 0은 목록 어느 주제와도 상관없을 때만(게임·연예·드라마·종교·쇼핑 상품 후기·맛집 등).

출력: JSON 객체 하나만. 열쇠 = 제목 번호(문자), 값 = [[검색어 후보들], 칸번호]. 모든 제목 번호를 빠짐없이.
예) {{"1": [["국민연금 수령나이", "국민연금 수령시기"], 105], "2": [["장례식화환"], 0]}}

칸 목록
{catalog}

제목
{items}"""

KEYWORD_PROMPT = """아래 검색어마다 가장 가까운 칸 번호 하나를 고르세요.
- 검색어 주제가 목록의 어느 주제에 들어가면 그 주제 안에서 가장 가까운 칸. 어느 주제와도 상관없으면 0.
- 회사·쇼핑몰·가게 이름만 있는 말, 띄어쓰기가 깨진 말·문장, 지역 맛집·카페, 게임, 성인, 주가·시세는 0.

출력: 한 줄에 하나씩 `번호|칸번호` (다른 말 없이)

칸 목록
{catalog}

검색어
{items}"""

KW_LINE = re.compile(r"^\s*(\d+)\s*[|｜]\s*(\d+)\s*$")


@dataclass
class Picked:
    """제목 하나에 대한 AI 답."""

    candidates: List[str] = field(default_factory=list)
    subtopic_id: Optional[int] = None


async def catalog(db: AsyncSession, user_id: int) -> Dict[int, Tuple[int, str]]:
    """칸 목록 {하위주제 id: (주제 id, '주제>하위주제')}. 지운 칸은 뺀다."""
    from ...models.category import SubTopic, Topic

    rows = (await db.execute(
        select(SubTopic.id, Topic.id, Topic.name, SubTopic.name)
        .join(Topic, Topic.id == SubTopic.topic_id)
        .where(SubTopic.is_deleted.is_(False), Topic.is_deleted.is_(False),
               Topic.user_id == user_id)
        .order_by(SubTopic.id))).all()
    return {sid: (tid, f"{tname}>{sname}") for sid, tid, tname, sname in rows}


def catalog_text(cat: Dict[int, Tuple[int, str]]) -> str:
    """프롬프트에 넣을 칸 목록 — 주제별 한 줄(예: '세금/절세: 87 연말정산, 88 종합소득세')."""
    groups: Dict[str, List[str]] = {}
    for sid, (_, name) in cat.items():
        topic, _, sub = name.partition(">")
        groups.setdefault(topic, []).append(f"{sid} {sub}")
    return "\n".join(f"- {t}: {', '.join(items)}" for t, items in groups.items())


def _json(text: str) -> Optional[dict]:
    """답에서 JSON 객체를 꺼낸다(코드 울타리·앞뒤 말 무시)."""
    import json

    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def parse_titles(text: str, size: int, valid: Sequence[int]) -> Dict[int, Picked]:
    """AI 답(JSON) → {0부터 번호: Picked}. 칸 번호가 목록에 없으면 None. 빠진 번호는 결과에 없다."""
    data = _json(text) or {}
    ok = set(valid)
    out: Dict[int, Picked] = {}
    for k, v in data.items():
        try:
            idx = int(k) - 1
            words, sid = v[0], int(v[1] or 0)
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if not 0 <= idx < size or not isinstance(words, list):
            continue
        cands = [str(c).strip(" \"'“”") for c in words if str(c).strip()]
        out[idx] = Picked(cands[:3], sid if sid in ok else None)
    return out


def parse_keywords(text: str, size: int, valid: Sequence[int]) -> Dict[int, Optional[int]]:
    """칸 붙이기 답 → {0부터 번호: 칸 id 또는 None}."""
    out: Dict[int, Optional[int]] = {}
    ok = set(valid)
    for line in (text or "").splitlines():
        m = KW_LINE.match(line.strip().strip("`"))
        if not m:
            continue
        idx, sid = int(m.group(1)) - 1, int(m.group(2))
        if 0 <= idx < size:
            out[idx] = sid if sid in ok else None
    return out


class Extractor:
    """AI 호출 묶음. 호출 수·실패 수를 세어 비용을 보고한다."""

    def __init__(self, db: AsyncSession, cat: Dict[int, Tuple[int, str]]):
        from ..ai.ai_service import AIService

        self.ai = AIService(db)
        self.cat = cat
        self.cat_text = catalog_text(cat)
        self.calls = 0
        self.failed = 0
        self.chars_in = 0
        self.chars_out = 0

    async def _ask(self, prompt: str, max_tokens: int) -> str:
        """한 번 부른다. 실패는 빈 글(그 묶음은 다음 회차에 다시)."""
        self.calls += 1
        self.chars_in += len(prompt)
        try:
            res: Any = await self.ai.generate(prompt=prompt, provider=PROVIDER, model=MODEL,
                                              max_tokens=max_tokens, temperature=0.2)
        except Exception as e:  # noqa: BLE001 — 한 묶음 실패로 회차를 죽이지 않는다
            self.failed += 1
            logger.warning("[TITLE_SCREEN] AI 실패 | %s", e)
            return ""
        text = ((res or {}).get("content") or "").strip()
        if not text:
            self.failed += 1
        self.chars_out += len(text)
        return text

    async def titles(self, titles: List[str]) -> Dict[int, Picked]:
        """제목 묶음(50개까지) → 후보·칸. 답이 없는 번호는 결과에 없다(판정 보류)."""
        items = "\n".join(f"{i + 1}. {t[:120]}" for i, t in enumerate(titles))
        text = await self._ask(TITLE_PROMPT.format(catalog=self.cat_text, items=items),
                               max_tokens=60 * len(titles) + 200)
        return parse_titles(text, len(titles), list(self.cat))

    async def keywords(self, words: List[str]) -> Dict[int, Optional[int]]:
        """검색어 묶음(100개까지) → 칸."""
        items = "\n".join(f"{i + 1}. {w}" for i, w in enumerate(words))
        text = await self._ask(KEYWORD_PROMPT.format(catalog=self.cat_text, items=items),
                               max_tokens=10 * len(words) + 100)
        return parse_keywords(text, len(words), list(self.cat))
