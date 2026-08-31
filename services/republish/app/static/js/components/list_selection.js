/**
 * 목록 표 선택 상태 — 블로그·모듈이 같은 로직을 쓴다.
 *
 * 선택은 **탭마다 독립**이다. 프롬프트 탭에서 전체선택해도 수집 탭은
 * 그대로여야 한다. 그래서 table_id 를 범위(scope)로 삼아 배열을 따로 둔다.
 *
 * 화면은 이 객체를 Alpine 컴포넌트에 펼쳐 넣는다:
 *     return { ...listSelectionMixin(), ... }
 */
function listSelectionMixin() {
    return {
        // {scope: [id, …]}
        listSelection: {},

        /** 해당 범위의 선택 배열(없으면 만들어 준다) */
        listSelected(scope) {
            if (!this.listSelection[scope]) this.listSelection[scope] = [];
            return this.listSelection[scope];
        },

        listSelectedCount(scope) {
            return (this.listSelection[scope] || []).length;
        },

        /** 개별 행이 선택됐는지 — 렌더 중에 호출되므로 상태를 바꾸지 않는다 */
        listIsSelected(scope, id) {
            return (this.listSelection[scope] || []).includes(id);
        },

        /** 개별 행 선택 토글.
         *  x-model 을 쓰지 않는 이유: 아직 만들어지지 않은 범위 키에
         *  x-model 을 걸면 Alpine 이 배열이 아닌 불리언으로 다뤄 선택이 깨진다. */
        listToggleOne(scope, id) {
            const sel = this.listSelected(scope);
            const at = sel.indexOf(id);
            if (at === -1) sel.push(id);
            else sel.splice(at, 1);
            // 배열을 새로 대입해야 Alpine 이 변경을 감지한다.
            this.listSelection[scope] = [...sel];
        },

        /** 머리글 체크 상태 — 보이는 항목이 모두 선택됐을 때만 켜진다 */
        listAllChecked(scope, rows) {
            const list = rows || [];
            if (!list.length) return false;
            const sel = this.listSelection[scope] || [];
            return list.every(r => sel.includes(r.id));
        },

        /** 전체 선택/해제. 검색으로 걸러진 '보이는 것'만 대상으로 한다 —
         *  화면에 없는 항목이 선택되면 사용자가 모르는 것을 지우게 된다. */
        listToggleAll(scope, rows) {
            const list = rows || [];
            const ids = list.map(r => r.id);
            this.listSelection[scope] =
                this.listAllChecked(scope, list) ? [] : ids;
        },

        listClearSelection(scope) {
            this.listSelection[scope] = [];
        },

        /** 선택된 항목 객체들 */
        listSelectedRows(scope, rows) {
            const sel = this.listSelection[scope] || [];
            return (rows || []).filter(r => sel.includes(r.id));
        },
    };
}
