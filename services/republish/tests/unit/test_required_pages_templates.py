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


# ---------------------------------------------------------------------------
# 블로그별 소개 본문 (author_profile.about_body)
# ---------------------------------------------------------------------------
from app.services.publishing.required_pages_templates import about_body_to_html  # noqa: E402


def test_about_body_takes_priority_over_overrides_and_preset():
    blog = _make_blog(author_profile={"about_body": "블로그별 소개입니다."})
    _, html = build_required_pages(
        blog, "owner@example.com", overrides={"about": "<p>공통 소개</p>"},
    )["about"]
    assert "블로그별 소개입니다." in html
    assert "공통 소개" not in html


def test_empty_about_body_falls_back_to_overrides_then_preset():
    blog = _make_blog(author_profile={"about_body": "   "})
    _, html = build_required_pages(
        blog, "owner@example.com", overrides={"about": "<p>공통 소개</p>"},
    )["about"]
    assert "공통 소개" in html
    _, html2 = build_required_pages(blog, "owner@example.com")["about"]
    assert "방문자에게 유용한 정보" in html2


def test_about_body_does_not_affect_other_pages_and_title_kept():
    blog = _make_blog(author_profile={"about_body": "소개 본문"})
    pages = build_required_pages(blog, "owner@example.com")
    assert pages["about"][0] == "테스트블로그 소개"
    assert "소개 본문" not in pages["contact"][1]


def test_about_body_plain_text_conversion():
    out = about_body_to_html(
        "## 운영 목적\n첫 줄 <b>강조</b>\n둘째 줄\n\n- 항목1\n- 항목2\n\n마지막 문단"
    )
    assert "<h3>운영 목적</h3>" in out
    assert "<p>첫 줄 &lt;b&gt;강조&lt;/b&gt;<br>둘째 줄</p>" in out
    assert "<ul><li>항목1</li><li>항목2</li></ul>" in out
    assert "<p>마지막 문단</p>" in out
    assert "<b>" not in out


def test_about_body_html_kept_as_is():
    assert about_body_to_html("<p>직접 <b>HTML</b></p>") == "<p>직접 <b>HTML</b></p>"


def test_about_body_contact_section_appended_and_tokens_rendered():
    blog = _make_blog(author_profile={
        "about_body": "{{blog_name}}에 오신 것을 환영합니다.",
        "contact_form_url": "https://tally.so/r/abc",
    })
    _, html = build_required_pages(blog, "owner@example.com")["about"]
    assert "테스트블로그에 오신 것을 환영합니다." in html
    assert "<h3>문의</h3>" in html
    assert "https://tally.so/r/abc" in html
    assert "<iframe" not in html  # 소개 페이지는 링크만


def test_about_body_with_contact_token_not_duplicated():
    blog = _make_blog(author_profile={"about_body": "소개\n\n{{contact}}"})
    _, html = build_required_pages(blog, "owner@example.com")["about"]
    assert html.count("owner@example.com") == 2  # mailto href + 텍스트 1세트
    assert "<h3>문의</h3>" not in html
    assert "<p><p>" not in html
