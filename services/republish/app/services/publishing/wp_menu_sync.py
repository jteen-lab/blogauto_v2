"""WordPress 메뉴 보장 — 필수 페이지 4개 + 동기화된 카테고리를 'BlogAuto 메뉴'로.

순서도: docs/flowcharts/wp_category_sync.md

WP 5.9+ 의 /wp/v2/menus, /menu-items, /menu-locations 사용(edit_theme_options 필요).
엔드포인트가 없거나 권한이 없으면 {'supported': False, 'reason': ...} 를 돌려주고 끝낸다.
다른 메뉴가 이미 걸린 테마 위치는 덮어쓰지 않는다.
"""
import httpx

from ...core.logger import get_logger
from .wp_category_sync import MAP_KEY, api_base, map_key, wp_auth_headers

logger = get_logger("wp_menu_sync", "app.log")

MENU_NAME = "BlogAuto 메뉴"
PAGE_ORDER = ("about", "contact", "privacy", "terms")
UNSUPPORTED = (401, 403, 404)


def desired_items(blog, category_names: dict | None = None,
                  include_subtopics: bool = False) -> list:
    """메뉴에 들어갈 항목 계획. category_names: {"t:1": "이름", "s:2": "이름"}

    기본은 '상위 주제 + 필수 페이지'만 — 하위주제까지 넣으면 항목이 20개를 넘어
    모바일에서 지저분해진다(2026-09-29 오너 결정). 하위주제 글은 주제 페이지에 모인다.

    반환: [{key, type, object, object_id, title, parent_key}]
    """
    items = []
    cat_map = (blog.placeholders or {}).get(MAP_KEY) or {}
    names = category_names or {}
    parents = names.get("_parents", {})
    for key, wp_id in cat_map.items():
        if not key.startswith("t:"):
            continue
        items.append({"key": key, "type": "taxonomy", "object": "category",
                      "object_id": int(wp_id), "title": names.get(key, ""),
                      "parent_key": None})
    for key, wp_id in cat_map.items():
        if not include_subtopics or not key.startswith("s:"):
            continue
        items.append({"key": key, "type": "taxonomy", "object": "category",
                      "object_id": int(wp_id), "title": names.get(key, ""),
                      "parent_key": parents.get(key)})
    pages = blog.required_page_ids or {}
    for name in PAGE_ORDER:
        pid = pages.get(name)
        if pid and str(pid).isdigit():
            items.append({"key": f"p:{name}", "type": "post_type", "object": "page",
                          "object_id": int(pid), "title": "", "parent_key": None})
    return items


_PRIMARY_HINTS = ("primary", "main", "header", "menu-1", "top")


def _ordered_slugs(locations: dict) -> list:
    """주 메뉴처럼 보이는 위치를 앞으로."""
    slugs = list((locations or {}).keys())
    return sorted(slugs, key=lambda s: (not any(h in s.lower() for h in _PRIMARY_HINTS), slugs.index(s)))


def existing_primary_menu(locations: dict) -> int | None:
    """이미 주 메뉴 자리에 걸린 메뉴가 있으면 그 id — 새 메뉴를 만들지 않고 거기에 보탠다."""
    for slug in _ordered_slugs(locations):
        mid = int(((locations or {}).get(slug) or {}).get("menu") or 0)
        if mid:
            return mid
    return None


def pick_location(locations: dict, menu_id: int) -> str | None:
    """이미 우리 메뉴가 걸린 위치 → 빈 위치(첫 번째) 순. 남의 메뉴는 건드리지 않는다."""
    for slug, loc in (locations or {}).items():
        if int((loc or {}).get("menu") or 0) == int(menu_id):
            return slug
    for slug in _ordered_slugs(locations):
        if not int(((locations or {}).get(slug) or {}).get("menu") or 0):
            return slug
    return None


async def ensure_menu(blog, category_names: dict | None = None, client=None) -> dict:
    """메뉴 생성/보강 + 테마 위치 지정. 절대 예외를 올리지 않는다."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=20.0)
    try:
        return await _ensure_menu(blog, category_names, client)
    except Exception as e:  # noqa: BLE001
        logger.warning("[WP_MENU] 실패 | blog=%s | %s", getattr(blog, "id", None), e)
        return {"supported": True, "error": f"{type(e).__name__}: {e}"}
    finally:
        if own:
            await client.aclose()


async def _ensure_menu(blog, category_names, client) -> dict:
    base, headers = api_base(blog), wp_auth_headers(blog)
    resp = await client.get(f"{base}/menu-locations", headers=headers)
    if resp.status_code in UNSUPPORTED:
        return {"supported": False, "reason": f"menu-locations HTTP {resp.status_code}"}
    locations = resp.json() if resp.status_code == 200 else {}

    locs = locations if isinstance(locations, dict) else {}
    # 이미 주 메뉴가 걸려 있으면(예: 필수 페이지 4개 메뉴) 그 메뉴에 빠진 항목만 보탠다.
    menu_id = existing_primary_menu(locs)
    reused = menu_id is not None
    if menu_id is None:
        menu_id = await _find_or_create_menu(client, base, headers)
    if menu_id is None:
        return {"supported": False, "reason": "menus 엔드포인트 사용 불가"}

    added = await _add_missing_items(client, base, headers, menu_id,
                                     desired_items(blog, category_names))
    location = None if reused else pick_location(locs, menu_id)
    assigned = reused
    if location:
        r = await client.post(f"{base}/menus/{menu_id}",
                              json={"locations": [location]}, headers=headers)
        assigned = r.status_code in (200, 201)
    return {"supported": True, "menu_id": menu_id, "added": added,
            "location": location, "assigned": assigned, "reused_existing": reused}


async def _find_or_create_menu(client, base, headers) -> int | None:
    resp = await client.get(f"{base}/menus", params={"per_page": 100}, headers=headers)
    if resp.status_code in UNSUPPORTED:
        return None
    for m in resp.json() or []:
        if m.get("name") == MENU_NAME:
            return int(m["id"])
    resp = await client.post(f"{base}/menus", json={"name": MENU_NAME}, headers=headers)
    if resp.status_code not in (200, 201):
        return None
    return int(resp.json()["id"])


async def _add_missing_items(client, base, headers, menu_id, items) -> list:
    resp = await client.get(f"{base}/menu-items",
                            params={"menus": menu_id, "per_page": 100}, headers=headers)
    existing = resp.json() if resp.status_code == 200 else []
    have = {(e.get("object"), int(e.get("object_id") or 0)): int(e["id"])
            for e in existing or []}
    key_to_item_id, added = {}, []
    base_order = len(existing or [])
    for order, it in enumerate(items, start=base_order + 1):
        ident = (it["object"], it["object_id"])
        if ident in have:
            key_to_item_id[it["key"]] = have[ident]
            continue
        body = {"menus": menu_id, "type": it["type"], "object": it["object"],
                "object_id": it["object_id"], "status": "publish", "menu_order": order}
        if it["title"]:
            body["title"] = it["title"]
        if it["parent_key"] and it["parent_key"] in key_to_item_id:
            body["parent"] = key_to_item_id[it["parent_key"]]
        r = await client.post(f"{base}/menu-items", json=body, headers=headers)
        if r.status_code in (200, 201):
            key_to_item_id[it["key"]] = int(r.json()["id"])
            added.append(it["key"])
    return added


def names_from_sync(result: dict) -> dict:
    """sync_categories 결과 → desired_items 용 이름/부모 사전."""
    names, parents = {}, {}
    for status in ("created", "existing"):
        for e in result.get(status, []):
            names[map_key(e["kind"], e["id"])] = e["name"]
            if e["kind"] == "s" and e.get("parent_topic"):
                parents[map_key("s", e["id"])] = map_key("t", e["parent_topic"])
    names["_parents"] = parents
    return names
