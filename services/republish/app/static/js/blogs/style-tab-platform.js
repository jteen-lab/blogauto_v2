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
         * 플랫폼 기반 CSS 접두 반환
         * Blogger는 본문이 .post-body 안에 위치하므로 모든 규칙을 스코프해야 한다.
         * WordPress 등 그 외 플랫폼은 접두 없이 그대로 출력.
         * @returns {string} CSS 접두 문자열 ('.post-body ' 또는 '')
         */
        cssPrefix() {
            return this.platform === 'blogger' ? '.post-body ' : '';
        },

        /**
         * 미리보기 본문 래퍼 클래스 반환 (접두와 일치)
         * @returns {string} 래퍼 클래스 ('post-body' 또는 '')
         */
        previewWrapperClass() {
            return this.platform === 'blogger' ? 'post-body' : '';
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
                    this.placeholderConfig,
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
            // [진단] 호출 여부 + 실패 지점 특정용 라벨 로깅 + 견고화(오류가 컴포넌트를 깨지 않게)
            console.log('[STYLE-PREVIEW] updatePreview 호출');
            try {
                const css = this.generateCss();
                let previewContent = this.sampleContent;

                if (typeof applyClassesToPreviewHtml === 'function') {
                    previewContent = applyClassesToPreviewHtml(this.sampleContent, this.placeholderConfig);
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

                // previewHtml도 갱신(직접쓰기 실패 시 :srcdoc 폴백 가능하도록)
                this.previewHtml = fullHtml;
                // iframe contentDocument 직접 쓰기로 확실하게 재렌더
                this.renderPreviewToIframe(fullHtml);
                console.log('[STYLE-PREVIEW] updatePreview 완료 | css길이=', css ? css.length : 0);
            } catch (e) {
                console.error('[STYLE-PREVIEW] updatePreview 실패:', e && e.message, e);
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
            // [진단] iframe 로드 후 제목이 실제 스타일을 먹는지 자동 로깅
            const plat = this.platform || '(빈값)';
            f.addEventListener('load', function onload() {
                f.removeEventListener('load', onload);
                try {
                    const d = f.contentDocument;
                    const h = d && d.querySelector('h1');
                    const st = d && d.querySelector('style');
                    console.log(
                        '[STYLE-DIAG] platform=', plat,
                        '| h1색상=', h ? getComputedStyle(h).color : 'NO_H1',
                        '| h1부모class=', h ? h.parentElement.className : '-',
                        '| 접두.post-body=', !!(st && st.textContent.includes('.post-body'))
                    );
                } catch (e) {
                    console.log('[STYLE-DIAG] iframe 진단 실패:', e && e.message);
                }
            });
        }
    };
}
