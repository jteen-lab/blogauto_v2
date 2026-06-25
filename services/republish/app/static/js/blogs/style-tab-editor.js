/**
 * 스타일 탭 편집기 보조 믹스인 (B/C: 유형별 맞춤 편집 + 미리보기 클릭 편집)
 * File: app/static/js/blogs/style-tab-editor.js
 * Last-Updated: 2026-06-25
 *
 * styleTabApp()에서 Object.assign()으로 합성하여 사용.
 * 목적:
 * - 선택자 유형 판별(editorKindFor)로 관련 컨트롤만 노출
 * - 미리보기에서 클릭한 요소의 선택자를 활성화(setActiveSelectorFromPreview)
 */

/**
 * 편집기 보조 메서드 믹스인
 * @returns {Object} Alpine.js 컴포넌트에 합성할 메서드 객체
 */
function styleTabEditorMixin() {
    return {
        /**
         * 선택자 유형 판별 (B: 유형별 맞춤 편집 UI)
         * 선택자에 맞는 컨트롤만 노출하기 위한 분류.
         * @param {string} selector - 선택자 (h1, p, a, a.button, table 등)
         * @returns {string} 유형: 'heading'|'text'|'link'|'button'|'table'|'list'|'quote'|'generic'
         */
        editorKindFor(selector) {
            const sel = selector || this.activeSelector || '';
            if (/^h[1-6]$/.test(sel)) return 'heading';
            if (sel === 'p') return 'text';
            if (sel === 'a.button' || sel === 'a.button:hover') return 'button';
            if (sel === 'a' || sel === 'a:hover') return 'link';
            if (sel === 'table' || sel === 'th' || sel === 'td') return 'table';
            if (sel === 'ul' || sel === 'ol' || sel === 'li') return 'list';
            if (sel === 'blockquote') return 'quote';
            return 'generic';
        },

        /**
         * 현재 활성 선택자의 유형 반환 (UI x-show 바인딩용 단축)
         * @returns {string}
         */
        activeKind() {
            return this.editorKindFor(this.activeSelector);
        },

        /**
         * hover 선택자 여부 (link/button hover 추가 컨트롤 노출용)
         * @returns {boolean}
         */
        isHoverSelector() {
            return this.activeSelector === 'a:hover' || this.activeSelector === 'a.button:hover';
        },

        /**
         * 미리보기 클릭으로 전달된 선택자를 활성화 (C)
         * selectors 목록에 있을 때만 적용. 버튼/표는 테이블모드 해제 후 편집.
         * @param {string} sel - 미리보기에서 판별된 선택자
         */
        setActiveSelectorFromPreview(sel) {
            if (!sel || !this.selectors.includes(sel)) return;
            this.tableMode = false;
            this.activeSelector = sel;
            this.loadCurrentSelectorStyles();
            // 편집 영역으로 스크롤 (있을 때만)
            this.$nextTick(() => {
                const el = document.getElementById('styleEditorPanel');
                if (el && typeof el.scrollIntoView === 'function') {
                    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            });
        }
    };
}
