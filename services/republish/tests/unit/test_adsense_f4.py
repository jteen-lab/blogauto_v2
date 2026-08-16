"""F4 — 니치(주제) 강제(모듈 단위, 옵트인 차단) 판정 테스트.

2026-08-16: 블로그 단위(adsense_status)에서 프롬프트 모듈 settings 기반으로 이전.
"""
from app.services.generation.adsense_niche import resolve_module_niche


class TestResolveModuleNiche:
    """niche_enabled 토글 + niche_topic_ids 있을 때만 강제, 그 외 None."""

    def test_enabled_with_niche(self):
        assert resolve_module_niche({"niche_enabled": True, "niche_topic_ids": [3, 5]}) == [3, 5]

    def test_enabled_empty_niche(self):
        assert resolve_module_niche({"niche_enabled": True, "niche_topic_ids": []}) is None

    def test_enabled_none_niche(self):
        assert resolve_module_niche({"niche_enabled": True, "niche_topic_ids": None}) is None

    def test_disabled_optin(self):
        # 옵트인: 토글 꺼짐이면 topic이 있어도 강제 안 함
        assert resolve_module_niche({"niche_enabled": False, "niche_topic_ids": [3]}) is None

    def test_missing_enabled_key(self):
        # niche_enabled 키 없으면 강제 안 함(기존 모듈 무영향)
        assert resolve_module_niche({"niche_topic_ids": [3]}) is None

    def test_empty_settings(self):
        assert resolve_module_niche({}) is None

    def test_none_settings(self):
        assert resolve_module_niche(None) is None

    def test_string_ids_normalized(self):
        assert resolve_module_niche({"niche_enabled": True, "niche_topic_ids": ["3", "5"]}) == [3, 5]

    def test_none_values_filtered(self):
        assert resolve_module_niche({"niche_enabled": True, "niche_topic_ids": [3, None, 5]}) == [3, 5]
