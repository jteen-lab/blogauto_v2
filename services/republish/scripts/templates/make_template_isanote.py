"""이사노트 템플릿 배경 — 1600x900 (구글 디스커버 16:9).

레시피노트(테라코타 카드형)·카인포노트(다크 도로형)와 겹치지 않도록
'맑은 날 새 집으로 옮기는 장면'으로 잡았다.

제목은 x140~1460 / y170~600 에 합성되므로 장식은 전부 y>620 에 둔다.
모든 오브젝트는 앞 언덕의 지면선 ground(x) 위에 세워 원근을 맞춘다.
"""
import math
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = sys.argv[1] if len(sys.argv) > 1 else "NanumGothic-Bold.ttf"
OUT = sys.argv[2] if len(sys.argv) > 2 else "template_21.png"

W, H = 1600, 900
SKY_TOP, SKY_BOT = (166, 213, 238), (245, 241, 232)
HILL_BACK, HILL = (132, 186, 163), (176, 215, 195)
BOX, BOX_LID, TAPE, BOX_LINE = (206, 148, 87), (227, 178, 120), (244, 232, 210), (172, 118, 64)
WALL, ROOF, WIN = (250, 249, 245), (74, 121, 145), (169, 205, 224)
TRUCK, CAB, WHEEL = (243, 246, 248), (77, 124, 148), (58, 74, 86)
TRUNK, LEAF = (139, 112, 84), (122, 178, 146)
NAVY, TEAL = (18, 58, 82), (43, 138, 158)

BASE, AMP, PHASE = 806, 22, 2.2   # 앞 언덕


def ground(x: float) -> int:
    """그 x 지점의 지면 높이."""
    return int(BASE - AMP * math.sin(x / 430 + PHASE))


img = Image.new("RGB", (W, H), SKY_TOP)
d = ImageDraw.Draw(img)
for y in range(H):
    t = (y / (H - 1)) ** 0.9
    d.line([(0, y), (W, y)], fill=tuple(
        int(SKY_TOP[i] + (SKY_BOT[i] - SKY_TOP[i]) * t) for i in range(3)))

# 햇살 + 구름
glow = Image.new("L", (W, H), 0)
ImageDraw.Draw(glow).ellipse([1230, -260, 1820, 330], fill=95)
glow = glow.filter(ImageFilter.GaussianBlur(110))
img.paste(Image.new("RGB", (W, H), (255, 253, 243)), (0, 0), glow)

cloud = Image.new("L", (W, H), 0)
cd = ImageDraw.Draw(cloud)
for cx, cy, r in ((178, 126, 60), (252, 144, 44), (104, 148, 42),
                  (1338, 706, 0), (398, 96, 34), (452, 108, 26)):
    if r:
        cd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=110)
cloud = cloud.filter(ImageFilter.GaussianBlur(14))
img.paste(Image.new("RGB", (W, H), (255, 255, 255)), (0, 0), cloud)
d = ImageDraw.Draw(img)

# 언덕 두 겹
d.polygon([(x, ground(x) - 74 - int(16 * math.sin(x / 260)))
           for x in range(0, W + 1, 6)] + [(W, H), (0, H)], fill=HILL_BACK)
d.polygon([(x, ground(x)) for x in range(0, W + 1, 6)] + [(W, H), (0, H)],
          fill=HILL)


def tree(x, h=86):
    g = ground(x)
    d.rectangle([x - 6, g - h * 0.42, x + 6, g], fill=TRUNK)
    d.ellipse([x - 34, g - h, x + 34, g - h * 0.34], fill=LEAF)


def house(x, w=176, wall_h=92):
    g = ground(x + w // 2)
    top = g - wall_h
    d.polygon([(x - 24, top), (x + w // 2, top - 62), (x + w + 24, top)],
              fill=ROOF)
    d.rectangle([x, top, x + w, g], fill=WALL)
    d.rectangle([x + 26, g - 58, x + 68, g], fill=ROOF)          # 문
    d.rectangle([x + 104, g - 62, x + 148, g - 26], fill=WIN)     # 창


def box(x, bottom, w, h, lid=18):
    d.rectangle([x, bottom - h, x + w, bottom], fill=BOX)
    d.rectangle([x, bottom - h, x + w, bottom - h + lid], fill=BOX_LID)
    cx = x + w // 2
    d.rectangle([cx - 13, bottom - h, cx + 13, bottom], fill=TAPE)
    d.rectangle([x, bottom - h, x + w, bottom], outline=BOX_LINE, width=3)


def truck(x):
    """이삿짐 트럭 — 적재함 + 캡 + 바퀴."""
    g = ground(x + 110)
    d.rectangle([x, g - 104, x + 150, g - 18], fill=TRUCK,
                outline=(196, 208, 216), width=3)
    d.polygon([(x + 150, g - 18), (x + 150, g - 80), (x + 196, g - 80),
               (x + 224, g - 44), (x + 224, g - 18)], fill=CAB)
    d.rectangle([x + 160, g - 74, x + 194, g - 48], fill=WIN)
    for wx in (x + 44, x + 196):
        d.ellipse([wx - 20, g - 38, wx + 20, g + 2], fill=WHEEL)
        d.ellipse([wx - 8, g - 26, wx + 8, g - 10], fill=(214, 222, 228))
    d.line([(x + 75, g - 104), (x + 75, g - 18)],
           fill=(206, 216, 223), width=3)                       # 적재함 문 이음선
    d.rectangle([x + 62, g - 66, x + 70, g - 54], fill=(176, 190, 200))


# ── 하단 장면: 좌(집·나무) → 우(트럭·박스) ──────────────
house(186)
tree(414, 94)
tree(470, 66)
truck(690)
box(1188, ground(1250), 156, 104)
box(1212, ground(1250) - 104, 116, 84)
box(1358, ground(1400), 120, 76)
tree(1496, 74)

# ── 로고: 우상단 (레시피=하단중앙 · 카인포=좌상단과 겹치지 않게) ──
font = ImageFont.truetype(FONT, 56)
tw = d.textlength("이사노트", font=font)
d.text((1460 - tw, 74), "이사노트", font=font, fill=NAVY)
d.rounded_rectangle([1460 - tw, 144, 1460, 151], radius=4, fill=TEAL)

img.save(OUT, "PNG", optimize=True)
print("saved", img.size)
