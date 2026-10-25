"""템플릿 카드 글자 다듬기 (2026-10-25 마케팅 검수, 형 '전부 적용').

그림 글자는 글처럼 쉽게 못 고친다. 그래서 카드에는 오래 가는 글자만 넣는다.

- 연도·괄호 빼기: '(2026년 기준)' 이 박히면 해가 바뀌면 지난 연도 카드가 된다(/416).
- 앞 검색어 부분만: 제목 전체 대신 쉼표·빗금·대시 앞까지('셀프염색할 때 꿀팁 / …' →
  '셀프염색할 때 꿀팁', /555). 앞부분이 너무 짧으면 제목 그대로.
- 마지막 줄 한 글자 피하기: '…법' 한 글자만 떨어지면 앞 줄 끝 낱말을 같이 내린다(/1773).
- 글자 뒤 바탕 띠: overlay_config.text_band 가 있으면 글자 묶음 뒤에 반투명 띠(/542 화살표).

순서도: docs/flowcharts/renewal_performance_pick.md (5. 카드 글자)
"""
from __future__ import annotations

import re
from typing import Any, List, Optional

_BRACKETS = re.compile(r"\s*[(\[（【][^)\]）】]*[)\]）】]")
_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}\s*년?\s*도?(?:\s*기준)?(?!\d)")
_SEPARATORS = (" / ", "/", " | ", "|", " — ", " – ", " - ", ":", ",")
MIN_HEAD = 5        # 앞부분이 이보다 짧으면(공백 뺀 글자) 자르지 않는다
BAND_PAD = 24


def card_text(title: str) -> str:
    """카드에 넣을 글자. 순수 함수."""
    text = _BRACKETS.sub("", title or "")
    text = _YEAR.sub(" ", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" ,·-")
    for sep in _SEPARATORS:
        if sep in text:
            head = text.split(sep, 1)[0].strip(" ,·-")
            if len(head.replace(" ", "")) >= MIN_HEAD:
                text = head
            break
    return text.rstrip(" .") or (title or "").strip()


def fix_orphan(lines: List[str], fits: Any) -> List[str]:
    """마지막 줄이 한 글자면 앞 줄 끝 낱말을 같이 내린다(fits(줄) 이 참일 때만)."""
    if len(lines) < 2 or len(lines[-1].replace(" ", "")) > 1:
        return lines
    prev = lines[-2].split()
    if len(prev) < 2:
        return lines
    moved = f"{prev[-1]} {lines[-1]}"
    if not fits(moved):
        return lines
    return lines[:-2] + [" ".join(prev[:-1]), moved]


def draw_band(image: Any, draw: Any, lines: List[str], font: Any,
              positions: list, config: dict) -> None:
    """overlay_config.text_band = {"color": "#ffffff", "opacity": 0.8} 이면 글자 뒤 띠."""
    band: Optional[dict] = config.get("text_band") if isinstance(config, dict) else None
    if not isinstance(band, dict) or not band.get("enabled", True) or not positions:
        return
    from PIL import ImageColor, ImageDraw

    boxes = [draw.textbbox(pos, line, font=font) for pos, line in zip(positions, lines)]
    pad = int(band.get("padding", BAND_PAD))
    box = (max(0, min(b[0] for b in boxes) - pad), max(0, min(b[1] for b in boxes) - pad),
           min(image.size[0], max(b[2] for b in boxes) + pad),
           min(image.size[1], max(b[3] for b in boxes) + pad))
    rgb = ImageColor.getrgb(band.get("color") or "#ffffff")[:3]
    alpha = int(255 * float(band.get("opacity", 0.8)))
    ImageDraw.Draw(image, "RGBA").rounded_rectangle(
        box, radius=int(band.get("radius", 18)), fill=(*rgb, alpha))
