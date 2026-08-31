/**
 * 플로우 목록 표 어댑터.
 *
 * 공용 표 컴포넌트(components/list_table.html)가 요구하는 함수들을 제공한다.
 * flows/list.js 는 이미 1200줄이 넘어 여기에 나눠 담는다.
 *
 * 화면에 펼쳐 넣는다:
 *     return { ...flowListTableMixin(), ...listSelectionMixin(), ... }
 *
 * 순서도: docs/flowcharts/flow_list_table.md
 */
function flowListTableMixin() {
    return {
        // 이름·설명·모듈·블로그를 대상으로 하는 검색어
        flowSearch: '',

        // ── 탭 ────────────────────────────────────────────────
        /**
         * 플로우가 속할 탭. 연결된 블로그의 플랫폼으로 나눈다.
         * 어느 탭에도 못 들어가면 화면에서 사라지므로 네 갈래가 전부다.
         */
        flowTab(flow) {
            // 판정은 components/platform_tabs.js 한 곳에만 둔다 — 오토런과
            // 규칙이 갈리면 같은 플로우가 화면마다 다른 탭에 들어간다.
            return platformTabOf(
                (this.getFlowBlogs(flow) || []).map(fb => fb.blog?.platform)
            );
        },

        getFlowsByTab(tab) {
            return (this.flows || []).filter(f => this.flowTab(f) === tab);
        },

        /**
         * 탭 + 검색으로 걸러낸 목록.
         * 정렬은 기존 sortedFlows 를 그대로 쓴다 — 정렬 구현을 한 벌 더
         * 만들면 드롭다운과 열 머리글이 서로 다른 순서를 낸다.
         */
        visibleFlows(tab) {
            const q = (this.flowSearch || '').trim().toLowerCase();
            return this.sortedFlows.filter(flow => {
                if (this.flowTab(flow) !== tab) return false;
                if (!q) return true;
                return (flow.name || '').toLowerCase().includes(q)
                    || (flow.description || '').toLowerCase().includes(q)
                    || this.flowModuleNames(flow).toLowerCase().includes(q)
                    || this.flowBlogNames(flow).toLowerCase().includes(q);
            });
        },

        // ── 셀 값 ─────────────────────────────────────────────
        /** 모듈 아이콘 + 이름. 카드가 아이콘과 이름을 함께 보여줬다. */
        flowModuleNames(flow) {
            const modules = this.getFlowModules(flow) || [];
            if (!modules.length) return '-';
            return modules
                .map(fm => {
                    const m = fm.module || {};
                    const code = m.module_type?.code || '';
                    return `${this.getModuleIcon(code)} ${m.name || ''}`.trim();
                })
                .join(' · ');
        },

        /** WP/BL 접두 + 블로그명. 카드의 플랫폼 배지를 글자로 옮긴 것. */
        flowBlogNames(flow) {
            const blogs = this.getFlowBlogs(flow) || [];
            if (!blogs.length) return '-';
            return blogs
                .map(fb => {
                    const b = fb.blog || {};
                    const badge = b.platform === 'wordpress' ? 'WP' : 'BL';
                    return `${badge} ${b.name || ''}`.trim();
                })
                .join(' · ');
        },

        formatFlowDate(value) {
            if (!value) return '-';
            const d = new Date(value);
            if (isNaN(d.getTime())) return '-';
            const p = n => String(n).padStart(2, '0');
            return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
        },

        // ── 공용 표 규약 ──────────────────────────────────────
        listColumns() {
            return [
                { key: 'name',    label: '이름',   width: '22%', strong: true, sortable: true },
                { key: 'modules', label: '모듈',   width: '30%', sortable: true },
                { key: 'blogs',   label: '블로그', width: '20%', sortable: true },
                { key: '_badges', label: '상태',   width: '16%' },
                { key: 'updated', label: '수정',   width: '12%', sortable: true },
            ];
        },

        listCell(flow, key) {
            switch (key) {
                case 'name': return flow.name || '';
                case 'modules': return this.flowModuleNames(flow);
                case 'blogs': return this.flowBlogNames(flow);
                case 'updated': return this.formatFlowDate(flow.updated_at || flow.created_at);
                default: return '';
            }
        },

        listBadges(flow) {
            const badges = [];
            if (this.flowHasGP(flow)) {
                badges.push({
                    label: `📈 ${this.getGPModuleName(flow) || '성장 전략'}`,
                    cls: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
                    tip: '성장 프로파일이 연결된 플로우',
                });
            }
            const moduleCount = (this.getFlowModules(flow) || []).length;
            if (moduleCount === 0) {
                badges.push({
                    label: '모듈 없음',
                    cls: 'bg-amber-50 text-amber-700 border border-amber-200',
                    tip: '연결된 모듈이 없어 실행되지 않는다',
                });
            }
            return badges;
        },

        listTitle(flow) {
            return flow.name || '';
        },

        listSub(flow) {
            const parts = [
                `모듈 ${(this.getFlowModules(flow) || []).length}`,
                `블로그 ${(this.getFlowBlogs(flow) || []).length}`,
                this.formatFlowDate(flow.updated_at || flow.created_at),
            ];
            if (flow.description) parts.unshift(flow.description);
            return parts.join(' · ');
        },

        // ── 정렬 ──────────────────────────────────────────────
        // 열 머리글은 기존 드롭다운과 **같은 상태**를 바꾼다. 별도 정렬
        // 상태를 두면 드롭다운 표시와 실제 순서가 어긋난다.
        listSortKeyFor(columnKey) {
            return {
                name: 'name',
                modules: 'module_count',
                blogs: 'blog_count',
                updated: 'updated_at',
            }[columnKey] || null;
        },

        listSort(columnKey) {
            const sortBy = this.listSortKeyFor(columnKey);
            if (!sortBy) return;
            if (this.sortBy === sortBy) {
                this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortBy = sortBy;
                this.sortOrder = 'asc';
            }
            if (typeof this.saveSortPreference === 'function') this.saveSortPreference();
        },

        listSortIcon(columnKey) {
            if (this.listSortKeyFor(columnKey) !== this.sortBy) return '↕';
            return this.sortOrder === 'asc' ? '▲' : '▼';
        },

        // ── 일괄 삭제 ─────────────────────────────────────────
        /** 선택한 플로우 일괄 삭제. 탭마다 선택이 따로라 지금 탭의 것만 지운다. */
        async deleteSelectedFlows(scope, rows) {
            const targets = this.listSelectedRows(scope, rows);
            if (!targets.length) return;

            const names = targets.slice(0, 5).map(f => f.name).join(', ');
            const more = targets.length > 5 ? ` 외 ${targets.length - 5}개` : '';
            if (!confirm(
                `플로우 ${targets.length}개를 삭제합니다.\n\n${names}${more}\n\n`
                + '이 작업은 되돌릴 수 없습니다. 계속하시겠습니까?')) return;

            const failed = [];
            let deleted = 0;
            for (const flow of targets) {
                try {
                    const response = await fetch(`/api/v1/flows/${flow.id}`, {
                        method: 'DELETE', credentials: 'include',
                    });
                    if (response.ok) deleted += 1;
                    else failed.push(flow.name);
                } catch (error) {
                    failed.push(flow.name);
                }
            }

            const failedNames = new Set(failed);
            const removed = new Set(
                targets.filter(f => !failedNames.has(f.name)).map(f => f.id)
            );
            this.flows = this.flows.filter(f => !removed.has(f.id));
            this.listClearSelection(scope);
            this.refreshGlobalSummary();

            if (failed.length) this.showError(`${deleted}개 삭제 · 실패 ${failed.length}개`);
            else this.showSuccess(`플로우 ${deleted}개가 삭제되었습니다`);
        },
    };
}
