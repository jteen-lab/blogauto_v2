/**
 * 제목 작업대 — 임시제목 탭의 수집·생성 실행 패널.
 *
 * 체크한 섹션만 실행된다. 자동 모듈과 같은 실행기를 부른다.
 *
 * 오래 걸리는 회차가 있어 배경 실행 + 폴링을 쓴다. Caddy 가 60초에
 * 응답 헤더를 끊어 과거 "Unexpected end of JSON input" 이 났다.
 *
 * 계획서: docs/plans/title_tab_workplan.md §1
 */
function titleWorkbench() {
    return {
        busy: false,
        elapsed: 0,
        timer: null,
        poll: null,
        result: null,
        message: '',
        messageType: 'info',
        blogs: [],
        stats: { partial_domains: null, blocked_domains: null },

        collect: {
            enabled: false,
            // ① 제목 수집 — 설정은 둘뿐이다. 상한을 두지 않는다.
            search_enabled: true,
            seed_limit: 10,
            titles_per_keyword: 30,
            // ② 도메인 추출 — 1회 추출 URL 수(회차 전체 예산)
            extract_enabled: true,
            extract_urls: 100,
            // 초기 기본은 표시(mark). 차단부터 켜면 되돌릴 수 없다.
            niche_mode: 'mark',
        },

        gen: {
            enabled: false,
            blog_id: '',
            dry_run: true,
            // AI 를 안 고르고 블로그도 없으면 제목이 만들어지지 않는다
            ai_provider: '',
            ai_model: '',
            l1_enabled: true,
            cluster_limit: 5,
            keyword_limit: 20,
            titles_per_keyword: 3,
            use_angles: true,
            l3_enabled: false,
            news_days: 3,
            news_limit: 10,
            expires_days: 14,
        },

        async init() {
            await Promise.all([this.loadStats(), this.loadBlogs()]);
        },

        anyEnabled() {
            return this.collect.enabled || this.gen.enabled;
        },

        async loadStats() {
            const d = await this.get('/api/v1/title-workbench/stats');
            if (d) this.stats = d;
        },

        async loadBlogs() {
            // 응답은 {"blogs": [...]} 다. items 를 먼저 보면 객체 자체가
            // 목록에 들어가 x-for 가 아무것도 그리지 못한다.
            const d = await this.get('/api/v1/blogs');
            if (!d) { this.blogs = []; return; }
            this.blogs = d.blogs || d.items || (Array.isArray(d) ? d : []);
        },

        async run() {
            if (this.busy || !this.anyEnabled()) return;
            this.busy = true;
            this.elapsed = 0;
            this.result = null;
            this.message = '';
            this.timer = setInterval(() => { this.elapsed += 1; }, 1000);

            const started = await this.post('/api/v1/title-workbench/run', {
                collect: this.collect.enabled ? this.collect : null,
                gen: this.gen.enabled ? this.gen : null,
            });
            if (!started) { this.stop(); return; }
            this.poll = setInterval(() => this.check(), 2000);
        },

        async check() {
            const d = await this.get('/api/v1/title-workbench/status');
            if (!d) { this.stop(); return; }
            if (!d.done) return;

            this.stop();
            if (d.error) {
                this.message = d.error;
                this.messageType = 'error';
                return;
            }
            this.result = d.result;
            await this.loadStats();
            // 목록을 새로 읽어 방금 저장된 제목이 보이게 한다
            window.dispatchEvent(new CustomEvent('titles-changed'));
        },

        stop() {
            this.busy = false;
            if (this.timer) { clearInterval(this.timer); this.timer = null; }
            if (this.poll) { clearInterval(this.poll); this.poll = null; }
        },

        async get(url) {
            try {
                const r = await fetch(url, { credentials: 'include' });
                const text = await r.text();
                if (!r.ok) throw new Error(this.detail(text, r.status));
                return text ? JSON.parse(text) : null;
            } catch (e) {
                this.message = e.message;
                this.messageType = 'error';
                return null;
            }
        },

        async post(url, body) {
            try {
                const r = await fetch(url, {
                    method: 'POST', credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body || {}),
                });
                const text = await r.text();
                if (!r.ok) throw new Error(this.detail(text, r.status));
                if (!text) throw new Error('서버가 빈 응답을 돌려줬습니다');
                return JSON.parse(text);
            } catch (e) {
                this.message = e.message;
                this.messageType = 'error';
                return null;
            }
        },

        detail(text, status) {
            try { return JSON.parse(text).detail || `요청 실패 (${status})`; }
            catch (e) { return `요청 실패 (${status})`; }
        },
    };
}
