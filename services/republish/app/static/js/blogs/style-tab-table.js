/**
 * 스타일 탭 테이블 전용 편집 모드 믹스인
 * File: app/static/js/blogs/style-tab-table.js
 * Last-Updated: 2026-04-23
 *
 * styleTabApp()에서 Object.assign()으로 합성하여 사용.
 * 의존성: style-tab-presets.js (TABLE_PRESETS, HIDDEN_SELECTORS)
 */

/**
 * 테이블 편집 모드 메서드 믹스인
 * @returns {Object} Alpine.js 컴포넌트에 합성할 메서드 객체
 */
function styleTabTableMixin() {
    return {
        /**
         * 테이블 편집 모드 진입
         */
        enterTableMode() {
            this.tableMode = true;
            this.syncTableConfigFromStyleConfig();
        },

        /**
         * 테이블 편집 모드 해제
         */
        exitTableMode() {
            this.tableMode = false;
        },

        /**
         * 테이블 프리셋 적용
         * @param {string} presetName - 프리셋 이름
         */
        applyTablePreset(presetName) {
            const preset = TABLE_PRESETS[presetName];
            if (!preset) return;
            // 기존 테이블 관련 선택자 초기화
            for (const sel of ['table', 'th', 'td']) {
                this.styleConfig[sel] = {};
            }
            // 프리셋 값 적용
            if (preset.table) this.styleConfig['table'] = { ...preset.table };
            if (preset.th) this.styleConfig['th'] = { ...preset.th };
            if (preset.td) this.styleConfig['td'] = { ...preset.td };
            // Zebra 설정
            if (preset.zebra) {
                this.styleConfig['tr:nth-child(even)'] = { 'background-color': preset.zebra.even };
                this.styleConfig['tr:nth-child(odd)'] = { 'background-color': preset.zebra.odd };
            } else {
                delete this.styleConfig['tr:nth-child(even)'];
                delete this.styleConfig['tr:nth-child(odd)'];
            }
            this.syncTableConfigFromStyleConfig();
            this.debounceUpdatePreview();
        },

        /**
         * tableConfig -> styleConfig 동기화 (테이블 UI 변경 시)
         */
        syncStyleConfigFromTable() {
            // table 선택자
            const tbl = {};
            tbl['width'] = this.tableConfig.tableWidth === 'custom'
                ? (this.tableConfig.tableWidthCustom || '100%')
                : this.tableConfig.tableWidth;
            tbl['border-collapse'] = this.tableConfig.borderCollapse;
            if (this.tableConfig.borderCollapse === 'separate' && this.tableConfig.borderSpacing !== '0') {
                tbl['border-spacing'] = this.tableConfig.borderSpacing;
            }
            Object.assign(tbl, this._buildTableBorder());
            this.styleConfig['table'] = tbl;

            // th 선택자
            const th = {};
            if (this.tableConfig.thBgColor) th['background-color'] = this.tableConfig.thBgColor;
            if (this.tableConfig.thTextColor) th['color'] = this.tableConfig.thTextColor;
            th['font-weight'] = this.tableConfig.thFontWeight;
            th['padding-top'] = String(this.tableConfig.thPadding);
            th['padding-right'] = String(this.tableConfig.thPadding + 2);
            th['padding-bottom'] = String(this.tableConfig.thPadding);
            th['padding-left'] = String(this.tableConfig.thPadding + 2);
            Object.assign(th, this._buildCellBorder('th'));
            this.styleConfig['th'] = th;

            // td 선택자
            const td = {};
            if (this.tableConfig.tdBgColor) td['background-color'] = this.tableConfig.tdBgColor;
            if (this.tableConfig.tdTextColor) td['color'] = this.tableConfig.tdTextColor;
            td['padding-top'] = String(this.tableConfig.tdPadding);
            td['padding-right'] = String(this.tableConfig.tdPadding + 2);
            td['padding-bottom'] = String(this.tableConfig.tdPadding);
            td['padding-left'] = String(this.tableConfig.tdPadding + 2);
            Object.assign(td, this._buildCellBorder('td'));
            this.styleConfig['td'] = td;

            // Zebra Striping
            if (this.tableConfig.zebraEnabled) {
                this.styleConfig['tr:nth-child(even)'] = { 'background-color': this.tableConfig.zebraEvenColor };
                this.styleConfig['tr:nth-child(odd)'] = { 'background-color': this.tableConfig.zebraOddColor };
            } else {
                delete this.styleConfig['tr:nth-child(even)'];
                delete this.styleConfig['tr:nth-child(odd)'];
            }

            this.debounceUpdatePreview();
        },

        /**
         * styleConfig -> tableConfig 역동기화 (테이블 모드 진입 시)
         */
        syncTableConfigFromStyleConfig() {
            const tbl = this.styleConfig['table'] || {};
            const th = this.styleConfig['th'] || {};
            const td = this.styleConfig['td'] || {};
            const even = this.styleConfig['tr:nth-child(even)'] || {};

            // 테이블 레이아웃
            this.tableConfig.tableWidth = tbl['width'] || '100%';
            if (!['auto', '100%'].includes(this.tableConfig.tableWidth)) {
                this.tableConfig.tableWidthCustom = this.tableConfig.tableWidth;
                this.tableConfig.tableWidth = 'custom';
            }
            this.tableConfig.borderCollapse = tbl['border-collapse'] || 'collapse';
            this.tableConfig.borderSpacing = tbl['border-spacing'] || '0';

            // 테두리
            this.tableConfig.borderColor = tbl['border-color'] || th['border-color'] || '#e5e7eb';
            this.tableConfig.borderWidth = parseInt(tbl['border-width'] || '1');
            this.tableConfig.borderStyle = tbl['border-style'] || 'solid';
            this.tableConfig.borderPreset = this._detectBorderPreset();

            // 헤더 (th)
            this.tableConfig.thBgColor = th['background-color'] || '';
            this.tableConfig.thTextColor = th['color'] || '#1f2937';
            this.tableConfig.thFontWeight = th['font-weight'] || '600';
            this.tableConfig.thPadding = parseInt(th['padding-top'] || '10');

            // 데이터 셀 (td)
            this.tableConfig.tdBgColor = td['background-color'] || '';
            this.tableConfig.tdTextColor = td['color'] || '#374151';
            this.tableConfig.tdPadding = parseInt(td['padding-top'] || '8');

            // Zebra
            this.tableConfig.zebraEnabled = Object.keys(even).length > 0;
            this.tableConfig.zebraEvenColor = even['background-color'] || '#f9fafb';
            this.tableConfig.zebraOddColor = (this.styleConfig['tr:nth-child(odd)'] || {})['background-color'] || '#ffffff';
        },

        /**
         * 테두리 프리셋에 따른 table 선택자 border 속성 생성
         * @returns {Object} CSS 속성 객체
         */
        _buildTableBorder() {
            const p = this.tableConfig.borderPreset;
            const c = this.tableConfig.borderColor;
            const w = String(this.tableConfig.borderWidth);
            const s = this.tableConfig.borderStyle;
            if (p === 'none') return { 'border-style': 'none' };
            if (p === 'outline') return { 'border-style': s, 'border-width': w, 'border-color': c };
            if (p === 'all') return { 'border-style': s, 'border-width': w, 'border-color': c };
            return {};
        },

        /**
         * 테두리 프리셋에 따른 셀(th/td) border 속성 생성
         * @param {string} sel - 선택자 ('th' 또는 'td')
         * @returns {Object} CSS 속성 객체
         */
        _buildCellBorder(sel) {
            const p = this.tableConfig.borderPreset;
            const c = this.tableConfig.borderColor;
            const w = String(this.tableConfig.borderWidth);
            const s = this.tableConfig.borderStyle;
            if (p === 'none' || p === 'outline') return { 'border-style': 'none' };
            if (p === 'all') return { 'border-style': s, 'border-width': w, 'border-color': c };
            if (p === 'horizontal') {
                return {
                    'border-top-style': s, 'border-top-width': w, 'border-top-color': c,
                    'border-bottom-style': s, 'border-bottom-width': w, 'border-bottom-color': c
                };
            }
            if (p === 'vertical') {
                return {
                    'border-left-style': s, 'border-left-width': w, 'border-left-color': c,
                    'border-right-style': s, 'border-right-width': w, 'border-right-color': c
                };
            }
            return {};
        },

        /**
         * 현재 styleConfig에서 테두리 프리셋 역추론
         * @returns {string} 테두리 프리셋 이름
         */
        _detectBorderPreset() {
            const tbl = this.styleConfig['table'] || {};
            const th = this.styleConfig['th'] || {};
            if (tbl['border-style'] === 'none' || (!tbl['border-style'] && !th['border-style'])) return 'none';
            if (tbl['border-style'] && th['border-style'] === 'none') return 'outline';
            if (th['border-bottom-style'] && !th['border-left-style']) return 'horizontal';
            if (th['border-left-style'] && !th['border-top-style']) return 'vertical';
            if (tbl['border-style'] || th['border-style']) return 'all';
            return 'custom';
        },

        /**
         * 테이블 설정 변경 핸들러 (UI 컨트롤 변경 시 호출)
         */
        onTableConfigChange() {
            this.syncStyleConfigFromTable();
        }
    };
}
