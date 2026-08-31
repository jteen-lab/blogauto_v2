"""이미 블로그에 없는 글도 기록을 정리한다 (2026-08-31).

취업인포마스터에서 153편을 블로거에서 직접 지웠는데 blogauto 기록은
그대로 남아 「발행완료」로 보였다. 앱의 삭제 기능으로도 지워지지 않았다.

원인: 블로거는 URL 로 바로 지울 수 없어 posts/bypath 로 postId 를 먼저
찾는데, **이미 지운 글은 이 조회가 404** 라 삭제 단계에 닿지도 못하고
실패로 처리됐다. 실패한 건은 로컬 기록을 지우지 않으므로 영영 남는다.

같은 이유로 08-31 12:35 로그가 「인생꿀팁 — 0건 / 실패 24건」 이었다.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.blog import BlogPlatform
from app.services.publishing.post_cleanup_service import PostDeleter, slug_of


def _resp(status: int, payload=None) -> SimpleNamespace:
    return SimpleNamespace(status_code=status, json=lambda: payload)


class _Client:
    """httpx.AsyncClient 대역. 호출 순서대로 응답을 돌려준다."""

    def __init__(self, gets, deletes=None, posts=None):
        self._gets = list(gets)
        self._deletes = list(deletes or [])
        self._posts = list(posts or [])
        self.delete_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **kw):
        return self._gets.pop(0)

    async def delete(self, *a, **kw):
        self.delete_calls += 1
        return self._deletes.pop(0)

    async def post(self, *a, **kw):
        return self._posts.pop(0)


def _blogger_blog():
    return SimpleNamespace(platform=BlogPlatform.BLOGGER, url="https://x.blogspot.com",
                           name="취업인포마스터", id=17)


def _wp_blog():
    return SimpleNamespace(platform=BlogPlatform.WORDPRESS, url="https://x.com",
                           name="인생꿀팁", id=14)


# ── 블로거 ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_blogger_already_deleted_counts_as_done() -> None:
    """조회가 404 면 이미 없는 것이다. 실패로 두면 기록이 영영 남는다."""
    client = _Client(gets=[_resp(404), _resp(404)])

    with patch("app.services.publishing.blogger_publisher.BloggerPublisher") as pub, \
         patch("httpx.AsyncClient", return_value=client):
        pub.return_value._get_access_token = AsyncMock(return_value="tok")
        pub.return_value._extract_blog_id = AsyncMock(return_value="b1")
        result = await PostDeleter(_blogger_blog()).delete_by_urls(
            ["https://x.blogspot.com/a.html", "https://x.blogspot.com/b.html"])

    assert result["done"] == 2, "이미 없는 글이 실패로 잡힌다"
    assert result["already_gone"] == 2
    assert result["failed"] == []
    assert client.delete_calls == 0, "없는 글을 지우려 API 를 부를 이유가 없다"


@pytest.mark.asyncio
async def test_blogger_real_error_is_still_a_failure() -> None:
    """권한 오류까지 '이미 없음' 으로 넘기면 안 지워진 글의 기록이 사라진다."""
    client = _Client(gets=[_resp(403)])

    with patch("app.services.publishing.blogger_publisher.BloggerPublisher") as pub, \
         patch("httpx.AsyncClient", return_value=client):
        pub.return_value._get_access_token = AsyncMock(return_value="tok")
        pub.return_value._extract_blog_id = AsyncMock(return_value="b1")
        result = await PostDeleter(_blogger_blog()).delete_by_urls(
            ["https://x.blogspot.com/a.html"])

    assert result["done"] == 0
    assert len(result["failed"]) == 1
    assert "403" in result["failed"][0]["error"]


@pytest.mark.asyncio
async def test_blogger_existing_post_is_deleted_normally() -> None:
    client = _Client(gets=[_resp(200, {"id": "p1"})], deletes=[_resp(204)])

    with patch("app.services.publishing.blogger_publisher.BloggerPublisher") as pub, \
         patch("httpx.AsyncClient", return_value=client):
        pub.return_value._get_access_token = AsyncMock(return_value="tok")
        pub.return_value._extract_blog_id = AsyncMock(return_value="b1")
        result = await PostDeleter(_blogger_blog()).delete_by_urls(
            ["https://x.blogspot.com/a.html"])

    assert result == {"done": 1, "failed": [], "already_gone": 0}
    assert client.delete_calls == 1


# ── 워드프레스 ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_wordpress_missing_slug_counts_as_done() -> None:
    """슬러그 조회가 성공했는데 결과가 없으면 이미 없는 것이다."""
    client = _Client(gets=[_resp(200, [])])

    blog = _wp_blog()
    with patch("httpx.AsyncClient", return_value=client), \
         patch.object(PostDeleter, "__init__", lambda self, b: (
             setattr(self, "blog", b),
             setattr(self, "_svc", SimpleNamespace(_wp_auth=lambda: "auth")),
             None)[-1]):
        result = await PostDeleter(blog).delete_by_urls(["https://x.com/gone/"])

    assert result["done"] == 1 and result["already_gone"] == 1
    assert result["failed"] == []


@pytest.mark.asyncio
async def test_wordpress_lookup_failure_is_not_treated_as_gone() -> None:
    """조회 자체가 실패한 것과 글이 없는 것을 구분해야 한다."""
    client = _Client(gets=[_resp(500, [])])

    blog = _wp_blog()
    with patch("httpx.AsyncClient", return_value=client), \
         patch.object(PostDeleter, "__init__", lambda self, b: (
             setattr(self, "blog", b),
             setattr(self, "_svc", SimpleNamespace(_wp_auth=lambda: "auth")),
             None)[-1]):
        result = await PostDeleter(blog).delete_by_urls(["https://x.com/gone/"])

    assert result["done"] == 0
    assert len(result["failed"]) == 1


@pytest.mark.asyncio
async def test_wordpress_delete_404_counts_as_done() -> None:
    """id 는 찾았는데 지우려니 없는 경우(410 Gone 포함).

    doooit082 계열은 /1998/ 처럼 글 번호를 URL 로 쓴다 — 조회 없이 바로 지운다.
    """
    client = _Client(gets=[], deletes=[_resp(410)])

    blog = _wp_blog()
    with patch("httpx.AsyncClient", return_value=client), \
         patch.object(PostDeleter, "__init__", lambda self, b: (
             setattr(self, "blog", b),
             setattr(self, "_svc", SimpleNamespace(_wp_auth=lambda: "auth")),
             None)[-1]):
        result = await PostDeleter(blog).delete_by_urls(["https://x.com/1998/"])

    assert result["done"] == 1 and result["already_gone"] == 1


def test_slug_of() -> None:
    assert slug_of("https://a.com/2026/08/my-post/") == "my-post"
    assert slug_of("") == ""


def test_router_reports_already_gone_separately() -> None:
    """합쳐서 '24건 처리' 만 보이면 무엇이 일어났는지 알 수 없다."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2]
           / "app/routers/post_cleanup.py").read_text(encoding="utf-8")
    assert "already_gone" in src
    assert "이미 없던 글" in src
