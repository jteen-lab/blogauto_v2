"""검색 노출 라우터 테스트 (2026-08-28 회귀).

서비스 단위 테스트는 전부 통과했는데 운영에서 모든 엔드포인트가 500 이었다.
원인은 `get_blog_or_404(blog_id, user, db)` 를 `(db, blog_id, user_id)` 로
호출한 인자 순서 실수 — 라우터를 실제로 호출하는 테스트가 없어서 놓쳤다.

여기서는 실제 ASGI 요청을 보내 상태 코드와 응답 형태를 확인한다.
"""
import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base, get_db_session
from app.models.blog import Blog, BlogPlatform
from app.models.user import User
from app.routers.auth import get_current_user
from app.routers.search_visibility import router


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # noqa: D103 — 테스트 전용 shim
    return "JSON"


@pytest_asyncio.fixture
async def context():
    """앱 + 세션 + 블로그 1개."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        user = User(email="api@example.com", full_name="테스터", hashed_password="x")
        session.add(user)
        await session.flush()
        blog = Blog(
            user_id=user.id, name="테스트블로그", url="https://example.com",
            platform=BlogPlatform.WORDPRESS,
        )
        session.add(blog)
        await session.commit()

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[get_db_session] = lambda: session
        app.dependency_overrides[get_current_user] = lambda: user

        yield TestClient(app), blog, user

    await engine.dispose()


def test_get_status_returns_config_and_summary(context):
    client, blog, _ = context
    resp = client.get(f"/api/v1/blogs/{blog.id}/search-visibility")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "config" in body and "summary" in body
    # 기준선 확보 전이므로 IndexNow 는 꺼져 있어야 한다
    assert body["config"]["indexnow_enabled"] is False
    assert body["summary"]["total"] == 0


def test_list_urls_empty(context):
    client, blog, _ = context
    resp = client.get(f"/api/v1/blogs/{blog.id}/search-visibility/urls")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"urls": []}


def test_backfill_endpoint_responds(context):
    client, blog, _ = context
    resp = client.post(
        f"/api/v1/blogs/{blog.id}/search-visibility/backfill?limit=5",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"scanned": 0, "created": 0, "existing": 0}


def test_issue_key_then_config_view(context):
    client, blog, _ = context
    resp = client.post(f"/api/v1/blogs/{blog.id}/search-visibility/indexnow/key")
    assert resp.status_code == 200, resp.text
    config = resp.json()["config"]
    assert len(config["indexnow_key"]) == 32
    assert config["indexnow_key_verified"] is False
    assert config["key_file_url"].endswith(f"/{config['indexnow_key']}.txt")


def test_cannot_enable_indexnow_before_verification(context):
    """검증 전에 켜지면 403 이 반복된다 — 서버가 막아야 한다."""
    client, blog, _ = context
    client.post(f"/api/v1/blogs/{blog.id}/search-visibility/indexnow/key")
    resp = client.put(
        f"/api/v1/blogs/{blog.id}/search-visibility/config",
        json={"indexnow_enabled": True},
    )
    assert resp.status_code == 422
    assert "검증" in resp.json()["detail"]


def test_save_config_persists(context):
    client, blog, _ = context
    resp = client.put(
        f"/api/v1/blogs/{blog.id}/search-visibility/config",
        json={"index_check_daily_cap": 77, "sitemap_url": "https://example.com/s.xml"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"]["index_check_daily_cap"] == 77

    again = client.get(f"/api/v1/blogs/{blog.id}/search-visibility")
    assert again.json()["config"]["sitemap_url"] == "https://example.com/s.xml"


def test_index_check_reports_not_connected(context):
    """GSC 미연동이면 조용히 성공하지 말고 사유를 돌려줘야 한다."""
    client, blog, _ = context
    resp = client.post(f"/api/v1/blogs/{blog.id}/search-visibility/check/index")
    assert resp.status_code == 200, resp.text
    assert resp.json()["skipped"] == "gsc_not_connected"


def test_other_users_blog_is_404(context):
    client, _, _ = context
    resp = client.get("/api/v1/blogs/99999/search-visibility")
    assert resp.status_code == 404
