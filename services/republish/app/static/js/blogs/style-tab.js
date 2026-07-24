/**
 * 스타일 탭 Alpine.js 컴포넌트
 * File: app/static/js/blogs/style-tab.js
 * Last-Updated: 2026-01-24
 *
 * 의존성:
 * - style-tab-presets.js (프리셋 정의)
 * - style-tab-css-utils.js (CSS 유틸리티)
 * - style-tab-table.js (테이블 전용 편집 믹스인)
 */

/**
 * 스타일 탭 메인 컴포넌트
 */
function styleTabApp() {
    const base = {
        // 상태
        loading: false,
        saving: false,
        showCssPanel: false,

        // 테이블 전용 편집 모드
        tableMode: false,

        // 캔버스 레이아웃: 플로팅 편집 카드 노출 여부
        // 미리보기에서 요소를 클릭하면 true(카드 열림), 닫기(×) 시 false.
        editorOpen: false,

        // 테이블 설정 (테이블 전용 UI 상태)
        tableConfig: {
            // 테두리 — 외곽선/가로선/세로선 각각 독립 그룹
            // 그룹 간 색/두께/종류를 공유하지 않으므로 한 선의 색을 바꿔도 다른 선에 영향 없음.
            outline: { on: true, color: '#e5e7eb', width: 1, style: 'solid' }, // 표 바깥 외곽선
            hline: { on: true, color: '#e5e7eb', width: 1, style: 'solid' },   // 가로선(행 구분, 셀 border-bottom)
            vline: { on: true, color: '#e5e7eb', width: 1, style: 'solid' },   // 세로선(열 구분, 셀 border-left/right)
            thBgColor: '#f3f4f6',
            thTextColor: '#1f2937',
            thFontWeight: '600',
            thPadding: 10,
            tdBgColor: '',
            tdTextColor: '#374151',
            tdPadding: 8,
            zebraEnabled: false,
            zebraEvenColor: '#f9fafb',
            zebraOddColor: '#ffffff',
            tableWidth: '100%',
            tableWidthCustom: '',
            borderCollapse: 'collapse',
            borderSpacing: '0',
            // 표 고급 (P4)
            borderRadius: 0,      // 둥근 모서리 (px, 0이면 미적용)
            firstColWidth: '',    // 첫 열 너비 (예: '35%', 빈값이면 미적용)
        },

        // 테이블 프리셋 참조 (Alpine x-for에서 접근 가능하도록)
        tablePresets: {},

        // 선택자 목록 (프리셋 파일에서 가져오거나 기본값)
        selectors: typeof STYLE_SELECTORS !== 'undefined' ? STYLE_SELECTORS : [
            'h1', 'h2', 'h3', 'h4', 'h5',
            'p', 'a', 'a:hover', 'a.button', 'a.button:hover', 'li',
            'ul', 'ol', 'table', 'th', 'td', 'blockquote'
        ],

        // 선택자 표시명
        selectorLabels: typeof SELECTOR_LABELS !== 'undefined' ? SELECTOR_LABELS : {
            'h1': 'h1', 'h2': 'h2', 'h3': 'h3', 'h4': 'h4', 'h5': 'h5',
            'p': 'p', 'a': 'a (일반 링크)', 'a:hover': '링크 (마우스오버)',
            'a.button': 'a (버튼 링크)', 'a.button:hover': '버튼 (마우스오버)',
            'li': 'li', 'ul': 'ul', 'ol': 'ol',
            'table': 'table', 'th': 'th', 'td': 'td', 'blockquote': 'blockquote'
        },

        // 치환자 설정 (링크 스타일, CSS 클래스 연동용)
        placeholderConfig: {
            css_classes: {},
            link_styles: { default_class: '', button_class: 'button-link' }
        },

        // 현재 선택된 선택자
        activeSelector: 'h1',

        // 선택자별 스타일 설정
        styleConfig: {},

        // 테마 갤러리 (P3): 목록 / 적용된 테마 id / 메인 색상
        themes: typeof STYLE_THEMES !== 'undefined' ? STYLE_THEMES : [],
        appliedThemeId: null,
        mainColor: '',

        // 현재 선택자의 스타일 (편집용)
        currentStyles: {},
        // 미리보기 모드 / 생성된 CSS / 미리보기 HTML / 블로그 ID
        previewMode: 'desktop',
        generatedCss: '',
        previewHtml: '',
        blogId: null,

        // 블로그 플랫폼 (소문자 정규화: 'blogger' | 'wordpress' | '')
        // Blogger는 본문이 .post-body 스코프 안에 들어가므로 CSS 접두가 필요하다.
        platform: '',

        // 샘플 콘텐츠 (프리셋 파일에서 가져오거나 기본값)
        sampleContent: typeof SAMPLE_CONTENT !== 'undefined' ? SAMPLE_CONTENT : `
            <h1>제목 (H1)</h1>
            <h2>소제목 (H2)</h2>
            <p>일반 텍스트 단락입니다. <a href="#">일반 링크</a></p>
            <div class="button-link"><a href="#">버튼 링크</a></div>
            <blockquote>인용문 텍스트입니다.</blockquote>
        `,

        /**
         * 초기화
         */
        init() {
            // 테이블 프리셋 로드 (전역 변수 → 컴포넌트 데이터)
            if (typeof TABLE_PRESETS !== 'undefined') this.tablePresets = TABLE_PRESETS;

            // 전역 이벤트 리스너 등록 - blogSettingsApp에서 setBlog 호출 시
            window.addEventListener('blog-settings-loaded', (e) => {
                if (e.detail && e.detail.blogId) {
                    this.blogId = e.detail.blogId;
                    // 현재 블로그 기준으로 platform 갱신(이전 블로그 값 고착 방지)
                    if (e.detail.blog && e.detail.blog.platform) {
                        this.platform = String(e.detail.blog.platform).toLowerCase();
                    }
                    console.log('[styleTabApp] 이벤트로 blogId 수신:', this.blogId, 'platform:', this.platform);
                    this.load();
                }
            });

            // 치환자 설정 변경 이벤트 리스닝 (탭 간 동기화)
            window.addEventListener('placeholders-saved', () => {
                console.log('[styleTabApp] 치환자 설정 변경 감지, 재로드');
                this.reloadPlaceholders();
            });

            // 스타일 탭 재진입 시 서버 최신값 재로드.
            // - 저장하지 않은 스타일 편집 폐기(미저장 값 지속 방지)
            // - 치환자 탭에서 저장한 최신 CSS 클래스를 CSS 보기/미리보기에 반영
            window.addEventListener('blog-tab-changed', (e) => {
                if (e.detail && e.detail.tab === 'style' && this.blogId) {
                    this.load();
                }
            });

            this.initDefaultStyles();
            this.loadCurrentSelectorStyles();
            this.updatePreview();
            // iframe 마운트 보장 후 1회 더 직접 렌더 (A: 초기 직접쓰기 견고화)
            this.$nextTick(() => this.updatePreview());

            // 미리보기 클릭 → 해당 선택자 편집 (C)
            window.addEventListener('message', (e) => {
                if (e.data && e.data.type === 'style-select') {
                    this.setActiveSelectorFromPreview(e.data.selector);
                }
            });

            // 부모 컴포넌트에서 blogId 가져오기 시도
            this.tryLoadFromParent();
        },

        /**
         * 부모 컴포넌트에서 blogId 가져오기 시도
         */
        tryLoadFromParent() {
            const settingsEl = document.getElementById('blogSettings');
            if (settingsEl && settingsEl._x_dataStack && settingsEl._x_dataStack[0]) {
                const parentData = settingsEl._x_dataStack[0];
                if (parentData.selectedBlog && parentData.selectedBlog.id) {
                    this.blogId = parentData.selectedBlog.id;
                    // 부모 selectedBlog에서 platform 취득 (소문자 정규화)
                    if (parentData.selectedBlog.platform) {
                        this.platform = String(parentData.selectedBlog.platform).toLowerCase();
                    }
                    console.log('[styleTabApp] 부모에서 blogId 가져옴:', this.blogId, 'platform:', this.platform);
                    this.load();
                    return true;
                }
            }
            // URL에서도 시도
            const urlId = this.getBlogIdFromUrl();
            if (urlId) {
                this.blogId = urlId;
                this.load();
                return true;
            }
            return false;
        },

        /**
         * URL에서 블로그 ID 추출
         */
        getBlogIdFromUrl() {
            const match = window.location.pathname.match(/\/blogs\/(\d+)/);
            return match ? match[1] : null;
        },

        /**
         * 기본 스타일 설정 초기화
         */
        initDefaultStyles() {
            this.selectors.forEach(selector => {
                if (!this.styleConfig[selector]) {
                    this.styleConfig[selector] = {};
                }
            });
        },

        /**
         * 현재 선택자의 스타일을 편집용 객체로 복사
         */
        loadCurrentSelectorStyles() {
            const config = this.styleConfig[this.activeSelector] || {};
            this.currentStyles = {
                'font-size': config['font-size'] || '',
                'color': config['color'] || '',
                'font-weight': config['font-weight'] || '',
                'font-style': config['font-style'] || '',
                'line-height': config['line-height'] || '',
                'margin-top': config['margin-top'] || '',
                'margin-right': config['margin-right'] || '',
                'margin-bottom': config['margin-bottom'] || '',
                'margin-left': config['margin-left'] || '',
                'padding-top': config['padding-top'] || '',
                'padding-right': config['padding-right'] || '',
                'padding-bottom': config['padding-bottom'] || '',
                'padding-left': config['padding-left'] || '',
                // 테두리 - 전체
                'border-style': config['border-style'] || '',
                'border-width': config['border-width'] || '',
                'border-color': config['border-color'] || '',
                'border-radius': config['border-radius'] || '',
                // 테두리 - 방향별
                'border-top-style': config['border-top-style'] || '',
                'border-top-width': config['border-top-width'] || '',
                'border-top-color': config['border-top-color'] || '',
                'border-right-style': config['border-right-style'] || '',
                'border-right-width': config['border-right-width'] || '',
                'border-right-color': config['border-right-color'] || '',
                'border-bottom-style': config['border-bottom-style'] || '',
                'border-bottom-width': config['border-bottom-width'] || '',
                'border-bottom-color': config['border-bottom-color'] || '',
                'border-left-style': config['border-left-style'] || '',
                'border-left-width': config['border-left-width'] || '',
                'border-left-color': config['border-left-color'] || '',
                'background-color': config['background-color'] || '',
                // 추가 속성 (P2) - px 자동부여 대상 아님, 사용자가 단위 직접 입력
                'text-align': config['text-align'] || '',
                'text-decoration': config['text-decoration'] || '',
                'text-transform': config['text-transform'] || '',
                'font-family': config['font-family'] || '',
                'display': config['display'] || '',
                'width': config['width'] || '',
                'box-sizing': config['box-sizing'] || '',
                'list-style': config['list-style'] || ''
            };
        },

        /**
         * 색상 값이 유효한지 확인
         */
        hasColorValue(value) {
            return value && value.trim() !== '';
        },

        /**
         * 스타일 값 업데이트
         */
        updateStyle(property, value) {
            this.currentStyles[property] = value;
            if (!this.styleConfig[this.activeSelector]) {
                this.styleConfig[this.activeSelector] = {};
            }
            if (value && value.trim()) {
                this.styleConfig[this.activeSelector][property] = value;
            } else {
                delete this.styleConfig[this.activeSelector][property];
            }
            this.debounceUpdatePreview();
        },

        /**
         * 디바운스된 미리보기 업데이트
         */
        debounceUpdatePreview() {
            if (this._previewTimer) clearTimeout(this._previewTimer);
            this._previewTimer = setTimeout(() => this.updatePreview(), 150);
        },

        /**
         * 특정 선택자에 스타일이 있는지 확인
         */
        hasStyles(selector) {
            const config = this.styleConfig[selector];
            return config && Object.keys(config).length > 0;
        },

        /**
         * 플로팅 편집 카드 닫기 (캔버스 레이아웃)
         * 닫아도 activeSelector/tableMode 상태는 보존(다시 클릭 시 동일 요소 복원).
         */
        closeEditor() {
            this.editorOpen = false;
        },

        /**
         * 현재 선택자의 스타일 초기화
         */
        clearSelectorStyles() {
            this.styleConfig[this.activeSelector] = {};
            this.loadCurrentSelectorStyles();
            this.updatePreview();
        },

        /**
         * 전체 스타일 초기화
         */
        resetToDefault() {
            if (!confirm('모든 스타일 설정을 초기화하시겠습니까?')) return;
            this.styleConfig = {};
            this.initDefaultStyles();
            this.loadCurrentSelectorStyles();
            this.updatePreview();
        },

        /**
         * 표시(pre)/복사(copyCss)용 생성 CSS 문자열 반환.
         * - Google Blogger: <style>...</style> 로 감싼다(테마 편집/HTML 가젯에
         *   그대로 붙여넣어야 하므로 style 태그 필요).
         * - WordPress 등 그 외: '추가 CSS(Additional CSS)' 입력란에는 raw CSS만
         *   넣어야 하므로 <style> 태그를 제거하고 순수 CSS만 반환한다.
         * - this.generatedCss 원본은 내부 그대로 유지(저장 등에 사용).
         * @returns {string} 플랫폼에 맞춘 CSS 문자열
         */
        cssWithStyleTag() {
            const css = this.generatedCss || '';
            if (this.platform === 'blogger') {
                return '<style>\n' + css + '\n</style>';
            }
            return css;
        },

        /**
         * CSS 복사 (Blogger는 <style> 래핑, WordPress 등은 raw CSS)
         */
        async copyCss() {
            const text = this.cssWithStyleTag();
            try {
                // HTTPS/localhost 등 보안 컨텍스트에서만 navigator.clipboard 사용 가능.
                // HTTP(비보안)에서는 undefined이므로 execCommand 폴백으로 처리.
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(text);
                } else {
                    this._fallbackCopy(text);
                }
                if (typeof showSuccessMessage === 'function') {
                    showSuccessMessage('CSS가 클립보드에 복사되었습니다.');
                }
            } catch (error) {
                // clipboard API 실패 시에도 폴백 재시도
                try {
                    this._fallbackCopy(text);
                    if (typeof showSuccessMessage === 'function') {
                        showSuccessMessage('CSS가 클립보드에 복사되었습니다.');
                    }
                } catch (e) {
                    console.error('복사 실패:', e);
                    if (typeof showErrorMessage === 'function') {
                        showErrorMessage('복사에 실패했습니다. CSS 코드를 직접 선택해 복사하세요.');
                    }
                }
            }
        },

        /**
         * execCommand('copy') 기반 클립보드 폴백 (비보안 컨텍스트/HTTP용).
         * @param {string} text - 복사할 텍스트
         */
        _fallbackCopy(text) {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.setAttribute('readonly', '');
            ta.style.position = 'fixed';
            ta.style.top = '-9999px';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            const ok = document.execCommand('copy');
            document.body.removeChild(ta);
            if (!ok) throw new Error('execCommand copy 실패');
        },

        /**
         * 프리셋 적용
         */
        applyPreset(presetName) {
            const presets = typeof STYLE_PRESETS !== 'undefined' ? STYLE_PRESETS : {};
            const preset = presets[presetName];
            if (preset) {
                this.styleConfig = {};
                this.initDefaultStyles();
                for (const [selector, styles] of Object.entries(preset)) {
                    this.styleConfig[selector] = { ...styles };
                }
                this.loadCurrentSelectorStyles();
                this.updatePreview();
                if (typeof showSuccessMessage === 'function') {
                    showSuccessMessage(`'${presetName}' 프리셋이 적용되었습니다.`);
                }
            }
        },

        /**
         * 데이터 로드 (스타일 + 치환자 설정)
         */
        async load() {
            this.loading = true;
            try {
                const [styleRes, placeholderRes] = await Promise.all([
                    fetch(`/api/v1/blogs/${this.blogId}/settings/style`),
                    fetch(`/api/v1/blogs/${this.blogId}/settings/placeholders`)
                ]);

                if (styleRes.ok) {
                    const data = await styleRes.json();
                    if (data.style_config) this.styleConfig = data.style_config;
                    // API 응답에 platform 있으면 사용 (소문자 정규화)
                    if (data.platform) this.platform = String(data.platform).toLowerCase();
                }

                // 항상 현재 블로그(부모 selectedBlog) 기준으로 platform 갱신.
                // (API에 platform이 없을 때 이전 블로그의 platform이 남아 다른 플랫폼으로
                //  오인되던 버그 방지 — 블로거인데 entry-content가 출력되는 문제)
                this.syncPlatformFromParent();

                if (placeholderRes.ok) {
                    const data = await placeholderRes.json();
                    if (data.placeholders) {
                        this.placeholderConfig = {
                            css_classes: data.placeholders.css_classes || {},
                            link_styles: data.placeholders.link_styles || {
                                default_class: '', button_class: 'button-link'
                            }
                        };
                    }
                }

                this.initDefaultStyles();
                this.loadCurrentSelectorStyles();
                this.updatePreview();
            } catch (error) {
                console.error('데이터 로드 실패:', error);
            } finally {
                this.loading = false;
            }
        },

        /**
         * 치환자 설정 다시 로드 (탭 전환 시 동기화용)
         */
        async reloadPlaceholders() {
            try {
                const response = await fetch(`/api/v1/blogs/${this.blogId}/settings/placeholders`);
                if (response.ok) {
                    const data = await response.json();
                    if (data.placeholders) {
                        this.placeholderConfig = {
                            css_classes: data.placeholders.css_classes || {},
                            link_styles: data.placeholders.link_styles || {
                                default_class: '', button_class: 'button-link'
                            }
                        };
                        this.updatePreview();
                    }
                }
            } catch (error) {
                console.error('치환자 설정 로드 실패:', error);
            }
        },

        /**
         * 저장
         */
        async save() {
            // 부모에서 최신 blogId 동기화
            const settingsEl = document.getElementById('blogSettings');
            if (settingsEl && settingsEl._x_dataStack && settingsEl._x_dataStack[0] && settingsEl._x_dataStack[0].selectedBlog) {
                this.blogId = settingsEl._x_dataStack[0].selectedBlog.id;
            }
            if (!this.blogId || this.blogId === 'null') {
                console.error('[styleTabApp] 저장 실패: 유효한 blog_id가 없습니다.');
                if (typeof showErrorMessage === 'function') {
                    showErrorMessage('블로그 ID를 찾을 수 없습니다. 페이지를 새로고침해주세요.');
                }
                return;
            }

            this.saving = true;
            try {
                const response = await fetch(`/api/v1/blogs/${this.blogId}/settings/style`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        style_config: this.styleConfig,
                        generated_css: this.generatedCss
                    })
                });

                if (response.ok) {
                    if (typeof showSuccessMessage === 'function') {
                        showSuccessMessage('스타일 설정이 저장되었습니다.');
                    }
                } else {
                    throw new Error('저장 실패');
                }
            } catch (error) {
                console.error('저장 실패:', error);
                if (typeof showErrorMessage === 'function') {
                    showErrorMessage('저장에 실패했습니다.');
                }
            } finally {
                this.saving = false;
            }
        }
    };

    // 테이블 전용 편집 믹스인 합성
    const tableMixin = typeof styleTabTableMixin === 'function' ? styleTabTableMixin() : {};
    Object.assign(base, tableMixin);

    // 테마 갤러리 + 버튼 디자인 믹스인 합성 (P3)
    const themesMixin = typeof styleTabThemesMixin === 'function' ? styleTabThemesMixin() : {};
    Object.assign(base, themesMixin);

    // 플랫폼별 CSS 접두 믹스인 합성 (P4)
    const platformMixin = typeof styleTabPlatformMixin === 'function' ? styleTabPlatformMixin() : {};
    Object.assign(base, platformMixin);

    // 편집기 보조 믹스인 합성 (B/C: 유형별 편집 + 클릭 편집)
    const editorMixin = typeof styleTabEditorMixin === 'function' ? styleTabEditorMixin() : {};
    Object.assign(base, editorMixin);

    // 외부 CSS 붙여넣기 추출 믹스인 합성
    const cssImportMixin = typeof styleTabCssImportMixin === 'function' ? styleTabCssImportMixin() : {};
    Object.assign(base, cssImportMixin);

    return base;
}
