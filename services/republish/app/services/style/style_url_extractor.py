"""
URL 자동 스타일 추출 서비스.

헤드리스 Chromium(Playwright)으로 대상 URL을 렌더하고, 본문 요소의
computed(최종 계산) 스타일을 읽어 우리 style_config 모델로 매핑한다.
@media·CSS 변수·다중 스타일시트 캐스케이드가 이미 최종값으로 계산된
상태를 읽으므로 정적 붙여넣기 파싱보다 정확·일관적이다.

추출 품질은 붙여넣기 추출(style-tab-css-import.js)과 동일 수준을 목표로 한다:
- 단측 테두리(예: border-left만)도 활성 면 기준 통합으로 보존
- 버튼형 링크(.button-link a 등)를 a.button으로 별도 매핑
- computed 초기값 노이즈(list-style:disc, border-collapse:separate) 제거
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from ...core.logger import get_logger

logger = get_logger(__name__)

# 페이지에서 computed 스타일을 수집하는 JS.
# 본문 컨테이너를 탐지하고, 대상 태그별 대표 요소의 지원 속성을 읽는다.
# 일반 링크(a)는 버튼 클래스가 아닌 링크를 우선 선택하고, 버튼형 링크는
# a.button 키로 별도 수집해 버튼 스타일이 일반 링크로 뭉개지지 않게 한다.
_COLLECT_JS = r"""
(tagClasses) => {
    const TAG_TARGETS = ['h1','h2','h3','h4','h5','p','ul','ol','li',
        'table','th','td','blockquote'];
    const TAGS_SET = new Set(TAG_TARGETS.concat(['a']));
    const BTN_SELECTORS = ['.button-link a', 'a.button', 'a.btn', '.btn a',
        'a.wp-block-button__link', '.wp-block-button a', '.btn-link a'];
    const CONTENT_SELECTORS = ['.entry-content', '.post-content', '.post-body',
        '[itemprop="articleBody"]', 'article',
        '.tt_article_useless_p_margin', '.article_view', '.contents_style',
        '.article-view', '.xe_content', '.se-main-container', '.se_component_wrap',
        '.post_ct', '.view-content', 'main', '.content', '#content'];
    let container = null;
    for (const sel of CONTENT_SELECTORS) {
        const el = document.querySelector(sel);
        if (el && el.innerText && el.innerText.trim().length > 80) { container = el; break; }
    }
    if (!container) container = document.body;

    // 사이트가 요소에 다는 클래스 관례(tagClasses)를 정리.
    // '__orphan'(태그 없는 class-only 선택자)은 DOM에서 그 클래스를 가진
    // 요소의 태그로 해석해 병합한다(예: .wp-block-heading → h2).
    const tc = {};
    const srcTC = tagClasses || {};
    for (const k in srcTC) { if (k !== '__orphan') tc[k] = (srcTC[k] || []).slice(); }
    for (const c of (srcTC['__orphan'] || [])) {
        let ex = null;
        try { ex = document.querySelector('.' + CSS.escape(c)); } catch (e) {}
        if (ex) {
            const t = ex.tagName.toLowerCase();
            if (TAGS_SET.has(t)) { (tc[t] = tc[t] || []); if (tc[t].indexOf(c) < 0) tc[t].push(c); }
        }
    }

    const PROPS = ['font-size','font-weight','font-style','font-family','line-height',
        'color','background-color','text-align','text-decoration-line','text-transform',
        'margin-top','margin-right','margin-bottom','margin-left',
        'padding-top','padding-right','padding-bottom','padding-left',
        'border-top-width','border-right-width','border-bottom-width','border-left-width',
        'border-top-style','border-right-style','border-bottom-style','border-left-style',
        'border-top-color','border-right-color','border-bottom-color','border-left-color',
        'border-radius','list-style-type','border-collapse'];

    const read = (el) => {
        const cs = getComputedStyle(el);
        const o = {};
        for (const p of PROPS) o[p] = cs.getPropertyValue(p);
        return o;
    };

    const out = {};
    // 본문 기준 폰트(상속 기본값) — 요소별 font-family 노이즈 제거에 사용
    out['__base'] = { 'font-family': getComputedStyle(container).getPropertyValue('font-family') };

    // 1) 본문 실물 요소 우선 수집(있으면 그 요소가 가장 정확)
    for (const tag of TAG_TARGETS) {
        let el = container.querySelector(tag);
        // h1은 본문 밖(글 제목)에 있는 경우가 많음. 없으면 문서 전체에서 폴백.
        // 블로그 CSS의 h1 규칙은 제목 h1에도 적용되므로 대표값으로 유효.
        if (!el && tag === 'h1') el = document.querySelector('h1');
        if (el) out[tag] = read(el);
    }

    // 2) 링크: 배경 유무 + 버튼 셀렉터로 일반/버튼 분리
    // (본문 첫 링크가 버튼이어도 일반 링크 스타일이 버튼으로 오염되지 않게)
    const bgNone = (v) => !v || v === 'transparent' || v === 'rgba(0, 0, 0, 0)';
    const matchesBtn = (el) => {
        for (const s of BTN_SELECTORS) { try { if (el.matches(s)) return true; } catch (e) {} }
        return !!el.closest('.button-link, .wp-block-button, .btn-link');
    };
    let normalLink = null, btnLink = null;
    for (const el of Array.from(container.querySelectorAll('a'))) {
        const isBtn = matchesBtn(el) || !bgNone(getComputedStyle(el).backgroundColor);
        if (isBtn) { if (!btnLink) btnLink = el; }
        else if (!normalLink) normalLink = el;
        if (normalLink && btnLink) break;
    }
    if (normalLink) out['a'] = read(normalLink);
    if (btnLink) out['a.button'] = read(btnLink);

    // 3) 미사용 태그 보강: 본문에 없는 지원 태그는 숨긴 샘플을 본문 컨테이너에
    // 주입해 사이트 CSS를 상속받은 computed를 읽고 제거한다. computed는 실물이
    // 있어야 측정 가능하므로, 글에 없는 태그(표/인용/h5 등)도 이렇게 보강한다.
    const SAMPLE_HTML =
        '<h1>가</h1><h2>가</h2><h3>가</h3><h4>가</h4><h5>가</h5>'
        + '<p>가 <a href="#">링크</a></p>'
        + '<ul><li>가</li></ul><ol><li>가</li></ol>'
        + '<table><thead><tr><th>가</th></tr></thead>'
        + '<tbody><tr><td>가</td></tr></tbody></table>'
        + '<blockquote>가</blockquote>'
        + '<div class="button-link"><a href="#">가</a></div>';
    const sample = document.createElement('div');
    sample.setAttribute('aria-hidden', 'true');
    sample.style.cssText = 'position:absolute;left:-99999px;top:0;visibility:hidden';
    sample.innerHTML = SAMPLE_HTML;
    container.appendChild(sample);
    try {
        // 주입 요소에 사이트의 태그별 클래스를 입혀 class 기반 규칙(table.wp-block-table 등)도 매칭
        const applyCls = (el, tag) => {
            if (el && tc[tag] && tc[tag].length) el.className = tc[tag].join(' ');
        };
        for (const tag of TAG_TARGETS) {
            if (out[tag]) continue;             // 실물이 있으면 유지
            const el = sample.querySelector(tag);
            if (el) { applyCls(el, tag); out[tag] = read(el); }
        }
        if (!out['a']) { const el = sample.querySelector('p a'); if (el) { applyCls(el, 'a'); out['a'] = read(el); } }
        if (!out['a.button']) { const el = sample.querySelector('.button-link a'); if (el) out['a.button'] = read(el); }
    } finally {
        container.removeChild(sample);
    }
    return out;
}
"""

# 페이지의 모든 스타일시트를 나열: 인라인/접근가능은 cssText, 외부는 href.
# 외부(교차출처) CSS는 cssRules 접근이 CORS로 막히므로 href만 넘겨 Python이
# Playwright 네트워크로 원문을 받아 파싱한다(티스토리 등 스킨 CSS 대응).
_LIST_SHEETS_JS = r"""
() => {
    const out = [];
    for (const s of Array.from(document.styleSheets)) {
        if (s.href) { out.push({ href: s.href, text: null }); continue; }
        try {
            out.push({ href: null, text: Array.from(s.cssRules).map(r => r.cssText).join('\n') });
        } catch (e) { /* 접근 불가 인라인은 스킵 */ }
    }
    return out;
}
"""

# 사이트 클래스 관례 수집 대상 태그
_SUPPORTED_TAGS = {"h1", "h2", "h3", "h4", "h5", "p", "ul", "ol", "li",
                   "table", "th", "td", "blockquote", "a"}

# computed CSS 롱핸드 → 우리 style_config 키 (테두리 4면은 _extract_border에서 별도 처리)
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
    "border-radius": "border-radius",
    "list-style-type": "list-style",
    "border-collapse": "border-collapse",
}

# px 단위로 정규화(숫자화)할 속성
_PX_PROPS = {
    "font-size", "border-radius",
    "border-top-width", "border-right-width", "border-bottom-width", "border-left-width",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding-top", "padding-right", "padding-bottom", "padding-left",
}

# list-style를 반영할 태그(그 외 태그는 computed 초기값 'disc' 노이즈이므로 제외)
_LIST_TAGS = {"ul", "ol"}
_BORDER_SIDES = ("top", "right", "bottom", "left")
_PX_RE = re.compile(r"^(-?\d*\.?\d+)px$")
_ZERO_RE = re.compile(r"^0(px)?$")


def _normalize(our_prop: str, value: str) -> Optional[str]:
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
    if our_prop == "border-collapse" and low == "separate":
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


def _side_width_num(raw: str) -> str:
    """테두리 폭 문자열을 숫자 문자열로. 'Npx'→'N', 그 외 원값(0 폴백)."""
    v = (raw or "").strip()
    m = _PX_RE.match(v)
    if m:
        return m.group(1)
    return v if (v and v != "0") else "0"


def _extract_border(props: Dict[str, str]) -> Dict[str, str]:
    """
    4면 테두리를 활성 면 기준으로 통합.

    활성 면(style≠none & width>0)이 하나라도 있으면 그 대표값으로
    generic border-style/border-color를 잡고, 4면 폭을 명시(비활성=0)한다.
    이렇게 해야 한 면만 있는 테두리(예: border-left)도 재현되고,
    generic style이 다른 면으로 새어나가지 않는다.
    """
    out: Dict[str, str] = {}
    info: Dict[str, Dict[str, Any]] = {}
    first_active: Optional[str] = None
    for side in _BORDER_SIDES:
        style = (props.get(f"border-{side}-style", "") or "").strip().lower()
        width = (props.get(f"border-{side}-width", "") or "").strip()
        has = bool(style) and style != "none" and not _ZERO_RE.match(width or "")
        info[side] = {
            "has": has,
            "style": style,
            "width": width,
            "color": props.get(f"border-{side}-color", ""),
        }
        if has and first_active is None:
            first_active = side

    if first_active is None:
        return out

    out["border-style"] = info[first_active]["style"]
    color = _normalize("border-color", info[first_active]["color"])
    if color:
        out["border-color"] = color
    for side in _BORDER_SIDES:
        if info[side]["has"]:
            out[f"border-{side}-width"] = _side_width_num(info[side]["width"])
        else:
            out[f"border-{side}-width"] = "0"
    return out


def _map_computed(collected: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """태그별 computed props → 우리 style_config(지원 속성만, 정규화·테두리 통합)."""
    collected = collected or {}
    base_ff = ((collected.get("__base") or {}).get("font-family", "") or "").strip()

    style_config: Dict[str, Dict[str, str]] = {}
    for tag, props in collected.items():
        if tag == "__base":
            continue
        mapped: Dict[str, str] = {}
        for css_prop, our_prop in _CSS_TO_OUR.items():
            val = _normalize(our_prop, props.get(css_prop, ""))
            if val is None or val == "":
                continue
            # list-style는 목록 태그에만 (다른 태그 computed 초기값 disc 노이즈 제거)
            if our_prop == "list-style" and tag not in _LIST_TAGS:
                continue
            # font-family가 본문 상속 기본값과 같으면 노이즈 → 제외
            # (링크의 Arial처럼 의도적으로 다른 폰트만 남긴다)
            if our_prop == "font-family" and base_ff and val.strip() == base_ff:
                continue
            mapped[our_prop] = val
        # 테두리(4면 통합)
        mapped.update(_extract_border(props))
        if mapped:
            style_config[tag] = mapped
    return style_config


_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_SELGROUP_RE = re.compile(r"([^{}]+)\{")
_LEADTAG_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9]*)")
_CLASS_RE = re.compile(r"\.([\w-]+)")
_COMBINATOR_RE = re.compile(r"[\s>+~]+")


def _harvest_tag_classes(css_text: str) -> Dict[str, Any]:
    """
    CSS 텍스트에서 각 지원 태그가 쓰는 클래스 관례를 수집한다.

    - 태그가 붙은 선택자(`table.wp-block-table`, `.x h2.title`)는 rightmost
      심플 선택자의 태그·클래스를 그 태그의 관례로 등록.
    - 태그 없는 class-only 선택자(`.wp-block-heading`)는 태그를 알 수 없으므로
      '__orphan'에 모아, 브라우저 측에서 DOM으로 태그를 해석하게 한다.

    Returns:
        {tag: [class,...], "__orphan": [class,...]}
    """
    text = _COMMENT_RE.sub("", css_text or "")
    tag_classes: Dict[str, set] = {}
    orphan: set = set()
    for sel_group in _SELGROUP_RE.findall(text):
        for sel in sel_group.split(","):
            sel = sel.strip()
            if not sel or sel.startswith("@"):
                continue
            parts = [p for p in _COMBINATOR_RE.split(sel) if p]
            last = parts[-1] if parts else ""
            if not last:
                continue
            classes = _CLASS_RE.findall(last)
            if not classes:
                continue
            tm = _LEADTAG_RE.match(last)
            if tm:
                tag = tm.group(1).lower()
                if tag in _SUPPORTED_TAGS:
                    tag_classes.setdefault(tag, set()).update(classes)
            else:
                orphan.update(classes)

    result: Dict[str, Any] = {t: sorted(cs) for t, cs in tag_classes.items()}
    if orphan:
        result["__orphan"] = sorted(orphan)
    return result


async def _collect_all_css(page: Any) -> str:
    """
    페이지의 모든 CSS 원문을 모은다. 인라인/접근가능 스타일시트는 cssText,
    외부(교차출처) 스타일시트는 Playwright 네트워크로 원문을 받아 CORS를 우회.
    """
    try:
        sheets = await page.evaluate(_LIST_SHEETS_JS)
    except Exception:  # noqa: BLE001
        return ""
    parts = []
    for info in sheets or []:
        text = info.get("text")
        href = info.get("href")
        if text:
            parts.append(text)
        elif href:
            try:
                resp = await page.request.get(href, timeout=8000)
                if resp.ok:
                    parts.append(await resp.text())
            except Exception:  # noqa: BLE001
                continue
    return "\n".join(parts)


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
                # 사이트 CSS에서 태그별 클래스 관례를 수집(교차출처 포함)해
                # 미사용 태그 샘플 주입 시 class 기반 규칙까지 매칭되게 한다.
                css_text = await _collect_all_css(page)
                tag_classes = _harvest_tag_classes(css_text)
                collected = await page.evaluate(_COLLECT_JS, tag_classes)
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
