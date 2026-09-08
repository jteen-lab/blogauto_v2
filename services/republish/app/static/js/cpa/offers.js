/**
 * CPA 오퍼 화면.
 *
 * 확인해야 할 것(커버리지·미분류·충돌·advisory)을 카드 앞면에 둔다.
 * 접어두면 보지 않는다 — 유입 분석에서 매칭률 0%가 로그에만 찍혀
 * 아무도 몰랐던 일을 반복하지 않는다.
 */
function cpaApp() {
    return {
        items: [],
        counts: {},
        filter: '',
        showForm: false,
        openId: null,
        rawText: '',
        busy: false,
        STATES: [
            { key: 'draft', label: '확인 전' },
            { key: 'active', label: '사용중' },
            { key: 'recheck', label: '재확인 필요' },
            { key: 'stopped', label: '중단' },
        ],
        form: { network: 'adlix', offer_code: '', recheck_days: 30, raw_text: '' },

        async load() {
            const q = this.filter ? `?status=${this.filter}` : '';
            const r = await fetch(`/api/v1/cpa/offers${q}`, { credentials: 'include' });
            if (!r.ok) return;
            const d = await r.json();
            this.items = d.items || [];
            this.counts = d.counts || {};
        },

        async create() {
            this.busy = true;
            try {
                const r = await fetch('/api/v1/cpa/offers', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify(this.form),
                });
                const d = await r.json();
                if (!r.ok) { alert(d.detail || '등록 실패'); return; }
                // 무엇을 찾았는지 바로 알려준다. 빈 항목이 있으면 사람이 채워야 한다.
                alert(`등록했습니다.\n찾은 항목: ${(d.found || []).join(', ') || '없음'}`);
                this.form.raw_text = '';
                this.form.offer_code = '';
                this.showForm = false;
                await this.load();
            } finally {
                this.busy = false;
            }
        },

        async open(o) {
            if (this.openId === o.id) { this.openId = null; return; }
            const r = await fetch(`/api/v1/cpa/offers/${o.id}`, { credentials: 'include' });
            if (!r.ok) return;
            const d = await r.json();
            this.rawText = d.raw_text || '';
            this.openId = o.id;
        },

        async patch(o, body) {
            const r = await fetch(`/api/v1/cpa/offers/${o.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(body),
            });
            if (r.ok) await this.load();
        },

        async confirm_(o) {
            if (!confirm(`"${o.name}" 을(를) 승인합니다.\n\n`
                + '승인하면 이 오퍼로 글을 만듭니다. '
                + '규칙을 잘못 두면 이 오퍼로 만든 글 전부가 위반이 될 수 있습니다.')) return;
            const r = await fetch(`/api/v1/cpa/offers/${o.id}/confirm`, {
                method: 'POST', credentials: 'include',
            });
            const d = await r.json();
            if (!r.ok) { alert(d.detail || '승인 실패'); return; }
            await this.load();
        },

        stateLabel(o) {
            return { draft: '확인 전', active: '사용중',
                     recheck: '재확인 필요', stopped: '중단' }[o.status] || o.status;
        },

        badge(o) {
            return {
                draft: 'bg-gray-100 text-gray-700',
                active: 'bg-green-100 text-green-800',
                recheck: 'bg-amber-100 text-amber-800',
                stopped: 'bg-red-100 text-red-800',
            }[o.status] || 'bg-gray-100';
        },

        dday(iso) {
            if (!iso) return '—';
            const days = Math.ceil((new Date(iso) - new Date()) / 86400000);
            return days < 0 ? `${-days}일 지남` : `D-${days}`;
        },
    };
}
