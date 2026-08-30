"""모델 요금 기본값 — 제공자가 API 로 주지 않아 우리가 관리한다.

여기 값은 **시드**다. 요금이 바뀌면 관리 화면에서 DB 값을 고치면 되고,
코드 배포는 필요 없다. 화면에는 갱신일을 함께 표시해 오래된 값인지
사용자가 판단할 수 있게 한다.

단위: 100만 토큰당 USD. 딥시크처럼 시간대별 요금이 있으면 **비피크 기준**
으로 적고 note 에 밝힌다.

전체 모델이 아니라 선택지에 올릴 만한 것만 관리한다. 요금이 없는 모델은
화면에서 '요금 미등록' 으로 표시된다.
"""
from typing import Any, Dict, List

# (provider, model_id, input, output, cached_input, tier, note)
SEED: List[Dict[str, Any]] = [
    # ── OpenAI ────────────────────────────────────────────
    {"provider": "openai", "model_id": "gpt-5",
     "input_per_1m": 1.25, "output_per_1m": 10.0, "cached_input_per_1m": 0.125,
     "tier": "flagship"},
    {"provider": "openai", "model_id": "gpt-5-mini",
     "input_per_1m": 0.25, "output_per_1m": 2.0, "cached_input_per_1m": 0.025},
    {"provider": "openai", "model_id": "gpt-4.1",
     "input_per_1m": 2.0, "output_per_1m": 8.0, "cached_input_per_1m": 0.5},
    {"provider": "openai", "model_id": "gpt-4.1-mini",
     "input_per_1m": 0.4, "output_per_1m": 1.6, "cached_input_per_1m": 0.1,
     "tier": "value"},
    {"provider": "openai", "model_id": "gpt-4.1-nano",
     "input_per_1m": 0.1, "output_per_1m": 0.4, "cached_input_per_1m": 0.025},
    {"provider": "openai", "model_id": "gpt-4o",
     "input_per_1m": 2.5, "output_per_1m": 10.0, "cached_input_per_1m": 1.25},
    {"provider": "openai", "model_id": "gpt-4o-mini",
     "input_per_1m": 0.15, "output_per_1m": 0.6, "cached_input_per_1m": 0.075},

    # ── DeepSeek (비피크 기준 — 피크는 2배) ────────────────
    {"provider": "deepseek", "model_id": "deepseek-v4-flash",
     "input_per_1m": 0.22, "output_per_1m": 0.66, "cached_input_per_1m": 0.007,
     "tier": "value",
     "note": "비피크 기준. 피크(평일 KST 10~12시, 15~18시)는 2배"},
    {"provider": "deepseek", "model_id": "deepseek-v4-pro",
     "input_per_1m": 0.66, "output_per_1m": 1.98, "cached_input_per_1m": 0.022,
     "tier": "flagship",
     "note": "비피크 기준. 피크(평일 KST 10~12시, 15~18시)는 2배"},
    {"provider": "deepseek", "model_id": "deepseek-v4-flash-vision-exp",
     "input_per_1m": 0.22, "output_per_1m": 0.66, "cached_input_per_1m": 0.007,
     "note": "비피크 기준. Flash 와 동일 요금"},

    # ── Google ────────────────────────────────────────────
    {"provider": "google", "model_id": "gemini-3.1-pro-preview",
     "input_per_1m": 2.0, "output_per_1m": 12.0, "tier": "flagship"},
    {"provider": "google", "model_id": "gemini-3.5-flash",
     "input_per_1m": 0.3, "output_per_1m": 2.5, "tier": "value"},
    {"provider": "google", "model_id": "gemini-3.5-flash-lite",
     "input_per_1m": 0.1, "output_per_1m": 0.4},
    {"provider": "google", "model_id": "gemini-2.5-pro",
     "input_per_1m": 1.25, "output_per_1m": 10.0},
    {"provider": "google", "model_id": "gemini-2.5-flash",
     "input_per_1m": 0.3, "output_per_1m": 2.5},
    {"provider": "google", "model_id": "gemini-2.5-flash-lite",
     "input_per_1m": 0.1, "output_per_1m": 0.4},

    # ── Anthropic ─────────────────────────────────────────
    {"provider": "anthropic", "model_id": "claude-opus-4-5-20251101",
     "input_per_1m": 5.0, "output_per_1m": 25.0, "tier": "flagship"},
    {"provider": "anthropic", "model_id": "claude-sonnet-4-5-20250929",
     "input_per_1m": 3.0, "output_per_1m": 15.0},
    {"provider": "anthropic", "model_id": "claude-haiku-4-5-20251001",
     "input_per_1m": 1.0, "output_per_1m": 5.0, "tier": "value"},
]

# 글 한 편 기준 예상 비용을 계산할 때 쓰는 가정.
# 승인용 프롬프트(약 2,700자 ≈ 2,000토큰) + 본문 4,000자 ≈ 3,000토큰 수준을
# 실측에서 잡아 반올림한 값이다. 어디까지나 추정이며 실제 청구는 제공자 기준.
EST_INPUT_TOKENS = 3000
EST_OUTPUT_TOKENS = 4000


def estimate_per_post(input_per_1m, output_per_1m) -> float:
    """글 한 편당 대략 비용(USD)."""
    if input_per_1m is None or output_per_1m is None:
        return 0.0
    return (
        input_per_1m * EST_INPUT_TOKENS / 1_000_000
        + output_per_1m * EST_OUTPUT_TOKENS / 1_000_000
    )
