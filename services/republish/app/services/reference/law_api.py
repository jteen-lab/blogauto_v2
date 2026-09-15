"""법제처 국가법령정보 공동활용 API.

법 근거가 필요한 글에서 2차 정보 대신 원문을 쓴다. 네이버 검색이
링크를 주는 것과 달리 여기는 판시사항·판결요지를 그대로 준다 —
크롤링이 필요 없다.

순서도: docs/flowcharts/law_reference.md
"""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from ...schemas.reference_collection import SearchResult

logger = logging.getLogger(__name__)

LIST_URL = "http://www.law.go.kr/DRF/lawSearch.do"
BODY_URL = "http://www.law.go.kr/DRF/lawService.do"

#: 조회 대상 — 판례·법령·법령해석례
TARGET_PREC = "prec"
TARGET_LAW = "law"
TARGET_EXPC = "expc"

TIMEOUT = 10

#: 목록이 많아도 본문은 상위 몇 건만 가져온다. 판례는 상위 몇 건이
#: 그 쟁점의 대표인 경우가 많고, 전부 부르면 느리다.
BODY_FETCH_LIMIT = 3

#: 본문에서 잘라 쓸 길이. 판례 전문은 수만 자라 그대로 못 넣는다.
BODY_MAX_CHARS = 1200


def _clean(text: Any) -> str:
    """태그와 겹친 공백을 지운다."""
    out = re.sub(r"<[^>]+>", " ", str(text or ""))
    return re.sub(r"\s+", " ", out).strip()


class LawApiClient:
    """법제처 조회. 인증값이 없으면 아무것도 하지 않는다."""

    def __init__(self, oc: Optional[str]) -> None:
        """Args: oc: 사용자가 정한 API 인증값."""
        self._oc = (oc or "").strip()

    def is_configured(self) -> bool:
        """인증값이 있나. 없으면 호출부가 네이버로 돌아간다."""
        return bool(self._oc)

    async def _get(self, url: str, params: Dict[str, Any]) -> Optional[dict]:
        """한 번 호출한다. 실패는 None — 글 생성을 막지 않는다."""
        params = {**params, "OC": self._oc, "type": "JSON"}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning("[LAW_API] 응답 %s | %s",
                               resp.status_code, params.get("target"))
                return None
            return resp.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("[LAW_API] 호출 실패 | %s | %s",
                           params.get("target"), e)
            return None

    async def search(self, query: str, target: str = TARGET_PREC,
                     count: int = 20) -> List[dict]:
        """목록을 찾는다. 판례는 본문까지 뒤져 찾는다(search=2)."""
        if not self.is_configured() or not (query or "").strip():
            return []
        params: Dict[str, Any] = {
            "target": target, "query": query,
            "display": max(1, min(100, count)),
        }
        if target == TARGET_PREC:
            params["search"] = 2  # 판례명만이 아니라 본문까지
        data = await self._get(LIST_URL, params)
        return _rows(data, target)

    async def fetch_body(self, doc_id: str,
                         target: str = TARGET_PREC,
                         query: str = "") -> str:
        """본문을 가져온다. 법령이면 검색어가 든 조문을 앞세운다."""
        if not self.is_configured() or not doc_id:
            return ""
        data = await self._get(BODY_URL, {"target": target, "ID": doc_id})
        if not isinstance(data, dict):
            return ""
        return _body_text(data, query)


def _rows(data: Optional[dict], target: str) -> List[dict]:
    """응답에서 목록을 꺼낸다. 감싸는 키 이름이 대상마다 다르다."""
    if not isinstance(data, dict):
        return []
    for value in data.values():
        if not isinstance(value, dict):
            continue
        for key in ("prec", "law", "expc", "Law"):
            rows = value.get(key)
            if isinstance(rows, list):
                return rows
            if isinstance(rows, dict):
                return [rows]
    return []


def _article_text(unit: dict) -> str:
    """조문 하나를 글로 만든다.

    내용이 항으로 나뉜 조문은 `조문내용` 에 제목만 들어 있다. 항을
    붙이지 않으면 "제3조의2(보증금의 회수)" 처럼 제목만 남는다.
    """
    head = _clean(unit.get("조문내용"))
    rows = unit.get("항")
    if isinstance(rows, dict):
        rows = [rows]
    if isinstance(rows, list):
        bodies = [_clean(r.get("항내용")) for r in rows
                  if isinstance(r, dict)]
        bodies = [b for b in bodies if b]
        if bodies:
            return f"{head} {' '.join(bodies)}".strip()
    return head


def _articles(inner: dict, query: str) -> str:
    """법령은 조문을 모아 쓴다. 검색어가 든 조문을 앞에 놓는다.

    법 하나가 40조를 넘어 전문을 넣을 수 없다. 글이 실제로 묻는
    조문만 앞에 오면 나머지가 잘려도 쓸 것은 남는다.
    """
    units = ((inner.get("조문") or {}).get("조문단위") or [])
    if isinstance(units, dict):
        units = [units]
    texts = [_article_text(u) for u in units if isinstance(u, dict)]
    texts = [t for t in texts if len(t) > 10]
    if not texts:
        return ""
    q = (query or "").strip()
    if q:
        hit = [t for t in texts if q in t]
        rest = [t for t in texts if q not in t]
        texts = hit + rest
    return " ".join(texts)[:BODY_MAX_CHARS]


def _body_text(data: dict, query: str = "") -> str:
    """대상에 따라 본문을 뽑는다.

    판례는 판시사항·판결요지, 법령은 조문, 해석례는 해석 내용이다.
    """
    inner: dict = data
    for value in data.values():
        if isinstance(value, dict):
            inner = value
            break

    parts = []
    for key in ("판시사항", "판결요지", "법령해석", "회답", "이유"):
        text = _clean(inner.get(key))
        if text:
            parts.append(text)
    if parts:
        return " ".join(parts)[:BODY_MAX_CHARS]

    articles = _articles(inner, query)
    if articles:
        return articles
    return _clean(inner.get("판례내용"))[:BODY_MAX_CHARS]


def _label(row: dict) -> str:
    """목록 한 줄을 제목으로 만든다."""
    for key in ("사건명", "법령명한글", "안건명", "법령명"):
        text = _clean(row.get(key))
        if text:
            return text
    return "법령 자료"


def _doc_id(row: dict) -> str:
    """본문 조회에 쓸 일련번호."""
    for key in ("판례일련번호", "판례정보일련번호",
                "법령ID", "법령일련번호", "안건번호", "ID"):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _link(row: dict, target: str = TARGET_PREC) -> str:
    """원문 주소.

    응답이 주는 상세링크에는 **호출에 쓴 인증값이 박혀 있다.** 그대로
    두면 키가 글에 딸려 나간다. 일련번호로 공개 열람 주소를 만든다.
    """
    doc_id = _doc_id(row)
    if target == TARGET_PREC and doc_id:
        return f"https://www.law.go.kr/precInfoP.do?precSeq={doc_id}"
    if target == TARGET_LAW and doc_id:
        return f"https://www.law.go.kr/lsInfoP.do?lsiSeq={doc_id}"
    return "https://www.law.go.kr"


def _summary(row: dict) -> str:
    """본문을 못 받았을 때 쓸 한 줄."""
    bits = [_clean(row.get(k)) for k in
            ("법원명", "선고일자", "사건번호", "판결유형", "소관부처명")]
    return " · ".join(b for b in bits if b)


async def collect(oc: Optional[str], query: str,
                  target: str = TARGET_PREC,
                  count: int = 20) -> List[SearchResult]:
    """검색해서 상위 몇 건의 본문까지 채운 결과를 돌려준다.

    Args:
        oc: 법제처 인증값. 없으면 빈 목록 — 호출부가 네이버로 돌아간다
        query: 검색어
        target: prec 판례 | law 법령 | expc 법령해석례
        count: 목록 개수

    Returns:
        SearchResult 목록. 상위 몇 건은 description 에 원문이 들어 있어
        따로 크롤링하지 않아도 된다
    """
    client = LawApiClient(oc)
    rows = await client.search(query, target=target, count=count)
    if not rows:
        return []

    heads = rows[:BODY_FETCH_LIMIT]
    bodies = await asyncio.gather(
        *[client.fetch_body(_doc_id(r), target, query) for r in heads],
        return_exceptions=True)

    out: List[SearchResult] = []
    for i, row in enumerate(rows):
        body = ""
        if i < len(heads):
            got = bodies[i]
            body = got if isinstance(got, str) else ""
        out.append(SearchResult(
            title=_label(row),
            link=_link(row, target),
            description=body or _summary(row),
            postdate=_clean(row.get("선고일자")).replace(".", "") or None,
        ))
    logger.info("[LAW_API] %s '%s' | %d건 (본문 %d건)",
                target, query, len(out), len([b for b in bodies if b]))
    return out
