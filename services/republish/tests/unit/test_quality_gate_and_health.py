"""발행 전 품질 게이트 · 사이트 점검 · 내부링크 (2026-08-30).

라이프인포에서 146개를 사후에 비공개했고 doooit082 계열은 105종 제목이
사이트 간 중복 게재됐다. 사후 청소로는 생성 속도를 따라잡을 수 없어
생성 시점에 막는다.

진단: docs/plans/search_visibility_all_blogs.md
"""
from pathlib import Path

from app.services.generation.quality_gate import (
    MIN_BODY_CHARS,
    check_length,
    check_risky_topic,
    evaluate,
    strip_duplicate_h1,
)
from app.services.publishing.site_health_check import (
    check_naver_verification,
    check_noindex,
    check_sitemap_host,
)

ROOT = Path(__file__).resolve().parents[2]


def _body(n: int) -> str:
    return "가" * n


# ── 분량 ────────────────────────────────────────────────
def test_short_body_blocked():
    """잡학다식이 중앙값 1,588자였고 그 사이트가 색인 0건이다."""
    r = evaluate("제목", _body(1000))
    assert r.blocked and "본문" in r.message


def test_long_body_passes():
    assert evaluate("제목", _body(MIN_BODY_CHARS + 100)).blocked is False


def test_markdown_symbols_not_counted_as_content():
    """표·기호로 길이를 채운 글이 통과하면 안 된다."""
    padded = "# 제목\n" + "| --- | --- |\n" * 400
    assert check_length(padded) is not None


def test_links_not_counted():
    md = "[링크](https://example.com/a)" * 300
    assert check_length(md) is not None


# ── 위험 주제 ────────────────────────────────────────────
def test_risky_topics_warn_not_block():
    """같은 키워드라도 정상 정보 글일 수 있어 막지 않고 경고만 한다."""
    r = evaluate("롯데카드 고객센터 전화번호 확인하기", _body(MIN_BODY_CHARS + 10))
    assert r.blocked is False
    assert r.warnings and "연락처" in r.warnings[0]


def test_risky_patterns_cover_known_cases():
    """라이프인повер에서 걷어낸 유형이 잡히는지."""
    for title in ("티월드 고객센터 전화번호 안내",
                  "현대자동차 서비스센터 영업시간 안내",
                  "대한주택관리사협회 채용공고 안내",
                  "금강제화 상품권 현금화 저렴한 곳"):
        assert check_risky_topic(title), title


def test_normal_title_not_flagged():
    for title in ("소고기 미역국 황금 레시피", "윈도우 11 설치 순서 정리"):
        assert check_risky_topic(title) is None, title


# ── H1 중복 ──────────────────────────────────────────────
def test_duplicate_h1_removed():
    """테마가 제목을 출력하는데 본문에도 있어 두 번 보였다."""
    md = "# 홈트 근력운동 방법\n\n본문입니다."
    assert strip_duplicate_h1(md, "홈트 근력운동 방법").startswith("본문")


def test_h1_kept_when_different():
    md = "# 다른 소제목\n\n본문입니다."
    assert strip_duplicate_h1(md, "글 제목").startswith("# 다른 소제목")


def test_h1_whitespace_tolerant():
    md = "#   홈트 근력운동  방법  \n\n본문"
    assert strip_duplicate_h1(md, "홈트 근력운동 방법").startswith("본문")


def test_no_heading_untouched():
    md = "본문으로 바로 시작"
    assert strip_duplicate_h1(md, "제목") == md


# ── 사이트 점검 ──────────────────────────────────────────
def test_foreign_sitemap_detected():
    """레시피노트 robots.txt 가 수작남 사이트맵을 가리키고 있었다."""
    robots = "User-agent: *\nAllow: /\nSitemap: https://soojaknam.blogspot.com/sitemap.xml"
    msg = check_sitemap_host(robots, "recipenote4.blogspot.com")
    assert msg and "다른 도메인" in msg


def test_own_sitemap_ok():
    robots = "Sitemap: https://mine.com/sitemap.xml"
    assert check_sitemap_host(robots, "mine.com") is None


def test_missing_sitemap_declaration():
    assert check_sitemap_host("User-agent: *\nAllow: /", "mine.com")


def test_noindex_detected():
    assert check_noindex('<meta name="robots" content="noindex, follow">')
    assert check_noindex('<meta name="robots" content="index, follow">') is None


def test_naver_verification_missing():
    assert check_naver_verification("<html></html>")
    assert check_naver_verification(
        '<meta name="naver-site-verification" content="x">') is None


# ── 배선 ────────────────────────────────────────────────
def test_generator_applies_gate_and_h1():
    src = (ROOT / "app/services/generation/generator.py").read_text(
        encoding="utf-8")
    assert "strip_duplicate_h1" in src
    assert "품질 게이트 차단" in src


def test_connection_test_reports_health():
    src = (ROOT / "app/services/blog_service.py").read_text(encoding="utf-8")
    assert "site_health" in src
    assert "check_site" in src


def test_sibling_exclusion_defaults_on():
    """기능이 있는데 꺼져 있어 105종 제목이 중복 게재됐다."""
    src = (ROOT / "app/services/generation/inventory_trigger.py").read_text(
        encoding="utf-8")
    assert 'get("exclude_sibling_titles") is False' in src, (
        "명시적 false 일 때만 꺼져야 한다(기본 켜짐)"
    )
    js = (ROOT / "app/static/js/modules/prompt-form.js").read_text(
        encoding="utf-8")
    assert "settings.exclude_sibling_titles ?? true" in js


def test_intro_links_do_not_pad_with_unrelated():
    """개수를 채우려 관련 없는 글을 끌어오면 독자·검색엔진 모두에 손해다."""
    src = (ROOT / "app/services/generation/internal_linker.py").read_text(
        encoding="utf-8")
    assert "DEFAULT_INTRO_LINK_COUNT = 2" in src
    assert "채우지 않음" in src
    # 최신순으로 채우던 코드가 되돌아오면 실패
    assert "with_date.sort(key=lambda p: p.published_at, reverse=True)" not in src
