"""오토런 글에 홍보 링크(고지문·버튼)를 붙인다.

작업대(모듈 테스터)는 조립 단계에서 링크를 붙이지만, 오토런 생성기에는
그 단계가 없었다. 그래서 오토런으로 만든 업체 글에 버튼이 빠졌다
(이사노트, 2026-10-05 공개분부터).

고르는 규칙과 조립은 작업대와 **같은 함수**를 쓴다 — 미리보기와 오토런
결과가 갈리지 않게.

순서도: docs/flowcharts/promo_link_autorun.md
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from . import assembler, link_service

logger = logging.getLogger(__name__)

#: 모듈 설정의 자리
SETTINGS_KEY = "promo_link"


def _config(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """모듈 설정에서 링크 설정을 꺼낸다. 없으면 빈 dict."""
    raw = (settings or {}).get(SETTINGS_KEY)
    return raw if isinstance(raw, dict) else {}


def is_enabled(settings: Optional[Dict[str, Any]]) -> bool:
    """이 모듈이 오토런 링크 붙이기를 켰나. 기본은 꺼짐.

    링크 목록은 블로그를 비워 두면 모든 블로그에 쓰인다. 기본을 켜면
    '이사' 가 들어간 다른 블로그 글에도 이사 버튼이 붙는다.
    """
    return bool(_config(settings).get("auto"))


def excluded_word(title: str, settings: Optional[Dict[str, Any]]) -> str:
    """제목에 든 제외 낱말. 없으면 빈 문자열.

    키워드로는 업체 글처럼 보여도 실은 정보 글인 것을 거른다
    (예: 「수급자 이사비용 지원사업」).
    """
    words: List[str] = _config(settings).get("exclude") or []
    text = title or ""
    for word in words:
        w = str(word).strip()
        if w and w in text:
            return w
    return ""


async def attach(db: AsyncSession, html: str, title: str,
                 blog_id: Optional[int],
                 settings: Optional[Dict[str, Any]]) -> str:
    """켜져 있고 맞는 링크가 있으면 고지문·버튼을 붙인 HTML을 돌려준다.

    실패하면 원래 HTML을 그대로 돌려준다 — 링크 때문에 글을 잃지 않는다.

    Args:
        db: 세션
        html: 완성 본문
        title: 최종 제목
        blog_id: 블로그 번호(블로그 전용 링크를 가린다)
        settings: 모듈 설정

    Returns:
        HTML (붙였으면 고지문·버튼 포함)
    """
    if not html or not is_enabled(settings):
        return html
    word = excluded_word(title, settings)
    if word:
        logger.info("[PROMO_LINK] 오토런 제외 낱말 '%s' — 붙이지 않음 | %s",
                    word, (title or "")[:30])
        return html
    try:
        link = await link_service.pick_by_keyword(db, title, blog_id)
        if link is None:
            return html
        url = await link_service.tracked_url(db, link, blog_id=blog_id)
        out = assembler.assemble(html, link, title=title, tracked_url=url)
        logger.info("[PROMO_LINK] 오토런 부착 | blog=%s | %s → %s",
                    blog_id, (title or "")[:30], link.name)
        return out or html
    except Exception as e:  # noqa: BLE001
        logger.warning("[PROMO_LINK] 오토런 부착 실패(링크 없이 계속) | %s", e)
        return html
