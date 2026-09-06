/**
 * analytics_panel.js — 유입 분석 패널.
 *
 * 설정 창이 아니라 **대시보드**에 둔다. 유입은 매일 보는 숫자지,
 * 한 번 설정하고 잊는 값이 아니다.
 *
 * 연결(토큰·속성)도 여기 함께 둔다. 연결은 설정 창에, 결과는 대시보드에
 * 두면 처음 쓰는 사람이 둘을 오가야 한다.
 */
const _origDash_analytics = compactDashboard;
compactDashboard = function () {
    const app = _origDash_analytics();

    /* ── 상태 ── */
    app.gaExpanded = false;
    app.gaLoading = false;
    app.gaSaving = false;
    app.gaCollecting = false;
    app.gaSetupOpen = false;
    app.gaToken = '';
    app.gaShowToken = false;
    app.gaMsg = '';
    app.gaConn = null;          // /analytics/properties 응답
    app.gaSummary = null;       // /analytics/summary 응답
    app.gaPosts = [];           // /analytics/posts 항목
    app.gaJudge = {};           // 판정 분포
    app.gaDays = 28;
    app.gaBlogId = '';

    /** 패널을 처음 열 때만 불러온다. 대시보드 첫 로딩을 늦추지 않는다. */
    app.toggleAnalytics = async function () {
        this.gaExpanded = !this.gaExpanded;
        if (this.gaExpanded && this.gaConn === null) await this.loadAnalytics();
    };

    app.loadAnalytics = async function () {
        this.gaLoading = true;
        try {
            const [conn, summary, posts] = await Promise.all([
                this.gaGet('/api/v1/analytics/properties'),
                this.gaGet(`/api/v1/analytics/summary?days=${this.gaDays}` +
                           (this.gaBlogId ? `&blog_id=${this.gaBlogId}` : '')),
                this.gaGet(`/api/v1/analytics/posts?days=${this.gaDays}&limit=30` +
                           (this.gaBlogId ? `&blog_id=${this.gaBlogId}` : '')),
            ]);
            this.gaConn = conn || { connected: false };
            this.gaSummary = summary;
            this.gaPosts = (posts && posts.items) || [];
            this.gaJudge = (posts && posts.summary) || {};
            // 연결이 안 됐으면 설정을 펼쳐 둔다 — 뭘 해야 할지 보이게
            if (!this.gaConn.connected) this.gaSetupOpen = true;
        } finally {
            this.gaLoading = false;
        }
    };

    app.saveGaToken = async function () {
        if (!this.gaToken.trim()) { this.gaMsg = 'refresh token을 입력하세요'; return; }
        this.gaSaving = true; this.gaMsg = '';
        try {
            const r = await fetch('/api/v1/analytics/account', {
                method: 'POST', credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: this.gaToken.trim() }),
            });
            const d = await r.json();
            this.gaMsg = r.ok ? '저장되었습니다' : (d.detail || '저장 실패');
            if (r.ok) { this.gaToken = ''; await this.loadAnalytics(); }
        } catch (e) {
            this.gaMsg = '오류가 발생했습니다';
        } finally {
            this.gaSaving = false;
        }
    };

    /** 블로그에 GA4 속성을 연결한다. 속성은 블로그마다 따로다. */
    app.linkGaProperty = async function (blog, propertyId) {
        const prop = (this.gaConn.properties || [])
            .find(p => p.property_id === propertyId);
        try {
            await fetch('/api/v1/analytics/properties', {
                method: 'PUT', credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    blog_id: blog.id, property_id: propertyId,
                    display_name: prop ? prop.display_name : '',
                }),
            });
            blog.property_id = propertyId;
            this.gaMsg = blog.name + (propertyId ? ' 연결됨' : ' 연결 해제');
        } catch (e) {
            this.gaMsg = '연결 실패';
        }
    };

    /** 자동 수집(매일 05:20)을 기다리지 않고 지금 받아온다. */
    app.collectAnalytics = async function () {
        this.gaCollecting = true; this.gaMsg = '수집 중…';
        try {
            const scope = this.gaBlogId ? `&blog_id=${this.gaBlogId}` : '';
            const r = await fetch(
                `/api/v1/analytics/collect?days=${this.gaDays}${scope}`,
                { method: 'POST', credentials: 'include' });
            const d = await r.json();
            if (!r.ok) {
                this.gaMsg = d.detail || '수집 실패';
            } else if (d.skipped) {
                // 조용히 0건이면 왜 없는지 알 수 없다
                this.gaMsg = `수집 안 함 — ${d.skipped}`;
            } else {
                const where = this.gaBlogId ? this.gaScopeLabel() : `블로그 ${d.blogs ?? 0}개`;
                this.gaMsg = `${where} · ${d.rows ?? 0}건 적재`;
            }
            if (r.ok) await this.loadAnalytics();
        } catch (e) {
            this.gaMsg = '수집 실패';
        } finally {
            this.gaCollecting = false;
        }
    };

    app.gaGet = async function (url) {
        try {
            const r = await fetch(url, { credentials: 'include' });
            return r.ok ? await r.json() : null;
        } catch (e) {
            return null;
        }
    };

    /* ── 표시 도우미 ── */

    /** 판정을 사람 말로. 코드값(keep/augment)을 그대로 보여주면 못 읽는다. */
    app.gaActionLabel = function (action) {
        return {
            keep: '그대로 둠', augment: '보강', title: '제목 손질',
            rewrite: '새로 씀', legacy: '판정 보류',
        }[action] || action;
    };

    app.gaActionClass = function (action) {
        return {
            keep: 'bg-emerald-100 text-emerald-700',
            augment: 'bg-amber-100 text-amber-700',
            title: 'bg-blue-100 text-blue-700',
            rewrite: 'bg-rose-100 text-rose-700',
            legacy: 'bg-gray-100 text-gray-500',
        }[action] || 'bg-gray-100 text-gray-500';
    };

    /** 증감률. 비교 대상이 없으면 '-' — 0% 로 적으면 유지된 것처럼 보인다. */
    app.gaDelta = function (row) {
        if (row.decay === null || row.decay === undefined) return '-';
        const pct = Math.round(row.decay * 100);
        return (pct > 0 ? '+' : '') + pct + '%';
    };

    app.gaDeltaClass = function (row) {
        if (row.decay === null || row.decay === undefined) return 'text-gray-300';
        if (row.decay <= -0.2) return 'text-rose-600';
        if (row.decay > 0) return 'text-emerald-600';
        return 'text-gray-500';
    };

    /** 지금 무엇을 보고 있는가. 표만 보면 어느 블로그인지 알 수 없다. */
    app.gaScopeLabel = function () {
        if (!this.gaBlogId) return '전체 블로그';
        const found = ((this.gaConn && this.gaConn.blogs) || [])
            .find(b => String(b.id) === String(this.gaBlogId));
        return found ? found.name : '선택한 블로그';
    };

    /** 연결된 블로그 수. 0 이면 아무 데이터도 안 쌓인다. */
    app.gaLinkedCount = function () {
        return ((this.gaConn && this.gaConn.blogs) || [])
            .filter(b => b.property_id).length;
    };

    return app;
};
