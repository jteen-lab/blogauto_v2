/**
 * 스타일 탭 - 외부 CSS 붙여넣기 추출 (벤치마킹)
 * File: app/static/js/blogs/style-tab-css-import.js
 *
 * 외부 블로그 CSS를 파싱해 우리 스타일 모델(선택자·속성)로 추출한다.
 * - 순수 함수: extractStyleConfigFromCss (파싱/매핑/병합)
 * - 믹스인: styleTabCssImportMixin (Alpine 컴포넌트에 합성할 상태/메서드)
 * 추출은 '시작점'이며, 미리보기·보정 후 저장해야 반영된다.
 */

// 우리 모델이 지원하는 태그 선택자 (a/a:hover는 별도 처리)
const CSS_IMPORT_TAGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'ul', 'ol',
    'li', 'table', 'th', 'td', 'blockquote'];

// 우리 속성 → 조회할 CSS 롱핸드 (CSSOM이 단축속성을 롱핸드로 확장)
const CSS_IMPORT_PROP_MAP = {
    'font-size': 'font-size',
    'font-weight': 'font-weight',
    'font-style': 'font-style',
    'font-family': 'font-family',
    'line-height': 'line-height',
    'color': 'color',
    'background-color': 'background-color',
    'text-align': 'text-align',
    'text-decoration': 'text-decoration-line',
    'text-transform': 'text-transform',
    'margin-top': 'margin-top',
    'margin-right': 'margin-right',
    'margin-bottom': 'margin-bottom',
    'margin-left': 'margin-left',
    'padding-top': 'padding-top',
    'padding-right': 'padding-right',
    'padding-bottom': 'padding-bottom',
    'padding-left': 'padding-left',
    'border-radius': 'border-radius',
    'list-style': 'list-style-type',
    'width': 'width',
    'border-collapse': 'border-collapse'
    // border-style / border-color / border-*-width 는 사이드 통합 처리
    // (아래 _extractProps 특수 로직 — 단측 테두리가 다른 면으로 새어나가지 않게)
};

// px 단위로 정규화(숫자화)할 속성
const CSS_IMPORT_PX_PROPS = [
    'font-size', 'border-radius',
    'border-top-width', 'border-right-width', 'border-bottom-width', 'border-left-width',
    'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
    'padding-top', 'padding-right', 'padding-bottom', 'padding-left'
];

/**
 * 외부 CSS 텍스트를 파싱해 style rule 목록 반환.
 * media="not all"로 붙여 페이지에 적용하지 않고 파싱만 한다.
 * @media / @supports 등 그룹 규칙 내부도 재귀 수집한다(반응형에 들어간 규칙 누락 방지).
 * 각 규칙에 isMedia 플래그(그룹 규칙 내부 여부)를 부여한다.
 * @param {string} cssText - CSS 문자열
 * @returns {Array<{rule: CSSStyleRule, isMedia: boolean}>} 스타일 규칙 목록
 */
function cssImportParseRules(cssText) {
    // 복사본에 <style>...</style> 래퍼나 HTML 주석이 섞여 있으면 CSS 파서가
    // 첫 규칙을 무효 선택자로 오염시켜 삭제한다. 파싱 전에 제거.
    const cleaned = String(cssText || '')
        .replace(/<\/?style[^>]*>/gi, ' ')
        .replace(/<!--/g, ' ').replace(/-->/g, ' ');
    const style = document.createElement('style');
    style.media = 'not all';           // 파싱만, 페이지 미적용
    style.textContent = cleaned;
    document.head.appendChild(style);
    const out = [];
    const collect = (ruleList, inMedia) => {
        for (const rule of Array.from(ruleList || [])) {
            if (rule.type === 1 && rule.selectorText) {
                out.push({ rule, isMedia: inMedia });
            } else if (rule.cssRules) {
                // CSSMediaRule(4)/CSSSupportsRule(12) 등 그룹 규칙 → 재귀
                collect(rule.cssRules, true);
            }
        }
    };
    try {
        collect(style.sheet && style.sheet.cssRules, false);
    } catch (e) {
        // 파싱 실패는 빈 배열 (호출부에서 처리)
    } finally {
        document.head.removeChild(style);
    }
    return out;
}

/**
 * 개별 선택자를 우리 모델 선택자로 매핑.
 * rightmost 심플 선택자에서 태그·hover를 판별한다.
 * @param {string} sel - 단일 CSS 선택자
 * @returns {string|null} 'h1' | 'a' | 'a:hover' | null(미지원)
 */
function cssImportResolveSelector(sel) {
    const last = sel.trim().split(/[\s>+~]+/).filter(Boolean).pop() || '';
    if (!last) return null;
    const hover = /:hover\b/i.test(last);
    const tagMatch = last.match(/^([a-zA-Z][a-zA-Z0-9]*)/);
    const tag = tagMatch ? tagMatch[1].toLowerCase() : '';

    if (CSS_IMPORT_TAGS.includes(tag)) {
        return hover ? null : tag;      // 이 태그들의 hover는 우리 모델 미지원
    }
    if (tag === 'a') {
        // 버튼 링크(.button-link a 등)는 a.button / a.button:hover 로 매핑
        if (/button/i.test(sel)) return hover ? 'a.button:hover' : 'a.button';
        return hover ? 'a:hover' : 'a';
    }
    return null;
}

/**
 * 선택자 명시도 근사값 (id*10000 + class/attr/pseudo*100 + tag).
 * @param {string} sel - 단일 CSS 선택자
 * @returns {number} 명시도 점수
 */
function cssImportSpecificity(sel) {
    const ids = (sel.match(/#[\w-]+/g) || []).length;
    const classes = (sel.match(/\.[\w-]+|\[[^\]]+\]|:(?!:)[\w-]+/g) || []).length;
    const tags = (sel.replace(/[#.][\w-]+|\[[^\]]+\]|::?[\w-]+/g, ' ')
        .match(/[a-zA-Z][\w-]*/g) || []).length;
    return ids * 10000 + classes * 100 + tags;
}

/**
 * 값 정규화. px 속성은 'Npx' → 'N'(숫자), 그 외 단위/값은 원값 유지.
 * @param {string} prop - 우리 속성명
 * @param {string} value - 원본 값
 * @returns {string|null} 정규화 값 (빈값이면 null)
 */
function cssImportNormalizeValue(prop, value) {
    if (value === null || value === undefined) return null;
    const v = String(value).trim();
    if (!v || v === 'initial' || v === 'inherit' || v === 'unset' || v === 'normal' && prop === 'font-family') {
        return null;
    }
    if (CSS_IMPORT_PX_PROPS.includes(prop)) {
        const m = v.match(/^(-?\d*\.?\d+)px$/);
        if (m) return m[1];             // 숫자만
        if (/^0$/.test(v)) return '0';
        return v;                        // em/rem/%/calc 등은 원값 유지
    }
    return v;
}

/**
 * 한 규칙의 style에서 지원 속성만 추출.
 * @param {CSSStyleDeclaration} decl - rule.style
 * @returns {Object} { 우리속성: 값 }
 */
function cssImportExtractProps(decl) {
    const out = {};
    const get = (p) => {
        try { return decl.getPropertyValue(p); } catch (e) { return ''; }
    };
    // 1:1 매핑 속성
    for (const ourProp in CSS_IMPORT_PROP_MAP) {
        const val = cssImportNormalizeValue(ourProp, get(CSS_IMPORT_PROP_MAP[ourProp]));
        if (val !== null && val !== '') out[ourProp] = val;
    }

    // 테두리(사이드 통합): 활성 면(style != none && width > 0) 기준으로
    // generic border-style/border-color 대표값을 잡고, 4면 width를 명시한다.
    // 비활성 면 width는 0으로 명시해야 generic border-style가 다른 면으로 새지 않는다.
    // (원본이 border-left-* 단측이든, border 축약(전체)이든 동일하게 재현됨)
    const sideWidthNum = (raw) => {
        const v = (raw || '').trim();
        const m = v.match(/^(-?\d*\.?\d+)px$/);
        return m ? m[1] : (v && v !== '0' ? v : '0');
    };
    const sides = ['top', 'right', 'bottom', 'left'];
    const active = {};   // side -> {style, widthNum, color}
    let firstActive = null;
    sides.forEach(side => {
        const st = (get('border-' + side + '-style') || '').trim().toLowerCase();
        const wNum = sideWidthNum(get('border-' + side + '-width'));
        const hasBorder = st && st !== 'none' && wNum !== '0';
        active[side] = { hasBorder, style: st, widthNum: wNum, color: get('border-' + side + '-color') };
        if (hasBorder && !firstActive) firstActive = side;
    });
    if (firstActive) {
        out['border-style'] = active[firstActive].style;
        const col = cssImportNormalizeValue('border-color', active[firstActive].color);
        if (col) out['border-color'] = col;
        // 4면 width 명시(활성=실제값, 비활성=0) — 0도 포함해야 새어나감 방지
        sides.forEach(side => {
            out['border-' + side + '-width'] = active[side].hasBorder ? active[side].widthNum : '0';
        });
    }
    return out;
}

/**
 * 외부 CSS 텍스트 → styleConfig 초안 + 리포트.
 * @param {string} cssText - CSS 문자열
 * @returns {{styleConfig: Object, report: Object}}
 */
function extractStyleConfigFromCss(cssText) {
    const rules = cssImportParseRules(cssText);
    const bySelector = {};   // ourSelector -> [{props, spec, order, isMedia}]
    let ignoredRules = 0;

    rules.forEach((entry, order) => {
        const rule = entry.rule;
        const props = cssImportExtractProps(rule.style);
        const hasProps = Object.keys(props).length > 0;
        const parts = rule.selectorText.split(',').map(s => s.trim()).filter(Boolean);
        let matchedAny = false;

        parts.forEach(sel => {
            const target = cssImportResolveSelector(sel);
            if (!target) return;
            matchedAny = true;
            if (!hasProps) return;
            (bySelector[target] = bySelector[target] || []).push({
                props, spec: cssImportSpecificity(sel), order, isMedia: entry.isMedia
            });
        });

        if (!matchedAny) ignoredRules++;
    });

    // 선택자별 병합.
    // - base(비-@media) 규칙이 있으면 그것만 사용(데스크톱 기준값 우선),
    //   없으면 @media 규칙으로 폴백(최소한 태그가 누락되지 않게).
    // - 그 뒤 명시도 → 소스순서 오름차순으로 정렬해 좌→우로 덮어씀.
    const styleConfig = {};
    Object.keys(bySelector).forEach(target => {
        let list = bySelector[target];
        if (list.some(x => !x.isMedia)) list = list.filter(x => !x.isMedia);
        list = list.slice().sort((a, b) => (a.spec - b.spec) || (a.order - b.order));
        const merged = {};
        list.forEach(item => Object.assign(merged, item.props));
        styleConfig[target] = merged;
    });

    return {
        styleConfig,
        report: {
            totalRules: rules.length,
            matchedSelectors: Object.keys(styleConfig),
            ignoredRules
        }
    };
}

// 우리 요소 선택자 → 샘플 내 조회용 CSS 셀렉터
const CSS_IMPORT_QUERY = {
    'h1': 'h1', 'h2': 'h2', 'h3': 'h3', 'h4': 'h4', 'h5': 'h5',
    'p': 'p', 'ul': 'ul', 'ol': 'ol', 'li': 'li',
    'table': 'table', 'th': 'th', 'td': 'td', 'blockquote': 'blockquote',
    'a': 'p a', 'a.button': '.button-link a'
};

/**
 * 붙여넣은 CSS의 선택자에서 우리 요소별 클래스/조상 클래스를 수집해
 * 우리 발행 구조(.entry-content 래퍼 + 각 요소 + .button-link)를 흉내낸 샘플 HTML 생성.
 * @param {string} cssText - CSS 문자열
 * @returns {string} 샘플 HTML
 */
function cssImportBuildSample(cssText) {
    const rules = cssImportParseRules(cssText);
    const tagClasses = {};
    const ancestor = new Set();
    const addCls = (key, arr) => {
        if (!tagClasses[key]) tagClasses[key] = new Set();
        arr.forEach(c => tagClasses[key].add(c));
    };
    rules.forEach(entry => {
        entry.rule.selectorText.split(',').forEach(raw => {
            const sel = raw.trim();
            if (!sel) return;
            const parts = sel.split(/[\s>+~]+/).filter(Boolean);
            const last = parts[parts.length - 1] || '';
            parts.slice(0, -1).forEach(p => {
                (p.match(/\.[\w-]+/g) || []).forEach(c => ancestor.add(c.slice(1)));
            });
            const lastCls = (last.match(/\.[\w-]+/g) || []).map(c => c.slice(1));
            const target = cssImportResolveSelector(sel);
            if (target === 'a') addCls('a', lastCls);
            else if (target === 'a.button') addCls('abutton', lastCls);
            else if (target && CSS_IMPORT_TAGS.indexOf(target) !== -1) addCls(target, lastCls);
        });
    });
    const cl = (k) => Array.from(tagClasses[k] || []).join(' ');
    const anc = Array.from(ancestor).join(' ');
    return '<div class="entry-content ' + anc + '" id="__sp">'
        + '<h1 class="' + cl('h1') + '">가</h1><h2 class="' + cl('h2') + '">가</h2>'
        + '<h3 class="' + cl('h3') + '">가</h3><h4 class="' + cl('h4') + '">가</h4><h5 class="' + cl('h5') + '">가</h5>'
        + '<p class="' + cl('p') + '">가 <a href="#" class="' + cl('a') + '">링크</a></p>'
        + '<ul class="' + cl('ul') + '"><li class="' + cl('li') + '">가</li></ul>'
        + '<ol class="' + cl('ol') + '"><li>가</li></ol>'
        + '<table class="' + cl('table') + '"><thead><tr><th class="' + cl('th') + '">가</th></tr></thead>'
        + '<tbody><tr><td class="' + cl('td') + '">가</td></tr></tbody></table>'
        + '<blockquote class="' + cl('blockquote') + '">가</blockquote>'
        + '<div class="button-link ' + cl('abutton') + '"><a href="#">가</a></div>'
        + '</div>';
}

/**
 * computed 스타일에서 지원 속성 추출 (baseline과 diff해 UA 기본값 제거).
 * @param {CSSStyleDeclaration} styled - CSS 적용된 요소의 computed
 * @param {CSSStyleDeclaration} base - CSS 없는 동일 요소의 computed
 * @returns {Object} { 우리속성: 값 }
 */
function cssImportExtractFromComputed(styled, base) {
    const out = {};
    const sv = (p) => styled.getPropertyValue(p);
    const bv = (p) => base.getPropertyValue(p);
    for (const ourProp in CSS_IMPORT_PROP_MAP) {
        if (ourProp === 'width') continue;   // computed width는 px로 해석돼 의도(100%)와 달라 제외
        const cp = CSS_IMPORT_PROP_MAP[ourProp];
        const v = sv(cp);
        if (v && v !== bv(cp)) {
            const nv = cssImportNormalizeValue(ourProp, v);
            if (nv !== null && nv !== '') out[ourProp] = nv;
        }
    }
    // 테두리: styled/base가 다른 면이 있으면 활성 면 기준 통합 추출
    const sides = ['top', 'right', 'bottom', 'left'];
    let firstActive = null;
    const info = {};
    sides.forEach(side => {
        const st = (sv('border-' + side + '-style') || '').toLowerCase();
        const w = sv('border-' + side + '-width') || '';
        const diff = st !== (bv('border-' + side + '-style') || '').toLowerCase()
            || w !== (bv('border-' + side + '-width') || '');
        const hasBorder = st && st !== 'none' && !/^0(px)?$/.test(w);
        info[side] = { hasBorder, style: st, width: w, color: sv('border-' + side + '-color') };
        if (diff && hasBorder && !firstActive) firstActive = side;
    });
    if (firstActive) {
        out['border-style'] = info[firstActive].style;
        const col = cssImportNormalizeValue('border-color', info[firstActive].color);
        if (col) out['border-color'] = col;
        sides.forEach(side => {
            if (info[side].hasBorder) {
                const m = (info[side].width || '').match(/^(-?\d*\.?\d+)px$/);
                out['border-' + side + '-width'] = m ? m[1] : info[side].width;
            } else {
                out['border-' + side + '-width'] = '0';
            }
        });
    }
    return out;
}

/**
 * 샘플 HTML을 숨긴 iframe에 렌더 (onload 후 resolve).
 * @param {string} html - 샘플 HTML
 * @param {string|null} cleanedCss - 주입할 CSS(없으면 baseline)
 * @returns {Promise<HTMLIFrameElement>}
 */
function cssImportRenderFrame(html, cleanedCss) {
    return new Promise((resolve) => {
        const iframe = document.createElement('iframe');
        iframe.setAttribute('aria-hidden', 'true');
        iframe.style.cssText = 'position:fixed;left:-99999px;top:0;width:820px;height:20px;border:0;';
        let settled = false;
        const done = () => { if (!settled) { settled = true; resolve(iframe); } };
        iframe.onload = () => requestAnimationFrame(done);
        const style = cleanedCss ? '<style>' + cleanedCss + '</style>' : '';
        iframe.srcdoc = '<!DOCTYPE html><html><head><meta charset="utf-8">' + style
            + '</head><body>' + html + '</body></html>';
        document.body.appendChild(iframe);
        setTimeout(done, 1500);   // 폴백 타임아웃
    });
}

/**
 * iframe computed 방식 추출: 동적 샘플 + 붙여넣은 CSS를 렌더해
 * 각 요소의 computed 스타일을 baseline과 diff하여 styleConfig 추출.
 * @param {string} cssText - CSS 문자열
 * @returns {Promise<Object>} styleConfig
 */
async function cssImportExtractViaIframe(cssText) {
    const cleaned = String(cssText || '').replace(/<\/?style[^>]*>/gi, ' ');
    const sample = cssImportBuildSample(cssText);
    const styledFrame = await cssImportRenderFrame(sample, cleaned);
    const baseFrame = await cssImportRenderFrame(sample, null);
    const styleConfig = {};
    try {
        const sWin = styledFrame.contentWindow, sDoc = styledFrame.contentDocument;
        const bWin = baseFrame.contentWindow, bDoc = baseFrame.contentDocument;
        for (const sel in CSS_IMPORT_QUERY) {
            const q = '#__sp ' + CSS_IMPORT_QUERY[sel];
            const sEl = sDoc.querySelector(q);
            const bEl = bDoc.querySelector(q);
            if (!sEl || !bEl) continue;
            const props = cssImportExtractFromComputed(sWin.getComputedStyle(sEl), bWin.getComputedStyle(bEl));
            if (Object.keys(props).length) styleConfig[sel] = props;
        }
    } finally {
        styledFrame.remove();
        baseFrame.remove();
    }
    return styleConfig;
}

/**
 * 스타일 탭 CSS 추출 믹스인 (styleTabApp에 Object.assign으로 합성).
 * @returns {Object} 상태 + 메서드
 */
function styleTabCssImportMixin() {
    return {
        // 상태
        importCssModal: false,
        importCssText: '',
        importCssUrl: '',
        importCssLoading: false,
        importCssReport: null,   // { matchedSelectors, ignoredRules, source }

        /** 모달 열기 */
        openImportCssModal() {
            this.importCssText = '';
            this.importCssUrl = '';
            this.importCssReport = null;
            this.importCssModal = true;
        },

        /**
         * URL 자동 추출: 서버가 헤드리스로 렌더해 computed 스타일을 추출 → styleConfig 병합.
         * (편집 상태만 갱신, 저장해야 반영)
         */
        async extractFromUrl() {
            const url = (this.importCssUrl || '').trim();
            if (!url) {
                if (typeof showErrorMessage === 'function') showErrorMessage('URL을 입력하세요.');
                return;
            }
            if (!this.blogId) {
                if (typeof showErrorMessage === 'function') showErrorMessage('블로그 ID를 찾을 수 없습니다.');
                return;
            }
            this.importCssLoading = true;
            try {
                const res = await fetch(`/api/v1/blogs/${this.blogId}/settings/style/extract-url`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ url })
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || '추출 실패');
                }
                const data = await res.json();
                const extracted = data.style_config || {};
                const matched = Object.keys(extracted);
                if (matched.length === 0) {
                    this.importCssReport = { matchedSelectors: [], ignoredRules: 0, source: 'url' };
                    if (typeof showErrorMessage === 'function') showErrorMessage('본문에서 스타일을 찾지 못했습니다.');
                    return;
                }
                matched.forEach(sel => {
                    this.styleConfig[sel] = Object.assign({}, this.styleConfig[sel] || {}, extracted[sel]);
                });
                this.importCssReport = { matchedSelectors: matched, ignoredRules: 0, source: 'url' };
                if (typeof this.loadCurrentSelectorStyles === 'function') this.loadCurrentSelectorStyles();
                if (typeof this.updatePreview === 'function') this.updatePreview();
                if (typeof showSuccessMessage === 'function') {
                    showSuccessMessage(`${matched.length}개 선택자 스타일을 URL에서 가져왔습니다. 저장을 눌러 반영하세요.`);
                }
            } catch (error) {
                console.error('URL 추출 실패:', error);
                if (typeof showErrorMessage === 'function') {
                    showErrorMessage('URL 추출에 실패했습니다. (접근 불가 / 차단 / 시간초과)');
                }
            } finally {
                this.importCssLoading = false;
            }
        },

        /**
         * 붙여넣은 CSS 추출 → styleConfig 병합 → 미리보기 갱신 (편집 상태만, 저장해야 반영).
         *
         * 두 방식 결합:
         *  ① 선택자 파싱(extractStyleConfigFromCss) — 우리 CSS를 정확히 추출(값 우선).
         *  ② iframe computed — 동적 샘플+CSS 렌더 후 최종 계산 스타일로 외부/캐스케이드/변수 보완.
         * 선택자 파싱값이 우선(정확), computed는 파싱이 놓친 부분을 채운다.
         */
        async extractAndApplyCss() {
            const text = (this.importCssText || '').trim();
            if (!text) {
                if (typeof showErrorMessage === 'function') showErrorMessage('CSS를 붙여넣어 주세요.');
                return;
            }
            this.importCssLoading = true;
            try {
                // ① 선택자 파싱 (우리 CSS 정확)
                let selConfig = {};
                try { selConfig = (extractStyleConfigFromCss(text) || {}).styleConfig || {}; }
                catch (e) { console.error('선택자 파싱 실패:', e); }

                // ② iframe computed (외부/캐스케이드/변수 보완)
                let compConfig = {};
                try { compConfig = await cssImportExtractViaIframe(text); }
                catch (e) { console.error('iframe computed 추출 실패:', e); }

                // 병합: 선택자 파싱값 우선, computed로 빈 속성 보완
                const selectors = new Set(
                    Object.keys(compConfig).concat(Object.keys(selConfig))
                );
                const merged = {};
                selectors.forEach(sel => {
                    const m = Object.assign({}, compConfig[sel] || {}, selConfig[sel] || {});
                    if (Object.keys(m).length) merged[sel] = m;
                });

                const matched = Object.keys(merged);
                if (matched.length === 0) {
                    this.importCssReport = { matchedSelectors: [], ignoredRules: 0 };
                    if (typeof showErrorMessage === 'function') {
                        showErrorMessage('가져올 수 있는 스타일을 찾지 못했습니다.');
                    }
                    return;
                }

                matched.forEach(sel => {
                    this.styleConfig[sel] = Object.assign({}, this.styleConfig[sel] || {}, merged[sel]);
                });
                this.importCssReport = { matchedSelectors: matched, ignoredRules: 0 };

                if (typeof this.loadCurrentSelectorStyles === 'function') this.loadCurrentSelectorStyles();
                if (typeof this.updatePreview === 'function') this.updatePreview();

                if (typeof showSuccessMessage === 'function') {
                    showSuccessMessage(`${matched.length}개 선택자 스타일을 가져왔습니다. 저장을 눌러 반영하세요.`);
                }
            } finally {
                this.importCssLoading = false;
            }
        }
    };
}
