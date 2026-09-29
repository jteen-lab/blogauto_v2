"""WordPress 카테고리 동기화 — 블로그 카테고리(topic/subtopic)를 WP 카테고리로 만든다.

순서도: docs/flowcharts/wp_category_sync.md

- topic → WP 부모 카테고리, subtopic → 그 아래 자식 카테고리
- 매핑은 blog.placeholders['wp_category_map'] = {"t:<topic_id>": wp_id, "s:<subtopic_id>": wp_id}
- 발행 시 resolve_post_category_ids() 가 글의 MainTitle topic/subtopic 으로 WP ID 를 고른다.
"""
import base64
import html
from typing import Optional

import httpx

from ...core.encryption import decrypt_api_key
from ...core.logger import get_logger

logger = get_logger("wp_category_sync", "app.log")

MAP_KEY = "wp_category_map"
TIMEOUT = 20.0


# ---------------------------------------------------------------- 순수 함수
def map_key(kind: str, obj_id: int) -> str:
    """매핑 키. kind: 't'(topic) | 's'(subtopic)"""
    return f"{kind}:{int(obj_id)}"


def category_slug(kind: str, obj_id: int) -> str:
    """결정적 ASCII 슬러그 — 한글 이름이 바뀌어도 안정적이다."""
    prefix = "topic" if kind == "t" else "sub"
    return f"{prefix}-{int(obj_id)}"


def find_category(items: list, name: str, parent: int = 0) -> Optional[dict]:
    """검색 결과에서 이름(HTML 디코드)과 부모가 정확히 같은 카테고리를 찾는다."""
    want = (name or "").strip()
    for it in items or []:
        got = html.unescape(str(it.get("name", ""))).strip()
        if got == want and int(it.get("parent", 0) or 0) == int(parent or 0):
            return it
    return None


def find_by_slug(items: list, slug: str) -> Optional[dict]:
    for it in items or []:
        if it.get("slug") == slug:
            return it
    return None


def pick_category_id(
    cat_map: dict, topic_id: Optional[int], subtopic_id: Optional[int],
) -> Optional[int]:
    """가장 구체적인 카테고리 1개 — subtopic 매핑 우선, 없으면 topic."""
    cat_map = cat_map or {}
    if subtopic_id and map_key("s", subtopic_id) in cat_map:
        return int(cat_map[map_key("s", subtopic_id)])
    if topic_id and map_key("t", topic_id) in cat_map:
        return int(cat_map[map_key("t", topic_id)])
    return None


def plan_items(rows: list) -> list:
    """(topic_id, topic_name, subtopic_id, subtopic_name) 행 → 중복 없는 생성 계획.

    topic 이 먼저 오도록 정렬된 리스트를 돌려준다.
    """
    topics, subs = {}, {}
    for t_id, t_name, s_id, s_name in rows:
        if not t_id or not t_name:
            continue
        topics[t_id] = t_name
        if s_id and s_name:
            subs[s_id] = (s_name, t_id)
    plan = [
        {"kind": "t", "id": t, "name": n, "parent_topic": None}
        for t, n in sorted(topics.items())
    ]
    plan += [
        {"kind": "s", "id": s, "name": n, "parent_topic": t}
        for s, (n, t) in sorted(subs.items())
    ]
    return plan


def wp_auth_headers(blog) -> dict:
    """WordPressPublisher 와 같은 Basic(애플리케이션 비밀번호) 인증 헤더."""
    username = decrypt_api_key(blog.api_key_encrypted)
    app_password = decrypt_api_key(blog.api_secret_encrypted)
    token = base64.b64encode(f"{username}:{app_password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def api_base(blog) -> str:
    return f"{blog.url.rstrip('/')}/wp-json/wp/v2"


# ---------------------------------------------------------------- DB
async def load_category_rows(blog_id: int, db) -> list:
    """활성 blog_categories → (topic_id, topic_name, subtopic_id, subtopic_name)"""
    from sqlalchemy import select

    from ...models.category import BlogCategory, SubTopic, Topic

    stmt = (
        select(BlogCategory.topic_id, Topic.name, BlogCategory.subtopic_id, SubTopic.name)
        .join(Topic, Topic.id == BlogCategory.topic_id)
        .outerjoin(SubTopic, SubTopic.id == BlogCategory.subtopic_id)
        .where(BlogCategory.blog_id == blog_id, BlogCategory.is_active == True)  # noqa: E712
    )
    return [tuple(r) for r in (await db.execute(stmt)).all()]


def save_map(blog, cat_map: dict) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    ph = dict(blog.placeholders or {})
    ph[MAP_KEY] = cat_map
    blog.placeholders = ph
    try:
        flag_modified(blog, "placeholders")
    except Exception:  # noqa: BLE001 — 테스트용 가짜 객체
        pass


# ---------------------------------------------------------------- HTTP
async def _ensure_one(client, base, headers, item, parent, apply) -> tuple:
    """(wp_id|None, 'existing'|'created'|'planned'|'failed', 사유)"""
    slug = category_slug(item["kind"], item["id"])
    resp = await client.get(
        f"{base}/categories",
        params={"search": item["name"], "per_page": 100},
        headers=headers,
    )
    if resp.status_code != 200:
        return None, "failed", f"search HTTP {resp.status_code}"
    items = resp.json() or []
    hit = find_category(items, item["name"], parent) or find_by_slug(items, slug)
    if hit:
        return int(hit["id"]), "existing", ""
    if not apply:
        return None, "planned", ""
    resp = await client.post(
        f"{base}/categories",
        json={"name": item["name"], "slug": slug, "parent": parent},
        headers=headers,
    )
    if resp.status_code in (200, 201):
        return int(resp.json()["id"]), "created", ""
    data = _safe_json(resp)
    if data.get("code") == "term_exists" and (data.get("data") or {}).get("term_id"):
        return int(data["data"]["term_id"]), "existing", "term_exists"
    return None, "failed", f"create HTTP {resp.status_code} {data.get('code', '')}"


def _safe_json(resp) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


async def sync_categories(blog, db, *, apply: bool = True, client=None) -> dict:
    """활성 blog_categories 를 WP 카테고리로 보장하고 매핑을 저장한다.

    apply=False 면 조회만 하고 만들 것(planned)을 돌려준다(매핑 저장 안 함).
    """
    out = {"created": [], "existing": [], "failed": [], "planned": [], "map": {}}
    rows = await load_category_rows(blog.id, db)
    plan = plan_items(rows)
    try:
        headers = wp_auth_headers(blog)
    except Exception as e:  # noqa: BLE001
        out["failed"].append({"name": "*", "reason": f"인증 정보 복호화 실패: {e}"})
        return out

    cat_map = dict((blog.placeholders or {}).get(MAP_KEY) or {})
    own = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT)
    try:
        for item in plan:
            parent = 0
            if item["kind"] == "s":
                parent = cat_map.get(map_key("t", item["parent_topic"]))
                if not parent:
                    status = "planned" if not apply else "failed"
                    out[status].append({**item, "reason": "부모 topic 미생성"})
                    continue
            try:
                wp_id, status, reason = await _ensure_one(
                    client, api_base(blog), headers, item, int(parent), apply,
                )
            except Exception as e:  # noqa: BLE001
                wp_id, status, reason = None, "failed", f"{type(e).__name__}: {e}"
            entry = {"kind": item["kind"], "id": item["id"], "name": item["name"],
                     "wp_id": wp_id, "parent": parent,
                     "parent_topic": item["parent_topic"]}
            if reason:
                entry["reason"] = reason
            out[status].append(entry)
            if wp_id:
                cat_map[map_key(item["kind"], item["id"])] = wp_id
    finally:
        if own:
            await client.aclose()

    out["map"] = cat_map
    if apply and cat_map:
        save_map(blog, cat_map)
        await db.commit()
    logger.info(
        "[WP_CAT_SYNC] blog=%s | created=%d existing=%d failed=%d planned=%d",
        blog.id, len(out["created"]), len(out["existing"]),
        len(out["failed"]), len(out["planned"]),
    )
    return out


# ---------------------------------------------------------------- 발행 시
async def resolve_post_category_ids(blog, post) -> list:
    """글의 MainTitle topic/subtopic → 매핑된 WP 카테고리 ID 목록(0~1개).

    세션이 없거나 매핑이 없으면 빈 리스트(=기존 정적/기본 카테고리로 발행).
    절대 예외를 올리지 않는다.
    """
    mt_id = getattr(post, "matched_main_title_id", None)
    if post is None or not mt_id:
        return []
    try:
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_object_session

        from ...models.title import MainTitle

        session = async_object_session(post)
        if session is None:
            logger.warning("[WP_CATEGORY] 세션 없는 글 — 카테고리 매핑 생략 | post_id=%s",
                           getattr(post, "id", None))
            return []
        row = (await session.execute(
            select(MainTitle.topic_id, MainTitle.subtopic_id).where(MainTitle.id == mt_id)
        )).first()
        if not row:
            return []
        cat_map = (blog.placeholders or {}).get(MAP_KEY) or {}
        wp_id = pick_category_id(cat_map, row[0], row[1])
        if wp_id is None:
            logger.warning(
                "[WP_CATEGORY] 매핑 없음 — 기본 카테고리로 발행 | blog=%s topic=%s sub=%s",
                getattr(blog, "id", None), row[0], row[1],
            )
            return []
        return [wp_id]
    except Exception as e:  # noqa: BLE001
        logger.warning("[WP_CATEGORY] 카테고리 매핑 실패 — 생략 | post_id=%s | %s: %s",
                       getattr(post, "id", None), type(e).__name__, str(e)[:120])
        return []
