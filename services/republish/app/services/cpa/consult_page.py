"""상담 페이지 — 정보성 글이 여기로 모인다.

프로모션당 1~2개. 모든 글에 링크를 뿌리는 대신 한 곳으로 모아, 그 페이지가
전환을 맡는다.

**얇은 중개 페이지로 만들지 않는다.** 판별 기준은 하나다.

    바깥으로 나가는 링크를 전부 없애도 이 페이지가 쓸모 있는가?

아니라면 브릿지 페이지다. 검색엔진이 걸러내고, 나중에 유료 광고를 붙일 때는
승인 자체가 안 된다.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ...core.logger import get_logger

logger = get_logger("cpa_consult_page", "app.log")

# 이만큼은 우리가 쓴 내용이어야 한다
MIN_CHARS = 900


def _fields_block(offer: Any) -> str:
    fields = (offer.conversion or {}).get("fields") or []
    if not fields:
        return ""
    items = "".join(f"<li>{f}</li>" for f in fields)
    return (f"<h3>상담 시 남기는 정보</h3><ul>{items}</ul>"
            f"<p>이 정보는 상담 연결에만 쓰입니다.</p>")


def _eligibility_block(offer: Any) -> str:
    """대상이 아닌 사람을 부르면 미승인 DB 가 된다. 미리 걸러 준다."""
    rejects = (offer.conversion or {}).get("reject_reasons") or []
    keep = [r for r in rejects
            if r not in ("오류", "결번", "중복", "장기부재", "상담거절",
                         "장난DB", "본인아님")]
    if not keep:
        return ""
    items = "".join(f"<li>{r}</li>" for r in keep)
    return (f"<h3>상담이 어려운 경우</h3><ul>{items}</ul>"
            f"<p>해당하시면 상담이 진행되지 않을 수 있습니다.</p>")


def _facts_block(offer: Any) -> str:
    """광고주가 준 사실 정보만 쓴다. 없으면 수치를 쓰지 않는다."""
    facts = [str((r or {}).get("value") or "").strip()
             for r in (offer.rules or [])
             if (r or {}).get("type") == "content_source"]
    facts = [f for f in facts if len(f) > 5][:12]
    if not facts:
        return ("<h3>확인이 필요한 부분</h3>"
                "<p>조건은 상황에 따라 달라집니다. 상담에서 확인하실 수 있습니다.</p>")
    items = "".join(f"<li>{f}</li>" for f in facts)
    return f"<h3>알아두면 좋은 내용</h3><ul>{items}</ul>"


def build(offer: Any, landing_url: str, intro: str = "") -> Dict[str, Any]:
    """상담 페이지 HTML.

    Args:
        offer: CpaOffer
        landing_url: 서브아이디가 붙은 랜딩 URL
        intro: 사람이 쓴 도입부(선택). 있으면 앞에 붙는다.

    Returns:
        {"html", "chars", "thin": bool, "missing": [...]}
        `thin` 이면 얇다는 뜻이다 — 그대로 올리면 안 된다.
    """
    notice = (offer.ftc_notice or "").strip()
    blocks: List[str] = []

    # 대가성 문구는 맨 앞. 2024-12-01 개정으로 끝부분 게재가 막혔다.
    if notice:
        blocks.append(f'<p class="ad-notice"><strong>{notice}</strong></p>')

    blocks.append(f"<h2>{offer.name} 상담 안내</h2>")
    if intro:
        blocks.append(f"<p>{intro}</p>")

    blocks.append(_facts_block(offer))
    blocks.append(_eligibility_block(offer))
    blocks.append(_fields_block(offer))

    if landing_url:
        blocks.append(
            f'<p class="cta"><a href="{landing_url}" '
            f'rel="nofollow sponsored" target="_blank">상담 신청하기</a></p>')

    html = "\n".join(b for b in blocks if b)
    text_len = len(_strip(html))

    missing = []
    if not notice:
        missing.append("대가성 문구")
    if not intro:
        missing.append("직접 쓴 도입부")
    if text_len < MIN_CHARS:
        missing.append(f"분량 {text_len}/{MIN_CHARS}자")

    logger.info("[CPA_PAGE] '%s' | %d자 | 부족 %s",
                (offer.name or "")[:30], text_len, missing or "없음")
    return {"html": html, "chars": text_len,
            "thin": text_len < MIN_CHARS, "missing": missing}


def _strip(html: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", html or "").strip()
