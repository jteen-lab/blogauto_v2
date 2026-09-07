"""공공데이터포털 표준 어댑터 — **이 하나로 여러 API** 를 받는다.

포털에 올라온 API 는 인증(`serviceKey`)과 응답 구조가 표준화돼 있다.

    {"response": {"header": {...},
                  "body": {"items": {"item": [...]}, "totalCount": n}}}

그래서 새 API 를 붙일 때 코드를 만들 필요가 없다 — 등록표에 주소와 키만
넣으면 된다. 표준을 벗어난 응답은 `options.items_path` 로 경로를 일러 준다.

정책브리핑 보도자료(3d)도 이 어댑터로 받는다. 보도자료는 1차 출처이면서
최신이라, 제도·지원금 니치에서 특히 값이 크다.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import httpx

from ....core.logger import get_logger
from .base import SourceAdapter, SourceFact, SourceResult, decrypt_key

logger = get_logger("source_data_go_kr", "app.log")

TIMEOUT = 20.0
DEFAULT_ROWS = 10

# 응답에서 항목 목록까지 가는 기본 경로
DEFAULT_ITEMS_PATH = ["response", "body", "items", "item"]

# 포털 공통 오류 코드 → 무엇을 해야 하는지.
#
# 원문은 "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" 처럼 영문 상수라 사용자가
# 무엇을 고쳐야 할지 알 수 없다. 실제로 이 오류를 받고 멈췄다.
ERROR_GUIDE = {
    "SERVICE_KEY_IS_NOT_REGISTERED_ERROR": (
        "인증키가 이 API 에 등록돼 있지 않습니다. Decoding·Encoding 두 형태로 "
        "모두 시도했으므로 키 표기 문제는 아닙니다. "
        "① 공공데이터포털 > 마이페이지 > 오픈API > 개발계정에서 **이 API 가 "
        "목록에 있는지** 확인하세요(없으면 활용신청 필요). "
        "② 방금 신청했다면 반영에 최대 1시간이 걸립니다. "
        "③ 같은 기관의 다른 데이터셋을 신청한 것은 아닌지 확인하세요."),
    "NO_OPENAPI_SERVICE_ERROR": (
        "그 주소에 API 가 없습니다. 공공데이터포털 상세 페이지의 "
        "'요청주소'를 그대로 복사해 넣으세요."),
    "APPLICATION_ERROR": "제공기관 쪽 오류입니다. 잠시 후 다시 시도하세요.",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR": (
        "오늘 호출 한도를 넘었습니다. 개발계정은 하루 1,000회입니다."),
    "DEADLINE_HAS_EXPIRED_ERROR": (
        "활용신청 기간이 끝났습니다. 포털에서 연장 신청하세요."),
    "UNREGISTERED_IP_ERROR": "등록되지 않은 IP 입니다. 포털에서 IP 를 등록하세요.",
    "SERVICE_ACCESS_DENIED_ERROR": "이 API 에 대한 접근 권한이 없습니다.",
    "NO_MANDATORY_REQUEST_PARAMETERS_ERROR": (
        "필수 파라미터가 빠졌습니다. 이 API 는 날짜 범위 같은 값을 요구합니다 "
        "— 등록표 options 의 date_params 를 지정하세요."),
    "THREE_DAYS_OVER_ERROR": (
        "조회 기간이 너무 깁니다. 이 API 는 최대 3일까지만 조회됩니다 "
        "(options.date_range_days)."),
}


class DataGoKrAdapter(SourceAdapter):
    """공공데이터포털 REST API."""

    code = "data_go_kr"

    async def fetch(self, source: Any, query: str,
                    entities: List[str]) -> SourceResult:
        """질의로 조회해 항목을 사실로 바꾼다."""
        name = getattr(source, "name", "") or "공공데이터"
        key = decrypt_key(source)
        if not key:
            return SourceResult(code=source.code, name=name,
                                error="인증키가 없습니다")

        options: Dict[str, Any] = getattr(source, "options", None) or {}
        params = {
            "serviceKey": key,
            "returnType": "JSON",
            "type": "JSON",     # API 마다 이름이 달라 둘 다 보낸다
            "numOfRows": options.get("rows", DEFAULT_ROWS),
            "pageNo": 1,
        }
        # 질의 파라미터 이름이 API 마다 다르다(searchWrd, title, keyword…)
        query_field = options.get("query_field")
        if query_field and query:
            params[query_field] = query
        params.update(_date_params(options))
        params.update(options.get("extra_params") or {})

        try:
            response = await _call(source.endpoint, params)
        except Exception as e:  # noqa: BLE001
            return SourceResult(code=source.code, name=name,
                                error=f"호출 실패: {e}")

        # 포털은 오류를 200 으로도, 4xx 로도 준다. 본문의 코드를 먼저 본다.
        guide = _error_guide(response.text, source.endpoint)
        if guide:
            return SourceResult(code=source.code, name=name, error=guide)

        if response.status_code != 200:
            return SourceResult(
                code=source.code, name=name,
                error=f"HTTP {response.status_code}: {response.text[:120]}")

        # 포털 API 는 JSON 만 주는 곳, XML 만 주는 곳이 섞여 있다.
        # returnType=JSON 을 보내도 XML 로 오는 API 가 있다.
        items = _extract(response.text,
                         options.get("items_path") or DEFAULT_ITEMS_PATH)
        if items is None:
            return SourceResult(
                code=source.code, name=name,
                error="응답에서 목록을 찾지 못했습니다. options.items_path 를 "
                      "응답 구조에 맞게 지정해야 할 수 있습니다.")
        if not items:
            return SourceResult(
                code=source.code, name=name,
                error="호출은 성공했지만 결과가 0건입니다. "
                      "이 API 는 검색 조건이 다르거나 데이터가 없을 수 있습니다.")

        facts = _to_facts(items, options, entities, name,
                          getattr(source, "endpoint", ""))
        return SourceResult(code=source.code, name=name, facts=facts)


async def _call(endpoint: str, params: Dict[str, Any]):
    """호출한다. 키가 안 먹히면 **다른 형태로 한 번 더** 시도한다.

    포털은 인증키를 두 가지로 준다.

        Decoding  abc+def/ghi==
        Encoding  abc%2Bdef%2Fghi%3D%3D

    같은 키인데 표기가 다르다. httpx 는 파라미터를 자동 인코딩하므로
    Decoding 키가 맞지만, Encoding 키를 넣으면 `%` 가 다시 인코딩돼
    (`%252B`) SERVICE_KEY_IS_NOT_REGISTERED_ERROR 가 난다.

    어느 쪽을 넣었는지 사용자가 알기 어렵다. 실패하면 반대 형태로
    자동 재시도한다 — 화면에서 바꿔 가며 시험하게 할 이유가 없다.
    """
    from urllib.parse import quote, unquote

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(endpoint, params=params)
        if "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" not in (response.text or ""):
            return response

        key = str(params.get("serviceKey") or "")
        flipped = unquote(key) if "%" in key else quote(key, safe="")
        if not flipped or flipped == key:
            return response

        # 이미 인코딩된 키는 다시 인코딩되면 안 된다. 질의문자열을 직접 만든다.
        rest = "&".join(
            f"{k}={quote(str(v), safe='')}"
            for k, v in params.items() if k != "serviceKey")
        url = f"{endpoint}?serviceKey={flipped}"
        if rest:
            url = f"{url}&{rest}"
        logger.info("[DATA_GO_KR] 인증키 형태를 바꿔 재시도")
        retried = await client.get(url)
        if "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" not in (retried.text or ""):
            return retried
        return response


def _date_params(options: Dict[str, Any]) -> Dict[str, str]:
    """날짜가 필수인 API 에 기간을 채워 준다.

    정책브리핑은 startDate·endDate 가 없으면
    NO_MANDATORY_REQUEST_PARAMETERS_ERROR 를, 범위가 3일을 넘으면
    THREE_DAYS_OVER_ERROR 를 준다. 사용자가 알 수 없는 규칙이라
    등록표(options)에 적어 두고 여기서 계산한다.
    """
    from datetime import date, timedelta

    names = options.get("date_params") or {}
    start_key, end_key = names.get("start"), names.get("end")
    if not start_key or not end_key:
        return {}

    span = max(1, int(options.get("date_range_days") or 3))
    end = date.today()
    start = end - timedelta(days=span - 1)
    return {start_key: start.strftime("%Y%m%d"),
            end_key: end.strftime("%Y%m%d")}


def looks_like_service_base(endpoint: str) -> bool:
    """포털이 보여 주는 "End Point" 만 넣었는가.

    포털 상세 화면의 End Point 는 **서비스 주소**다. 실제 호출에는 그 뒤에
    오퍼레이션 이름이 붙는다.

        End Point  https://apis.data.go.kr/1371000/policyNewsService2
        요청 주소   https://apis.data.go.kr/1371000/policyNewsService2/policyNewsList

    기관코드 뒤 경로가 한 조각뿐이면 오퍼레이션이 빠진 것으로 본다.
    """
    raw = (endpoint or "").strip("/ ")
    if not raw:
        return False        # 주소가 없는 것이지 오퍼레이션 문제가 아니다
    path = re.sub(r"^https?://[^/]+/", "", raw)
    parts = [p for p in path.split("/") if p]
    return len(parts) <= 2      # 기관코드 + 서비스명


def _error_guide(text: str, endpoint: str = "") -> str:
    """응답 본문에서 포털 오류 코드를 찾아 할 일로 바꾼다.

    코드를 그대로 보여 주면 사용자가 무엇을 고쳐야 할지 알 수 없다.
    """
    body = text or ""
    for code, guide in ERROR_GUIDE.items():
        if code not in body:
            continue
        if code == "NO_OPENAPI_SERVICE_ERROR" and looks_like_service_base(
                endpoint):
            return (
                "주소에 **오퍼레이션 이름**이 빠졌습니다. 포털 상세 페이지의 "
                "End Point 는 서비스 주소이고, 그 뒤에 오퍼레이션(예: "
                "policyNewsList)을 붙여야 호출됩니다. 상세 페이지의 "
                "'요청 주소' 또는 오퍼레이션 목록에서 확인하세요. "
                f"(코드: {code})")
        return f"{guide} (코드: {code})"
    return ""


def _extract(text: str, path: List[str]) -> Optional[List[dict]]:
    """JSON 이든 XML 이든 항목 목록을 꺼낸다.

    포털은 API 마다 형식이 다르고, returnType=JSON 을 보내도 XML 로
    돌려주는 곳이 있다(서민금융진흥원). 한쪽만 지원하면 그 API 는 못 쓴다.
    """
    body = (text or "").strip()
    if not body:
        return None

    if body.startswith("{") or body.startswith("["):
        import json

        try:
            payload = json.loads(body)
        except Exception:  # noqa: BLE001
            return None
        found = _dig(payload, path)
        if found is None:
            return None
        if isinstance(found, dict):
            return [found]
        return [f for f in found if isinstance(f, dict)]

    if body.startswith("<"):
        return _from_xml(body, path)
    return None


def _from_xml(body: str, path: List[str]) -> Optional[List[dict]]:
    """XML 응답에서 항목을 꺼낸다.

    경로 마지막 조각(보통 `item`)을 찾는다. XML 은 같은 이름의 형제
    노드가 여러 개이므로 경로를 그대로 따라가지 않고 이름으로 찾는다.
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None

    leaf = path[-1] if path else "item"
    nodes = root.iter(leaf)
    out: List[dict] = []
    for node in nodes:
        row = {child.tag: (child.text or "").strip() for child in node}
        if row:
            out.append(row)
    if out:
        return out
    # `item` 이 없는 응답도 있다. items 아래 아무 자식이나 훑는다.
    for holder in root.iter("items"):
        for child in holder:
            row = {sub.tag: (sub.text or "").strip() for sub in child}
            if row:
                out.append(row)
    return out


def _dig(payload: Any, path: List[str]) -> Optional[Any]:
    """경로를 따라 내려간다. 중간에 없으면 None."""
    node = payload
    for key in path:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return None
    return node


def _to_facts(items: List[Any], options: Dict[str, Any],
              entities: List[str], source_name: str,
              endpoint: str) -> List[SourceFact]:
    """항목을 사실로. **개체와 무관한 항목은 버린다.**

    검색어로 조회해도 엉뚱한 항목이 섞여 온다. 여기서 한 번 더 좁히지
    않으면 "비슷한 다른 상품" 이 이 글의 사실로 들어간다.
    """
    from ..relevance import matches

    title_field = options.get("title_field")
    field_map: Dict[str, str] = options.get("field_map") or {}
    url_field = options.get("url_field")
    date_field = options.get("date_field")
    limit = int(options.get("max_facts", 3))

    facts: List[SourceFact] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get(title_field) or "").strip() if title_field else ""
        # 개체가 있는데 항목 어디에도 없으면 다른 것이다
        if entities and not matches(f"{title} {_flat(item)}", entities):
            continue

        # 보도자료 본문은 HTML 로 온다. 태그를 그대로 프롬프트에 넣으면
        # 토큰만 먹고, AI 가 그 마크업을 흉내 내기도 한다.
        limit_chars = int(options.get("field_chars", 700))
        if field_map:
            fields = {label: _plain(item.get(key), limit_chars)
                      for label, key in field_map.items()}
        else:
            fields = {k: _plain(v, limit_chars) for k, v in item.items()
                      if not isinstance(v, (dict, list))}
        facts.append(SourceFact(
            title=title or source_name,
            fields=fields,
            source_name=source_name,
            url=str(item.get(url_field) or "") if url_field else endpoint,
            published=str(item.get(date_field) or "") if date_field else "",
        ))
        if len(facts) >= limit:
            break
    return facts


_TAG = re.compile(r"<[^>]+>")
_ENTITY = re.compile(r"&(nbsp|amp|lt|gt|quot|#\d+);")


def _plain(value: Any, limit: int = 700) -> Any:
    """HTML 을 걷어내고 길이를 자른다.

    보도자료 DataContents 는 <p>·<figure>·캡션까지 통째로 온다. 그대로
    두면 참조 하나가 프롬프트를 다 차지한다.
    """
    if value is None or not isinstance(value, str):
        return value
    text = _TAG.sub(" ", value)
    text = _ENTITY.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + "…" if len(text) > limit else text


def _flat(item: Dict[str, Any]) -> str:
    """항목의 값들을 한 줄로. 개체 대조에 쓴다."""
    return " ".join(str(v) for v in item.values()
                    if not isinstance(v, (dict, list)))
