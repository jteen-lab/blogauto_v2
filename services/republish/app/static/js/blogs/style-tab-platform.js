/**
 * 스타일 탭 플랫폼별 CSS 접두 믹스인 (P4)
 * File: app/static/js/blogs/style-tab-platform.js
 * Last-Updated: 2026-06-24
 *
 * styleTabApp()에서 Object.assign()으로 합성하여 사용.
 * 목적: Blogger는 본문이 .post-body 스코프 안에 위치하므로 모든 CSS 규칙에
 *       '.post-body ' 접두를 붙이고, 미리보기 본문도 동일 래퍼로 감싸 일치시킨다.
 *       WordPress 등 그 외 플랫폼은 접두 없이 기존 동작을 유지한다.
 */

/**
 * 플랫폼별 CSS 접두 메서드 믹스인
 * @returns {Object} Alpine.js 컴포넌트에 합성할 메서드 객체
 */
function styleTabPlatformMixin() {
    return {
        /**
         * 플랫폼 기반 CSS 접두 반환 (접두 없음)
         *
         * 본문 스코프는 접두(자손 선택자)가 아니라 치환자 css_classes(각 본문 태그에
         * 플랫폼 본문 클래스를 부여: WP=entry-content / Blogger=post-body)로 처리한다.
         * 따라서 생성 CSS는 'h1.entry-content {}' 형태가 되며, 접두는 붙이지 않는다.
         * (접두를 함께 쓰면 '.post-body h1.post-body'처럼 이중 스코프가 되어 제거)
         * @returns {string} 항상 빈 문자열
         */
        cssPrefix() {
            return '';
        },

        /**
         * 미리보기 본문 래퍼 클래스 반환.
         * 생성 CSS가 '.entry-content h1'처럼 본문 스코프를 조상으로 둔 자손 선택자이므로,
         * 미리보기 본문도 같은 스코프 래퍼로 감싸야 스타일이 일치한다.
         * @returns {string} 래퍼 클래스 ('entry-content' | 'post-body' | 'post-content')
         */
        previewWrapperClass() {
            return this.contentBaseClass();
        },

        /**
         * 블로그 플랫폼별 본문 스코프 기본 클래스 반환(치환자 탭과 동일 규칙).
         * - 워드프레스: 'entry-content', 구글 블로거: 'post-body', 그 외: 'post-content'
         * @returns {string} 본문 스코프 베이스 클래스
         */
        contentBaseClass() {
            // 공용 함수 위임(데이터관리 미리보기와 동일 규칙 보장). 미로드 시 폴백.
            if (typeof styleContentBaseClass === 'function') return styleContentBaseClass(this.platform);
            if (this.platform === 'wordpress') return 'entry-content';
            if (this.platform === 'blogger') return 'post-body';
            return 'post-content';
        },

        /**
         * CSS 생성/미리보기에 쓸 '스코프 자동 적용' 치환자 설정 반환.
         *
         * 본문 스코프(entry-content/post-body)는 블로그 플랫폼이 정하는 값이므로,
         * 치환자 저장 여부와 무관하게 스타일 탭이 자동 적용한다. 저장된 css_classes가
         * 있으면 그대로 쓰고, 비어 있으면 플랫폼 본문 스코프('{base}')만 채운다.
         * (스타일 '값'은 styleConfig에서 별도 관리되므로, 이 보강은 선택자 스코프에만 영향)
         * @returns {Object} 스코프가 보강된 placeholderConfig 사본
         */
        effectivePlaceholderConfig() {
            // 공용 함수 위임(데이터관리 미리보기와 동일 규칙 보장). 미로드 시 아래 폴백.
            if (typeof styleEffectivePlaceholderConfig === 'function') {
                return styleEffectivePlaceholderConfig(this.placeholderConfig, this.platform);
            }
            const base = this.contentBaseClass();
            const SCOPES = ['entry-content', 'post-body', 'post-content'];
            // 저장값에서 알려진 본문 스코프를 제거하고 현재 플랫폼 base 스코프를 앞에 부여.
            // 추가 토큰(프리셋/래퍼 클래스)은 보존. 값이 비면 fallbackExtra(없으면 base만).
            const withScope = (val, fallbackExtra) => {
                // 공백·점(.) 모두로 토큰 분해 → 점 붙은 스코프('.entry-content')나
                // 복합 클래스('a.entry-content')도 정확히 스코프로 인식해 중복 제거.
                let toks = String(val || '').trim().split(/[\s.]+/)
                    .filter(t => t && SCOPES.indexOf(t) === -1);
                if (!toks.length) return fallbackExtra ? `${base} ${fallbackExtra}` : base;
                return `${base} ${toks.join(' ')}`;
            };
            const TAGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol',
                'li', 'table', 'th', 'td', 'blockquote'];
            const saved = (this.placeholderConfig && this.placeholderConfig.css_classes) || {};
            const css = {};
            TAGS.forEach(tag => { css[tag] = withScope(saved[tag]); });
            // 저장된 비표준 태그도 보존
            Object.keys(saved).forEach(t => { if (!(t in css)) css[t] = withScope(saved[t]); });

            const savedLink = (this.placeholderConfig && this.placeholderConfig.link_styles) || {};
            const link = Object.assign({}, savedLink);
            link.default_class = withScope(savedLink.default_class);
            link.button_class = withScope(savedLink.button_class, 'button-link');
            return Object.assign({}, this.placeholderConfig, { css_classes: css, link_styles: link });
        },

        /**
         * 부모 컴포넌트(selectedBlog)에서 platform 값 시도 취득
         * load() API 응답에 platform이 없을 때의 폴백.
         */
        syncPlatformFromParent() {
            try {
                const settingsEl = document.getElementById('blogSettings');
                const parentData = settingsEl?._x_dataStack?.[0];
                const p = parentData?.selectedBlog?.platform;
                if (p) this.platform = String(p).toLowerCase();
            } catch (e) {
                // 부모 접근 실패는 무시 (접두 없이 동작)
            }
        },

        /**
         * CSS 생성 (유틸리티 함수 사용, 플랫폼 접두 적용)
         * @returns {string} 생성된 CSS
         */
        generateCss() {
            if (typeof generateCssFromConfig === 'function') {
                this.generatedCss = generateCssFromConfig(
                    this.selectors,
                    this.styleConfig,
                    this.effectivePlaceholderConfig(),
                    this.cssPrefix()
                );
            } else {
                // 폴백: 유틸리티 없으면 간단 구현
                this.generatedCss = this.generateCssFallback();
            }
            return this.generatedCss;
        },

        /**
         * CSS 생성 폴백 (유틸리티 로드 실패 시)
         * @returns {string} 생성된 CSS
         */
        generateCssFallback() {
            const lines = [];
            for (const selector of this.selectors) {
                const config = this.styleConfig[selector];
                if (!config || Object.keys(config).length === 0) continue;
                const props = Object.entries(config)
                    .filter(([, v]) => v)
                    .map(([p, v]) => `    ${p}: ${v}${this.needsPixelUnitFallback(p) && !isNaN(v) ? 'px' : ''};`);
                if (props.length > 0) {
                    lines.push(`${selector} {`, ...props, '}', '');
                }
            }
            return lines.join('\n');
        },

        /**
         * 폴백용 px 단위 필요 속성 판별
         * @param {string} prop - CSS 속성명
         * @returns {boolean}
         */
        needsPixelUnitFallback(prop) {
            return ['font-size', 'border-width', 'border-radius',
                'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
                'padding-top', 'padding-right', 'padding-bottom', 'padding-left'
            ].includes(prop);
        },

        /**
         * 미리보기 업데이트 (유틸리티 함수 사용, 플랫폼 래퍼 적용)
         *
         * A) 렌더 견고화: Alpine :srcdoc 재렌더가 불안정해 편집이 반영 안 되는
         *    버그를 근본 수정. previewHtml 갱신(폴백 유지) 후 iframe contentDocument에
         *    직접 써서 확실히 재렌더한다.
         */
        updatePreview() {
            // 견고화: 미리보기 오류가 컴포넌트(반응성)를 깨지 않도록 try/catch
            try {
                const css = this.generateCss();
                let previewContent = this.sampleContent;

                if (typeof applyClassesToPreviewHtml === 'function') {
                    // 저장된 치환자 설정으로만 미리보기 요소에 클래스 부여(미저장 값은 반영 안 함)
                    previewContent = applyClassesToPreviewHtml(this.sampleContent, this.effectivePlaceholderConfig());
                }

                let fullHtml;
                if (typeof generatePreviewHtml === 'function') {
                    // 플랫폼에 맞춰 본문 래퍼 적용 (Blogger면 post-body 래핑)
                    fullHtml = generatePreviewHtml(css, previewContent, this.previewWrapperClass());
                } else {
                    // 폴백
                    const wrapClass = this.previewWrapperClass();
                    const body = wrapClass ? `<div class="${wrapClass}">${previewContent}</div>` : previewContent;
                    fullHtml = `<!DOCTYPE html><html><head><style>${css}</style></head><body>${body}</body></html>`;
                }

                this.previewHtml = fullHtml;
                // 콘텐츠(본문+래퍼)가 이전과 같으면(=스타일 속성만 편집) CSS만 교체한다.
                const bodyKey = (this.previewWrapperClass() || '') + '\n' + previewContent;
                this.renderPreviewToIframe(fullHtml, css, bodyKey);
            } catch (e) {
                console.error('[스타일 미리보기] 갱신 오류:', e && e.message);
            }
        },

        /**
         * iframe contentDocument에 미리보기 HTML을 렌더.
         * 최적화: 콘텐츠(본문 구조)가 직전과 동일하면 iframe을 통째로 재로드하지 않고
         * 사용자 CSS(style#__preview_css)의 textContent만 교체한다. 이렇게 하면 스타일
         * 속성을 슬라이더/색상으로 연속 편집할 때 문서 재파싱·선택스크립트 재실행이
         * 사라져 메인 스레드 블로킹(마우스 랙)이 발생하지 않는다.
         * 콘텐츠가 바뀌었거나 iframe이 아직 준비 안 됐으면 srcdoc 전체 렌더로 폴백한다.
         * @param {string} fullHtml - 전체 미리보기 HTML 문서
         * @param {string} [css] - 사용자 생성 CSS (in-place 교체용)
         * @param {string} [bodyKey] - 콘텐츠 동일성 키 (변하면 전체 재로드)
         */
        renderPreviewToIframe(fullHtml, css, bodyKey) {
            const f = document.getElementById('stylePreviewFrame');
            if (!f) { this.previewHtml = fullHtml; return; } // 폴백
            // 콘텐츠 동일 + style 요소 존재 → CSS만 교체(전체 재로드 회피)
            if (typeof css === 'string' && bodyKey !== undefined && this._previewBodyKey === bodyKey) {
                try {
                    const doc = f.contentDocument;
                    const styleEl = doc && doc.getElementById('__preview_css');
                    if (styleEl) { styleEl.textContent = css; return; }
                } catch (_) { /* 접근 실패 시 아래 전체 재로드로 폴백 */ }
            }
            // 최초 렌더 또는 콘텐츠 변경 → 전체 문서 재로드
            this._previewBodyKey = bodyKey;
            f.srcdoc = fullHtml;
        }
    };
}
