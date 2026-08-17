"""F11 — 애드센스 승인용 전용 프롬프트 프리셋 테스트.

4축 조합이 아니라 완성 프롬프트(full_prompt)를 그대로 채우는 전용 프리셋.
"""
from app.services.prompt_builder.presets import PRESETS, ADSENSE_APPROVAL_PROMPT
from app.services.prompt_builder import blocks as B


def _adsense_preset():
    return next((p for p in PRESETS if p["code"] == "adsense-approval"), None)


class TestF11Preset:
    """카탈로그에 전용 프롬프트 프리셋이 존재하고 형태가 올바른지."""

    def test_preset_exists(self):
        assert _adsense_preset() is not None

    def test_preset_carries_full_prompt(self):
        p = _adsense_preset()
        assert p.get("full_prompt") == ADSENSE_APPROVAL_PROMPT
        assert p["full_prompt"].strip()

    def test_preset_has_no_axis_composition(self):
        # 전용 프롬프트라 4축 코드를 갖지 않는다(조립 대신 텍스트 그대로 사용)
        p = _adsense_preset()
        for axis in ("persona", "reader", "pattern", "tone"):
            assert axis not in p

    def test_prompt_has_pipeline_placeholders(self):
        # 생성 파이프라인이 치환하는 플레이스홀더 포함
        for token in ("{title}", "{category}", "{keywords}", "{reference_materials}"):
            assert token in ADSENSE_APPROVAL_PROMPT

    def test_prompt_encodes_adsense_signals(self):
        # 애드센스 승인 핵심 신호가 프롬프트에 담겨 있는지(정보이득·정직 가드·people-first)
        for kw in ("정보이득", "검색 의도", "정직 규칙", "people-first"):
            assert kw in ADSENSE_APPROVAL_PROMPT

    def test_preset_served_to_template(self):
        # load_blocks_for_template가 presets를 그대로 전달하므로 프론트에 노출됨
        assert any(p["code"] == "adsense-approval" for p in B.PRESETS)
