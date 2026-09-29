"""WP 카테고리·메뉴 동기화 단위 테스트 (가짜 HTTP)."""
import json
from types import SimpleNamespace

import httpx
import pytest

from app.services.publishing import wp_category_sync as wcs
from app.services.publishing import wp_menu_sync as wms
from app.services.publishing.wordpress_publisher import WordPressPublisher


class FakeDB:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


def _blog(**kw):
    base = dict(id=6, url="https://ex.com/", placeholders={}, api_key_encrypted="u",
                api_secret_encrypted="p", required_page_ids=None)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _no_crypto(monkeypatch):
    monkeypatch.setattr(wcs, "decrypt_api_key", lambda v: v)


def _wp_server(existing):
    """existing: [{id,name,parent,slug}] — POST 시 추가된다."""
    created = []

    def handler(req: httpx.Request):
        assert req.headers["Authorization"].startswith("Basic ")
        if req.method == "GET" and req.url.path.endswith("/categories"):
            q = req.url.params["search"]
            return httpx.Response(200, json=[c for c in existing if q in c["name"]])
        if req.method == "POST" and req.url.path.endswith("/categories"):
            body = json.loads(req.content)
            item = {"id": 100 + len(created), **body}
            created.append(item)
            existing.append(item)
            return httpx.Response(201, json=item)
        return httpx.Response(404)
    return handler, created


@pytest.mark.asyncio
async def test_existing_reused_and_missing_created(monkeypatch):
    async def rows(bid, db):
        return [(6, "여행/관광", 25, "국내여행지"), (6, "여행/관광", 27, "여행 정보")]
    monkeypatch.setattr(wcs, "load_category_rows", rows)
    existing = [{"id": 5, "name": "여행/관광", "parent": 0, "slug": "x"},
                {"id": 9, "name": "국내여행지", "parent": 77, "slug": "y"}]  # 부모 다름 → 재사용 안 됨
    handler, created = _wp_server(existing)
    blog, db = _blog(), FakeDB()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        res = await wcs.sync_categories(blog, db, client=c)

    assert [e["wp_id"] for e in res["existing"]] == [5]
    assert {(c["name"], c["slug"], c["parent"]) for c in created} == {
        ("국내여행지", "sub-25", 5), ("여행 정보", "sub-27", 5)}
    assert blog.placeholders["wp_category_map"] == {"t:6": 5, "s:25": 100, "s:27": 101}
    assert db.commits == 1 and res["failed"] == []


@pytest.mark.asyncio
async def test_dry_run_creates_nothing(monkeypatch):
    async def rows(bid, db):
        return [(4, "AI/인공지능", 40, "생성형AI")]
    monkeypatch.setattr(wcs, "load_category_rows", rows)
    handler, created = _wp_server([])
    blog, db = _blog(), FakeDB()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        res = await wcs.sync_categories(blog, db, apply=False, client=c)
    assert created == [] and db.commits == 0
    assert [e["kind"] for e in res["planned"]] == ["t", "s"]
    assert "wp_category_map" not in blog.placeholders


def test_pure_helpers():
    assert wcs.category_slug("t", 6) == "topic-6"
    assert wcs.find_category([{"id": 1, "name": "A &amp; B", "parent": 0}], "A & B")["id"] == 1
    m = {"t:6": 5, "s:25": 100}
    assert wcs.pick_category_id(m, 6, 25) == 100
    assert wcs.pick_category_id(m, 6, 99) == 5
    assert wcs.pick_category_id(m, 7, None) is None


@pytest.mark.asyncio
async def test_publish_payload_uses_mapped_subtopic(monkeypatch):
    async def fake_resolve(blog, post):
        return [100]
    monkeypatch.setattr(wcs, "resolve_post_category_ids", fake_resolve)
    blog = _blog(placeholders={"wp_categories": [3]})
    payload = {"categories": [3]}
    await WordPressPublisher._merge_mapped_categories(blog, object(), payload)
    assert payload["categories"] == [3, 100]


@pytest.mark.asyncio
async def test_resolve_fallback_without_session_or_mapping():
    blog = _blog(placeholders={"wp_category_map": {"t:6": 5}})
    # 세션에 붙지 않은 글 → 빈 리스트(기본 카테고리로 발행)
    post = SimpleNamespace(id=1, matched_main_title_id=10)
    assert await wcs.resolve_post_category_ids(blog, post) == []
    payload = {}
    await WordPressPublisher._merge_mapped_categories(blog, post, payload)
    assert "categories" not in payload


@pytest.mark.asyncio
async def test_resolve_with_session(monkeypatch):
    class Sess:
        async def execute(self, stmt):
            return SimpleNamespace(first=lambda: (6, 25))
    monkeypatch.setattr("sqlalchemy.ext.asyncio.async_object_session", lambda p: Sess())
    post = SimpleNamespace(id=1, matched_main_title_id=10)
    mapped = _blog(placeholders={"wp_category_map": {"t:6": 5, "s:25": 100}})
    assert await wcs.resolve_post_category_ids(mapped, post) == [100]
    unmapped = _blog(placeholders={"wp_category_map": {"t:9": 5}})
    assert await wcs.resolve_post_category_ids(unmapped, post) == []


@pytest.mark.asyncio
async def test_menu_unsupported():
    handler = lambda req: httpx.Response(401, json={"code": "rest_cannot_view"})  # noqa: E731
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        res = await wms.ensure_menu(_blog(), client=c)
    assert res["supported"] is False and "401" in res["reason"]


@pytest.mark.asyncio
async def test_menu_created_and_assigned_to_empty_location():
    posts = []

    def handler(req):
        p = req.url.path
        if req.method == "GET" and p.endswith("/menu-locations"):
            return httpx.Response(200, json={"primary": {"menu": 0}, "footer": {"menu": 0}})
        if req.method == "GET" and p.endswith("/menus"):
            return httpx.Response(200, json=[])
        if req.method == "GET" and p.endswith("/menu-items"):
            return httpx.Response(200, json=[])
        body = json.loads(req.content)
        posts.append((p, body))
        return httpx.Response(201, json={"id": 50 + len(posts)})

    blog = _blog(placeholders={"wp_category_map": {"t:6": 5, "s:25": 100}},
                 required_page_ids={"privacy": "11", "terms": "12", "about": "13", "contact": "14"})
    names = wms.names_from_sync({"created": [
        {"kind": "t", "id": 6, "name": "여행", "parent_topic": None},
        {"kind": "s", "id": 25, "name": "국내", "parent_topic": 6}], "existing": []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        res = await wms.ensure_menu(blog, names, client=c)
    assert res["supported"] and res["location"] == "primary" and res["assigned"]
    items = [b for p, b in posts if p.endswith("/menu-items")]
    # 기본은 상위 주제 + 필수 페이지만(하위주제 제외)
    assert len(items) == 5
    assert not any(b["object_id"] == 100 for b in items)
    top = next(b for b in items if b["object_id"] == 5)
    assert top.get("title") == "여행"


# ── 메뉴: 상위 주제 + 필수 페이지만, 기존 주 메뉴 재사용 (2026-09-29) ──
from app.services.publishing import wp_menu_sync as _wm


def test_desired_items_기본은_상위주제와_필수페이지만():
    blog = _blog(placeholders={"wp_category_map": {"t:6": 5, "s:25": 100}})
    blog.required_page_ids = {"about": "11", "contact": "12", "privacy": "13", "terms": "14"}
    keys = [i["key"] for i in _wm.desired_items(blog, {"t:6": "여행"})]
    assert keys == ["t:6", "p:about", "p:contact", "p:privacy", "p:terms"]
    keys_all = [i["key"] for i in _wm.desired_items(blog, {}, include_subtopics=True)]
    assert "s:25" in keys_all


def test_기존_주메뉴가_있으면_그_메뉴를_쓴다():
    locs = {"footer": {"menu": 0}, "primary": {"menu": 7}}
    assert _wm.existing_primary_menu(locs) == 7
    assert _wm.existing_primary_menu({"primary": {"menu": 0}}) is None


def test_빈_자리는_주메뉴_자리부터():
    locs = {"footer": {"menu": 0}, "primary": {"menu": 0}}
    assert _wm.pick_location(locs, 99) == "primary"
