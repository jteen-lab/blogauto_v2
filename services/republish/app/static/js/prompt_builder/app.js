/**
 * 프롬프트 빌더 — 재사용 가능 Alpine.js state 팩토리.
 *
 * 두 군데에서 같은 로직을 사용:
 *  1) 별도 페이지 /prompt-builder  → mode='page'   (복사 버튼)
 *  2) 모듈 폼 안 확장 패널         → mode='embedded' (반영 버튼 + onApply 콜백)
 *
 * 기능:
 *  - 페르소나/독자수준/글쓰기기본원칙/섹션패턴/시작톤 5축 라디오 선택
 *  - 프리셋 1클릭 적용 + 어울리는 카테고리 표기 (기본 10종 + 사용자 커스텀)
 *  - 사용자 커스텀 프리셋 localStorage 저장 + 중복 조합 차단(글자수 설정 포함)
 *  - 섹션 수는 패턴 본문에서 도출해 표시만(사용자 조절 불가 → 프롬프트와 항상 일치)
 *  - 각 4축 EDIT 임시 수정 (라디오 변경 시 자동 초기화)
 */

/**
 * 옵션:
 *  - mode: 'page' | 'embedded'
 *  - onApply: (text) => void   (mode === 'embedded' 일 때 "반영" 버튼이 호출)
 *  - blocksDataElementId: 페이지의 <script id> 직접 지정. 없으면 표준값 시도.
 */
function createPromptBuilderState(opts = {}) {
    return {
        mode: opts.mode || 'page',
        onApply: typeof opts.onApply === 'function' ? opts.onApply : null,
        // F11: 전용 프롬프트 프리셋(애드센스 승인용) 적용 시 호출(모듈 토글 연동용)
        onApplyPreset: typeof opts.onApplyPreset === 'function' ? opts.onApplyPreset : null,
        blocksDataElementId: opts.blocksDataElementId || null,
        expanded: false, // embedded 모드에서 폼 안 접기/펼치기
        // F11: 전용 프롬프트(full_prompt) 프리셋 적용 시 이 텍스트를 그대로 사용.
        // 비어있으면 4축 조합으로 프롬프트를 만든다.
        fullPromptOverride: '',

        // ── 데이터 ────────────────────────────────────────
        personas: [],
        readers: [],
        patterns: [],
        tones: [],
        commons: [],       // 글쓰기 기본 원칙 옵션(선택형 축)
        builtinPresets: [],
        customPresets: [],
        divider: '',

        // ── 선택값 ────────────────────────────────────────
        persona: '',
        reader: '',
        pattern: '',
        tone: '',
        common: '',        // 글쓰기 기본 원칙 선택 코드(로드 시 기본값 자동선택)
        // 구조 약속 글자수(하드코딩 제거 → 설정화). 구성마다 조절 가능.
        introChars: 200,
        sectionChars: 250,
        outroChars: 200,

        // ── 임시 수정(EDIT) ───────────────────────────────
        overrides: { persona: null, reader: null, pattern: null, tone: null, common: null },
        editing: { persona: false, reader: false, pattern: false, tone: false, common: false },

        // ── UI 상태 ───────────────────────────────────────
        justCopied: false,
        justApplied: false,
        newPresetName: '',
        presetWarning: '',
        blockMsg: '',       // 옵션 저장/추가/삭제 안내 메시지
        blockBusy: false,   // CRUD 진행 중 중복요청 방지

        // ── 초기화 ────────────────────────────────────────
        init() {
            this.loadBlocksData();
            this.loadCustomPresets();
            this.$watch('persona', () => { this.overrides.persona = null; this.editing.persona = false; });
            this.$watch('reader', () => { this.overrides.reader = null; this.editing.reader = false; });
            this.$watch('pattern', () => { this.overrides.pattern = null; this.editing.pattern = false; });
            this.$watch('tone', () => { this.overrides.tone = null; this.editing.tone = false; });
            this.$watch('common', () => { this.overrides.common = null; this.editing.common = false; });
            this.$watch('newPresetName', () => { this.presetWarning = ''; });
        },

        loadBlocksData() {
            const id = this.blocksDataElementId
                || (document.getElementById('prompt-builder-blocks-data') ? 'prompt-builder-blocks-data' : 'blocks-data');
            const node = document.getElementById(id);
            if (!node) {
                console.error('[prompt-builder] blocks-data 요소를 찾지 못했습니다 (id:', id, ').');
                return;
            }
            try {
                const data = JSON.parse(node.textContent);
                this.personas = data.personas || [];
                this.readers = data.readers || [];
                this.patterns = data.patterns || [];
                this.tones = data.tones || [];
                this.commons = data.commons || [];
                this.builtinPresets = data.presets || [];
                this.divider = data.divider || '─'.repeat(40);
                this.ensureCommonSelected();
            } catch (e) {
                console.error('[prompt-builder] blocks-data 파싱 실패:', e);
            }
        },

        // 글쓰기 기본 원칙은 항상 하나가 선택돼 있어야 함(기존 하드코딩 동작 유지).
        // 미선택이거나 선택 코드가 목록에서 사라졌으면 첫 옵션으로 자동 선택.
        ensureCommonSelected() {
            if (!this.commons.length) return;
            const exists = this.commons.some((c) => c.code === this.common);
            if (!this.common || !exists) this.common = this.commons[0].code;
        },

        // ── 프리셋 ─────────────────────────────────────────
        get presets() {
            // 기본 + 커스텀 합쳐서 노출 (커스텀이 뒤에 옴)
            return [...this.builtinPresets, ...this.customPresets];
        },

        applyPreset(code) {
            const p = this.presets.find((x) => x.code === code);
            if (!p) return;
            // F11: 전용 프롬프트 프리셋(애드센스 승인용) — 4축 조합 대신 완성 프롬프트를
            // 그대로 사용. 미리보기·반영이 이 텍스트를 쓰며 4축·글자수 설정은 무시된다.
            if (p.full_prompt) {
                this.fullPromptOverride = p.full_prompt;
                if (this.onApplyPreset) this.onApplyPreset(p);
                return;
            }
            this.fullPromptOverride = '';
            this.persona = p.persona;
            this.reader = p.reader;
            this.pattern = p.pattern;
            this.tone = p.tone;
            // 글쓰기 기본 원칙 복원(프리셋에 없거나 목록에 없으면 기본값 유지).
            if (p.common && this.commons.some((c) => c.code === p.common)) this.common = p.common;
            else this.ensureCommonSelected();
            // 글자수 설정도 복원(프리셋에 없으면 기본값) → 프리셋 적용이 항상 결정적.
            this.introChars = (typeof p.introChars === 'number') ? p.introChars : 200;
            this.sectionChars = (typeof p.sectionChars === 'number') ? p.sectionChars : 250;
            this.outroChars = (typeof p.outroChars === 'number') ? p.outroChars : 200;
        },

        // 현재 4축 조합이 이 프리셋과 완전히 일치하는지(테두리 하이라이트용).
        // 조합 중복 저장이 차단되므로 활성 프리셋은 최대 1개.
        isActivePreset(p) {
            // 전용 프롬프트 프리셋은 텍스트 일치로 판정
            if (p.full_prompt) return this.fullPromptOverride === p.full_prompt;
            return this.isComplete()
                && !this.fullPromptOverride
                && p.persona === this.persona
                && p.reader === this.reader
                && p.pattern === this.pattern
                && p.tone === this.tone;
        },

        // 현재 4축 조합으로 커스텀 프리셋 저장 (이름 필요)
        saveCustomPreset() {
            this.presetWarning = '';
            if (!this.isComplete()) {
                this.presetWarning = '4개 블록을 모두 선택한 후 저장하세요.';
                return;
            }
            const name = (this.newPresetName || '').trim();
            if (!name) {
                this.presetWarning = '프리셋 이름을 입력하세요.';
                return;
            }
            // 중복 조합 차단 (기본 + 커스텀 풀 전체와 비교)
            const dup = this.presets.find((p) =>
                p.persona === this.persona &&
                p.reader === this.reader &&
                p.pattern === this.pattern &&
                p.tone === this.tone
            );
            if (dup) {
                this.presetWarning = `이미 같은 조합의 프리셋이 있습니다: ${dup.label}`;
                return;
            }
            // 이름 중복도 차단
            const nameDup = this.customPresets.find((p) => p.label === name);
            if (nameDup) {
                this.presetWarning = `같은 이름의 커스텀 프리셋이 이미 있습니다.`;
                return;
            }
            const newPreset = {
                code: 'custom-' + Date.now(),
                label: name,
                categories: '커스텀',
                persona: this.persona,
                reader: this.reader,
                pattern: this.pattern,
                tone: this.tone,
                // 글쓰기 기본 원칙 + 글자수 함께 저장(섹션 수는 패턴 코드에 내재 → 별도 저장 불필요).
                common: this.common,
                introChars: this.introChars,
                sectionChars: this.sectionChars,
                outroChars: this.outroChars,
                _custom: true,
            };
            this.customPresets.push(newPreset);
            this.persistCustomPresets();
            this.newPresetName = '';
        },

        deleteCustomPreset(code) {
            this.customPresets = this.customPresets.filter((p) => p.code !== code);
            this.persistCustomPresets();
        },

        persistCustomPresets() {
            try {
                localStorage.setItem(
                    'blogauto_prompt_builder_custom_presets',
                    JSON.stringify(this.customPresets),
                );
            } catch (e) {
                console.warn('[prompt-builder] customPresets 저장 실패:', e);
            }
        },

        loadCustomPresets() {
            try {
                const raw = localStorage.getItem('blogauto_prompt_builder_custom_presets');
                if (raw) {
                    const arr = JSON.parse(raw);
                    if (Array.isArray(arr)) this.customPresets = arr;
                }
            } catch (e) {
                console.warn('[prompt-builder] customPresets 로드 실패:', e);
                this.customPresets = [];
            }
        },

        // ── 헬퍼 ───────────────────────────────────────────
        find(list, code) {
            return list.find((it) => it.code === code) || null;
        },
        selectedLabel(field, list) {
            const hit = this.find(list, this[field]);
            return hit ? hit.label : '미선택';
        },
        // 전용 프롬프트 적용 여부(불리언).
        // 주의: fullPromptOverride 는 '' 로 시작하는 **문자열**이라 그대로
        // :disabled 에 바인딩하면 Alpine 이 null/undefined/false 만 속성을 지우므로
        // disabled="" 가 항상 붙어 4축이 영구 비활성화된다. 항상 이 게터를 쓸 것.
        get fullPromptLocked() {
            return Boolean(this.fullPromptOverride);
        },
        isComplete() {
            if (this.fullPromptOverride) return true; // 전용 프롬프트는 즉시 반영 가능
            return Boolean(this.persona && this.reader && this.pattern && this.tone);
        },
        bodyFor(field, list) {
            if (this.overrides[field] !== null) return this.overrides[field];
            const hit = this.find(list, this[field]);
            return hit ? hit.body : '(블록을 선택하세요)';
        },

        // ── EDIT 토글 ─────────────────────────────────────
        toggleEdit(field) {
            if (!this[field]) return;
            const next = !this.editing[field];
            this.editing[field] = next;
            if (next && this.overrides[field] === null) {
                const lists = { persona: this.personas, reader: this.readers, pattern: this.patterns, tone: this.tones, common: this.commons };
                const list = lists[field];
                if (!list) return;
                // 편집/저장은 항상 '원문 그대로'(패턴 포함) — 재가공 없이 본문을 그대로 편집.
                this.overrides[field] = this.find(list, this[field])?.body || '';
            }
        },
        resetOverride(field) {
            this.overrides[field] = null;
            this.editing[field] = false;
        },

        // ── 옵션 영구 저장/추가/삭제 (DB CRUD) ───────────────
        _listFor(field) {
            return {
                persona: this.personas, reader: this.readers,
                pattern: this.patterns, tone: this.tones, common: this.commons,
            }[field];
        },
        _applyBlocks(field, items) {
            if (!Array.isArray(items)) return;
            if (field === 'persona') this.personas = items;
            else if (field === 'reader') this.readers = items;
            else if (field === 'pattern') this.patterns = items;
            else if (field === 'tone') this.tones = items;
            else if (field === 'common') this.commons = items;
        },
        flashBlockMsg(msg) {
            this.blockMsg = msg;
            setTimeout(() => { if (this.blockMsg === msg) this.blockMsg = ''; }, 2000);
        },
        async reloadBlocks() {
            try {
                const res = await fetch('/api/v1/prompt-builder/blocks', { credentials: 'include' });
                if (!res.ok) return;
                const all = await res.json();
                const byType = { persona: [], reader: [], pattern: [], tone: [], common: [] };
                for (const b of all) {
                    if (b.is_active && byType[b.block_type]) {
                        byType[b.block_type].push({
                            id: b.id, code: b.code, label: b.label,
                            cluster: b.cluster || '', body: b.body,
                        });
                    }
                }
                ['persona', 'reader', 'pattern', 'tone', 'common'].forEach((f) => {
                    if (byType[f].length) this._applyBlocks(f, byType[f]);
                });
                this.ensureCommonSelected();
            } catch (e) { console.warn('[prompt-builder] reloadBlocks 실패:', e); }
        },
        async persistBlock(field) {
            if (this.blockBusy) return;
            const blk = this.find(this._listFor(field), this[field]);
            if (!blk || !blk.id) { this.flashBlockMsg('기본 데이터라 저장 불가'); return; }
            const body = this.overrides[field];
            if (body == null || !body.trim()) { this.flashBlockMsg('내용이 비었습니다'); return; }
            this.blockBusy = true;
            try {
                const res = await fetch('/api/v1/prompt-builder/blocks/' + blk.id, {
                    method: 'PUT', credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ body }),
                });
                if (!res.ok) { this.flashBlockMsg('저장 실패 (HTTP ' + res.status + ')'); return; }
                await this.reloadBlocks();
                this.overrides[field] = null;
                this.editing[field] = false;
                this.flashBlockMsg('영구 저장됨');
            } finally { this.blockBusy = false; }
        },
        async saveAsNewBlock(field) {
            if (this.blockBusy) return;
            const cur = this.find(this._listFor(field), this[field]);
            const body = (this.overrides[field] != null ? this.overrides[field] : (cur ? cur.body : '')).trim();
            if (!body) { this.flashBlockMsg('내용이 비었습니다'); return; }
            const label = (window.prompt('새 옵션 이름을 입력하세요') || '').trim();
            if (!label) return;
            this.blockBusy = true;
            try {
                const res = await fetch('/api/v1/prompt-builder/blocks', {
                    method: 'POST', credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ block_type: field, label, body }),
                });
                if (!res.ok) { this.flashBlockMsg('추가 실패 (HTTP ' + res.status + ')'); return; }
                const created = await res.json();
                await this.reloadBlocks();
                this[field] = created.code;
                this.overrides[field] = null;
                this.editing[field] = false;
                this.flashBlockMsg('새 옵션 추가됨: ' + label);
            } finally { this.blockBusy = false; }
        },
        async deleteSelectedBlock(field) {
            if (this.blockBusy) return;
            const blk = this.find(this._listFor(field), this[field]);
            if (!blk || !blk.id) { this.flashBlockMsg('기본 데이터라 삭제 불가'); return; }
            if (!window.confirm('선택한 옵션을 삭제할까요?\n' + blk.label)) return;
            this.blockBusy = true;
            try {
                const res = await fetch('/api/v1/prompt-builder/blocks/' + blk.id, {
                    method: 'DELETE', credentials: 'include',
                });
                if (!res.ok) { this.flashBlockMsg('삭제 실패 (HTTP ' + res.status + ')'); return; }
                this[field] = '';
                this.overrides[field] = null;
                this.editing[field] = false;
                await this.reloadBlocks();
                this.flashBlockMsg('삭제됨');
            } finally { this.blockBusy = false; }
        },

        // ── 본문 조립 ─────────────────────────────────────
        // 완성 프롬프트에 들어가는 '최종 패턴 본문'. 구조 약속·섹션 수가 모두
        // 이 값을 단일 진실원천으로 삼는다. 섹션 수는 사용자 조절 대상이 아니며
        // 패턴 본문(빌트인 원본 또는 수정 원문)이 섹션 구조를 그대로 정한다.
        get finalPatternBody() {
            if (this.overrides.pattern !== null) return this.overrides.pattern;
            const p = this.find(this.patterns, this.pattern);
            return p ? p.body : '(블록을 선택하세요)';
        },
        // 최종 패턴 본문을 파싱해 섹션을 순서대로 반환(순수 함수 위임, structure.js)
        patternSections() {
            return (typeof pbParsePatternSections === 'function')
                ? pbParsePatternSections(this.finalPatternBody) : [];
        },
        // 생성될 섹션 수(패턴 본문에서 도출) — 표시 전용, 사용자 조절 불가.
        get derivedSectionCount() { return this.patternSections().length; },

        get builtPrompt() {
            // F11: 전용 프롬프트 프리셋 적용 시 완성 텍스트를 그대로 반환
            if (this.fullPromptOverride) return this.fullPromptOverride;
            const D = this.divider;
            return [
                '제목: {title}',
                '카테고리: {category}',
                '키워드: {keywords}',
                '',
                D, this.bodyFor('persona', this.personas), D,
                '',
                D, this.bodyFor('reader', this.readers), D,
                '',
                D, this.bodyFor('common', this.commons), D,
                '',
                D, this.finalPatternBody, D,
                '',
                D, this.bodyFor('tone', this.tones), D,
                '',
                D, this.buildStructure(), D,
            ].join('\n');
        },

        // 구조 약속을 '실제 패턴 본문'에서 유도(순수 함수 위임, structure.js).
        // 섹션 수·표/목록이 패턴과 항상 일치하고, 글자수는 설정값을 쓴다.
        buildStructure() {
            if (typeof pbBuildStructure !== 'function') return '';
            return pbBuildStructure(this.patternSections(), {
                introChars: this.introChars,
                sectionChars: this.sectionChars,
                outroChars: this.outroChars,
            });
        },

        get charCount() { return this.builtPrompt.length; },
        get lineCount() { return this.builtPrompt.split('\n').length; },

        clearAll() {
            this.persona = '';
            this.reader = '';
            this.pattern = '';
            this.tone = '';
            this.fullPromptOverride = ''; // F11: 전용 프롬프트 해제 → 4축 조합 복귀
        },

        // ── 액션: 복사 / 반영 ─────────────────────────────
        async copyToClipboard() {
            if (!this.isComplete()) return;
            const text = this.builtPrompt;
            try {
                if (navigator.clipboard && window.isSecureContext) {
                    await navigator.clipboard.writeText(text);
                } else {
                    const ta = this.$refs.output;
                    ta.removeAttribute('readonly');
                    ta.select();
                    document.execCommand('copy');
                    ta.setAttribute('readonly', '');
                    window.getSelection()?.removeAllRanges();
                }
                this.justCopied = true;
                setTimeout(() => { this.justCopied = false; }, 1500);
            } catch (e) {
                console.error('[prompt-builder] 복사 실패:', e);
                alert('복사에 실패했습니다. 미리보기 영역을 직접 선택해 복사해주세요.');
            }
        },

        applyToTemplate() {
            if (!this.isComplete()) return;
            if (typeof this.onApply === 'function') {
                this.onApply(this.builtPrompt);
                this.justApplied = true;
                setTimeout(() => { this.justApplied = false; }, 1500);
            }
        },
    };
}

// 별도 페이지 진입용 래퍼 (기존 호환)
function promptBuilderApp() {
    return createPromptBuilderState({ mode: 'page', blocksDataElementId: 'blocks-data' });
}
