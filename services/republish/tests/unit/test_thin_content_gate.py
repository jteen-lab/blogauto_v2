"""최소 분량 게이트 단위 테스트 (애드센스 F6)."""
from app.services.publishing.thin_content_gate import (
    THIN_CONTENT_MIN_CHARS,
    check_thin_content,
    extract_text_length,
)


def test_extract_text_length_strips_tags():
    html = "<h1>제목</h1><p>본문 텍스트</p>"
    assert extract_text_length(html) == len("제목 본문 텍스트")


def test_extract_text_length_empty_html_returns_zero():
    assert extract_text_length("") == 0
    assert extract_text_length(None) == 0


def test_check_thin_content_below_threshold_blocks():
    short_html = f"<p>{'가' * (THIN_CONTENT_MIN_CHARS - 1)}</p>"
    error = check_thin_content(short_html)
    assert error is not None
    assert "분량 미달" in error
    assert str(THIN_CONTENT_MIN_CHARS) in error


def test_check_thin_content_at_or_above_threshold_passes():
    long_html = f"<p>{'가' * THIN_CONTENT_MIN_CHARS}</p>"
    assert check_thin_content(long_html) is None


def test_check_thin_content_ignores_markup_length():
    # 태그만 잔뜩 있고 실제 텍스트는 짧은 경우 → 차단돼야 함
    html = "<div>" * 200 + "짧은 본문" + "</div>" * 200
    error = check_thin_content(html)
    assert error is not None
