"""저자 바이라인/편집감독 문구 주입 단위 테스트 (애드센스 F2)."""
from app.models.blog import Blog, BlogPlatform
from app.services.generation.author_signal_injector import inject_author_signal


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


def test_no_author_profile_returns_html_unchanged():
    blog = _make_blog()
    html = "<p>본문</p>"
    assert inject_author_signal(html, blog) == html


def test_author_profile_without_name_returns_html_unchanged():
    blog = _make_blog(author_profile={"bio": "소개만 있음"})
    html = "<p>본문</p>"
    assert inject_author_signal(html, blog) == html


def test_author_profile_with_name_appends_byline_and_notice():
    blog = _make_blog(author_profile={
        "name": "홍길동", "bio": "10년차 금융 전문가", "expertise": "재테크",
    })
    html = "<p>본문</p>"
    result = inject_author_signal(html, blog)
    assert result.startswith(html)
    assert "홍길동" in result
    assert "재테크" in result
    assert "10년차 금융 전문가" in result
    assert "사람이 검수·편집" in result


def test_author_profile_with_name_only_omits_optional_blocks():
    blog = _make_blog(author_profile={"name": "홍길동"})
    result = inject_author_signal("<p>본문</p>", blog)
    assert "홍길동" in result
    assert "사람이 검수·편집" in result


# ── 2026-10-20 블로그별 꼬리말(editorial_notice) 갈래 ──────────────
def test_editorial_notice_default_is_exact_common_string():
    """키가 없으면 다른 블로그와 완전히 같은 공통 문구."""
    from app.services.generation.author_signal_injector import (
        EDITORIAL_NOTICE, editorial_notice_html,
    )
    assert editorial_notice_html({"name": "a"}) == EDITORIAL_NOTICE
    assert editorial_notice_html({"editorial_notice": "  "}) == EDITORIAL_NOTICE
    assert editorial_notice_html(None) == EDITORIAL_NOTICE


def test_editorial_notice_custom_text_used():
    """키가 있으면 그 글로 바뀌고 공통 문구는 빠진다."""
    from types import SimpleNamespace
    from app.services.generation.author_signal_injector import (
        inject_author_signal,
    )
    blog = SimpleNamespace(author_profile={
        "name": "슈마즈", "editorial_notice": "공식 자료로 정리했습니다.",
    })
    out = inject_author_signal("<p>본문</p>", blog)
    assert "공식 자료로 정리했습니다.</p>" in out
    assert "사람이 검수" not in out
