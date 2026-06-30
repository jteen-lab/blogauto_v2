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
         * 미리보기 본문 래퍼 클래스 반환 (래퍼 없음 — 클래스는 각 태그에 직접 부여)
         * @returns {string} 항상 빈 문자열
         */
        previewWrapperClass() {
            return '';
        },

        /**
         * 블로그 플랫폼별 본문 스코프 기본 클래스 반환(치환자 탭과 동일 규칙).
         * - 워드프레스: 'entry-content', 구글 블로거: 'post-body', 그 외: 'post-content'
         * @returns {string} 본문 스코프 베이스 클래스
         */
        contentBaseClass() {
            if (this.platform === 'wordpress') return 'entry-content';
            if (this.platform === 'blogger') return 'post-body';
            return 'post-content';
        },

        /**
         * CSS 생성/미리보기에 쓸 '유효' 치환자 설정 반환.
         *
         * 치환자 탭을 아직 저장하지 않아 placeholderConfig.css_classes가 비어도,
         * 각 본문 태그에 플랫폼 기본 클래스('{base} {tag}')를 채워(치환자 자동입력과 동일),
         * 스타일 탭 CSS/미리보기가 항상 'h1.entry-content {}' 형태로 기본 클래스를 반영하게 한다.
         * 저장값이 있으면 그대로 사용한다.
         * @returns {Object} css_classes가 보강된 placeholderConfig 사본
         */
        effectivePlaceholderConfig() {
            const base = this.contentBaseClass();
            const TAGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol',
                'li', 'table', 'th', 'td', 'blockquote'];
            const saved = (this.placeholderConfig && this.placeholderConfig.css_classes) || {};
            const css = Object.assign({}, saved);
            TAGS.forEach(tag => {
                if (!css[tag] || !String(css[tag]).trim()) {
                    css[tag] = `${base} ${tag}`;
                }
            });
            return Object.assign({}, this.placeholderConfig, { css_classes: css });
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
                    // 기본 클래스 보강된 유효 설정으로 미리보기 요소에도 동일 클래스 부여
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
                this.renderPreviewToIframe(fullHtml);
            } catch (e) {
                console.error('[스타일 미리보기] 갱신 오류:', e && e.message);
            }
        },

        /**
         * iframe contentDocument에 미리보기 HTML을 직접 써서 렌더
         * Alpine :srcdoc 바인딩보다 안정적으로 동작한다.
         * iframe이 아직 없으면(초기화 타이밍) previewHtml만 유지(폴백).
         * @param {string} fullHtml - 전체 미리보기 HTML 문서
         */
        renderPreviewToIframe(fullHtml) {
            const f = document.getElementById('stylePreviewFrame');
            if (!f) { this.previewHtml = fullHtml; return; } // 폴백
            // srcdoc 속성을 직접 설정하면 iframe이 매번 새 문서로 강제 재로드된다.
            // document.write 는 Edge 등에서 재호출 시 조용히 실패하는 경우가 있어 신뢰 불가.
            f.srcdoc = fullHtml;
        }
    };
}
