"""F4 — 니치(주제) 강제(옵트인 차단) 판정 테스트."""
from app.services.generation.adsense_niche import resolve_adsense_niche


class TestResolveAdsenseNiche:
    """preparing + 니치 설정 시에만 강제, 그 외 None(기존 동작)."""

    def test_preparing_with_niche(self):
        assert resolve_adsense_niche("preparing", [3, 5]) == [3, 5]

    def test_preparing_empty_niche(self):
        assert resolve_adsense_niche("preparing", []) is None

    def test_preparing_none_niche(self):
        assert resolve_adsense_niche("preparing", None) is None

    def test_none_status_optin(self):
        # 옵트인: none 상태는 니치가 있어도 강제 안 함
        assert resolve_adsense_niche("none", [3]) is None

    def test_approved_status(self):
        assert resolve_adsense_niche("approved", [3]) is None

    def test_applied_status_not_enforced(self):
        # applied는 이미 신청 상태 → 차단 안 함(preparing만 차단)
        assert resolve_adsense_niche("applied", [3]) is None

    def test_string_ids_normalized(self):
        assert resolve_adsense_niche("preparing", ["3", "5"]) == [3, 5]

    def test_none_values_filtered(self):
        assert resolve_adsense_niche("preparing", [3, None, 5]) == [3, 5]
