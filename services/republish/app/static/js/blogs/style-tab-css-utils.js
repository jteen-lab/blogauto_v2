/**
 * 스타일 탭 CSS 유틸리티 함수
 * File: app/static/js/blogs/style-tab-css-utils.js
 * Last-Updated: 2026-01-24
 *
 * 기능:
 * - CSS 생성 헬퍼 함수
 * - 선택자 빌드 함수
 * - 미리보기 생성 함수
 */

/**
 * px 단위가 필요한 CSS 속성 목록
 */
const CSS_PIXEL_PROPERTIES = [
    'font-size', 'border-width', 'border-radius',
    'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
    'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
    'border-top-width', 'border-right-width', 'border-bottom-width', 'border-left-width'
];

/**
 * px 단위가 필요한 속성인지 확인
 * @param {string} property - CSS 속성명
 * @returns {boolean}
 */
function needsPixelUnit(property) {
    return CSS_PIXEL_PROPERTIES.includes(property);
}

/**
 * 버튼 링크 래퍼(div) 선택자 반환 (예: ".button-link" 또는 ".btn.primary")
 * @param {Object} placeholderConfig - 치환자 설정
 * @returns {string} 래퍼 div CSS 선택자
 */
function buttonWrapperSelector(placeholderConfig) {
    const linkStyles = placeholderConfig?.link_styles || {};
    const buttonClass = linkStyles.button_class;
    if (buttonClass && buttonClass.trim()) {
        return buttonClass.trim().split(/\s+/).map(c => `.${c}`).join('');
    }
    return '.button-link';
}

/**
 * CSS 선택자 빌드 (치환자 CSS 클래스 연동)
 * @param {string} selector - 기본 선택자 (h1, p, a, a.button 등)
 * @param {Object} placeholderConfig - 치환자 설정
 * @returns {string} 클래스가 적용된 CSS 선택자
 */
function buildCssSelector(selector, placeholderConfig) {
    const cssClasses = placeholderConfig?.css_classes || {};
    const linkStyles = placeholderConfig?.link_styles || {};

    // a.button:hover (버튼 마우스오버)인 경우
    // 버튼 hover 스타일도 래퍼(div) 안의 a 에 적용 -> ".button-link a:hover"
    if (selector === 'a.button:hover') {
        return `${buttonWrapperSelector(placeholderConfig)} a:hover`;
    }

    // a.button (버튼 링크)인 경우
    // 실제 발행 HTML은 <div class="button-link"><a>...</a></div> 구조이므로
    // 버튼 시각 스타일은 래퍼(div) 안의 a 에 적용해야 한다 -> ".button-link a"
    if (selector === 'a.button') {
        return `${buttonWrapperSelector(placeholderConfig)} a`;
    }

    // a:hover (일반 링크 마우스오버)인 경우
    // 일반 a 처리 로직을 재사용하여 ':hover' 접미
    if (selector === 'a:hover') {
        const defaultClass = linkStyles.default_class;
        if (defaultClass && defaultClass.trim()) {
            const classes = defaultClass.trim().split(/\s+/).map(c => `.${c}`).join('');
            return `a${classes}:hover`;
        }
        // 일반 a 태그 (클래스 없이)
        return 'a:hover';
    }

    // a (일반 링크)인 경우
    if (selector === 'a') {
        const defaultClass = linkStyles.default_class;
        if (defaultClass && defaultClass.trim()) {
            const classes = defaultClass.trim().split(/\s+/).map(c => `.${c}`).join('');
            return `a${classes}`;
        }
        // 일반 a 태그 (클래스 없이)
        return 'a';
    }

    // 일반 태그인 경우 css_classes에서 확인
    const tagClass = cssClasses[selector];
    if (tagClass && tagClass.trim()) {
        const classes = tagClass.trim().split(/\s+/).map(c => `.${c}`).join('');
        return `${selector}${classes}`;
    }

    // 클래스 없으면 태그 그대로
    return selector;
}

/**
 * 선택자별 스타일 설정에서 CSS 코드 생성
 * @param {string[]} selectors - 선택자 목록
 * @param {Object} styleConfig - 선택자별 스타일 설정
 * @param {Object} placeholderConfig - 치환자 설정
 * @returns {string} 생성된 CSS 코드
 */
function generateCssFromConfig(selectors, styleConfig, placeholderConfig) {
    const lines = [];

    for (const selector of selectors) {
        const config = styleConfig[selector];
        if (!config || Object.keys(config).length === 0) {
            continue;
        }

        const properties = [];
        for (const [prop, value] of Object.entries(config)) {
            if (!value) continue;

            // 단위 처리
            let cssValue = value;
            if (needsPixelUnit(prop) && !isNaN(value)) {
                cssValue = `${value}px`;
            }

            properties.push(`    ${prop}: ${cssValue};`);
        }

        if (properties.length > 0) {
            // 버튼 링크는 래퍼(div) 블록 규칙을 함께 생성해야
            // <div class="button-link"><a>...</a></div> 구조에서 한 줄 버튼으로 보인다.
            if (selector === 'a.button') {
                const wrapper = buttonWrapperSelector(placeholderConfig);
                lines.push(`${wrapper} {`);
                lines.push('    display: block;');
                lines.push('    margin-bottom: 10px;');
                lines.push('}');
                lines.push('');
            }
            // CSS 선택자 결정 (치환자 클래스 적용)
            const cssSelector = buildCssSelector(selector, placeholderConfig);
            lines.push(`${cssSelector} {`);
            lines.push(...properties);
            lines.push('}');
            lines.push('');
        }
    }

    // 숨겨진 선택자 CSS 생성 (Zebra Striping 등)
    const hiddenSelectors = typeof HIDDEN_SELECTORS !== 'undefined' ? HIDDEN_SELECTORS : [];
    for (const selector of hiddenSelectors) {
        const config = styleConfig[selector];
        if (!config || Object.keys(config).length === 0) continue;
        const properties = [];
        for (const [prop, value] of Object.entries(config)) {
            if (!value) continue;
            const unit = needsPixelUnit(prop) ? 'px' : '';
            properties.push(`    ${prop}: ${value}${unit};`);
        }
        if (properties.length > 0) {
            lines.push(`${selector} {`);
            lines.push(...properties);
            lines.push('}');
            lines.push('');
        }
    }

    return lines.join('\n');
}

/**
 * 미리보기 HTML에 치환자 클래스 적용
 * @param {string} htmlContent - 원본 HTML
 * @param {Object} placeholderConfig - 치환자 설정
 * @returns {string} 클래스가 적용된 HTML
 */
function applyClassesToPreviewHtml(htmlContent, placeholderConfig) {
    const cssClasses = placeholderConfig?.css_classes || {};
    const linkStyles = placeholderConfig?.link_styles || {};

    let result = htmlContent;

    // 각 태그에 클래스 추가 (정규식 사용)
    for (const [tag, className] of Object.entries(cssClasses)) {
        if (!className || tag === 'a') continue; // a 태그는 별도 처리

        // <tag> 또는 <tag ... 형태 찾아서 클래스 추가
        const regex = new RegExp(`<${tag}(\\s|>)`, 'gi');
        result = result.replace(regex, (match, suffix) => {
            if (suffix === '>') {
                return `<${tag} class="${className}">`;
            }
            return `<${tag} class="${className}"${suffix}`;
        });
    }

    // 링크 스타일 적용
    const defaultLinkClass = linkStyles.default_class;
    const buttonLinkClass = linkStyles.button_class || 'button-link';

    // 버튼 링크 클래스 교체
    if (buttonLinkClass) {
        result = result.replace(/class="button-link"/g, `class="${buttonLinkClass}"`);
    }

    // 일반 링크 클래스 추가 (클래스 없는 a 태그에만)
    if (defaultLinkClass) {
        result = result.replace(/<a href="([^"]*)">/g, `<a href="$1" class="${defaultLinkClass}">`);
    }

    return result;
}

/**
 * 미리보기용 전체 HTML 문서 생성
 * @param {string} css - 생성된 CSS
 * @param {string} content - 본문 HTML
 * @returns {string} 전체 HTML 문서
 */
function generatePreviewHtml(css, content) {
    return `
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 16px; }
                table { border-collapse: collapse; width: 100%; }
                ${css}
            </style>
        </head>
        <body>${content}</body>
        </html>
    `;
}
