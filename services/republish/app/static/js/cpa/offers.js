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
        showUnmatched: null,
        showConflicts: null,
        preview: '',
        tpl: null,
        criticalMissing: [],
        topics: [],
        subtopics: [],
        rawText: '',
        busy: false,
        STATES: [
            { key: 'draft', label: '확인 전' },
            { key: 'active', label: '사용중' },
            { key: 'recheck', label: '재확인 필요' },
            { key: 'stopped', label: '중단' },
        ],
        form: { network: 'adlix', offer_code: '', recheck_days: 30, raw_text: '' },




        async loadTopics() {
            const r = await fetch('/api/v1/categories/topics', { credentials: 'include' });
            if (!r.ok) return;
            this.topics = await r.json();
            // 하위주제는 주제별로 받아 하나로 합친다
            const all = [];
            for (const t of this.topics) {
                const sub = await fetch(
                    `/api/v1/categories/topics/${t.id}/subtopics`,
                    { credentials: 'include' });
                if (!sub.ok) continue;
                for (const one of await sub.json()) {
                    all.push({ id: one.id, name: one.name, topic_name: t.name });
                }
            }
            this.subtopics = all;
        },

        async saveSubtopics(o, ids, newName = null, newTopicId = null) {
            const r = await fetch(`/api/v1/cpa/offers/${o.id}/subtopics`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ subtopic_ids: ids, new_name: newName,
                                       new_topic_id: newTopicId }),
            });
            const d = await r.json();
            if (!r.ok) { alert(d.detail || '저장 실패'); return; }
            o.subtopic_ids = d.subtopic_ids;
        },

        async toggleSubtopic(o, id, checked) {
            const next = checked
                ? [...new Set([...(o.subtopic_ids || []), id])]
                : (o.subtopic_ids || []).filter(x => x !== id);
            await this.saveSubtopics(o, next);
        },

        async newSubtopic(o) {
            const el = document.getElementById(`newtopic-${o.id}`);
            if (!el || !el.value) { alert('주제를 먼저 고르세요.'); return; }
            const name = prompt('새 하위주제 이름', o.name);
            if (!name) return;
            await this.saveSubtopics(o, o.subtopic_ids || [], name,
                                     Number(el.value));
            await this.loadTopics();
        },


        async load() {
            if (!this.topics.length) await this.loadTopics();
            const q = this.filter ? `?status=${this.filter}` : '';
            const r = await fetch(`/api/v1/cpa/offers${q}`, { credentials: 'include' });
            if (!r.ok) return;
            const d = await r.json();
            this.items = d.items || [];
            this.counts = d.counts || {};
            // 열려 있는 상세도 같이 새로 고친다.
            // **여기서 하지 않으면 각 동작이 저마다 잊는다.** 실제로 규칙 97건을
            // 뽑고도 화면은 뽑기 전 값인 정형 항목 3/19 를 계속 보여줬다
            // (2026-09-09 안과 오퍼). 목록을 고치는 모든 길이 이 함수를 지나므로
            // 상세 갱신도 여기 한 곳에 둔다.
            if (!this.openId) return;
            if (this.items.some(x => x.id === this.openId)) {
                await this.fetchDetail(this.openId);
            } else {
                this.closeDetail();
            }
        },

        /** 상세(원문·정형 항목·필수 누락)를 받아 화면 상태에 넣는다. */
        async fetchDetail(id) {
            const r = await fetch(`/api/v1/cpa/offers/${id}`, { credentials: 'include' });
            if (!r.ok) return false;
            const d = await r.json();
            this.rawText = d.raw_text || '';
            this.tpl = d.template || null;
            this.criticalMissing = d.critical_missing || [];
            return true;
        },

        /** 상세를 닫는다. 남겨두면 다른 오퍼에 옛 정형 항목이 비친다. */
        closeDetail() {
            this.openId = null;
            this.tpl = null;
            this.criticalMissing = [];
            this.rawText = '';
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

        async extract(o) {
            if (!confirm(`"${o.name}" 의 원문에서 규칙을 뽑습니다.\n\n`
                + '뽑고 나면 승인 전 상태로 되돌아갑니다. 규칙이 바뀌었으니 다시 확인해야 합니다.')) return;
            this.busy = true;
            try {
                const r = await fetch(`/api/v1/cpa/offers/${o.id}/extract`, {
                    method: 'POST', credentials: 'include',
                });
                const d = await r.json();
                if (!r.ok) { alert(d.detail || '추출 실패'); return; }
                const off = d.offer;
                // 뽑은 결과를 **그 자리에서 펼친다.** 목록만 새로 고치면 접혀 있던
                // 상세가 뽑기 전 정형 항목을 그대로 보여줘, 채워진 칸을 못 채운 것으로
                // 읽는다(2026-09-09 안과 오퍼: 실제 17/19 를 3/19 로 봤다).
                this.openId = off.id;
                await this.load();
                alert(`규칙 ${off.rules.length}건\n`
                    + `정형 항목 ${this.tpl?.filled ?? 0}/${this.tpl?.total ?? 0} 채움\n`
                    + (this.criticalMissing.length
                        ? `필수 누락: ${this.criticalMissing.join(', ')}\n` : '')
                    + `미분류 ${off.unmatched.length}개 (검사되지 않음)\n`
                    + `충돌 ${off.conflicts.length}건`);
            } finally {
                this.busy = false;
            }
        },

        async open(o) {
            if (this.openId === o.id) { this.closeDetail(); return; }
            if (!await this.fetchDetail(o.id)) return;
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

        async addRule(o, line, selectId) {
            const el = document.getElementById(selectId);
            const type = el ? el.value : '';
            if (!type) { alert('유형을 먼저 고르세요.'); return; }
            const value = prompt('규칙 값을 확인하세요 (낱말·문구·내용)', line) ;
            if (value === null) return;
            const r = await fetch(`/api/v1/cpa/offers/${o.id}/rules`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ type, value, target: value,
                                       source_quote: line,
                                       drop_unmatched: line }),
            });
            const d = await r.json();
            if (!r.ok) { alert(d.detail || '추가 실패'); return; }
            await this.load();
        },

        async ignore(o, line) {
            const r = await fetch(`/api/v1/cpa/offers/${o.id}/unmatched/ignore`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ line }),
            });
            if (r.ok) await this.load();
        },

        async makeTitles(o) {
            this.busy = true;
            try {
                const r = await fetch(`/api/v1/cpa/offers/${o.id}/titles`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ limit: 40 }),
                });
                const d = await r.json();
                if (!r.ok) { alert(d.detail || '생성 실패'); return; }
                // 규칙에 걸려 버린 후보를 함께 알린다. 왜 적게 나왔는지 알아야 한다.
                // 0개일 때 이유를 말해야 다음에 무엇을 할지 안다.
                const kw = d.keywords || [];
                const lines = [`제목 ${d.added}개 추가`];
                lines.push(kw.length
                    ? `키워드 ${kw.length}개: ${kw.slice(0, 5).join(', ')}`
                    : '키워드 없음');
                if ((d.skipped || []).length) {
                    lines.push(`규칙에 걸려 제외 ${d.skipped.length}개`);
                }
                if (d.reason) lines.push('', d.reason);
                alert(lines.join('\n'));
            } finally {
                this.busy = false;
            }
        },

        async showPrompt(o) {
            const r = await fetch(`/api/v1/cpa/offers/${o.id}/prompt`, {
                credentials: 'include' });
            if (!r.ok) return;
            const d = await r.json();
            this.preview = d.prompt || '(지시문 없음)';
        },

        async showPage(o) {
            const r = await fetch(`/api/v1/cpa/offers/${o.id}/consult-page`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ intro: '' }),
            });
            if (!r.ok) return;
            const d = await r.json();
            const warn = d.thin
                ? `⚠ 얇습니다 (${d.chars}자) — 부족: ${(d.missing || []).join(', ')}\n\n`
                : `분량 ${d.chars}자\n\n`;
            this.preview = warn + d.html;
        },

        async uploadImage(o, ev) {
            const file = ev.target.files && ev.target.files[0];
            if (!file) return;
            const form = new FormData();
            form.append('file', file);
            const r = await fetch(`/api/v1/cpa/offers/${o.id}/images`, {
                method: 'POST', credentials: 'include', body: form,
            });
            const d = await r.json();
            ev.target.value = '';
            if (!r.ok) { alert(d.detail || '업로드 실패'); return; }
            o.images = d.images;
        },

        async removeImage(o, index) {
            if (!confirm('이 이미지를 뺍니다. 파일도 지워집니다.')) return;
            const r = await fetch(`/api/v1/cpa/offers/${o.id}/images/${index}`, {
                method: 'DELETE', credentials: 'include',
            });
            const d = await r.json();
            if (!r.ok) { alert(d.detail || '삭제 실패'); return; }
            o.images = d.images;
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
