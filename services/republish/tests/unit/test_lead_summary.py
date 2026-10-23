"""블로거 첫 문단 = 검색 설명 지시(lead_summary) — 10/23."""
from types import SimpleNamespace

from app.models.blog import BlogPlatform
from app.services.generation import lead_summary as ls


def test_blogger_gets_directive_once():
    blog = SimpleNamespace(name="수작남", platform=BlogPlatform.BLOGGER)
    once = ls.append("본문 지시", blog)
    assert once.startswith("본문 지시\n\n") and ls.MARK in once
    assert ls.append(once, blog) == once


def test_other_platforms_untouched():
    for p in (BlogPlatform.WORDPRESS, BlogPlatform.OTHER, None, "wordpress"):
        assert ls.append("본문 지시", SimpleNamespace(name="x", platform=p)) == "본문 지시"


def test_string_platform_blogger():
    assert ls.MARK in ls.append("p", SimpleNamespace(name="x", platform="BLOGGER"))
