"""
URL 자동 스타일 추출 서비스.

헤드리스 Chromium(Playwright)으로 대상 URL을 렌더하고, 본문 요소의
computed(최종 계산) 스타일을 읽어 우리 style_config 모델로 매핑한다.
@media·CSS 변수·다중 스타일시트 캐스케이드가 이미 최종값으로 계산된
상태를 읽으므로 정적 붙여넣기 파싱보다 정확·일관적이다.
"""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlparse

from ...core.logger import get_logger

logger = get_logger(__name__)

# 페이지에서 computed 스타일을 수집하는 JS.
# 본문 컨테이너를 탐지하고, 대상 태그별 대표 요소의 지원 속성을 읽는다.
_COLLECT_JS = r"""
() => {
    const TARGETS = ['h1','h2','h3','h4','h5','p','ul','ol','li',
        'table','th','td','blockquote','a'];
    const CONTENT_SELECTORS = ['.entry-content', '.post-content', '.post-body',
        '[itemprop="articleBody"]', 'article', 'main', '.content', '#content'];
    let container = null;
    for (const sel of CONTENT_SELECTORS) {
        const el = document.querySelector(sel);
        if (el && el.innerText && el.innerText.trim().length > 80) { container = el; break; }
    }
    if (!container) container = document.body;

    const PROPS = ['font-size','font-weight','font-style','font-family','line-height',
        'color','background-color','text-align','text-decoration-line','text-transform',
        'margin-top','margin-right','margin-bottom','margin-left',
        'padding-top','padding-right','padding-bottom','padding-left',
        'border-top-width','border-right-width','border-bottom-width','border-left-width',
        'border-top-style','border-top-color','border-radius','list-style-type'];

    const out = {};
    for (const tag of TARGETS) {
        const el = container.querySelector(tag);
        if (!el) continue;
        const cs = getComputedStyle(el);
        const o = {};
        for (const p of PROPS) o[p] = cs.getPropertyValue(p);
        out[tag] = o;
    }
    return out;
}
"""

# computed CSS 롱핸드 → 우리 style_config 키
_CSS_TO_OUR = {
    "font-size": "font-size",
    "font-weight": "font-weight",
    "font-style": "font-style",
    "font-family": "font-family",
    "line-height": "line-height",
    "color": "color",
    "background-color": "background-color",
    "text-align": "text-align",
    "text-decoration-line": "text-decoration",
    "text-transform": "text-transform",
    "margin-top": "margin-top",
    "margin-right": "margin-right",
    "margin-bottom": "margin-bottom",
    "margin-left": "margin-left",
    "padding-top": "padding-top",
    "padding-right": "padding-right",
    "padding-bottom": "padding-bottom",
    "padding-left": "padding-left",
    "border-top-width": "border-top-width",
    "border-right-width": "border-right-width",
    "border-bottom-width": "border-bottom-width",
    "border-left-width": "border-left-width",
    "border-top-style": "border-style",
    "border-top-color": "border-color",
    "border-radius": "border-radius",
    "list-style-type": "list-style",
}

# px 단위로 정규화(숫자화)할 속성
_PX_PROPS = {
    "font-size", "border-radius",
    "border-top-width", "border-right-width", "border-bottom-width", "border-left-width",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding-top", "padding-right", "padding-bottom", "padding-left",
}


def _normalize(our_prop: str, value: str) -> str | None:
    """값 정규화 + 기본값(no-op) 노이즈 제거. 반영할 값이 없으면 None."""
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None

    low = v.lower()
    if low in ("initial", "inherit", "unset", "auto"):
        return None

    # 속성별 no-op(기본값) 스킵
    if our_prop in ("font-style", "line-height") and low == "normal":
        return None
    if our_prop == "font-weight" and low in ("400", "normal"):
        return None
    if our_prop in ("text-decoration", "text-transform", "border-style") and low == "none":
        return None
    if our_prop == "text-align" and low in ("start", "left"):
        return None
    if our_prop == "background-color" and low in ("transparent", "rgba(0, 0, 0, 0)"):
        return None
    if our_prop in ("border-radius", "border-top-width", "border-right-width",
                    "border-bottom-width", "border-left-width") and low in ("0", "0px"):
        return None

    # px 속성은 'Npx' → 'N'
    if our_prop in _PX_PROPS:
        if low.endswith("px"):
            num = v[:-2].strip()
            try:
                float(num)
                return num
            except ValueError:
                return v
        return v
    return v


def _map_computed(collected: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """태그별 computed props → 우리 style_config(지원 속성만, 정규화)."""
    style_config: Dict[str, Dict[str, str]] = {}
    for tag, props in (collected or {}).items():
        mapped: Dict[str, str] = {}
        for css_prop, our_prop in _CSS_TO_OUR.items():
            val = _normalize(our_prop, props.get(css_prop, ""))
            if val is not None and val != "":
                mapped[our_prop] = val
        if mapped:
            style_config[tag] = mapped
    return style_config


def _validate_url(url: str) -> str:
    """http(s) URL만 허용. 유효하지 않으면 ValueError."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("http(s) URL만 지원합니다.")
    return url.strip()


async def extract_style_from_url(url: str) -> Dict[str, Any]:
    """
    URL을 렌더해 본문 요소의 computed 스타일을 style_config로 추출한다.

    Args:
        url: 벤치마킹할 블로그 글 URL (http/https)

    Returns:
        {"style_config": {...}, "report": {"matched_selectors": [...]}}

    Raises:
        ValueError: URL이 유효하지 않을 때
        RuntimeError: 렌더/추출 실패 시
    """
    target = _validate_url(url)

    # 지연 import: Playwright 미설치 환경에서도 모듈 로드는 되도록
    from playwright.async_api import async_playwright

    logger.info(f"[STYLE-URL] 추출 시작 | url={target}")
    collected: Dict[str, Dict[str, str]] = {}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
            try:
                page = await browser.new_page()
                await page.goto(target, wait_until="load", timeout=25000)
                # 웹폰트/지연 스타일 안정화 대기(짧게)
                await page.wait_for_timeout(1200)
                collected = await page.evaluate(_COLLECT_JS)
            finally:
                await browser.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[STYLE-URL] 렌더 실패 | url={target} | {exc}")
        raise RuntimeError(f"렌더/추출에 실패했습니다: {exc}") from exc

    style_config = _map_computed(collected)
    logger.info(f"[STYLE-URL] 추출 완료 | url={target} | 선택자={list(style_config.keys())}")
    return {
        "style_config": style_config,
        "report": {"matched_selectors": list(style_config.keys())},
    }
