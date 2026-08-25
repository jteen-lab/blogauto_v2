"""검색 노출 3종 순수 로직 테스트 (네트워크 없음).

대상:
    - S1 IndexNow: 스킵 사유 판정, 응답 코드 해석
    - S2 사이트맵: XML 파싱, 포함 판정, lastmod 경과일
    - S6 색인: 응답 해석
    - 설정 병합 / 플랫폼 지원 판정
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.search_visibility import config as cfg
from app.services.search_visibility import indexnow_service as ins
from app.services.search_visibility import index_check_service as ics
from app.services.search_visibility import sitemap_service as sms


def _blog(platform="wordpress", url="https://example.com"):
    return SimpleNamespace(id=1, name="테스트", platform=platform, url=url,
                           search_index_config=None)


# ---------- 설정 ----------

def test_merge_config_fills_defaults():
    merged = cfg.merge_config(None)
    assert merged["indexnow_enabled"] is False  # 기준선 확보 전까지 꺼둔다
    assert merged["sitemap_check_enabled"] is True
    assert merged["index_check_daily_cap"] == 20


def test_merge_config_ignores_unknown_keys():
    merged = cfg.merge_config({"indexnow_enabled": True, "몰라": 1})
    assert merged["indexnow_enabled"] is True
    assert "몰라" not in merged


def test_blogger_is_not_indexnow_supported():
    assert cfg.indexnow_supported(_blog("blogger")) is False
    assert cfg.indexnow_supported(_blog("wordpress")) is True


def test_key_file_url_is_host_root():
    blog = _blog(url="https://a.example.com/blog")
    assert cfg.key_file_url(blog, "abc") == "https://a.example.com/abc.txt"


def test_generate_key_is_32_hex():
    key = cfg.generate_indexnow_key()
    assert len(key) == 32
    int(key, 16)  # 16진수여야 한다


# ---------- S1 IndexNow ----------

def test_skip_when_disabled():
    conf = cfg.merge_config({"indexnow_enabled": False})
    assert ins._skip_reason(_blog(), "https://example.com/a", conf) == ins.SKIP_DISABLED


def test_skip_when_platform_unsupported():
    conf = cfg.merge_config(
        {"indexnow_enabled": True, "indexnow_key": "k", "indexnow_key_verified": True},
    )
    reason = ins._skip_reason(_blog("blogger"), "https://example.com/a", conf)
    assert reason == ins.SKIP_UNSUPPORTED


def test_skip_when_key_unverified():
    conf = cfg.merge_config({"indexnow_enabled": True, "indexnow_key": "k"})
    reason = ins._skip_reason(_blog(), "https://example.com/a", conf)
    assert reason == ins.SKIP_KEY_UNVERIFIED


def test_skip_when_host_mismatch():
    conf = cfg.merge_config(
        {"indexnow_enabled": True, "indexnow_key": "k", "indexnow_key_verified": True},
    )
    reason = ins._skip_reason(_blog(), "https://other.com/a", conf)
    assert reason == ins.SKIP_HOST_MISMATCH


def test_no_skip_when_all_ready():
    conf = cfg.merge_config(
        {"indexnow_enabled": True, "indexnow_key": "k", "indexnow_key_verified": True},
    )
    assert ins._skip_reason(_blog(), "https://example.com/a", conf) is None


@pytest.mark.parametrize("code,submitted", [(200, True), (202, True), (403, False),
                                            (422, False), (429, False), (500, False)])
def test_classify_submitted_flag(code, submitted):
    assert ins._classify(code).submitted is submitted


def test_403_invalidates_key():
    outcome = ins._classify(403)
    assert outcome.invalidate_key is True
    assert outcome.retryable is False


def test_429_is_retryable_only():
    outcome = ins._classify(429)
    assert outcome.retryable is True
    assert outcome.invalidate_key is False


# ---------- S2 사이트맵 ----------

URLSET = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/5089/</loc><lastmod>2026-08-20</lastmod></url>
  <url><loc>https://example.com/5090/</loc><lastmod>2026-08-21</lastmod></url>
</urlset>"""

INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/post-sitemap1.xml</loc>
  <lastmod>2026-08-20</lastmod></sitemap>
</sitemapindex>"""


def test_parse_urlset():
    children, urls, lastmod = sms._parse(URLSET)
    assert children == []
    assert "https://example.com/5090/" in urls
    assert lastmod == "2026-08-21"


def test_parse_index():
    children, urls, lastmod = sms._parse(INDEX)
    assert children == ["https://example.com/post-sitemap1.xml"]
    assert urls == []
    assert lastmod == "2026-08-20"


def test_parse_garbage_does_not_raise():
    assert sms._parse(b"not xml") == ([], [], None)


def test_contains_ignores_trailing_slash():
    snap = sms.SitemapSnapshot(ok=True, urls={"https://example.com/5090/"})
    assert sms.contains(snap, "https://example.com/5090") is True
    assert sms.contains(snap, "https://example.com/9999") is False


def test_stale_days_counts_from_lastmod():
    three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    snap = sms.SitemapSnapshot(ok=True, latest_lastmod=three_days_ago)
    assert sms.stale_days(snap) == 3


def test_stale_days_none_without_lastmod():
    assert sms.stale_days(sms.SitemapSnapshot(ok=True)) is None


def test_wordpress_candidates_have_wp_sitemap_first():
    urls = sms.candidate_sitemap_urls(_blog(), cfg.merge_config(None))
    assert urls[0] == "https://example.com/wp-sitemap.xml"


def test_manual_sitemap_url_wins():
    conf = cfg.merge_config({"sitemap_url": "https://example.com/custom.xml"})
    assert sms.candidate_sitemap_urls(_blog(), conf) == [
        "https://example.com/custom.xml",
    ]


# ---------- S6 색인 ----------

def test_interpret_pass_is_indexed():
    indexed, detail = ics.interpret(
        {"indexStatusResult": {"verdict": "PASS", "coverageState": "제출되어 색인이 생성됨"}},
    )
    assert indexed is True
    assert detail["coverageState"] == "제출되어 색인이 생성됨"


def test_interpret_neutral_is_not_indexed():
    indexed, _ = ics.interpret({"indexStatusResult": {"verdict": "NEUTRAL"}})
    assert indexed is False


def test_interpret_empty_response():
    indexed, detail = ics.interpret({})
    assert indexed is False
    assert detail["verdict"] is None


def test_property_url_is_origin():
    assert ics.property_url(_blog(url="https://a.example.com/blog/x")) == (
        "https://a.example.com/"
    )
