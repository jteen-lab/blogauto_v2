/**
 * 스타일 탭 테마 갤러리 정의 (P3)
 * File: app/static/js/blogs/style-tab-themes.js
 * Last-Updated: 2026-06-24
 *
 * 완성형 디자인 프리셋 모음. 각 테마는 메인 색상(accentColor)을
 * styleConfig 내 강조 속성에 그대로 사용하여, 메인색 1개 변경으로
 * 전체 강조색을 일괄 치환할 수 있게 한다.
 *
 * 규칙:
 * - px 대상 속성(font-size, border-width, border-radius, margin, padding)은
 *   숫자 문자열로 둔다(생성기가 px 자동부여).
 * - 색상은 #hex 형식.
 * - accentColor 값은 강조 속성(h2.border-left-color, h3.color, a.color,
 *   a.button.background-color, a.button:hover.background-color,
 *   th.background-color, blockquote.border-left-color 등)에 실제로 그대로 사용.
 * - 버튼 시각 스타일은 'a.button' 키, hover는 'a.button:hover' 키에 저장.
 *   (생성기가 래퍼 .button-link 구조로 변환)
 */

/**
 * 테마 목록 (전역)
 * 각 테마: { id, name, accentColor, styleConfig }
 */
const STYLE_THEMES = [
    {
        id: 'pink-minimal',
        name: '핑크 미니멀',
        accentColor: '#ec4899',
        styleConfig: {
            'h1': { 'font-size': '28', 'font-weight': 'bold', 'margin-bottom': '16', 'color': '#1f2937' },
            'h2': {
                'font-size': '23', 'font-weight': '600', 'margin-top': '24', 'margin-bottom': '12',
                'color': '#1f2937', 'padding-left': '12',
                'border-left-style': 'solid', 'border-left-width': '4', 'border-left-color': '#ec4899'
            },
            'h3': { 'font-size': '19', 'font-weight': '600', 'margin-bottom': '10', 'color': '#ec4899' },
            'p': { 'font-size': '16', 'line-height': '1.8', 'margin-bottom': '14', 'color': '#374151' },
            'a': { 'color': '#ec4899', 'text-decoration': 'underline' },
            'a.button': {
                'color': '#ffffff', 'background-color': '#ec4899',
                'padding-top': '11', 'padding-bottom': '11', 'padding-left': '22', 'padding-right': '22',
                'border-radius': '8', 'font-weight': '600', 'text-align': 'center'
            },
            'a.button:hover': { 'background-color': '#ec4899', 'opacity': '0.85' },
            'li': { 'font-size': '16', 'line-height': '1.7', 'margin-bottom': '6', 'color': '#374151' },
            'table': { 'width': '100%', 'border-collapse': 'collapse', 'border-style': 'solid', 'border-width': '1', 'border-color': '#f3d3e4' },
            'th': {
                'background-color': '#ec4899', 'color': '#ffffff', 'font-weight': '600',
                'padding-top': '12', 'padding-bottom': '12', 'padding-left': '14', 'padding-right': '14'
            },
            'td': {
                'color': '#374151', 'padding-top': '10', 'padding-bottom': '10', 'padding-left': '14', 'padding-right': '14',
                'border-style': 'solid', 'border-width': '1', 'border-color': '#f3d3e4'
            },
            'blockquote': {
                'padding-top': '12', 'padding-bottom': '12', 'padding-left': '18',
                'background-color': '#fdf2f8', 'color': '#6b7280', 'font-style': 'italic',
                'border-left-style': 'solid', 'border-left-width': '4', 'border-left-color': '#ec4899'
            }
        }
    },
    {
        id: 'blue-modern',
        name: '블루 모던',
        accentColor: '#3b82f6',
        styleConfig: {
            'h1': { 'font-size': '32', 'font-weight': 'bold', 'margin-bottom': '20', 'color': '#0f172a' },
            'h2': {
                'font-size': '25', 'font-weight': 'bold', 'margin-top': '28', 'margin-bottom': '14',
                'color': '#1e293b', 'padding-left': '12',
                'border-left-style': 'solid', 'border-left-width': '5', 'border-left-color': '#3b82f6'
            },
            'h3': { 'font-size': '20', 'font-weight': '600', 'margin-bottom': '10', 'color': '#3b82f6' },
            'p': { 'font-size': '16', 'line-height': '1.8', 'margin-bottom': '16', 'color': '#475569' },
            'a': { 'color': '#3b82f6', 'font-weight': '500' },
            'a.button': {
                'color': '#ffffff', 'background-color': '#3b82f6',
                'padding-top': '12', 'padding-bottom': '12', 'padding-left': '24', 'padding-right': '24',
                'border-radius': '8', 'font-weight': '600', 'text-align': 'center'
            },
            'a.button:hover': { 'background-color': '#3b82f6', 'opacity': '0.85' },
            'li': { 'font-size': '16', 'line-height': '1.7', 'margin-bottom': '6', 'color': '#475569' },
            'table': { 'width': '100%', 'border-collapse': 'separate', 'border-radius': '8' },
            'th': {
                'background-color': '#3b82f6', 'color': '#ffffff', 'font-weight': '600',
                'padding-top': '12', 'padding-bottom': '12', 'padding-left': '16', 'padding-right': '16'
            },
            'td': {
                'color': '#475569', 'padding-top': '10', 'padding-bottom': '10', 'padding-left': '16', 'padding-right': '16',
                'border-bottom-style': 'solid', 'border-bottom-width': '1', 'border-bottom-color': '#e2e8f0'
            },
            'blockquote': {
                'padding-top': '14', 'padding-bottom': '14', 'padding-left': '20',
                'background-color': '#eff6ff', 'color': '#475569',
                'border-left-style': 'solid', 'border-left-width': '4', 'border-left-color': '#3b82f6', 'border-radius': '4'
            }
        }
    },
    {
        id: 'green-natural',
        name: '그린 내추럴',
        accentColor: '#16a34a',
        styleConfig: {
            'h1': { 'font-size': '29', 'font-weight': 'bold', 'margin-bottom': '18', 'color': '#14532d' },
            'h2': {
                'font-size': '23', 'font-weight': '600', 'margin-top': '26', 'margin-bottom': '12',
                'color': '#166534', 'padding-left': '12',
                'border-left-style': 'solid', 'border-left-width': '4', 'border-left-color': '#16a34a'
            },
            'h3': { 'font-size': '19', 'font-weight': '600', 'margin-bottom': '10', 'color': '#16a34a' },
            'p': { 'font-size': '16', 'line-height': '1.8', 'margin-bottom': '14', 'color': '#374151' },
            'a': { 'color': '#16a34a', 'text-decoration': 'underline' },
            'a.button': {
                'color': '#ffffff', 'background-color': '#16a34a',
                'padding-top': '11', 'padding-bottom': '11', 'padding-left': '22', 'padding-right': '22',
                'border-radius': '6', 'font-weight': '600', 'text-align': 'center'
            },
            'a.button:hover': { 'background-color': '#16a34a', 'opacity': '0.85' },
            'li': { 'font-size': '16', 'line-height': '1.7', 'margin-bottom': '6', 'color': '#374151' },
            'table': { 'width': '100%', 'border-collapse': 'collapse', 'border-style': 'solid', 'border-width': '1', 'border-color': '#d1e7d8' },
            'th': {
                'background-color': '#16a34a', 'color': '#ffffff', 'font-weight': '600',
                'padding-top': '12', 'padding-bottom': '12', 'padding-left': '14', 'padding-right': '14'
            },
            'td': {
                'color': '#374151', 'padding-top': '10', 'padding-bottom': '10', 'padding-left': '14', 'padding-right': '14',
                'border-style': 'solid', 'border-width': '1', 'border-color': '#d1e7d8'
            },
            'blockquote': {
                'padding-top': '12', 'padding-bottom': '12', 'padding-left': '18',
                'background-color': '#f0fdf4', 'color': '#4b5563', 'font-style': 'italic',
                'border-left-style': 'solid', 'border-left-width': '4', 'border-left-color': '#16a34a'
            }
        }
    },
    {
        id: 'gray-classic',
        name: '그레이 클래식',
        accentColor: '#475569',
        styleConfig: {
            'h1': { 'font-size': '28', 'font-weight': 'bold', 'margin-bottom': '16', 'color': '#111827' },
            'h2': {
                'font-size': '23', 'font-weight': 'bold', 'margin-top': '24', 'margin-bottom': '12',
                'color': '#1f2937', 'padding-bottom': '6',
                'border-bottom-style': 'solid', 'border-bottom-width': '2', 'border-bottom-color': '#475569'
            },
            'h3': { 'font-size': '19', 'font-weight': '600', 'margin-bottom': '10', 'color': '#475569' },
            'p': { 'font-size': '16', 'line-height': '1.75', 'margin-bottom': '14', 'color': '#374151' },
            'a': { 'color': '#475569', 'text-decoration': 'underline' },
            'a.button': {
                'color': '#ffffff', 'background-color': '#475569',
                'padding-top': '11', 'padding-bottom': '11', 'padding-left': '22', 'padding-right': '22',
                'border-radius': '4', 'font-weight': '600', 'text-align': 'center'
            },
            'a.button:hover': { 'background-color': '#475569', 'opacity': '0.85' },
            'li': { 'font-size': '16', 'line-height': '1.7', 'margin-bottom': '6', 'color': '#374151' },
            'table': { 'width': '100%', 'border-collapse': 'collapse', 'border-style': 'solid', 'border-width': '2', 'border-color': '#475569' },
            'th': {
                'background-color': '#475569', 'color': '#ffffff', 'font-weight': '600',
                'padding-top': '12', 'padding-bottom': '12', 'padding-left': '14', 'padding-right': '14'
            },
            'td': {
                'color': '#1f2937', 'padding-top': '10', 'padding-bottom': '10', 'padding-left': '14', 'padding-right': '14',
                'border-style': 'solid', 'border-width': '1', 'border-color': '#cbd5e1'
            },
            'blockquote': {
                'padding-top': '12', 'padding-bottom': '12', 'padding-left': '18',
                'background-color': '#f8fafc', 'color': '#6b7280', 'font-style': 'italic',
                'border-left-style': 'solid', 'border-left-width': '4', 'border-left-color': '#475569'
            }
        }
    }
];

/**
 * 테마 갤러리 + 버튼 디자인(쉬운 설정) 메서드 믹스인
 * styleTabApp()에서 Object.assign()으로 합성하여 사용.
 * @returns {Object} Alpine.js 컴포넌트에 합성할 메서드 객체
 */
function styleTabThemesMixin() {
    return {
        /* ========== P3-A: 테마 갤러리 ========== */

        /**
         * 객체 깊은 복사 (테마 styleConfig 복제용)
         * @param {Object} obj - 복사할 객체
         * @returns {Object} 깊은 복사본
         */
        _deepCopyConfig(obj) {
            return JSON.parse(JSON.stringify(obj || {}));
        },

        /**
         * 테마 id로 테마 객체 조회
         * @param {string} themeId - 테마 id
         * @returns {Object|null}
         */
        _findTheme(themeId) {
            return this.themes.find(t => t.id === themeId) || null;
        },

        /**
         * 테마 적용: 해당 테마 styleConfig를 통째로 적용(기존 덮어씀)
         * @param {string} themeId - 테마 id
         */
        applyTheme(themeId) {
            const theme = this._findTheme(themeId);
            if (!theme) return;
            // 깊은 복사로 적용 (원본 테마 변형 방지)
            this.styleConfig = this._deepCopyConfig(theme.styleConfig);
            this.appliedThemeId = themeId;
            this.mainColor = theme.accentColor;
            this.initDefaultStyles();
            this.loadCurrentSelectorStyles();
            this.updatePreview();
            if (typeof showSuccessMessage === 'function') {
                showSuccessMessage(`'${theme.name}' 테마가 적용되었습니다.`);
            }
        },

        /**
         * 메인 색상 일괄 변경: 원본 테마의 accentColor와 같은 값인
         * 모든 속성을 새 color로 치환
         * @param {string} color - 새 메인 색상 (#hex)
         */
        recolorMain(color) {
            if (!this.appliedThemeId || !color) return;
            const theme = this._findTheme(this.appliedThemeId);
            if (!theme) return;
            const oldColor = theme.accentColor.toLowerCase();
            // 원본 테마 기준으로 다시 생성 (반복 치환 누적 방지)
            const next = this._deepCopyConfig(theme.styleConfig);
            for (const selector of Object.keys(next)) {
                const props = next[selector];
                for (const prop of Object.keys(props)) {
                    if (String(props[prop]).toLowerCase() === oldColor) {
                        props[prop] = color;
                    }
                }
            }
            this.styleConfig = next;
            this.mainColor = color;
            this.initDefaultStyles();
            this.loadCurrentSelectorStyles();
            this.updatePreview();
        },

        /* ========== P3-B: 버튼 디자인(쉬운 설정) ========== */

        /**
         * 버튼 스타일 값 조회
         * @param {string} prop - CSS 속성명
         * @param {boolean} hover - true면 a.button:hover 키 조회
         * @returns {string} 속성 값 (없으면 '')
         */
        getButtonStyle(prop, hover = false) {
            const key = hover ? 'a.button:hover' : 'a.button';
            const config = this.styleConfig[key] || {};
            return config[prop] || '';
        },

        /**
         * 버튼 스타일 값 설정 (빈 값이면 제거)
         * @param {string} prop - CSS 속성명
         * @param {string} value - 설정할 값
         * @param {boolean} hover - true면 a.button:hover 키에 설정
         */
        setButtonOption(prop, value, hover = false) {
            const key = hover ? 'a.button:hover' : 'a.button';
            if (!this.styleConfig[key]) this.styleConfig[key] = {};
            if (value !== '' && value !== null && value !== undefined) {
                this.styleConfig[key][prop] = value;
            } else {
                delete this.styleConfig[key][prop];
            }
            // 현재 활성 선택자가 버튼 키면 편집 폼도 동기화
            if (this.activeSelector === key) this.loadCurrentSelectorStyles();
            this.debounceUpdatePreview();
        },

        /**
         * 버튼 전체폭 토글
         * on: a.button에 width/display/box-sizing/text-align 추가
         * off: 위 4개 속성 제거
         * @param {boolean} enabled - 전체폭 여부
         */
        setButtonFullWidth(enabled) {
            const key = 'a.button';
            if (!this.styleConfig[key]) this.styleConfig[key] = {};
            const config = this.styleConfig[key];
            if (enabled) {
                config['width'] = '100%';
                config['display'] = 'inline-block';
                config['box-sizing'] = 'border-box';
                config['text-align'] = 'center';
            } else {
                delete config['width'];
                delete config['display'];
                delete config['box-sizing'];
                delete config['text-align'];
            }
            if (this.activeSelector === key) this.loadCurrentSelectorStyles();
            this.debounceUpdatePreview();
        },

        /**
         * 버튼 전체폭 활성 여부 (UI 체크박스 바인딩용)
         * @returns {boolean}
         */
        isButtonFullWidth() {
            return (this.styleConfig['a.button'] || {})['width'] === '100%';
        }
    };
}
