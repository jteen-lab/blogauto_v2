"""F11 — 애드센스 승인용 고정 프롬프트 프리셋 테스트."""
from app.services.prompt_builder.presets import PRESETS
from app.services.prompt_builder import blocks as B


def _adsense_preset():
    return next((p for p in PRESETS if p["code"] == "adsense-approval"), None)


class TestF11Preset:
    """카탈로그에 고정 애드센스 프리셋이 존재하고 플래그가 올바른지."""

    def test_preset_exists(self):
        assert _adsense_preset() is not None

    def test_preset_flags(self):
        p = _adsense_preset()
        assert p["info_gain"] is True   # 적용 시 F7 토글 자동 ON
        assert p["locked"] is True      # 문체·옵션 편집 잠금

    def test_preset_axes_are_valid_codes(self):
        p = _adsense_preset()
        assert any(x["code"] == p["persona"] for x in B.PERSONAS)
        assert any(x["code"] == p["reader"] for x in B.READERS)
        assert any(x["code"] == p["pattern"] for x in B.PATTERNS)
        assert any(x["code"] == p["tone"] for x in B.TONES)

    def test_combo_not_duplicated_with_other_presets(self):
        # isActivePreset 하이라이트 모호성 방지: 4축 조합이 다른 프리셋과 겹치지 않아야
        p = _adsense_preset()
        combo = (p["persona"], p["reader"], p["pattern"], p["tone"])
        others = [
            (o["persona"], o["reader"], o["pattern"], o["tone"])
            for o in PRESETS if o["code"] != "adsense-approval"
        ]
        assert combo not in others

    def test_preset_served_to_template(self):
        # load_blocks_for_template가 presets를 그대로 전달하므로 프론트에 노출됨
        assert any(p["code"] == "adsense-approval" for p in B.PRESETS)
