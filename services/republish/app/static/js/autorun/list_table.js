/**
 * 오토런 목록 표 어댑터.
 *
 * 다른 화면과 결정적으로 다른 점: **오토런은 이미 선택 기능이 있다.**
 * selectedIds 를 상단 바의 전체/일시정지/재개/제외 버튼이 함께 읽는다.
 * 그래서 listSelectionMixin() 을 쓰지 않는다 — 선택 저장소가 둘이 되면
 * 표에서 고른 것과 버튼이 동작하는 대상이 갈라진다.
 *
 * 대신 공용 표가 요구하는 선택 함수를 selectedIds 위에 그대로 구현한다.
 * id 가 화면 전체에서 유일하므로 배열 하나로도 탭별 동작이 성립한다:
 * 전체선택은 "그 탭에 보이는 행" 만 넣고 뺀다.
 *
 * 주의: 여기의 값은 전개(spread)되므로 getter 를 두면 안 된다 —
 * {...obj} 는 getter 를 그 시점 값으로 굳혀 버린다. 전부 메서드로 둔다.
 *
 * 순서도: docs/flowcharts/autorun_list_table.md
 */
function autorunListTableMixin() {
    return {
        // 현재 탭. 상단 바(전체 선택·일괄 동작)도 이 값을 봐야 하므로
        // 중첩 x-data 가 아니라 앱 상태로 둔다.
        autorunTab: 'wordpress',
        autorunSearch: '',

        listSortKey: 'name',
        listSortDir: 'asc',

        // ── 탭 ────────────────────────────────────────────────
        autorunTabOf(flow) {
            return platformTabOf(
                (flow.blog_links || []).map(link => link.blog?.platform)
            );
        },

        getAutorunByTab(tab) {
            return (this.autorunFlows || []).filter(f => this.autorunTabOf(f) === tab);
        },

        /** 탭 + 검색 + 정렬을 거친 목록. 화면에 실제로 보이는 행이다. */
        visibleAutorun(tab) {
            const q = (this.autorunSearch || '').trim().toLowerCase();
            const rows = this.getAutorunByTab(tab).filter(f => {
                if (!q) return true;
                return (f.name || '').toLowerCase().includes(q)
                    || (f.description || '').toLowerCase().includes(q)
                    || this.autorunModuleNames(f).toLowerCase().includes(q)
                    || this.autorunBlogNames(f).toLowerCase().includes(q);
            });
            const dir = this.listSortDir === 'asc' ? 1 : -1;
            return [...rows].sort((a, b) => {
                const va = this.autorunSortValue(a, this.listSortKey);
                const vb = this.autorunSortValue(b, this.listSortKey);
                if (va === vb) return 0;
                return va > vb ? dir : -dir;
            });
        },

        // ── 셀 값 ─────────────────────────────────────────────
        /**
         * 카드는 실행중이 아니면 전부 🟡 로 뭉뚱그렸다. 오토런 목록에는
         * status='inactive' 인 플로우도 섞여 있어(상단 바의 🟢·🟡 합이
         * 총 개수보다 작은 이유가 이것이다) 일시정지와 구분해 보여준다.
         * 상태가 정렬 가능한 열이 된 이상 뭉뚱그리면 오해를 키운다.
         */
        autorunStatusText(flow) {
            if (flow.status === 'active') return '🟢 실행중';
            if (flow.auto_paused) return '🔴 자동정지';
            if (flow.status === 'paused') return '🟡 일시정지';
            return '⚪ 비활성';
        },

        autorunStatusIcon(flow) {
            return this.autorunStatusText(flow).slice(0, 2).trim();
        },

        /** 모듈 아이콘 + 이름. 검색·모바일 요약에 쓴다. */
        autorunModuleNames(flow) {
            const links = flow.module_links || [];
            if (!links.length) return '-';
            return links
                .map(link => {
                    const m = link.module || {};
                    const code = m.module_type?.code || 'republish';
                    return `${getModuleIcon(code)} ${m.name || ''}`.trim();
                })
                .join(' · ');
        },

        /**
         * 모듈 아이콘 + 이름 + 설정값. 카드가 흘려 보여주던 내용이다.
         * 이름만 남기면 카드가 전달하던 정보가 통째로 사라진다.
         */
        autorunModuleDetail(flow) {
            const links = flow.module_links || [];
            if (!links.length) return '연결된 모듈이 없습니다';
            return links
                .map(link => {
                    const m = link.module || {};
                    const code = m.module_type?.code || 'republish';
                    const head = `${getModuleIcon(code)} ${m.name || ''}`.trim();
                    let items = [];
                    try {
                        items = (getModuleInfoItems(m) || [])
                            .filter(i => i && i.value)
                            .map(i => `${i.label} ${i.value}`);
                    } catch (e) { items = []; }
                    return items.length ? `${head} — ${items.join(' · ')}` : head;
                })
                .join('   ◆   ');
        },

        autorunBlogNames(flow) {
            const links = flow.blog_links || [];
            if (!links.length) return '-';
            return links
                .map(link => {
                    const b = link.blog || {};
                    return `${b.platform === 'wordpress' ? 'WP' : 'BL'} ${b.name || ''}`.trim();
                })
                .join(' · ');
        },

        autorunNextText(flow) {
            if (flow.status !== 'active' || !flow.next_execution) return '-';
            return formatTime(flow.next_execution);
        },

        // ── 공용 표 규약 ──────────────────────────────────────
        listColumns() {
            return [
                { key: 'name',    label: '이름',   width: '22%', strong: true, sortable: true },
                { key: 'status',  label: '상태',   width: '12%', sortable: true },
                { key: 'next',    label: '다음 실행', width: '13%', sortable: true },
                { key: 'modules', label: '모듈',   width: '23%', slide: true },
                { key: 'blogs',   label: '블로그', width: '15%' },
                { key: '_badges', label: '알림',   width: '15%' },
            ];
        },

        listCell(flow, key) {
            switch (key) {
                case 'name': return flow.name || '';
                case 'status': return this.autorunStatusText(flow);
                case 'next': return this.autorunNextText(flow);
                case 'modules': return this.autorunModuleDetail(flow);
                case 'blogs': return this.autorunBlogNames(flow);
                default: return '';
            }
        },

        /** 카드가 본문에 크게 띄우던 경고들. 놓치면 안 되는 정보다. */
        listBadges(flow) {
            const badges = [];
            const blocked = flow.generation_blocked || [];
            if (blocked.length) {
                badges.push({
                    label: '생성 정지',
                    cls: 'bg-orange-50 text-orange-700 border border-orange-200',
                    tip: blocked.map(b => b.module_name).join(', ')
                         + ' — 승인용 프리셋을 찾을 수 없음',
                });
            }
            if (flow.status === 'paused' && flow.auto_paused) {
                const actions = flow.paused_actions || [];
                badges.push({
                    label: `연속 실패 ${flow.consecutive_failures || 0}회`,
                    cls: 'bg-red-50 text-red-700 border border-red-200',
                    tip: actions.length ? `자동 일시정지 (${actions.join(', ')})` : '자동 일시정지',
                });
            }
            if (!(flow.module_links || []).length) {
                badges.push({
                    label: '모듈 없음',
                    cls: 'bg-amber-50 text-amber-700 border border-amber-200',
                    tip: '연결된 모듈이 없어 실행되지 않는다',
                });
            }
            return badges;
        },

        listTitle(flow) {
            return `${this.autorunStatusIcon(flow)} ${flow.name || ''}`;
        },

        listSub(flow) {
            const parts = [
                this.autorunStatusText(flow).replace(/^\S+\s/, ''),
                `모듈 ${flow.module_count || 0}`,
                `블로그 ${flow.blog_count || 0}`,
            ];
            if (flow.status === 'active' && flow.next_execution) {
                parts.push(`다음 ${formatTime(flow.next_execution)}`);
            }
            return parts.join(' · ');
        },

        // ── 정렬 ──────────────────────────────────────────────
        autorunSortValue(flow, key) {
            switch (key) {
                case 'name': return (flow.name || '').toLowerCase();
                // 실행중 → 일시정지 → 자동정지 순. 손봐야 할 것이 뒤로 몰리면
                // 오름차순 한 번으로 문제 있는 플로우가 모인다.
                case 'status':
                    if (flow.status === 'active') return '1';
                    if (flow.status !== 'paused') return '2';   // 비활성
                    return flow.auto_paused ? '4' : '3';
                // 예정 없는 것은 뒤로. 빈 값이 앞에 오면 훑기가 나빠진다.
                case 'next': return flow.next_execution || '9999';
                default: return '';
            }
        },

        listSort(key) {
            if (this.listSortKey === key) {
                this.listSortDir = this.listSortDir === 'asc' ? 'desc' : 'asc';
            } else {
                this.listSortKey = key;
                this.listSortDir = 'asc';
            }
        },

        listSortIcon(key) {
            if (this.listSortKey !== key) return '↕';
            return this.listSortDir === 'asc' ? '▲' : '▼';
        },

        // ── 선택 (selectedIds 위에 구현) ──────────────────────
        listIsSelected(scope, id) {
            return this.selectedIds.includes(id);
        },

        listToggleOne(scope, id) {
            this.toggleSelect(id);
        },

        listSelectedCount(scope) {
            return this.scopedSelectedIds().length;
        },

        listAllChecked(scope, rows) {
            const list = rows || [];
            if (!list.length) return false;
            return list.every(f => this.selectedIds.includes(f.id));
        },

        /** 전체 선택/해제 — 검색으로 걸러진 '보이는 행' 만 대상. */
        listToggleAll(scope, rows) {
            const list = rows || [];
            const ids = list.map(f => f.id);
            if (this.listAllChecked(scope, list)) {
                this.selectedIds = this.selectedIds.filter(id => !ids.includes(id));
            } else {
                this.selectedIds = [...new Set([...this.selectedIds, ...ids])];
            }
        },

        listClearSelection(scope) {
            this.clearScopedSelection();
        },

        listSelectedRows(scope, rows) {
            return (rows || []).filter(f => this.selectedIds.includes(f.id));
        },

        // ── 상단 바가 쓰는 범위 ───────────────────────────────
        /** 지금 탭에서 보이는 것 중 선택된 id. 일괄 동작의 대상이다. */
        scopedSelectedIds() {
            const visible = new Set(this.visibleAutorun(this.autorunTab).map(f => f.id));
            return this.selectedIds.filter(id => visible.has(id));
        },

        clearScopedSelection() {
            const visible = new Set(this.visibleAutorun(this.autorunTab).map(f => f.id));
            this.selectedIds = this.selectedIds.filter(id => !visible.has(id));
        },
    };
}
