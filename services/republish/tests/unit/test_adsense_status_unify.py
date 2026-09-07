"""애드센스 상태는 **애드센스만** 본다.

사용자 지적(2026-09-07): 애드센스 화면에는 "준비 중" 인데 blogauto 는
"준비중" 으로 남고, 갱신해도 바뀌지 않았다.

원인: 준비 중(GETTING_READY/REQUIRES_REVIEW)을 받아 놓고 **blogauto 내부
저장값**으로 준비중/심사중을 갈랐다. 갱신은 애드센스를 읽지만 표시는
내부값을 봤기 때문에 영원히 안 바뀐다.

애드센스에 사이트가 등록돼 "준비 중" 이면 이미 신청한 것 = 심사중이다.
"""
import pathlib

import pytest

from app.services.publishing.adsense_status_resolver import (
    ST_APPLIED, ST_APPROVED, ST_ATTENTION, ST_NONE,
    build_sites_index, resolve_display_status,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _blog(local_status="preparing"):
    from types import SimpleNamespace

    return SimpleNamespace(url="https://moneyjjoaa.blogspot.com/",
                           adsense_status=local_status)


def _index(state, domain="moneyjjoaa.blogspot.com"):
    from types import SimpleNamespace

    return build_sites_index([SimpleNamespace(domain=domain, state=state)])


class TestStateMapping:
    @pytest.mark.parametrize("state,expected", [
        ("READY", ST_APPROVED),
        ("GETTING_READY", ST_APPLIED),
        ("REQUIRES_REVIEW", ST_APPLIED),
        ("NEEDS_ATTENTION", ST_ATTENTION),
    ])
    def test_state_decides(self, state, expected):
        assert resolve_display_status(
            _blog(), _index(state))["status"] == expected

    def test_not_listed_is_none(self):
        assert resolve_display_status(_blog(), {})["status"] == ST_NONE


class TestLocalValueIgnored:
    """내부 저장값이 무엇이든 표시는 같아야 한다."""

    @pytest.mark.parametrize("local", ["none", "preparing", "applied",
                                       "approved", None])
    def test_preparing_state_always_applied(self, local):
        assert resolve_display_status(
            _blog(local), _index("GETTING_READY"))["status"] == ST_APPLIED

    def test_source_is_adsense_not_local(self):
        """근거가 local 이면 갱신해도 안 바뀐다는 뜻이다."""
        verdict = resolve_display_status(_blog(), _index("REQUIRES_REVIEW"))
        assert verdict["source"] == "adsense"

    def test_approved_not_downgraded_by_local(self):
        assert resolve_display_status(
            _blog("none"), _index("READY"))["status"] == ST_APPROVED


class TestSyncNoLongerPins:
    """동기화가 preparing→applied 강등만 막느라 반대 방향도 막았다."""

    def test_no_preparing_guard(self):
        src = (ROOT / "app/services/publishing/adsense_account_service.py"
               ).read_text(encoding="utf-8")
        assert "사용자가 신청했다고 표시한 상태는 유지" not in src
        assert "ST_PREPARING" not in src

    def test_attention_still_display_only(self):
        """'확인 필요' 는 표시 전용이라 저장값을 덮지 않는다."""
        src = (ROOT / "app/services/publishing/adsense_account_service.py"
               ).read_text(encoding="utf-8")
        assert "if new_status == ST_ATTENTION:" in src


class TestScreen:
    def test_original_state_shown(self):
        """화면엔 둘 다 '심사중' 이지만 단계는 다르다."""
        html = (ROOT / "app/templates/blogs/list.html").read_text(
            encoding="utf-8")
        assert "blog.adsense_site_state" in html

    def test_preparing_marked_legacy(self):
        html = (ROOT / "app/templates/blogs/list.html").read_text(
            encoding="utf-8")
        block = html[html.index("preparing: {"):html.index("attention: {")]
        assert "옛 상태" in block

    def test_applied_tip_matches_adsense_wording(self):
        html = (ROOT / "app/templates/blogs/list.html").read_text(
            encoding="utf-8")
        block = html[html.index("applied:   {"):html.index("preparing: {")]
        assert "준비 중" in block
