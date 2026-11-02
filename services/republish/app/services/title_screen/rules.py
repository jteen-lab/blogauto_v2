"""2단계 0원 규칙 거르기 + 지문·사이트 열쇠 (D2 + 보강 ②③).

AI·검색량 재기 전에 규칙으로 먼저 버린다. 실제 예는 마케팅 D 방식 최종안 2단계 표.
'론' 은 **대출 상품 이름**일 때만 버린다(메론·○○금융론·○○이론·토론 통과).

순서도: docs/flowcharts/title_screen_d.md (2)
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional
from urllib.parse import parse_qs, urlparse

HANGUL = re.compile(r"[가-힣]")

# (이름, 정규식) — 이름은 지문 reason 으로 남는다.
TITLE_RULES = (
    ("stock", re.compile(r"주가|시세|코인|비트코인|이더리움|리플|상한가|급등주|공모주\s*청약")),
    ("restaurant", re.compile(r"맛집")),
    ("game", re.compile(r"게임|리니지|메이플스토리|던파|배그|롤토체스|발로란트|닌텐도|"
                        r"플스|PS[45]|FPGA|공략집")),
    ("news", re.compile(r"^\s*\[(?:실시간|속보|단독|포토|영상|종합|e뉴스|이슈)[^\]]*\]|"
                        r"\[(?:속보|단독|포토)\]|열애|결혼\s*발표|컴백|아이돌|"
                        r"드라마\s*\d+\s*화|예능")),
    ("model_list", re.compile(r"(?<![A-Za-z0-9])(?!KB\d)(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{8,}"
                              r"(?![A-Za-z0-9])|본사\s*직영")),
    ("town_list", re.compile(r"[가-힣]{1,6}(?:면|읍)\s*[가-힣]{1,6}리(?=\s|$|[,.·])|"
                             r"[가-힣]{1,6}(?:동|면|읍|리)\s+(?:이삿짐\s*센터|포장\s*이사|"
                             r"용달\s*이사|용달|원룸\s*이사|입주\s*청소|이사\s*청소|"
                             r"에어컨\s*청소|철거|폐기물)")),
    ("product_list", re.compile(r"구매\s*(?:예정|계획)이신가요|구매하실\s*예정이신가요")),
    ("adult", re.compile(r"성인용품|19금|야동|조건\s*만남")),
)

# 동네 이름만 바꿔 찍어 낸 업체 광고(지역 + 업종 말). 예: '수원 장례식화환 당일 제작 배송'
LOCAL_BIZ = re.compile(r"화환|꽃배달|이삿짐\s*센터|포장\s*이사|용달|입주\s*청소|이사\s*청소|"
                       r"에어컨\s*청소|철거|폐기물|누수\s*탐지|하수구|싱크대|방충망|도배|열쇠|"
                       r"퀵\s*서비스|대리\s*운전|중고차\s*매입|폐차|용접|간판|흰개미|방역")
_REGIONS: Optional[set] = None


def _regions() -> set:
    """지역명 목록(같은 블로그 중복 검사와 같은 것). 못 읽으면 빈 집합."""
    global _REGIONS
    if _REGIONS is None:
        try:
            from ..generation.same_blog_dedupe import _regions as load

            _REGIONS = set(load())
        except Exception:  # noqa: BLE001
            _REGIONS = set()
    return _REGIONS


def local_ad(title: str) -> bool:
    """앞 두 낱말 안에 지역명이 있고 업종 말이 있으면 동네 나열형 광고."""
    if not LOCAL_BIZ.search(title):
        return False
    regions = _regions()
    for w in title.split()[:2]:
        w = w.strip("[]()")
        if w in regions or (len(w) >= 2 and w[:-1] in regions and w[-1] in "시군구동읍면"):
            return True
    return False


# 대출 상품: 이름 그대로 버리는 것 + '○○론 금리/한도/신청/조건'
LOAN_NAMES = re.compile(r"햇살론|사잇돌\s*론?|비상금\s*(?:론|대출)|카드론|소액\s*대출|"
                        r"당일\s*대출|무직자\s*대출|주부\s*대출|대부(?!분)|급전")
NAMED_LON = re.compile(r"([가-힣A-Za-z0-9]{1,10}론)\s*(?:금리|한도|신청|조건|자격)")
LON_OK_TAIL = ("금융론", "이론", "토론", "메론", "결론", "여론", "추론", "방법론",
               "개론", "총론", "각론", "언론", "본론", "서론", "논론", "재론")
BANK_LOAN = re.compile(r"(?:은행|저축은행|캐피탈|카드|금고|농협|신협|새마을|카카오뱅크|"
                       r"케이뱅크|토스)\S{0,10}\s*\S{0,15}\s*(?:신용)?대출\s*(?:금리|한도)")

# 지난 연도(보다 이른 해가 제목에 박힘). 두 자리 연도는 시기 말이 붙을 때만.
YEAR4 = re.compile(r"(?<!\d)(20\d\d)(?!\d)")


def fingerprint(title: str) -> str:
    """지문 = 공백 뺀 소문자(500자까지)."""
    return re.sub(r"\s+", "", title or "").lower()[:500]


def loan_product(title: str) -> Optional[str]:
    """대출 상품 제목이면 그 상품 말. 메론·○○금융론·○○이론·토론은 통과."""
    m = LOAN_NAMES.search(title)
    if m:
        return m.group(0)
    for m in NAMED_LON.finditer(title):
        word = m.group(1)
        if not word.endswith(LON_OK_TAIL):
            return word
    m = BANK_LOAN.search(title)
    return m.group(0) if m else None


def past_year(title: str, today: Optional[date] = None) -> Optional[int]:
    """제목에 박힌 지난 연도(가장 최근 것). 없으면 None."""
    year = (today or date.today()).year
    past = [int(y) for y in YEAR4.findall(title or "") if int(y) < year]
    return max(past) if past else None


def junk_reason(title: str, today: Optional[date] = None) -> Optional[str]:
    """버릴 제목이면 규칙 이름, 아니면 None."""
    text = (title or "").strip()
    if len(text) < 4:
        return "too_short"
    if not HANGUL.search(text):
        return "not_korean"
    for name, pattern in TITLE_RULES:
        if pattern.search(text):
            return name
    if loan_product(text):
        return "loan_product"
    if local_ad(text):
        return "town_list"
    if past_year(text, today):
        return "past_year"
    return None


# ── 검색어(0단계) ────────────────────────────────────────────────────
KW_JUNK = re.compile(r"주가|시세|코인|맛집|게임|성인|19금|야동|대출\s*(?:금리|한도)|신용대출")
SENTENCE_END = re.compile(r"(?:습니다|었다|였다|해요|어요|아요|니다|네요)$")


def keyword_junk(keyword: str) -> Optional[str]:
    """버릴 검색어면 이유. 칸 판정(회사·쇼핑몰 이름만 등)은 AI 몫이다."""
    kw = (keyword or "").strip()
    if not kw or not HANGUL.search(kw):
        return "not_korean"
    if KW_JUNK.search(kw) or loan_product(kw):
        return "junk_word"
    if SENTENCE_END.search(kw) or len(kw.split()) >= 5:
        return "broken_spacing"
    return None


# ── 사이트 열쇠 ──────────────────────────────────────────────────────
PER_USER_HOSTS = ("blog.naver.com", "cafe.naver.com", "post.naver.com", "brunch.co.kr",
                  "in.naver.com")


def site_key(url: Optional[str]) -> str:
    """출처 사이트 열쇠. 네이버 블로그·카페 등은 호스트/아이디까지 본다."""
    if not url:
        return ""
    try:
        parsed = urlparse(url if "//" in url else f"https://{url}")
    except ValueError:
        return ""
    host = (parsed.netloc or "").lower()
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    if host not in PER_USER_HOSTS:
        return host[:255]
    qs = parse_qs(parsed.query or "")
    owner = (qs.get("blogId") or qs.get("clubid") or [""])[0]
    if not owner:
        parts = [p for p in (parsed.path or "").split("/") if p]
        owner = parts[0] if parts else ""
    return f"{host}/{owner}"[:255] if owner else host
