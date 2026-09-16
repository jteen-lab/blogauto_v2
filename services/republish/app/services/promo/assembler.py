"""글 조립 — 고지문·표지·본문·버튼을 한 덩어리로 만든다.

수작업으로 매번 손으로 붙이던 부분이다. 미리보기와 저장이 갈리지
않도록 조립은 여기 한 곳에서만 한다.
"""
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: 고지문 서식 — 본문보다 작고 흐리게
NOTICE_STYLE = "font-size:15px;color:#8a8a8a;"

#: 표지 이미지 블록 서식 (Blogger 기본 구조와 같게)
IMAGE_BLOCK = (
    '<div class="separator" style="clear:both;text-align:center;">\n'
    '    <img border="0" src="{src}" alt="{alt}" '
    'style="max-width:100%;height:auto;">\n'
    '</div>\n<br/>'
)

#: 버튼 — button-link 는 블록 스타일이라 div 로 감싸야 한다
BUTTON_BLOCK = (
    '<div class="button-link">'
    '<a href="{url}" rel="nofollow sponsored">{text}</a>'
    '</div>'
)


def _escape(text: str) -> str:
    """속성값에 들어갈 문자를 막는다."""
    return (str(text or "")
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def has_notice(html: str) -> bool:
    """이미 고지문이 붙어 있나. 두 번 붙는 것을 막는다."""
    head = (html or "")[:600]
    return "애드릭스" in head or NOTICE_STYLE in head


def has_button(html: str, url: str) -> bool:
    """같은 주소의 버튼이 이미 있나."""
    if not url:
        return False
    return url in (html or "")


def _image_block(image_url: str, alt: str) -> str:
    """표지 블록. 본문에 이미 그 주소가 있으면 넣지 않는다."""
    return IMAGE_BLOCK.format(src=_escape(image_url), alt=_escape(alt))


def assemble(html: str, link: Optional[Any] = None,
             image_url: Optional[str] = None,
             title: str = "", tracked_url: str = "") -> str:
    """완성 HTML을 만든다.

    Args:
        html: 생성된 본문
        link: PromoLink 또는 None. None 이면 정보성 글 — 고지문도
            버튼도 붙지 않는다
        image_url: 표지 이미지 주소. 본문에 이미 있으면 건너뛴다
        title: 표지 대체 텍스트로 쓴다
        tracked_url: 추적값이 붙은 주소. 있으면 링크 주소 대신 쓴다

    Returns:
        조립된 HTML. 입력 본문이 비면 빈 문자열
    """
    body = (html or "").strip()
    if not body:
        return ""

    # 항목마다 쪼개진 목록을 하나로 되돌린다. 조립은 미리보기·저장·재발행이
    # 함께 지나는 자리라, 다른 경로로 만들어진 옛 본문도 여기서 고쳐진다.
    from ..generation.markdown_lists import renumber

    body = renumber(body)

    blocks = []

    notice = (getattr(link, "notice", "") or "").strip() if link else ""
    if notice and not has_notice(body):
        blocks.append(f'<p style="{NOTICE_STYLE}">{notice}</p>')

    if image_url and image_url not in body:
        blocks.append(_image_block(image_url, title))

    blocks.append(body)

    if link:
        url = (tracked_url or getattr(link, "url", "") or "").strip()
        text = (getattr(link, "button_text", "") or "").strip()
        if url and text and not has_button(body, url):
            blocks.append(BUTTON_BLOCK.format(
                url=_escape(url), text=_escape(text)))

    return "\n".join(b for b in blocks if b)


def strip_assembly(html: str) -> str:
    """조립분을 떼어낸다. 다시 조립할 때 겹치지 않게.

    고지문 한 줄과 맨 뒤 버튼 한 덩어리만 지운다. 본문은 건드리지
    않는다.
    """
    out = (html or "").strip()
    out = re.sub(
        r'^\s*<p[^>]*font-size:15px[^>]*>.*?</p>\s*', "", out,
        count=1, flags=re.S)
    out = re.sub(
        r'\s*<div class="button-link">.*?</div>\s*$', "", out,
        count=1, flags=re.S)
    return out.strip()
