"""군타(blog 12) 템플릿 배경 4장 — 프롬프트 주제별로 확연히 다른 그림.

쓰는 법: python3 scripts/make_gunta_backgrounds.py
결과 파일을 media/blogs/12/template/ 에 올리면 된다.

디스커버 규격 1200x675.

두 가지를 지켜야 한다.
  · 제목은 **정중앙에 검은 글씨**로 얹힌다(vertical_align=center,
    text_color=#000000, 외곽선 없음). 그래서 바탕은 밝아야 하고
    가운데는 비워 둬야 한다.
  · 주제가 한눈에 갈려야 한다. 넷이 서로 닮을 필요는 없다.
"""
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 675
LOGO_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a: str, b: str, t: float):
    ra, rb = _rgb(a), _rgb(b)
    return tuple(int(ra[i] + (rb[i] - ra[i]) * t) for i in range(3))


def grad(top: str, bottom: str, diagonal: bool = False) -> Image.Image:
    """두 색 사이 그라데이션 바탕."""
    small = Image.new("RGB", (2, 2) if diagonal else (1, 2))
    if diagonal:
        small.putpixel((0, 0), _rgb(top))
        small.putpixel((1, 0), _mix(top, bottom, 0.45))
        small.putpixel((0, 1), _mix(top, bottom, 0.55))
        small.putpixel((1, 1), _rgb(bottom))
    else:
        small.putpixel((0, 0), _rgb(top))
        small.putpixel((0, 1), _rgb(bottom))
    return small.resize((W, H), Image.BICUBIC)


def clear_center(img: Image.Image, strength: int = 170) -> Image.Image:
    """가운데를 밝게 씻어 검은 제목이 또렷하게 얹히도록."""
    veil = Image.new("L", (W, H), 0)
    ImageDraw.Draw(veil).ellipse((30, 60, W - 30, H - 80), fill=strength)
    veil = veil.filter(ImageFilter.GaussianBlur(95))
    white = Image.new("RGB", (W, H), (255, 255, 255))
    return Image.composite(white, img, veil)


def wordmark(img: Image.Image, color=(0, 0, 0, 60)) -> Image.Image:
    """오른쪽 아래 작은 이름표. 기존 배경의 GOONTA 를 잇는다."""
    d = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype(LOGO_FONT, 30)
    except OSError:
        return img
    d.text((W - 42, 42), "GOONTA", font=font, fill=color, anchor="rt")
    return img


def stocks() -> Image.Image:
    """주식·ETF — 아래쪽 캔들과 상승선. 가운데는 비운다."""
    img = grad("#EDF4FF", "#C3D9F7")
    d = ImageDraw.Draw(img, "RGBA")
    for x in range(0, W, 80):
        d.line([(x, 430), (x, H)], fill=(40, 80, 150, 26), width=1)
    for y in range(440, H, 56):
        d.line([(0, y), (W, y)], fill=(40, 80, 150, 26), width=1)

    tops = [598, 572, 586, 546, 560, 520, 508, 480, 492, 452, 436, 408]
    for i, top in enumerate(tops):
        x = 62 + i * 94
        up = i % 3 != 1
        col = (214, 58, 66, 240) if up else (36, 122, 176, 240)
        d.line([(x + 13, top - 26), (x + 13, top + 74)], fill=col, width=3)
        d.rectangle([x, top, x + 26, top + 50], fill=col)
    pts = [(62, 628), (250, 606), (430, 580), (620, 546),
           (810, 514), (1000, 468), (1140, 428)]
    d.line(pts, fill=(22, 132, 96, 235), width=7, joint="curve")
    d.polygon([(1150, 420), (1110, 438), (1126, 456)],
              fill=(22, 132, 96, 235))
    return wordmark(clear_center(img, 150))


def subsidy() -> Image.Image:
    """정부 지원금 — 서류와 확인 표, 관공서."""
    img = grad("#EAF8F2", "#BFE9DA", diagonal=True)
    d = ImageDraw.Draw(img, "RGBA")

    for i, (x, y) in enumerate(((44, 346), (28, 378), (12, 410))):
        d.rounded_rectangle([x, y, x + 250, y + 250], 16,
                            fill=(255, 255, 255, 250 - i * 30),
                            outline=(28, 122, 104, 90), width=2)
    for k in range(5):
        y = 452 + k * 29
        d.rounded_rectangle([46, y, 46 + (196 if k % 3 else 128), y + 10], 5,
                            fill=(26, 118, 100, 190))
    d.ellipse([192, 496, 296, 600], fill=(246, 176, 46, 255))
    d.line([(218, 550), (239, 573), (273, 526)],
           fill=(255, 255, 255, 255), width=14, joint="curve")

    base = H - 52
    d.rectangle([880, base, 1160, base + 14], fill=(28, 122, 104, 70))
    for i in range(5):
        x = 906 + i * 52
        d.rectangle([x, base - 150, x + 26, base], fill=(28, 122, 104, 62))
        d.rectangle([x - 4, base - 158, x + 30, base - 148],
                    fill=(28, 122, 104, 78))
    d.polygon([(866, base - 158), (1174, base - 158), (1020, base - 226)],
              fill=(28, 122, 104, 78))
    return wordmark(clear_center(img, 150))


def tax() -> Image.Image:
    """세금·연말정산 — 계산기와 영수증."""
    img = grad("#FFF6E9", "#FBDFBC", diagonal=True)
    d = ImageDraw.Draw(img, "RGBA")

    d.rounded_rectangle([46, 352, 238, 626], 20, fill=(255, 255, 255, 252),
                        outline=(150, 92, 40, 90), width=2)
    d.rounded_rectangle([66, 372, 218, 422], 9, fill=(62, 44, 30, 235))
    for r in range(4):
        for c in range(3):
            x, y = 70 + c * 54, 440 + r * 45
            hot = (r == 3 and c == 2)
            d.rounded_rectangle([x, y, x + 42, y + 33], 8,
                                fill=(226, 108, 72, 245) if hot
                                else (208, 176, 146, 235))

    rx, ry = 946, 330
    d.rectangle([rx, ry, rx + 222, ry + 268], fill=(255, 255, 255, 252))
    teeth = []
    for i in range(8):
        teeth.append((rx + i * 32, ry + 268))
        teeth.append((rx + i * 32 + 16, ry + 290))
    teeth += [(rx + 222, ry + 268), (rx, ry + 268)]
    d.polygon(teeth, fill=(255, 255, 255, 252))
    for k in range(6):
        y = ry + 32 + k * 36
        d.rounded_rectangle([rx + 22, y, rx + 22 + (102 if k % 2 else 168),
                             y + 10], 5, fill=(158, 96, 44, 195))
    for i, (cx, cy) in enumerate(((820, 576), (874, 576), (846, 530))):
        d.ellipse([cx, cy, cx + 58, cy + 58], fill=(244, 186, 64, 252))
        d.ellipse([cx + 11, cy + 11, cx + 47, cy + 47],
                  outline=(176, 122, 34, 220), width=4)
    return wordmark(clear_center(img, 150))


def savings() -> Image.Image:
    """적금·예금 — 돼지저금통과 쌓이는 동전."""
    img = grad("#FFF1F4", "#FBD3DE", diagonal=True)
    d = ImageDraw.Draw(img, "RGBA")

    pig = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pig)
    pink = (232, 116, 152, 255)
    px, py = 56, 372
    pd.polygon([(px + 196, py + 8), (px + 258, py - 42), (px + 252, py + 44)],
               fill=pink)
    pd.ellipse([px, py, px + 290, py + 216], fill=pink)
    pd.ellipse([px + 238, py + 76, px + 316, py + 148], fill=pink)
    for i in range(4):
        x = px + 42 + i * 62
        pd.rounded_rectangle([x, py + 196, x + 38, py + 244], 9, fill=pink)
    pd.rounded_rectangle([px + 96, py + 22, px + 186, py + 38], 8,
                         fill=(150, 52, 88, 255))
    pd.ellipse([px + 266, py + 100, px + 282, py + 122],
               fill=(150, 52, 88, 255))
    pd.ellipse([px + 296, py + 100, px + 312, py + 122],
               fill=(150, 52, 88, 255))
    pd.ellipse([px + 202, py + 50, px + 226, py + 74], fill=(96, 32, 58, 255))
    img.paste(pig, (0, 0), pig)

    for col, n in enumerate((3, 5, 7, 9)):
        for k in range(n):
            x = 790 + col * 100
            y = H - 74 - k * 24
            d.ellipse([x, y, x + 84, y + 30], fill=(244, 190, 74, 252))
            d.ellipse([x + 11, y + 6, x + 73, y + 24],
                      outline=(176, 126, 36, 220), width=3)
    return wordmark(clear_center(img, 150))


def main() -> None:
    # 화면은 기본 배경(슬롯 0)을 템플릿 1 자리로 쓴다. 그래서 첫 장은
    # 슬롯 없는 이름으로, 나머지는 슬롯 1~3 으로 낸다.
    jobs = (("template_12.png", stocks, "주식·ETF (기본)"),
            ("template_12_1.png", subsidy, "정부 지원금"),
            ("template_12_2.png", tax, "세금·연말정산"),
            ("template_12_3.png", savings, "적금·예금"))
    for name, fn, label in jobs:
        img = fn()
        img.save(name, "PNG", optimize=True)
        print(f"  {label:12} → {name} {img.size}")


main()
