"""공식 출처 0건 보류 스위치(official_hold) — 취업인포마스터 재정비 10/8."""
import asyncio
from types import SimpleNamespace

from app.services.generation import official_hold as oh


class DB:
    """commit 만 받는 가짜 세션."""

    async def commit(self):
        return None


def _title():
    return SimpleNamespace(hold_count=0, last_held_at=None, hold_reason=None)


def _ref(*urls):
    return SimpleNamespace(summaries=[SimpleNamespace(url=u) for u in urls], sources=[])


def _run(settings, ref):
    title = _title()
    out = asyncio.run(oh.hold_if_no_official(DB(), settings, title, ref, "전기기사 응시 자격", 17))
    return out, title


def test_no_key_is_unchanged():
    """키가 없거나 꺼져 있으면 공식 출처가 0건이어도 아무것도 안 한다."""
    blog_only = _ref("https://blog.naver.com/a/1", "https://tistory.com/2")
    for settings in (None, {}, {"reference": {"enabled": True}},
                     {"reference": {"require_official": False}}):
        out, title = _run(settings, blog_only)
        assert out is None and title.hold_count == 0


def test_on_and_zero_official_is_held():
    out, title = _run({"reference": {"require_official": True}},
                      _ref("https://blog.naver.com/a/1", "https://fakeq-net.or.kr.evil.com/x"))
    assert out == oh.REASON
    assert title.hold_count == 1 and "공식" in title.hold_reason


def test_on_and_official_passes():
    out, title = _run({"reference": {"require_official": True}},
                      _ref("https://blog.naver.com/a/1", "https://www.q-net.or.kr/crf005.do"))
    assert out is None and title.hold_count == 0
    # 통합 요약(sources)으로 들어온 주소도 센다
    ref = SimpleNamespace(summaries=[], sources=["https://www.work24.go.kr/cm/main.do"])
    out, _ = _run({"reference": {"require_official": True}}, ref)
    assert out is None


def test_custom_domains_and_matching():
    doms = oh.switch({"reference": {"require_official": True,
                                    "official_domains": ["korcham.net"]}})
    assert doms == ["korcham.net"]
    assert oh.is_official("https://license.korcham.net/", doms)
    assert not oh.is_official("https://notkorcham.net/", doms)
    assert not oh.is_official("https://www.q-net.or.kr/", doms)
    assert oh.is_official("https://lic.kotsa.or.kr/", oh.DEFAULT_DOMAINS)
