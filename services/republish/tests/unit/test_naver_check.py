"""NEO 네이버 점검 — robots.txt 해석 테스트.

Yeti(네이버 크롤러) 전용 그룹이 있으면 그것이, 없으면 `*` 그룹이 적용된다.
전용 그룹이 있을 때 `*` 를 보면 오판한다.
"""
from types import SimpleNamespace

from app.services.search_visibility import naver_check as nc


def _verdict(robots: str):
    return nc._yeti_verdict(robots)


def test_star_allow_all_is_not_blocked():
    """운영 블로그 대부분이 이 형태 — Disallow 값이 비면 전체 허용."""
    assert _verdict("User-agent: *\nDisallow:") == (False, "*")


def test_star_allow_slash_is_not_blocked():
    assert _verdict("User-agent: *\nAllow: /\nSitemap: https://x/sitemap.xml") == (
        False, "*",
    )


def test_star_disallow_root_is_blocked():
    assert _verdict("User-agent: *\nDisallow: /") == (True, "*")


def test_yeti_group_wins_over_star():
    """Yeti 전용 그룹이 있으면 * 를 보면 안 된다."""
    robots = "User-agent: *\nDisallow:\n\nUser-agent: Yeti\nDisallow: /"
    assert _verdict(robots) == (True, "Yeti")


def test_yeti_allowed_while_star_blocked():
    robots = "User-agent: *\nDisallow: /\n\nUser-agent: Yeti\nDisallow:"
    assert _verdict(robots) == (False, "Yeti")


def test_agent_name_is_case_insensitive():
    robots = "user-agent: YETI\ndisallow: /"
    assert _verdict(robots) == (True, "Yeti")


def test_partial_disallow_is_not_a_full_block():
    """/search 만 막는 것은 사이트 차단이 아니다(슈마즈 실제 형태)."""
    robots = "User-agent: *\nDisallow: /search\nDisallow: /share-widget"
    assert _verdict(robots) == (False, "*")


def test_comments_are_ignored():
    robots = "# 주석\nUser-agent: *  # 뒤 주석\nDisallow: /"
    assert _verdict(robots) == (True, "*")


def test_no_matching_group_defaults_to_allowed():
    assert _verdict("User-agent: Googlebot\nDisallow: /") == (False, None)


def test_empty_robots():
    assert _verdict("") == (False, None)


def test_check_result_defaults():
    result = nc.NaverCheckResult(ok=True)
    assert result.yeti_blocked is None
    assert result.verification_meta is None
