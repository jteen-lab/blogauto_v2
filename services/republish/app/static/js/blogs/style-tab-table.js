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
            // 캔버스 레이아웃: 표 편집 진입 시 플로팅 편집 카드 열기
            this.editorOpen = true;
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
            // 둥근 모서리 활성 여부 (>0)
            const radius = parseInt(this.tableConfig.borderRadius || 0);
            const roundEnabled = radius > 0;

            // table 선택자
            const tbl = {};
            tbl['width'] = this.tableConfig.tableWidth === 'custom'
                ? (this.tableConfig.tableWidthCustom || '100%')
                : this.tableConfig.tableWidth;
            if (roundEnabled) {
                // 둥근 표는 border-collapse:separate + overflow:hidden + radius 필요
                tbl['border-collapse'] = 'separate';
                tbl['border-spacing'] = '0';
                tbl['overflow'] = 'hidden';
                tbl['border-radius'] = String(radius);
            } else {
                tbl['border-collapse'] = this.tableConfig.borderCollapse;
                if (this.tableConfig.borderCollapse === 'separate' && this.tableConfig.borderSpacing !== '0') {
                    tbl['border-spacing'] = this.tableConfig.borderSpacing;
                }
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

            // 표 고급 (둥근 모서리 중복선 제거 + 첫 열 너비)
            this._applyTableAdvanced(roundEnabled);

            this.debounceUpdatePreview();
        },

        /**
         * 표 고급 의사선택자 규칙 적용/제거 (P4)
         * - 둥근 모서리: 마지막 열/행 중복선 제거를 위해 border-right/border-bottom 0
         * - 첫 열 너비: th/td:first-child width
         * @param {boolean} roundEnabled - 둥근 모서리 활성 여부
         */
        _applyTableAdvanced(roundEnabled) {
            // 둥근 표 중복선 제거 규칙
            if (roundEnabled) {
                this.styleConfig['tr th:last-child'] = { 'border-right': '0' };
                this.styleConfig['tr td:last-child'] = { 'border-right': '0' };
                this.styleConfig['tr:last-child td'] = { 'border-bottom': '0' };
                this.styleConfig['tr:last-child th'] = { 'border-bottom': '0' };
            } else {
                delete this.styleConfig['tr th:last-child'];
                delete this.styleConfig['tr td:last-child'];
                delete this.styleConfig['tr:last-child td'];
                delete this.styleConfig['tr:last-child th'];
            }

            // 첫 열 너비
            const fcw = (this.tableConfig.firstColWidth || '').trim();
            if (fcw) {
                this.styleConfig['th:first-child'] = { 'width': fcw };
                this.styleConfig['td:first-child'] = { 'width': fcw };
            } else {
                delete this.styleConfig['th:first-child'];
                delete this.styleConfig['td:first-child'];
            }
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

            // 테두리 — 외곽선/가로선/세로선 3그룹 역동기화 (각 독립)
            this._syncBorderGroupsFromStyleConfig(tbl, td);

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

            // 표 고급 (P4) - 둥근 모서리 / 첫 열 너비 역동기화
            this.tableConfig.borderRadius = parseInt(tbl['border-radius'] || '0');
            this.tableConfig.firstColWidth = (this.styleConfig['th:first-child'] || {})['width'] || '';
        },

        /**
         * 외곽선(outline) 그룹 → table 선택자 border 속성 생성
         * outline.on이면 표 바깥 외곽선 적용, off면 테두리 없음(border-style:none).
         * @returns {Object} CSS 속성 객체
         */
        _buildTableBorder() {
            const o = this.tableConfig.outline || {};
            if (!o.on) return { 'border-style': 'none' };
            return {
                'border-style': o.style,
                'border-width': String(o.width),
                'border-color': o.color
            };
        },

        /**
         * 가로선(hline)/세로선(vline) 그룹 → 셀(th/td) border 속성 생성
         * hline.on → border-bottom-*(가로선), vline.on → border-left/right-*(세로선).
         * 각 그룹은 자기 색/두께/종류만 사용(독립). 둘 다 off면 빈 객체.
         * @param {string} sel - 선택자 ('th' 또는 'td')
         * @returns {Object} CSS 속성 객체
         */
        _buildCellBorder(sel) {
            const props = {};
            const h = this.tableConfig.hline || {};
            const v = this.tableConfig.vline || {};
            // 가로선: 셀 아래 테두리
            if (h.on) {
                props['border-bottom-style'] = h.style;
                props['border-bottom-width'] = String(h.width);
                props['border-bottom-color'] = h.color;
            }
            // 세로선: 셀 좌/우 테두리
            if (v.on) {
                props['border-left-style'] = v.style;
                props['border-left-width'] = String(v.width);
                props['border-left-color'] = v.color;
                props['border-right-style'] = v.style;
                props['border-right-width'] = String(v.width);
                props['border-right-color'] = v.color;
            }
            return props;
        },

        /**
         * styleConfig → 테두리 3그룹(outline/hline/vline) 역동기화
         * - outline: table 선택자의 border-* (외곽선)
         * - hline: td 선택자의 border-bottom-* (가로선)
         * - vline: td 선택자의 border-left-* (세로선)
         * 각 그룹 감지 안 되면 on:false로 둠.
         * @param {Object} tbl - styleConfig['table']
         * @param {Object} td - styleConfig['td']
         */
        _syncBorderGroupsFromStyleConfig(tbl, td) {
            // 외곽선 (table border)
            const outOn = !!tbl['border-style'] && tbl['border-style'] !== 'none';
            this.tableConfig.outline = {
                on: outOn,
                color: tbl['border-color'] || '#e5e7eb',
                width: parseInt(tbl['border-width'] || '1'),
                style: outOn ? (tbl['border-style'] || 'solid') : 'solid'
            };
            // 가로선 (td border-bottom)
            const hOn = !!td['border-bottom-style'] && td['border-bottom-style'] !== 'none';
            this.tableConfig.hline = {
                on: hOn,
                color: td['border-bottom-color'] || '#e5e7eb',
                width: parseInt(td['border-bottom-width'] || '1'),
                style: hOn ? (td['border-bottom-style'] || 'solid') : 'solid'
            };
            // 세로선 (td border-left)
            const vOn = !!td['border-left-style'] && td['border-left-style'] !== 'none';
            this.tableConfig.vline = {
                on: vOn,
                color: td['border-left-color'] || '#e5e7eb',
                width: parseInt(td['border-left-width'] || '1'),
                style: vOn ? (td['border-left-style'] || 'solid') : 'solid'
            };
        },

        /**
         * 테이블 설정 변경 핸들러 (UI 컨트롤 변경 시 호출)
         */
        onTableConfigChange() {
            this.syncStyleConfigFromTable();
        }
    };
}
