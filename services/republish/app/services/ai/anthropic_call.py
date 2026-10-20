"""Anthropic(클로드) 호출 도우미 — 모델별 샘플링 값 정리와 응답 읽기.

2026-10 기준 클로드 모델마다 받아 주는 샘플링 값이 다르다.
- Haiku 4.5 · Sonnet 4.5 계열: temperature 와 top_p 를 같이 보내면 400
  → temperature 만 보낸다(top_p·top_k 뺌).
- Sonnet 5 · Opus 4.7 이상 · Opus 5 계열 · Fable 계열: 샘플링 값 자체가 400
  → temperature·top_p·top_k 셋 다 뺀다.
- 그 밖의 옛 모델: 지금까지처럼 들어온 값을 그대로 보낸다.
"""
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5"
# 글 한 편(한국어 4~5천 자 + HTML)이 4096 에서 잘리는 일이 있어 클로드만 올린다.
MIN_ARTICLE_MAX_TOKENS = 8000

_TEMPERATURE_ONLY: Tuple[str, ...] = ("claude-haiku-4-5", "claude-sonnet-4-5")
_NO_SAMPLING: Tuple[str, ...] = (
    "claude-sonnet-5", "claude-opus-4-7", "claude-opus-4-8",
    "claude-opus-5", "claude-fable", "claude-mythos",
)


def sampling_kwargs(
    model: str,
    temperature: Optional[float],
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
) -> Dict[str, Any]:
    """모델 이름에 맞춰 보낼 샘플링 값만 골라 돌려준다.

    Args:
        model: 클로드 모델 ID
        temperature: 온도(없으면 None)
        top_p: top_p(없으면 None)
        top_k: top_k(없으면 None)

    Returns:
        messages.create 에 그대로 넘길 dict
    """
    name = (model or "").lower()
    if name.startswith(_NO_SAMPLING):
        return {}
    out: Dict[str, Any] = {}
    if temperature is not None:
        out["temperature"] = temperature
    if name.startswith(_TEMPERATURE_ONLY):
        return out
    if top_p is not None:
        out["top_p"] = top_p
    if top_k is not None:
        out["top_k"] = top_k
    return out


def response_text(resp: Any, model: str) -> str:
    """응답 content 중 text 블록만 이어 붙인다. 잘렸으면 로그를 남긴다.

    Args:
        resp: anthropic Message 객체
        model: 로그용 모델 ID

    Returns:
        앞뒤 공백을 뗀 본문 문자열(없으면 빈 문자열)
    """
    parts = [
        getattr(b, "text", "") or ""
        for b in (getattr(resp, "content", None) or [])
        if getattr(b, "type", None) == "text"
    ]
    usage = getattr(resp, "usage", None)
    if usage is not None:
        logger.info(
            "[AI_SERVICE] anthropic 토큰 | model=%s | 입력 %s | 출력 %s",
            model, getattr(usage, "input_tokens", "?"),
            getattr(usage, "output_tokens", "?"),
        )
    if getattr(resp, "stop_reason", None) == "max_tokens":
        logger.warning("[AI_SERVICE] anthropic 잘림 | model=%s | max_tokens 도달", model)
    return "".join(parts).strip()
