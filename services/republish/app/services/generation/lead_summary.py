"""블로거 글의 첫 문단을 검색 설명처럼 쓰게 하는 지시문.

블로거는 글마다 '검색 설명'을 API 로 넣을 수 없다(customMetaData 무시, 10/19 시험).
그래서 글 페이지의 설명 칸은 블로그 설명으로 채워지고, 검색엔진은 본문 첫머리를
요약으로 가져간다. 테마 head 에 본문 앞부분을 meta description 으로 내보내는 줄을
넣으면(형 손) 그 첫머리가 곧 검색 설명이 된다. 첫 문단을 처음부터 그 용도로 쓰게 한다.

순서도: docs/flowcharts/blogger_lead_summary.md
"""
from typing import Any

from ...core.logger import get_logger

logger = get_logger("lead_summary", "app.log")

MARK = "✦ 첫 문단 = 검색 설명"

DIRECTIVE = (
    f"{MARK} (블로거)\n"
    "- H1 바로 다음 첫 문단은 제목이 묻는 것에 바로 답하는 2문장, 합쳐 100~150자로 쓸 것. "
    "이 문단이 검색 결과의 요약 문구로 그대로 쓰인다\n"
    "- 인사말·배경 설명·'이 글에서는 …알아보겠습니다' 로 시작하지 말 것. "
    "두 문장 안에 핵심 숫자나 조건을 넣을 것\n"
    "- 첫 문단은 표·목록·소제목 없이 문장으로만. 그다음 문단부터 도입을 이어 써도 된다"
)


def _is_blogger(blog: Any) -> bool:
    """블로거 블로그인가(모델 속성·문자열 모두 받음)."""
    platform = getattr(blog, "platform", None)
    value = getattr(platform, "value", platform)
    return str(value or "").upper() == "BLOGGER"


def append(full_prompt: str, blog: Any) -> str:
    """블로거면 지시문을 붙인다. 이미 있거나 다른 플랫폼이면 그대로."""
    if not _is_blogger(blog) or MARK in full_prompt:
        return full_prompt
    logger.info("[LEAD_SUMMARY] 첫 문단 검색 설명 지시 주입 | blog=%s",
                getattr(blog, "name", None))
    return f"{full_prompt}\n\n{DIRECTIVE}"
