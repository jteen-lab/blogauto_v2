"""분량 지시문 — 게이트 임계값 하나에서 모델에게 줄 목표치를 만든다.

지금까지 게이트는 1,800자를 보고 프롬프트는 2,000자를 말했는데 둘이
서로를 몰랐다. 모듈에서 임계를 바꿔도 모델에게 가는 말은 그대로였다.

조사: docs/plans/min_length_generation.md
순서도: docs/flowcharts/min_length_generation.md
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# 요구한 만큼 나오지 않는다. 실측(요구 2,000자): 중앙 1,883자(0.94배),
# 하위 10% 1,484자(0.74배). 하위 10%가 임계를 넘으려면 1.35배가 필요해
# 여유를 조금 더 두어 1.4배로 잡는다.
DEFAULT_MARGIN = 1.4

# 소제목 1개당 실측 중앙 231자. 6구획이면 1,386자로 임계에 못 미친다.
# 통과율은 7구획 71%, 10구획 93%지만 11구획은 36%로 오히려 낮다 —
# 구획만 늘리면 얕아지므로 구획 수와 구획당 분량을 함께 지시한다.
DEFAULT_SECTIONS = 6

# 한 구획이 이보다 짧으면 나눈 의미가 없다.
MIN_SECTION_CHARS = 250


def resolve(min_chars: int, module_settings: Optional[dict] = None) -> Dict[str, Any]:
    """임계값에서 목표 분량·구획 수·구획당 분량을 계산한다."""
    gate = ((module_settings or {}).get("quality_gate") or {})

    try:
        margin = float(gate.get("length_margin") or DEFAULT_MARGIN)
    except (TypeError, ValueError):
        margin = DEFAULT_MARGIN
    margin = max(1.0, min(2.0, margin))

    try:
        sections = int(gate.get("min_sections") or DEFAULT_SECTIONS)
    except (TypeError, ValueError):
        sections = DEFAULT_SECTIONS
    sections = max(3, min(12, sections))

    target = int(round(min_chars * margin / 100.0)) * 100  # 100자 단위로 정리
    per_section = max(MIN_SECTION_CHARS, target // sections // 10 * 10)

    return {
        "target": target,
        "sections": sections,
        "per_section": per_section,
        "min_chars": min_chars,
    }


def build(min_chars: int, module_settings: Optional[dict] = None) -> str:
    """프롬프트 말미에 붙일 분량 지시문.

    모듈 프롬프트가 이미 자기 나름의 분량을 말하고 있을 수 있다. 어느
    쪽을 따라야 하는지 모델이 헷갈리지 않도록 우선순위를 명시한다.
    """
    plan = resolve(min_chars, module_settings)
    return (
        "■ 분량 기준 (위의 다른 분량 언급보다 이 기준이 우선합니다)\n"
        f"- 본문 전체 {plan['target']:,}자 이상. "
        f"{plan['min_chars']:,}자 미만이면 발행되지 않습니다.\n"
        f"- 소제목(##) {plan['sections']}개 이상으로 나누고, "
        f"각 소제목 아래 본문을 {plan['per_section']:,}자 이상 쓰세요.\n"
        "- 분량은 내용으로 채웁니다. 앞서 쓴 내용을 되풀이하거나, "
        "같은 말을 바꿔 쓰거나, 목차·요약만 늘려 채우지 마세요.\n"
        "- 각 소제목은 서로 다른 질문에 답해야 합니다. "
        "한 소주제를 여러 구획으로 쪼개 분량을 만들지 마세요."
    )


def continuation_prompt(
    title: str, draft: str, current_chars: int, min_chars: int,
    module_settings: Optional[dict] = None,
) -> str:
    """이어쓰기 지시문 — 초안을 버리지 않고 모자란 만큼만 더 받는다.

    지금은 짧으면 전부 버리고 처음부터 다시 만들면서 모델에게 "짧았다"는
    사실조차 전하지 않는다. 같은 분포에서 다시 뽑을 뿐이다.
    """
    plan = resolve(min_chars, module_settings)
    shortfall = max(0, plan["target"] - current_chars)
    return (
        f"아래는 「{title}」 에 대해 작성 중인 글의 초안입니다. "
        f"현재 {current_chars:,}자로 목표 {plan['target']:,}자에 "
        f"{shortfall:,}자 모자랍니다.\n\n"
        "--- 초안 ---\n"
        f"{draft}\n"
        "--- 초안 끝 ---\n\n"
        "초안에 **이어서** 쓸 부분만 출력하세요. 다음을 지키세요.\n"
        f"- 새로운 소제목(##)을 추가해 최소 {shortfall:,}자를 더 씁니다.\n"
        "- 초안에 이미 나온 소제목·내용을 다시 쓰지 마세요. "
        "초안이 다루지 않은 질문을 새로 다룹니다.\n"
        "- 초안을 다시 출력하지 말고, 이어질 내용만 출력하세요.\n"
        "- 인사말·마무리 인사·「이어서」 같은 안내 문구를 넣지 마세요.\n"
        "- 초안과 같은 문체·형식(마크다운)을 유지합니다."
    )
