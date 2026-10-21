"""L3. 블로거 영어 주소 — 영어 제목으로 발행해 주소를 만든 뒤 한글 제목으로 바꾼다.

블로거는 한글 제목으로는 주소를 못 만들어 /2026/10/1.html 처럼 숫자를 붙인다.
주소는 첫 발행 때 제목으로 정해지고, 뒤에 제목을 바꿔도 그대로 남는다
(2026-10-22 슈마즈 실측: 영어 제목 발행 → 한글 제목 PATCH → 주소 유지).

켜는 법: 블로그 ``seo_config.english_slug = {"enabled": true}``.
꺼져 있거나 영어 키워드를 못 만들면 지금처럼 한글 제목으로 발행한다.

순서도: docs/flowcharts/shoemaz_fact_gate.md (L3)
"""
from __future__ import annotations

import re
from typing import Any, Optional

import httpx

from ...core.logger import get_logger

logger = get_logger("blogger_publisher", "app.log")

SLUG_PROVIDER = "openai"
SLUG_MODEL = "gpt-4o-mini"
MAX_LEN = 60
PATCH_TRIES = 3

PROMPT = """아래 한국어 블로그 제목을 검색용 영어 키워드 3~6개로 바꾸세요.
- 소문자 영어 단어만, 단어 사이는 하이픈(-)으로 잇습니다.
- 숫자는 그대로 둘 수 있습니다(예: 1억 원 → 100-million-won).
- 설명 없이 한 줄만 출력합니다. 예: deposit-insurance-limit-per-bank

제목: {title}"""


def enabled(blog: Any) -> bool:
    """블로그 seo_config.english_slug.enabled 가 True 일 때만 켠다."""
    cfg = (getattr(blog, "seo_config", None) or {}).get("english_slug")
    return isinstance(cfg, dict) and cfg.get("enabled") is True


def clean(text: str) -> str:
    """AI 답을 주소용 영어 키워드로 다듬는다(영문·숫자·하이픈만)."""
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    s = re.sub(r"[^a-z0-9]+", "-", line.lower()).strip("-")
    if len(s) > MAX_LEN:
        s = s[:MAX_LEN].rsplit("-", 1)[0]
    return s if len(s.split("-")) >= 2 else ""


async def make(db: Any, blog: Any, title: str) -> Optional[str]:
    """켜진 블로그면 영어 키워드 제목을 만든다. 실패하면 None(한글 그대로 발행)."""
    if not enabled(blog) or not (title or "").strip():
        return None
    try:
        from ..ai.ai_service import AIService

        res = await AIService(db).generate(
            prompt=PROMPT.format(title=title), provider=SLUG_PROVIDER,
            model=SLUG_MODEL, max_tokens=40, temperature=0.2)
        slug = clean((res or {}).get("content", ""))
    except Exception as e:  # noqa: BLE001
        logger.warning("[BLOGGER_SLUG] 키워드 생성 실패 → 한글 제목 발행 | %s", e)
        return None
    logger.info("[BLOGGER_SLUG] blog=%s | '%s' → %s", blog.name,
                title[:30], slug or "(없음)")
    return slug or None


async def restore_title(api_base: str, blog_id: str, post_id: str,
                        title: str, access_token: str) -> bool:
    """발행된 글의 제목을 한글로 되돌린다(주소는 그대로). 성공 여부."""
    url = f"{api_base}/blogs/{blog_id}/posts/{post_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    for attempt in range(PATCH_TRIES):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.patch(url, headers=headers,
                                          json={"title": title})
            if resp.status_code == 200:
                return True
            logger.warning("[BLOGGER_SLUG] 제목 되돌리기 실패 %d/%d | "
                           "status=%d", attempt + 1, PATCH_TRIES,
                           resp.status_code)
        except Exception as e:  # noqa: BLE001
            logger.warning("[BLOGGER_SLUG] 제목 되돌리기 오류 %d/%d | %s",
                           attempt + 1, PATCH_TRIES, e)
    logger.error("[BLOGGER_SLUG] 제목이 영어로 남음 — 손으로 고쳐야 함 | "
                 "post_id=%s | '%s'", post_id, title[:40])
    return False
