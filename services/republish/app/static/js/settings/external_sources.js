/**
 * external_sources.js — 1차 출처 API 등록.
 *
 * 프리셋을 고르면 주소·응답 경로가 채워지고 사용자는 인증키만 넣는다.
 * options(items_path·field_map 같은 것)를 손으로 적게 하면 아무도 못 쓴다.
 *
 * 연결 테스트가 핵심이다. 등록만 해 두고 글 생성 때 조용히 실패하면
 * 아무도 모른다.
 */
function externalSources() {
    return {
        sources: [],
        presets: [],
        saving: false,
        testing: false,
        msg: '',
        keyHint: '인증키',
        testResult: null,
        form: _blankForm(),

        async loadSources() {
            const meta = await this.get('/api/v1/external-sources/presets');
            this.presets = (meta && meta.presets) || [];
            const list = await this.get('/api/v1/external-sources');
            this.sources = (list && list.sources) || [];
        },

        /** 프리셋 적용 — 인증키만 빼고 다 채운다. */
        applyPreset(code) {
            if (!code) { this.reset(); return; }
            const p = this.presets.find(x => x.code === code);
            if (!p) return;
            this.form = {
                ..._blankForm(),
                preset: code,
                code: p.code,
                name: p.name,
                adapter: p.adapter,
                topics: (p.match_topics || []).join(', '),
                keywords: (p.match_keywords || []).join(', '),
            };
            this.keyHint = p.key_hint || '인증키';
            // 주소·options 는 서버가 프리셋에서 채운다. 화면에는 잠긴 채로
            // 비워 둔다 — 안내 문구를 넣으면 그게 주소로 저장될 수 있다.
            this.form.endpoint = '';
            this.msg = '';
        },

        edit(source) {
            this.form = {
                id: source.id, preset: '', code: source.code,
                name: source.name, adapter: source.adapter,
                endpoint: source.endpoint, auth_key: '',
                has_key: source.has_key,
                options: source.options || {},
                topics: (source.match_topics || []).join(', '),
                keywords: (source.match_keywords || []).join(', '),
                enabled: source.enabled,
            };
            this.msg = '';
            this.testResult = null;
        },

        reset() {
            this.form = _blankForm();
            this.keyHint = '인증키';
            this.msg = '';
        },

        _payload() {
            return {
                code: this.form.code, name: this.form.name,
                adapter: this.form.adapter,
                endpoint: this.form.endpoint,
                auth_key: this.form.auth_key || '',
                options: this.form.options || {},
                match_topics: _split(this.form.topics),
                match_keywords: _split(this.form.keywords),
                enabled: this.form.enabled !== false,
                preset: this.form.preset || '',
            };
        },

        /** 저장·테스트 전에 부족한 값을 알려 준다. 없으면 빈 문자열. */
        _missing() {
            if (!this.form.preset && !this.form.adapter) {
                return '어댑터를 고르세요 (프리셋을 선택하면 자동으로 정해집니다)';
            }
            if (!this.form.preset && !this.form.endpoint) {
                return '주소를 입력하세요';
            }
            if (!this.form.auth_key && !this.form.has_key) {
                return '인증키를 입력하세요';
            }
            return '';
        },

        async save() {
            if (!this.form.name || !this.form.code) {
                this.msg = '프리셋을 고르거나 이름·코드를 입력하세요';
                return;
            }
            const missing = this._missing();
            if (missing && !this.form.id) { this.msg = missing; return; }
            if (!_split(this.form.topics).length
                && !_split(this.form.keywords).length) {
                this.msg = '대상 주제 또는 제목 낱말 중 하나는 채워야 합니다';
                return;
            }
            this.saving = true; this.msg = '';
            const body = this._payload();
            const url = this.form.id
                ? `/api/v1/external-sources/${this.form.id}`
                : '/api/v1/external-sources';
            const d = await this.send(this.form.id ? 'PUT' : 'POST', url, body);
            this.saving = false;
            if (!d) return;
            this.msg = this.form.id ? '수정되었습니다' : '등록되었습니다';
            this.reset();
            await this.loadSources();
        },

        async remove(source) {
            if (!confirm(`${source.name} 을(를) 삭제할까요? 인증키도 함께 지워집니다.`)) return;
            const d = await this.send('DELETE',
                `/api/v1/external-sources/${source.id}`);
            if (d) { this.msg = '삭제되었습니다'; await this.loadSources(); }
        },

        /** 실제로 한 번 불러 본다. source 가 null 이면 입력 중인 값으로. */
        async runTest(source) {
            if (!source) {
                const missing = this._missing();
                if (missing) {
                    this.testResult = { id: null, ok: false, text: missing };
                    return;
                }
            }
            this.testing = true;
            this.testResult = null;
            const body = source
                ? { source_id: source.id, query: _sampleQuery(source) }
                : { ...this._payload(), query: _sampleQuery(this.form) };
            const d = await this.send('POST', '/api/v1/external-sources/test',
                                      body);
            this.testing = false;
            if (!d) return;
            this.testResult = {
                id: source ? source.id : null,
                ok: !!d.ok,
                text: d.ok
                    ? `질의 "${d.query}" → ${d.count}건\n${d.preview || ''}`
                    : (d.error || '자료를 찾지 못했습니다')
                      + (d.query
                         ? `\n(질의 "${d.query}", 개체 ${(d.entities || []).join(', ') || '없음'})`
                         : ''),
            };
        },

        async get(url) {
            try {
                const r = await fetch(url, { credentials: 'include' });
                return r.ok ? await r.json() : null;
            } catch (e) { return null; }
        },

        async send(method, url, body) {
            try {
                const r = await fetch(url, {
                    method, credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: body ? JSON.stringify(body) : undefined,
                });
                const d = await r.json().catch(() => ({}));
                if (!r.ok) { this.msg = d.detail || `요청 실패 (${r.status})`; return null; }
                return d;
            } catch (e) {
                this.msg = '오류가 발생했습니다';
                return null;
            }
        },
    };
}

function _blankForm() {
    return {
        id: null, preset: '', code: '', name: '', adapter: '',
        endpoint: '', auth_key: '', has_key: false, options: {},
        topics: '', keywords: '', enabled: true,
    };
}

function _split(text) {
    return (text || '').split(',').map(s => s.trim()).filter(Boolean);
}

/** 테스트 질의 — 등록한 낱말 중 하나를 쓴다. 없으면 무난한 값. */
function _sampleQuery(source) {
    const words = Array.isArray(source.match_keywords)
        ? source.match_keywords
        : _split(source.keywords);
    return words[0] || '주택담보대출';
}
