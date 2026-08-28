"""X1 외부 링크 정책 테스트.

원칙: 내부 링크는 건드리지 않고, 외부 링크에만 rel 표시와 전면광고 억제를 붙인다.
"""
from app.services.publishing import external_link_policy as elp

BLOG = "https://doooit082.com/"


def test_external_link_gets_rel_and_vignette_off():
    html = '<p><a href="https://partner.example.com/apply">신청</a></p>'
    result = elp.apply(html, BLOG)
    assert 'rel="sponsored nofollow"' in result.html
    assert 'data-google-vignette="false"' in result.html
    assert result.external_count == 1


def test_internal_link_is_untouched():
    """같은 블로그 글끼리는 정상 내부링크다 — 표시하면 안 된다."""
    html = '<a href="https://doooit082.com/5107/">다른 글</a>'
    result = elp.apply(html, BLOG)
    assert result.html == html
    assert result.external_count == 0


def test_www_variant_is_still_internal():
    html = '<a href="https://www.doooit082.com/5107/">글</a>'
    assert elp.apply(html, BLOG).external_count == 0


def test_relative_link_is_internal():
    html = '<a href="/5107/">글</a>'
    assert elp.apply(html, BLOG).external_count == 0


def test_existing_rel_is_preserved_and_extended():
    html = '<a href="https://x.com/a" rel="noopener">링크</a>'
    result = elp.apply(html, BLOG)
    assert "noopener" in result.html
    assert "sponsored" in result.html
    assert "nofollow" in result.html


def test_already_tagged_link_is_not_duplicated():
    html = (
        '<a href="https://x.com/a" rel="sponsored nofollow" '
        'data-google-vignette="false">링크</a>'
    )
    result = elp.apply(html, BLOG)
    assert result.html.count("sponsored") == 1
    assert result.html.count("data-google-vignette") == 1
    assert result.tagged == 0


def test_mailto_and_anchor_are_ignored():
    html = '<a href="mailto:a@b.com">메일</a><a href="#top">위로</a>'
    result = elp.apply(html, BLOG)
    assert result.external_count == 0
    assert result.html == html


def test_over_limit_is_flagged_but_html_still_produced():
    html = "".join(
        f'<a href="https://x{i}.com/">링크{i}</a>' for i in range(4)
    )
    result = elp.apply(html, BLOG, max_external=2)
    assert result.external_count == 4
    assert result.over_limit is True
    assert "sponsored" in result.html


def test_no_limit_means_no_flag():
    html = '<a href="https://x.com/">링크</a>'
    assert elp.apply(html, BLOG, max_external=0).over_limit is False


def test_empty_html():
    assert elp.apply("", BLOG).html == ""


def test_malformed_blog_url_does_not_crash():
    html = '<a href="https://x.com/">링크</a>'
    result = elp.apply(html, "")
    assert result.external_count == 1
