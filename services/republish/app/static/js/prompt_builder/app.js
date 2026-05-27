/**
 * 프롬프트 빌더 — 재사용 가능 Alpine.js state 팩토리.
 *
 * 두 군데에서 같은 로직을 사용:
 *  1) 별도 페이지 /prompt-builder  → mode='page'   (복사 버튼)
 *  2) 모듈 폼 안 확장 패널         → mode='embedded' (반영 버튼 + onApply 콜백)
 *
 * 기능:
 *  - 페르소나/독자수준/섹션패턴/시작톤 4축 라디오 선택
 *  - 프리셋 1클릭 적용 + 어울리는 카테고리 표기 (기본 10종 + 사용자 커스텀)
 *  - 사용자 커스텀 프리셋 localStorage 저장 + 중복 조합 차단
 *  - 섹션 수 4~8 가변 + 표·목록 자동 재배치
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
        blocksDataElementId: opts.blocksDataElementId || null,
        expanded: false, // embedded 모드에서 폼 안 접기/펼치기

        // ── 데이터 ────────────────────────────────────────
        personas: [],
        readers: [],
        patterns: [],
        tones: [],
        builtinPresets: [],
        customPresets: [],
        commonRules: '',
        structure: '',
        divider: '',

        // ── 선택값 ────────────────────────────────────────
        persona: '',
        reader: '',
        pattern: '',
        tone: '',
        sectionCount: 6,

        // ── 임시 수정(EDIT) ───────────────────────────────
        overrides: { persona: null, reader: null, pattern: null, tone: null },
        editing: { persona: false, reader: false, pattern: false, tone: false },

        // ── UI 상태 ───────────────────────────────────────
        justCopied: false,
        justApplied: false,
        newPresetName: '',
        presetWarning: '',

        // ── 초기화 ────────────────────────────────────────
        init() {
            this.loadBlocksData();
            this.loadCustomPresets();
            this.$watch('persona', () => { this.overrides.persona = null; this.editing.persona = false; });
            this.$watch('reader', () => { this.overrides.reader = null; this.editing.reader = false; });
            this.$watch('pattern', () => { this.overrides.pattern = null; this.editing.pattern = false; });
            this.$watch('tone', () => { this.overrides.tone = null; this.editing.tone = false; });
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
                this.builtinPresets = data.presets || [];
                this.commonRules = data.common_rules || '';
                this.structure = data.structure || '';
                this.divider = data.divider || '─'.repeat(40);
            } catch (e) {
                console.error('[prompt-builder] blocks-data 파싱 실패:', e);
            }
        },

        // ── 프리셋 ─────────────────────────────────────────
        get presets() {
            // 기본 + 커스텀 합쳐서 노출 (커스텀이 뒤에 옴)
            return [...this.builtinPresets, ...this.customPresets];
        },

        applyPreset(code) {
            const p = this.presets.find((x) => x.code === code);
            if (!p) return;
            this.persona = p.persona;
            this.reader = p.reader;
            this.pattern = p.pattern;
            this.tone = p.tone;
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
        isComplete() {
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
                const lists = { persona: this.personas, reader: this.readers, pattern: this.patterns, tone: this.tones };
                const list = lists[field];
                if (!list) return;
                let body = this.find(list, this[field])?.body || '';
                if (field === 'pattern') {
                    body = this.renderPatternBody(this.find(list, this[field]));
                }
                this.overrides[field] = body;
            }
        },
        resetOverride(field) {
            this.overrides[field] = null;
            this.editing[field] = false;
        },

        // ── 패턴 본문 동적 재생성 ─────────────────────────
        renderPatternBody(pattern) {
            if (!pattern) return '(블록을 선택하세요)';
            const n = this.sectionCount;
            const parsed = this.parsePatternBody(pattern.body);
            const layout = this.computeLayout(n);
            const letters = 'ABCDEFGHIJKL'.split('');
            const pools = { table: [...parsed.tables], list: [...parsed.lists], other: [...parsed.others] };
            const fallback = { table: '추가 비교·정리표', list: '추가 정리 목록', other: '심화·확장 관점' };
            const newLines = [];
            for (let i = 0; i < n; i++) {
                const role = layout[i];
                const pool = pools[role];
                const content = (pool && pool.length) ? pool.shift() : fallback[role];
                const suffix = (
                    role === 'table' ? ' ← 표 반드시 포함' :
                    role === 'list' ? ' ← 번호/불릿 목록 반드시 포함' :
                    ''
                );
                newLines.push(`- ${letters[i]}: ${content}${suffix}`);
            }
            return [parsed.header, ...newLines].join('\n');
        },
        parsePatternBody(body) {
            const sectionRe = /^- ([A-Z]):\s*(.+)$/;
            const tables = [], lists = [], others = [], headerLines = [];
            for (const raw of body.split('\n')) {
                const m = raw.match(sectionRe);
                if (!m) { headerLines.push(raw); continue; }
                const content = m[2].replace(/\s*←.*$/, '').trim();
                if (/← 표/.test(raw)) tables.push(content);
                else if (/← (번호|불릿|번호\/불릿) 목록/.test(raw)) lists.push(content);
                else others.push(content);
            }
            return { header: headerLines.join('\n'), tables, lists, others };
        },
        computeLayout(n) {
            const layout = new Array(n).fill('other');
            layout[1] = 'table';
            layout[2] = 'list';
            if (n >= 5) {
                layout[n - 2] = 'table';
                layout[n - 1] = 'list';
            }
            return layout;
        },

        // ── 본문 조립 ─────────────────────────────────────
        get builtPrompt() {
            const D = this.divider;
            const personaBody = this.bodyFor('persona', this.personas);
            const readerBody = this.bodyFor('reader', this.readers);
            const patternBody = this.overrides.pattern !== null
                ? this.overrides.pattern
                : this.renderPatternBody(this.find(this.patterns, this.pattern));
            const toneBody = this.bodyFor('tone', this.tones);
            const structure = this.buildStructure();

            return [
                '제목: {title}',
                '카테고리: {category}',
                '키워드: {keywords}',
                '',
                D, personaBody, D,
                '',
                D, readerBody, D,
                '',
                D, this.commonRules, D,
                '',
                D, patternBody, D,
                '',
                D, toneBody, D,
                '',
                D, structure, D,
            ].join('\n');
        },

        buildStructure() {
            const n = this.sectionCount;
            const letters = 'ABCDEFGHIJKL'.split('');
            const layout = this.computeLayout(n);
            const mid = Math.ceil(n / 2);
            const front = letters.slice(0, mid);
            const back = letters.slice(mid, n);
            const noteFor = (slice, startIdx) => {
                const notes = [];
                slice.forEach((label, j) => {
                    const idx = startIdx + j;
                    if (layout[idx] === 'table') notes.push(`${label} 표 필수`);
                    if (layout[idx] === 'list') notes.push(`${label} 목록 필수`);
                });
                return notes.length ? ` (${notes.join(', ')})` : '';
            };
            const lines = [
                '✦ 구조 약속',
                'STEP 1 ▸ H1(#) 타이틀 + 도입 200자+ (위 시작톤 적용, "안녕하세요" 금지)',
                `STEP 2 ▸ ## 섹션 ${front.join('·')} 각 250자+${noteFor(front, 0)}`,
            ];
            if (back.length) {
                lines.push(`STEP 3 ▸ ## 섹션 ${back.join('·')} 각 250자+${noteFor(back, mid)}`);
                lines.push('STEP 4 ▸ ## 마치며 200자+ (담백한 정리 + 댓글·경험 공유 유도)');
            } else {
                lines.push('STEP 3 ▸ ## 마치며 200자+ (담백한 정리 + 댓글·경험 공유 유도)');
            }
            return lines.join('\n');
        },

        get charCount() { return this.builtPrompt.length; },
        get lineCount() { return this.builtPrompt.split('\n').length; },

        clearAll() {
            this.persona = '';
            this.reader = '';
            this.pattern = '';
            this.tone = '';
            this.sectionCount = 6;
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
