"""최소 글자수를 생성 단계에서 채운다 (2026-08-31).

수작남이 3회 연속 실패했다. 원인은 토큰 상한이 아니라 **임계값이 실제
생산 분포의 한가운데** 있는 것이었다. 400편 실측 중앙 1,883자,
1,800자 미만이 42%.

조사: docs/plans/min_length_generation.md
순서도: docs/flowcharts/min_length_generation.md
"""

from __future__ import annotations

import pytest

from app.services.generation.length_directive import (
    DEFAULT_MARGIN,
    DEFAULT_SECTIONS,
    build,
    continuation_prompt,
    resolve,
)
from app.services.generation.quality_gate import plain_len


# ── 목표치는 임계값보다 크게 ─────────────────────────────
def test_target_exceeds_threshold_by_margin() -> None:
    """요구한 만큼 나오지 않는다.

    실측(요구 2,000자): 하위10% 1,484자 = 0.74배. 하위10%가 임계를
    넘으려면 1.35배가 필요하다. 목표를 임계와 같게 두면 절반이 막힌다.
    """
    plan = resolve(1800)
    assert plan["target"] >= 1800 * 1.35
    assert plan["target"] == 2500


def test_margin_scales_with_threshold() -> None:
    for minimum in (1200, 1500, 1800, 2500):
        plan = resolve(minimum)
        assert plan["target"] > minimum, minimum
        assert plan["target"] / minimum == pytest.approx(DEFAULT_MARGIN, abs=0.12)


def test_per_section_is_above_observed_median() -> None:
    """소제목 1개당 실측 중앙 231자. 그대로 두면 6구획 = 1,386자다."""
    plan = resolve(1800)
    assert plan["sections"] == DEFAULT_SECTIONS
    assert plan["per_section"] > 231
    assert plan["per_section"] * plan["sections"] >= 1800


# ── 모듈 설정으로 조정 ───────────────────────────────────
def test_module_can_override_margin_and_sections() -> None:
    plan = resolve(1800, {"quality_gate": {"length_margin": 1.6, "min_sections": 8}})
    assert plan["target"] == 2900
    assert plan["sections"] == 8


def test_absurd_settings_are_clamped() -> None:
    """구획 100개·여유 10배 같은 값이 그대로 모델에게 가면 안 된다."""
    plan = resolve(1800, {"quality_gate": {"length_margin": 10, "min_sections": 100}})
    assert plan["target"] / 1800 <= 2.0
    assert plan["sections"] <= 12

    plan = resolve(1800, {"quality_gate": {"length_margin": 0.1, "min_sections": 1}})
    assert plan["target"] >= 1800, "여유를 1 미만으로 두면 목표가 임계보다 낮아진다"
    assert plan["sections"] >= 3


def test_bad_values_fall_back_to_defaults() -> None:
    for bad in ({"length_margin": "빠르게"}, {"min_sections": None}, {}):
        plan = resolve(1800, {"quality_gate": bad})
        assert plan["target"] > 1800


# ── 지시문 내용 ──────────────────────────────────────────
def test_directive_states_both_numbers() -> None:
    """목표치와 '이 아래면 발행 안 됨' 을 함께 말해야 한다."""
    text = build(1800)
    assert "2,500자" in text
    assert "1,800자" in text
    assert "소제목" in text


def test_directive_overrides_module_prompt_wording() -> None:
    """모듈 프롬프트가 이미 '2,000자 이상' 을 말한다.

    어느 쪽을 따라야 하는지 모델이 헷갈리면 지시가 무의미해진다.
    """
    assert "우선" in build(1800)


def test_directive_forbids_padding() -> None:
    """분량을 늘리면 얕은 내용으로 채울 위험이 있다."""
    text = build(1800)
    assert "되풀이" in text or "반복" in text
    assert "쪼개" in text or "요약" in text


def test_directive_reflects_module_threshold() -> None:
    """게이트 임계를 바꿨는데 모델에게 가는 말이 그대로면 안 된다.

    고치기 전에는 게이트가 1,800을 보고 프롬프트는 2,000을 말하며 서로를
    몰랐다.
    """
    low = build(1200)
    high = build(2400)
    assert low != high
    assert "1,700자" in low and "1,200자" in low
    assert "3,400자" in high and "2,400자" in high


# ── 이어쓰기 지시문 ──────────────────────────────────────
def test_continuation_tells_the_model_what_is_missing() -> None:
    """지금은 '짧았다' 는 사실조차 전달되지 않아 같은 분포에서 다시 뽑는다."""
    text = continuation_prompt("제목", "초안 본문", 1400, 1800)
    assert "1,400자" in text          # 현재
    assert "2,500자" in text          # 목표
    assert "1,100자" in text          # 부족분
    assert "초안 본문" in text


def test_continuation_forbids_repeating_the_draft() -> None:
    text = continuation_prompt("제목", "초안", 1400, 1800)
    assert "다시 출력하지" in text
    assert "이미 나온" in text or "다루지 않은" in text


def test_continuation_shortfall_never_negative() -> None:
    text = continuation_prompt("제목", "초안", 9999, 1800)
    assert "0자 모자랍니다" in text


# ── 게이트와 같은 기준으로 센다 ──────────────────────────
def test_plain_len_matches_gate_basis() -> None:
    """호출자가 따로 세면 '1,689자로 막혔다' 와 비교가 안 된다."""
    markdown = "# 제목\n\n본문 내용입니다. [링크](http://a.com) 뒤 문장."
    n = plain_len(markdown)
    assert n > 0
    assert n < len(markdown), "마크다운 기호·링크가 걷혔는지"
