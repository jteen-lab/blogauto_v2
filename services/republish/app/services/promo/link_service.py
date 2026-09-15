"""홍보 링크를 글에 붙이는 일을 한 곳에 모은다.

미리보기와 저장이 같은 결과를 쓰게 하려면 조립 지점이 하나여야 한다.
"""
import logging
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from ...models import PromoLink
from . import assembler

logger = logging.getLogger(__name__)


async def load(db: AsyncSession, link_id: Optional[int]) -> Optional[PromoLink]:
    """고른 링크를 가져온다. 안 골랐으면 None(정보성 글)."""
    if not link_id:
        return None
    link = await db.get(PromoLink, link_id)
    if link is None or not link.is_active:
        logger.warning("[PROMO_LINK] 없거나 꺼진 링크 | id=%s", link_id)
        return None
    return link


async def tracked_url(db: AsyncSession, link: Optional[PromoLink],
                      post_id: Optional[int] = None,
                      blog_id: Optional[int] = None) -> str:
    """추적값이 붙은 주소. 오퍼와 이어져 있을 때만 붙는다.

    이어져 있지 않으면 링크 주소를 그대로 돌려준다 — 추적을 위해
    주소를 망가뜨리지 않는다.
    """
    if link is None:
        return ""
    raw = (link.url or "").strip()
    if not link.cpa_offer_id or not raw:
        return raw
    try:
        from ...models import CpaOffer
        from ..cpa import subid

        offer = await db.get(CpaOffer, link.cpa_offer_id)
        if offer is None:
            return raw
        return subid.apply(raw, offer, post_id=post_id, blog_id=blog_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("[PROMO_LINK] 추적값 부착 실패 | %s", e)
        return raw


async def build_html(db: AsyncSession, html: str,
                     link_id: Optional[int] = None,
                     image_url: Optional[str] = None,
                     title: str = "",
                     post_id: Optional[int] = None,
                     blog_id: Optional[int] = None) -> Tuple[str, Optional[PromoLink]]:
    """완성 HTML과 쓰인 링크를 함께 돌려준다.

    Args:
        html: 생성된 본문
        link_id: 고른 링크. 없으면 고지문·버튼 둘 다 붙지 않는다
        image_url: 표지 이미지
        title: 표지 대체 텍스트
        post_id: 있으면 추적값에 들어간다(저장 뒤에만 안다)
        blog_id: 추적값에 들어간다

    Returns:
        (조립된 HTML, 쓰인 링크 또는 None)
    """
    link = await load(db, link_id)
    url = await tracked_url(db, link, post_id=post_id, blog_id=blog_id)
    out = assembler.assemble(html, link, image_url=image_url,
                             title=title, tracked_url=url)
    return out, link
