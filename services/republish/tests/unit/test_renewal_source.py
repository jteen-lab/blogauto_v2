"""리뉴얼 소스 양식 판별 테스트 (P2a, 순수 함수)."""
from app.services.renewal.renewal_source import (
    detect_image_origin, extract_featured_image,
)


def test_wp_blogauto_image():
    u = "https://lifein4.com/wp-content/uploads/2026/06/blogauto_5b0dc909.webp"
    assert detect_image_origin("wordpress", u) == "blogauto"


def test_wp_legacy_image():
    u = "https://lifein4.com/wp-content/uploads/2026/06/photo_123.jpg"
    assert detect_image_origin("wordpress", u) == "legacy"


def test_blogger_imgbb_blogauto():
    assert detect_image_origin("blogger", "https://i.ibb.co/abc/x.webp") == "blogauto"


def test_blogger_google_legacy():
    u = "https://blogger.googleusercontent.com/img/a/x=w640"
    assert detect_image_origin("blogger", u) == "legacy"


def test_none_image():
    assert detect_image_origin("wordpress", None) == "none"
    assert detect_image_origin("blogger", "") == "none"


def test_extract_featured_image_first():
    html = '<p>hi</p><img src="https://x.com/a.webp" /><img src="b.jpg">'
    assert extract_featured_image(html) == "https://x.com/a.webp"
    assert extract_featured_image("") is None
    assert extract_featured_image("<p>no img</p>") is None
