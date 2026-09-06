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

from typing import Any, Dict, List, Optional

import httpx

from ....core.logger import get_logger
from .base import SourceAdapter, SourceFact, SourceResult, decrypt_key

logger = get_logger("source_data_go_kr", "app.log")

TIMEOUT = 20.0
DEFAULT_ROWS = 10

# 응답에서 항목 목록까지 가는 기본 경로
DEFAULT_ITEMS_PATH = ["response", "body", "items", "item"]


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
        params.update(options.get("extra_params") or {})

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(source.endpoint, params=params)
        except Exception as e:  # noqa: BLE001
            return SourceResult(code=source.code, name=name,
                                error=f"호출 실패: {e}")

        if response.status_code != 200:
            return SourceResult(
                code=source.code, name=name,
                error=f"HTTP {response.status_code}: {response.text[:120]}")

        try:
            payload = response.json()
        except Exception:  # noqa: BLE001 — XML 로 오는 경우가 있다
            return SourceResult(code=source.code, name=name,
                                error="JSON 이 아닌 응답")

        items = _dig(payload, options.get("items_path") or DEFAULT_ITEMS_PATH)
        if items is None:
            return SourceResult(code=source.code, name=name,
                                error="응답에서 목록을 찾지 못했습니다")
        if isinstance(items, dict):
            items = [items]

        facts = _to_facts(items, options, entities, name,
                          getattr(source, "endpoint", ""))
        return SourceResult(code=source.code, name=name, facts=facts)


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

        fields = {label: item.get(key) for label, key in field_map.items()} \
            if field_map else {k: v for k, v in item.items()
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


def _flat(item: Dict[str, Any]) -> str:
    """항목의 값들을 한 줄로. 개체 대조에 쓴다."""
    return " ".join(str(v) for v in item.values()
                    if not isinstance(v, (dict, list)))
