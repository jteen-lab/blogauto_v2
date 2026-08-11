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


def test_contact_form_url_replaces_mailto_exposure():
    """contact_form_url이 설정되면 이메일 텍스트를 노출하지 않아야 한다."""
    blog = _make_blog(author_profile={"contact_form_url": "https://forms.gle/abc123"})
    pages = build_required_pages(blog, "owner@example.com")
    for page_type in ("privacy", "about", "contact"):
        _, html = pages[page_type]
        assert "owner@example.com" not in html
        assert "mailto:" not in html
        assert "https://forms.gle/abc123" in html


def test_contact_page_falls_back_to_mailto_without_form_url():
    """contact_form_url 미설정 시 기존 mailto 방식으로 동작(하위호환)."""
    blog = _make_blog()
    _, html = build_required_pages(blog, "owner@example.com")["contact"]
    assert "mailto:owner@example.com" in html


def test_required_pages_use_stable_phrase_variant_per_blog():
    """블로그별 문구 변주는 재실행해도 동일해야 한다(재발행 시 diff 최소화)."""
    blog = _make_blog()
    _, html_first = build_required_pages(blog, "owner@example.com")["privacy"]
    _, html_second = build_required_pages(blog, "owner@example.com")["privacy"]
    assert html_first == html_second
