"""애드센스 '준비 중' vs '심사 중' 표시 (2026-08-30).

머니조아·군타·수작남 셋 다 신청했는데 수작남만 '심사 중'으로 떴다.
애드센스 API 는 셋 다 GETTING_READY 로만 보고한다 — 신청 여부를 알려주지
않는다. 그래서 '심사 중'은 사용자가 blogauto 에 기록해야 하는 값인데,
화면에 그 사정이 안 보여 왜 다른지 알 수 없었다.

기능상 preparing 과 applied 는 차이가 없다(둘 다 '승인 전'). 그 사실도
함께 지킨다 — 한쪽만 승인 전으로 취급하는 분기가 생기면 설정이 어긋난다.
"""
from pathlib import Path
from types import SimpleNamespace

from app.services.flow.module_blog_scope import is_module_active_for_blog
from app.services.generation.adsense_auto_settings import resolve_for_blog
from app.services.generation.adsense_prompt_switch import is_approved
from app.services.publishing.adsense_status_resolver import (
    ST_APPLIED,
    ST_APPROVED,
    ST_ATTENTION,
    ST_NONE,
    ST_PREPARING,
    resolve_display_status,
)

ROOT = Path(__file__).resolve().parents[2]


def _blog(url, status="none"):
    return SimpleNamespace(url=url, adsense_status=status,
                           required_pages_status="complete", name="테스트")


def _site(domain, state):
    return SimpleNamespace(domain=domain, state=state)


def _index(*pairs):
    return {d: _site(d, s) for d, s in pairs}


def test_getting_ready_shows_preparing_by_default():
    """애드센스가 준비 중이라고 하면 기본은 '준비 중'."""
    idx = _index(("moneyjjoaa.blogspot.com", "GETTING_READY"))
    v = resolve_display_status(_blog("https://moneyjjoaa.blogspot.com/"), idx)
    assert v["status"] == ST_PREPARING
    assert v["state"] == "GETTING_READY"


def test_user_marked_applied_shows_review():
    """사용자가 신청했다고 기록하면 같은 원문 상태여도 '심사 중'."""
    idx = _index(("soojaknam.blogspot.com", "GETTING_READY"))
    v = resolve_display_status(
        _blog("https://soojaknam.blogspot.com/", ST_APPLIED), idx)
    assert v["status"] == ST_APPLIED
    assert v["state"] == "GETTING_READY", "원문은 그대로 준비 중이다"


def test_same_remote_state_can_differ_by_local_record():
    """세 블로그가 같은 원문 상태인데 표시가 갈리는 상황 자체를 문서화한다."""
    idx = _index(
        ("guntamoney.blogspot.com", "GETTING_READY"),
        ("moneyjjoaa.blogspot.com", "GETTING_READY"),
        ("soojaknam.blogspot.com", "GETTING_READY"),
    )
    a = resolve_display_status(_blog("https://guntamoney.blogspot.com/"), idx)
    b = resolve_display_status(
        _blog("https://soojaknam.blogspot.com/", ST_APPLIED), idx)
    assert a["state"] == b["state"] == "GETTING_READY"
    assert a["status"] != b["status"], "차이는 내부 기록에서만 온다"


def test_ready_wins_over_local_record():
    """애드센스가 승인이라고 하면 내부 값과 무관하게 승인."""
    idx = _index(("doooit082.com", "READY"))
    v = resolve_display_status(_blog("https://doooit082.com/", ST_PREPARING), idx)
    assert v["status"] == ST_APPROVED


def test_needs_attention_surfaces():
    """주의 필요는 따로 드러나야 한다(놓치면 반려 사유를 못 본다)."""
    idx = _index(("lifein4.com", "NEEDS_ATTENTION"))
    v = resolve_display_status(_blog("https://lifein4.com/", ST_PREPARING), idx)
    assert v["status"] == ST_ATTENTION


def test_missing_site_is_not_applied():
    idx = _index(("other.com", "READY"))
    v = resolve_display_status(_blog("https://mine.com/", ST_APPLIED), idx)
    assert v["status"] == ST_NONE


def test_subdomain_inherits_parent():
    """서브도메인은 부모 도메인 상태를 따른다(애드센스 2023-03 정책)."""
    idx = _index(("doooit082.com", "READY"))
    v = resolve_display_status(_blog("https://blog.doooit082.com/"), idx)
    assert v["status"] == ST_APPROVED
    assert v["inherited_from"] == "doooit082.com"


def test_preparing_and_applied_behave_identically():
    """둘 다 '승인 전'이다 — 한쪽만 다르게 취급하는 분기가 생기면 안 된다."""
    module = SimpleNamespace(settings={"adsense_role": "adsense_only"})
    settings = {"adsense_auto": True, "niche_enabled": False,
                "info_gain_enabled": False}
    for status in (ST_PREPARING, ST_APPLIED):
        blog = _blog("https://x.com/", status)
        assert is_approved(blog) is False
        assert is_module_active_for_blog(module, blog) is True
        out = resolve_for_blog(settings, blog)
        assert out["niche_enabled"] is True
        assert out["info_gain_enabled"] is True

    approved = _blog("https://x.com/", ST_APPROVED)
    assert is_approved(approved) is True
    assert is_module_active_for_blog(module, approved) is False


def test_settings_screen_shows_remote_state():
    """왜 다른지 알 수 있게 원문 상태를 화면에 내려준다."""
    router = (ROOT / "app/routers/blog_settings_adsense.py").read_text(
        encoding="utf-8")
    assert '"remote"' in router
    tab = (ROOT / "app/templates/blogs/settings/_tab_adsense.html").read_text(
        encoding="utf-8")
    assert "remoteStatus" in tab
    assert "신청 여부를 알려주지 않습니다" in tab
    # 목록 표시(심사중)와 선택지 라벨이 어긋나면 사용자가 못 찾는다
    assert "심사 중" in tab
