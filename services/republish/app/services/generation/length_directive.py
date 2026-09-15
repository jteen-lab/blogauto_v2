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

# 구획(소제목) 수는 **여기서 정하지 않는다.**
# 프롬프트 빌더의 섹션 패턴(P1 은 A~F 여섯 개 …)과 구조 약속이 이미
# 섹션 수와 섹션당 분량을 지시한다. 여기서 또 말하면 둘이 다른 숫자를
# 불러 모델이 어느 쪽을 따를지 헷갈린다. 분량만 말한다.

# 출력 토큰 1개가 담는 한국어 글자 수.
# 실측(최근 30일 372편, 상한 4,096토큰): 최대 7,501자가 나왔다 —
# 1토큰이 최소 1.8자를 담았다는 뜻이다. 상한에 얼마나 근접했는지는
# 알 수 없으니 **보수적으로 1.5자**로 잡는다.
CHARS_PER_TOKEN = 1.5

# 서두·마무리처럼 분량과 무관하게 붙는 몫
TOKEN_MARGIN = 500


def resolve(min_chars: int, module_settings: Optional[dict] = None) -> Dict[str, Any]:
    """임계값에서 목표 분량을 계산한다. 구획 수는 다루지 않는다."""
    gate = ((module_settings or {}).get("quality_gate") or {})

    try:
        margin = float(gate.get("length_margin") or DEFAULT_MARGIN)
    except (TypeError, ValueError):
        margin = DEFAULT_MARGIN
    margin = max(1.0, min(2.0, margin))

    target = int(round(min_chars * margin / 100.0)) * 100  # 100자 단위로 정리
    return {"target": target, "min_chars": min_chars}


def needed_tokens(min_chars: int,
                  module_settings: Optional[dict] = None) -> int:
    """목표 분량을 쓰려면 출력 토큰이 얼마나 필요한가.

    분량만 올리고 최대 토큰을 그대로 두면 글이 중간에 잘린다. 두 값이
    따로 놀지 않도록 여기서 한 번에 계산한다.
    """
    target = resolve(min_chars, module_settings)["target"]
    return int(target / CHARS_PER_TOKEN) + TOKEN_MARGIN


def chars_for_tokens(max_tokens: int) -> int:
    """출력 상한으로 쓸 수 있는 글자 수. 화면에 글자로 보여줄 때 쓴다.

    토큰은 사람이 가늠하기 어려운 단위다. 설정 화면에서는 늘 글자로
    환산해 보여준다.
    """
    usable = max(0, int(max_tokens or 0) - TOKEN_MARGIN)
    return int(usable * CHARS_PER_TOKEN)


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
        "- 위에 적힌 구조(섹션 수와 섹션별 분량)를 지키면서 채웁니다.\n"
        "- 분량은 내용으로 채웁니다. 앞서 쓴 내용을 되풀이하거나, "
        "같은 말을 바꿔 쓰거나, 목차·요약만 늘려 채우지 마세요."
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
        f"- 초안이 다루지 않은 부분을 이어 최소 {shortfall:,}자를 더 씁니다.\n"
        "- 초안에 이미 나온 소제목·내용을 다시 쓰지 마세요. "
        "초안이 다루지 않은 질문을 새로 다룹니다.\n"
        "- 초안을 다시 출력하지 말고, 이어질 내용만 출력하세요.\n"
        "- 인사말·마무리 인사·「이어서」 같은 안내 문구를 넣지 마세요.\n"
        "- 초안과 같은 문체·형식(마크다운)을 유지합니다."
    )
