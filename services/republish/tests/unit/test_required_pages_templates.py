"""필수 페이지 4종 템플릿 단위 테스트 (애드센스 F1)."""
from app.models.blog import Blog, BlogPlatform
from app.services.publishing.required_pages_templates import (
    REQUIRED_PAGE_TYPES,
    build_required_pages,
)


def _make_blog(**overrides) -> Blog:
    blog = Blog(
        user_id=1,
        name="테스트블로그",
        url="https://example.com",
        platform=BlogPlatform.WORDPRESS,
    )
    for key, value in overrides.items():
        setattr(blog, key, value)
    return blog


def test_build_required_pages_returns_all_four_types():
    blog = _make_blog()
    pages = build_required_pages(blog, "owner@example.com")
    assert set(pages.keys()) == set(REQUIRED_PAGE_TYPES)
    for title, html in pages.values():
        assert title
        assert html


def test_privacy_page_mentions_adsense_and_contact():
    blog = _make_blog()
    _, html = build_required_pages(blog, "owner@example.com")["privacy"]
    assert "AdSense" in html
    assert "owner@example.com" in html


def test_about_page_includes_author_profile_when_set():
    blog = _make_blog(author_profile={
        "name": "홍길동", "bio": "10년차 금융 전문가", "expertise": "재테크",
    })
    _, html = build_required_pages(blog, "owner@example.com")["about"]
    assert "홍길동" in html
    assert "10년차 금융 전문가" in html
    assert "재테크" in html


def test_about_page_without_author_profile_has_no_author_block():
    blog = _make_blog()
    _, html = build_required_pages(blog, "owner@example.com")["about"]
    assert "운영자 소개" not in html
    assert "테스트블로그" in html
