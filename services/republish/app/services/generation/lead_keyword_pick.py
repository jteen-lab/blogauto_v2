"""맨 앞 검색어 고르기 — DB·API 없이 후보를 만들고 검색량으로 고르는 순수 함수.

N1 확장(2026-10-23, 마케팅 지시·형 승인): 원래 제목 앞 낱말만 후보로 두면
'고흥석류 효능'(10 미만)처럼 수식어가 붙은 말밖에 못 고른다. 사람들은
'석류 효능'(9,050)을 친다. 그래서 후보를 셋으로 넓힌다.

  title    원래 제목 앞 낱말 묶음 + 제목 핵심어(지금까지와 같음)
  stripped 앞 수식어(지역·연도)를 뺀 묶음 — '고흥석류 효능' → '석류 효능'
  related  검색광고가 같은 조회에서 돌려준 연관 검색어 중, 원래 제목 낱말과
           일반어(방법·효능·조건…)로만 이루어진 것 — 새 고유명사가 들어오면 버린다
           ('비타민C효능'·'국민은행대출' X)

고르기: 두 낱말 이상 우선 → 검색량 큰 순(바닥선 이상만). 경쟁 '높음'에 3만 이상인
큰 말이면 그 말을 품은 더 긴 묶음(바닥선 이상)을, 원래 제목 쪽 후보가 1.5배 안이면
원래 제목 쪽을, 제목이 지역으로 시작하고 그 지역 묶음이 바닥선 이상이면 지역 묶음을.

순서도: docs/flowcharts/title_lead_keyword.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .link_relevance import _strip_suffix

MIN_VOLUME = 50
BIG_VOLUME = 30000
NEAR_RATIO = 1.5
MAX_HINTS = 5
_PUNCT = re.compile(r"[^\w가-힣\s]")
_YEAR = re.compile(r"^(?:19|20)?\d{2}년?도?$")
_PARTICLES = set("은 는 이 가 을 를 의 에 도 와 과 로 만 란".split())

# 연관 검색어에 붙어도 주제가 바뀌지 않는 일반어(새 고유명사가 아님)
GENERIC: Set[str] = set(
    "방법 하는법 하는방법 사용법 먹는법 먹는방법 만드는법 보관법 관리법 해결법 해결방법 "
    "효능 효과 부작용 조건 비용 가격 시세 종류 뜻 신청 신청방법 조회 등록 차이 차이점 "
    "기간 서류 절차 후기 추천 정리 계산 계산기 대상 자격 금리 한도 시간 설치 다운로드 "
    "다운 해결 오류 갱신 발급 재발급 확인 칼로리 만들기 레시피 황금 황금비율 비율 양념 "
    "순위 비교 단축키 변경 해지 취소 혜택 지원 기준 요금 할인 납부 환급 출력 복사 교체 "
    "수리 열기 뷰어 설정 꿀팁 팁 주의사항 증상 원인 예방 관리 이자 상환 공제 중간정산 "
    "시세표 감가율 감가 중고 중고차 할부 조건표 담보 담보대출 대출 개설 사용처 사용 "
    "방법들 정상수치 수치 정상 기준표 총정리 쉽게 바로 빨리".split())
# 한 낱말 검색어로 쓰지 않을 말(너무 넓다)
SINGLE_STOP: Set[str] = GENERIC | {"모바일", "pc", "앱", "어플", "체크리스트"}


@dataclass
class Candidate:
    """검색량을 잴 후보. source = title|stripped|related."""

    text: str
    source: str
    volume: int = 0
    competition: str = ""

    @property
    def key(self) -> str:
        """검색광고가 돌려주는 꼴(공백 없음·소문자)."""
        return self.text.replace(" ", "").lower()


def words(title: str) -> List[str]:
    """제목 낱말(문장부호 뺌)."""
    return _PUNCT.sub(" ", title or "").split()


def _bundles(ws: List[str]) -> List[str]:
    """앞 낱말 2·3·1개 묶음(마지막 낱말은 조사를 뗀다)."""
    out = []
    for n in (2, 3, 1):
        if len(ws) >= n:
            head = ws[:n - 1] + [_strip_suffix(ws[n - 1]) or ws[n - 1]]
            out.append(" ".join(head))
    return out


def strip_modifiers(ws: List[str], regions: Set[str]) -> List[str]:
    """앞 수식어(지역 낱말·연도)를 뺀 낱말. 지역이 붙은 첫 낱말은 지역만 뗀다."""
    out = list(ws)
    while out and (out[0] in regions or _YEAR.match(out[0])
                   or _strip_suffix(out[0]) in regions):
        out.pop(0)
    if out:
        first = out[0]
        for r in sorted(regions, key=len, reverse=True):
            if len(r) >= 2 and first.startswith(r) and len(first) - len(r) >= 2:
                out[0] = first[len(r):]
                break
    return out


def region_lead(ws: List[str], regions: Set[str]) -> bool:
    """제목이 지역 낱말로 시작하나('청주 콜택시', '대구 벼룩시장')."""
    return bool(ws) and (ws[0] in regions or _strip_suffix(ws[0]) in regions)


def title_candidates(title: str, keywords: Optional[Iterable[str]],
                     regions: Set[str]) -> List[Candidate]:
    """원래 제목 쪽 후보(title·stripped), 공백 뺀 꼴 기준 중복 없이."""
    ws = words(title)
    raw = [Candidate(b, "title") for b in _bundles(ws)]
    raw += [Candidate(str(k).strip(), "title") for k in (keywords or []) if str(k).strip()]
    stripped = strip_modifiers(ws, regions)
    if stripped != ws:
        raw += [Candidate(b, "stripped") for b in _bundles(stripped)]
    seen: Set[str] = set()
    out = []
    for c in raw:
        if len(c.key) >= 2 and c.key not in seen:
            seen.add(c.key)
            out.append(c)
    return out


def hints(cands: List[Candidate], title: str) -> List[str]:
    """조회에 보낼 말(최대 5) — 두 낱말 묶음·수식어 뺀 묶음·핵심어·긴 낱말을 고루."""
    order = ([c for c in cands if c.source == "stripped"][:1]
             + [c for c in cands if c.source == "title"])
    out: List[str] = []
    for c in order:
        if c.text not in out:
            out.append(c.text)
    longest = sorted({_strip_suffix(w) or w for w in words(title)}, key=len, reverse=True)
    for w in longest:
        if len(out) >= MAX_HINTS:
            break
        if len(w) >= 2 and w not in GENERIC and all(w not in h for h in out):
            out.append(w)
    return out[:MAX_HINTS]


def _pieces(title: str) -> Set[str]:
    """제목 낱말과 조사 뗀 꼴(소문자)."""
    out: Set[str] = set()
    for w in words(title.lower()):
        out.add(w)
        s = _strip_suffix(w)
        if s:
            out.add(s)
    return out


def _from_title(part: str, pieces: Set[str], regions: Set[str]) -> bool:
    """제목 낱말 그대로이거나, 앞 지역·연도만 뗀 꼴, 뒤 일반어·조사만 뗀 꼴인가.

    '고흥석류'→'석류'(지역 뗌), '닭볶음탕레시피'→'닭볶음탕'(일반어 뗌)은 되고
    '스프레드시트'→'시트', '리즈다이어트'→'다이어트'는 안 된다(뜻이 바뀐다).
    """
    for p in pieces:
        if p == part:
            return True
        if p.startswith(part):
            rest = p[len(part):]
            if rest in GENERIC or rest in _PARTICLES or _strip_suffix(p) == part:
                return True
        if p.endswith(part):
            head = p[:-len(part)]
            if head in regions or _YEAR.match(head):
                return True
    return False


def _match_at(kw: str, i: int, pieces: Set[str], regions: Set[str]) -> int:
    """kw[i:] 앞에서 맞는 가장 긴 조각(제목 낱말 꼴 또는 일반어) 길이. 없으면 0."""
    for j in range(len(kw), i + 1, -1):
        part = kw[i:j]
        if part in GENERIC or _from_title(part, pieces, regions):
            return j - i
    return 0


def segment(kw: str, title: str, regions: Set[str] = frozenset()) -> Optional[str]:
    """연관 검색어를 제목 낱말·일반어로 나눠 띄어 쓴 꼴. 아니면 None.

    제목에서 온 조각이 둘 이상이어야 한다(주제 이탈 방지 — '컴퓨터 가격'은
    '그래픽카드 교체' 글의 검색어가 아니다). '석류효능' + '고흥석류 효능 …' → '석류 효능'.
    """
    kw = (kw or "").replace(" ", "").lower()
    pieces = _pieces(title)
    chunks: List[str] = []
    i = 0
    while i < len(kw):
        n = _match_at(kw, i, pieces, regions)
        if not n:
            return None
        chunks.append(kw[i:i + n])
        i += n
    lower = title.lower().replace(" ", "")
    count = sum(_weight(c, pieces, regions, lower) for c in chunks)
    return " ".join(_split_generic_tail(chunks)) if count >= 2 else None


def _weight(c: str, pieces: Set[str], regions: Set[str], lower: str) -> int:
    """제목에서 온 조각 수. '닭볶음탕레시피'처럼 일반어 꼬리가 붙은 제목 낱말은 2."""
    if c in GENERIC:
        return int(c in lower)
    if not _from_title(c, pieces, regions):
        return 0
    head = _split_generic_tail([c])[0]
    return 2 if head != c and not head[0].isdigit() else 1


def _split_generic_tail(chunks: List[str]) -> List[str]:
    """'닭볶음탕레시피' 처럼 끝에 일반어가 붙은 조각은 떼어 띄어 쓴다."""
    out = []
    for c in chunks:
        tail = next((g for g in sorted(GENERIC, key=len, reverse=True)
                     if c.endswith(g) and len(c) - len(g) >= 2), None)
        out += [c[:-len(tail)], tail] if tail else [c]
    return out


def related_candidates(stats: Dict[str, Tuple[int, str]], title: str,
                       known: Set[str], regions: Set[str] = frozenset()) -> List[Candidate]:
    """조회 결과 중 제목에서 벗어나지 않는 연관 검색어."""
    out = []
    for key, (vol, comp) in stats.items():
        if key in known or len(key) < 2:
            continue
        spaced = segment(key, title, regions)
        if spaced:
            out.append(Candidate(spaced, "related", vol, comp))
    return out


def _bigger_phrase(best: Candidate, pool: List[Candidate], floor: int) -> Candidate:
    """경쟁 높음·3만↑ 큰 말이면 그 말을 품은 더 긴 묶음(바닥선↑) 중 가장 큰 것."""
    if best.competition != "높음" or best.volume < BIG_VOLUME:
        return best
    longer = [c for c in pool if c.key != best.key and best.key in c.key
              and c.volume >= floor]
    return max(longer, key=lambda c: c.volume) if longer else best


def usable(c: Candidate) -> bool:
    """맨 앞 검색어로 쓸 수 있는 꼴(두 낱말↑, 또는 넓지 않은 세 글자↑ 한 낱말)."""
    if " " in c.text:
        return True
    return (len(c.text) >= 3 and c.text.lower() not in SINGLE_STOP
            and c.volume < BIG_VOLUME)


def choose(cands: List[Candidate], floor: int = MIN_VOLUME,
           region_first: bool = False) -> Optional[Candidate]:
    """검색량을 채운 후보에서 하나. 바닥선을 넘는 후보가 없으면 None."""
    ok = [c for c in cands if c.volume >= floor]
    multi = [c for c in ok if " " in c.text]
    pool = multi or [c for c in ok if usable(c)]
    if not pool:
        return None
    if region_first:
        local = [c for c in pool if c.source == "title"
                 and c.text.split()[0] == cands[0].text.split()[0]]
        if local:
            return max(local, key=lambda c: c.volume)
    best = _bigger_phrase(max(pool, key=lambda c: c.volume), ok, floor)
    if best.source == "related":
        near = [c for c in pool if c.source != "related"
                and c.volume * NEAR_RATIO >= best.volume]
        if near:
            best = max(near, key=lambda c: c.volume)
    return best
