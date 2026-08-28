"""AEO 지시문이 프롬프트 빌더의 구조를 침범하지 않는지 확인.

배경(2026-08-28): AEO 지시문은 완성된 프롬프트 **뒤에 덧붙는다**. LLM 은 뒤쪽
지시를 더 따르는 경향이 있어, "마지막에 FAQ" 같은 문구가 섹션 패턴이 정한
F 슬롯(P1 주의사항 / P4 의사결정 체크리스트)을 밀어낼 수 있었다.
→ 구조를 바꾸지 말고 덧붙이라고 명시하도록 수정했고, 그 문구를 여기서 고정한다.
"""
from app.services.prompt_builder.blocks import (
    PATTERNS, aeo_directive, adsense_gain_directive,
)


def _faq_line() -> str:
    return next(
        line for line in aeo_directive().split("\n") if "자주 묻는 질문" in line
    )


def test_faq_instruction_does_not_override_structure():
    """섹션 패턴을 밀어내지 말고 덧붙이라는 지시가 있어야 한다."""
    line = _faq_line()
    assert "구조를 바꾸지 말고" in line
    assert "덧붙일 것" in line


def test_faq_instruction_reuses_existing_faq_section():
    """P2·P3·P5 처럼 이미 FAQ 슬롯이 있으면 섹션을 새로 만들지 않는다."""
    assert "이미 FAQ" in _faq_line()


def test_aeo_keeps_machine_extractable_rules():
    body = aeo_directive()
    for keyword in ("즉답", "질문형", "비교 표", "키-값", "기준일", "한 문단 한 주장"):
        assert keyword in body, keyword


def test_aeo_and_info_gain_are_different_axes():
    """정보이득=무엇을 쓸지, AEO=어떤 형태로 쓸지. 같은 문구를 반복하면 안 된다."""
    aeo, gain = aeo_directive(), adsense_gain_directive()
    assert aeo and gain
    assert aeo != gain


def test_every_pattern_still_defines_six_sections():
    """AEO 도입과 무관하게 섹션 패턴은 A~F 골격을 유지한다."""
    for pattern in PATTERNS:
        body = pattern["body"]
        for slot in ("- A:", "- B:", "- C:", "- D:", "- E:", "- F:"):
            assert slot in body, f"{pattern['code']} 에 {slot} 없음"


def test_patterns_with_and_without_faq_slot_both_exist():
    """두 경우가 모두 존재하므로 조건부 지시가 필요하다(이 테스트가 그 전제를 지킨다)."""
    def has_faq(pattern) -> bool:
        line = next(l for l in pattern["body"].split("\n") if l.startswith("- F:"))
        return "질문" in line or "FAQ" in line

    with_faq = [p["code"] for p in PATTERNS if has_faq(p)]
    without_faq = [p["code"] for p in PATTERNS if not has_faq(p)]
    assert with_faq and without_faq, (with_faq, without_faq)
