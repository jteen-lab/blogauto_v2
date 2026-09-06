"""통합 요약 — 여러 문서를 **제목과 함께** 한 번에 읽는다.

기존 요약은 문서마다 따로 "이 문서를 요약해줘" 라고만 물었다. 우리 제목이
무엇을 묻는지 알려주지 않으니, 문서의 주된 내용이 요약되고 정작 필요한
부분은 빠졌다. 서로 모순되는 값이 와도 알 수 없었다.

한 번에 묶어 물으면 세 가지가 좋아진다.

    1. 제목이 묻는 것에 답이 모인다
    2. 자료끼리 값이 다르면 "다르다" 고 적을 수 있다
    3. AI 호출이 3회 → 1회로 준다

**모르면 모른다고 적게 한다.** 없는 수치를 지어내는 것이 무관한 자료보다
나쁘다. 금융·의료처럼 숫자가 곧 사실인 니치에서 특히 그렇다.

순서도: docs/flowcharts/reference_accuracy.md
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from ...core.logger import get_logger
from .relevance import NO_MATCH

logger = get_logger("reference_digest", "app.log")

# 문서 하나에서 읽을 최대 길이. 다 넣으면 토큰이 폭발하고, 중요한 내용은
# 대개 앞에 있다.
PER_DOC_CHARS = 2500

# 전체 입력 상한. 모델 컨텍스트와 비용을 함께 지킨다.
MAX_INPUT_CHARS = 9000

PROMPT = """다음 제목으로 블로그 글을 쓰려고 합니다.

제목: {title}

아래는 이 주제로 검색해 모은 문서들입니다. 글을 쓰는 데 필요한 사실만
{max_length}자 이내로 정리하세요.

지켜야 할 것:
- 제목이 묻는 것에 답이 되는 내용만 고릅니다. 문서의 다른 주제는 버립니다.
- 수치·조건·날짜는 **문서에 있는 값만** 옮깁니다. 없으면 적지 않습니다.
- 문서마다 값이 다르면 "자료에 따라 A 또는 B" 처럼 다르다는 사실을 밝힙니다.
- 어느 문서에서 온 값인지 [1] [2] 처럼 번호로 표시합니다.
- 이 제목과 관련된 내용이 어느 문서에도 없으면 "{no_match}" 라고만 답하세요.

[문서]
{documents}

[정리]"""


def build_prompt(title: str, documents: Sequence[Any],
                 max_length: int = 900) -> str:
    """묶음 요약 프롬프트. 문서가 없으면 빈 문자열."""
    blocks: List[str] = []
    used = 0
    for index, doc in enumerate(documents, 1):
        body = _clean(getattr(doc, "content", "") or "")[:PER_DOC_CHARS]
        if not body:
            continue
        head = (getattr(doc, "title", "") or "").strip()
        block = f"[{index}] {head}\n{body}"
        if used + len(block) > MAX_INPUT_CHARS:
            break
        blocks.append(block)
        used += len(block)

    if not blocks:
        return ""
    return PROMPT.format(title=title, max_length=max_length,
                         no_match=NO_MATCH, documents="\n\n".join(blocks))


def _clean(text: str) -> str:
    """공백 정리. 크롤링 본문은 줄바꿈이 과하게 많다."""
    return re.sub(r"\s+", " ", text).strip()


def sources_of(documents: Sequence[Any]) -> List[str]:
    """정리문에 붙일 출처 목록. 번호 순서가 프롬프트와 같아야 한다."""
    return [getattr(doc, "url", "") or "" for doc in documents
            if (getattr(doc, "content", "") or "").strip()]


async def summarize(ai_service: Any, title: str, documents: Sequence[Any],
                    provider: Optional[str], model: Optional[str],
                    max_length: int = 900) -> Dict[str, Any]:
    """한 번의 호출로 전체를 정리한다.

    Args:
        ai_service: AIService
        title: 재조합된 제목
        documents: CrawledDocument 목록
        provider/model: 요약에 쓸 AI
        max_length: 정리문 최대 길이

    Returns:
        {"text": 정리문, "sources": [url], "no_match": bool, "used": 문서수}
        실패하면 text 가 빈 문자열이다 — 호출자가 문서별 요약으로 되돌린다.
    """
    prompt = build_prompt(title, documents, max_length)
    if not prompt:
        return {"text": "", "sources": [], "no_match": False, "used": 0}

    try:
        # 요약은 낮은 온도로. 창의적으로 쓰면 없는 값을 채워 넣는다.
        result = await ai_service.generate(
            prompt=prompt, provider=provider, model=model,
            max_tokens=max(800, max_length * 2), temperature=0.2,
        )
    except Exception as e:  # noqa: BLE001 — 요약 실패로 글을 막지 않는다
        logger.warning("[REF_DIGEST] 호출 실패 | %s", e)
        return {"text": "", "sources": [], "no_match": False, "used": 0}

    text = _text_of(result).strip()
    if not text:
        return {"text": "", "sources": [], "no_match": False, "used": 0}

    from .relevance import is_no_match

    if is_no_match(text):
        logger.info("[REF_DIGEST] 관련 자료 없음 | title='%s'", title[:30])
        return {"text": "", "sources": [], "no_match": True,
                "used": len(documents)}

    return {"text": text, "sources": sources_of(documents),
            "no_match": False, "used": len(documents)}


def _text_of(result: Any) -> str:
    """AIService 반환형이 dict 든 str 든 문자열을 꺼낸다."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("content", "text", "result", "output"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return ""


def to_prompt_injection(text: str, sources: Sequence[str]) -> str:
    """생성 프롬프트에 넣을 형태.

    무엇을 하라는 말을 함께 준다. 딱지 없이 자료만 던지면 AI 가 그것을
    베끼거나 무시한다 — 어느 쪽인지는 모델이 정한다.
    """
    if not text:
        return ""
    lines = [
        "[참고 자료]",
        "아래는 이 제목으로 검색해 정리한 내용입니다.",
        "사실·수치·최신 정보는 여기서 가져오되 문장을 그대로 옮기지 마세요.",
        "여기에 없는 수치를 지어내지 말고, 출처 URL 은 본문에 쓰지 마세요.",
        "",
        text,
    ]
    if sources:
        lines.append("")
        lines.append("(참고한 문서: " + ", ".join(
            f"[{i}]" for i in range(1, len(sources) + 1)) + ")")
    return "\n".join(lines)
