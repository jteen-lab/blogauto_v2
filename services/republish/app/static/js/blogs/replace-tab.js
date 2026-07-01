/**
 * 치환자 탭 Alpine.js 컴포넌트
 * File: app/static/js/blogs/replace-tab.js
 * Last-Updated: 2026-06-25
 */

/**
 * CSS 클래스 치환 고정 태그 목록
 * - 스타일 탭 선택자와 일치하도록 th, td 포함
 * - 링크(a)는 link_styles에서 별도 관리하므로 제외
 */
const CSS_CLASS_TAGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'li', 'table', 'th', 'td', 'blockquote'];

/**
 * 치환자 탭 메인 컴포넌트
 */
function replaceTabApp() {
    return {
        // 상태
        activeSubTab: 'text',
        loading: false,
        saving: false,
        showPreview: false,
        hasCyclicMapping: false,

        // 데이터
        blogId: null,
        // 블로그 플랫폼('wordpress' | 'blogger' | 'other')
        // - css_classes 자동입력 본문 스코프 클래스(entry-content / post-body)를 결정한다.
        platform: '',
        placeholders: {
            html_tags: {},
            css_classes: {},
            link_styles: {
                default_class: '',
                button_class: 'button-link'
            },
            text_replace: []
        },

        // 편집용 배열
        textReplaceRows: [],
        htmlTagRows: [],
        cssClassRows: [],

        // 링크 스타일 (별도 관리)
        linkStyles: {
            default_class: '',
            button_class: 'button-link'
        },

        // 미리보기
        previewHtml: '',
        sampleMarkdown: `# 제목입니다
## 소제목입니다

일반 텍스트 단락입니다. ● 리스트 아이템을 나타내는 기호입니다.

- 리스트 1
- 리스트 2

**굵은 텍스트**와 *기울임 텍스트*가 있습니다.`,

        // 고유 ID 생성용 카운터
        idCounter: 0,

        /**
         * 초기화
         */
        init() {
            // 전역 이벤트 리스너 등록 - blogSettingsApp에서 setBlog 호출 시
            window.addEventListener('blog-settings-loaded', (e) => {
                if (e.detail && e.detail.blogId) {
                    this.blogId = e.detail.blogId;
                    if (e.detail.blog && e.detail.blog.platform) {
                        this.platform = String(e.detail.blog.platform).toLowerCase();
                    }
                    console.log('[replaceTabApp] 이벤트로 blogId 수신:', this.blogId, 'platform:', this.platform);
                    this.load();
                }
            });

            // 탭 재진입 시 서버 최신값을 다시 로드.
            // - 저장하지 않은 편집을 폐기(미저장 값 지속 방지)
            // - 다른 탭에서 저장한 최신 치환자 설정 반영
            window.addEventListener('blog-tab-changed', (e) => {
                if (e.detail && e.detail.tab === 'replace' && this.blogId) {
                    this.load();
                }
            });

            // 이미 blogSettings에 selectedBlog가 설정되어 있는 경우 (탭 전환 시)
            this.tryLoadFromParent();
        },

        /**
         * 부모 컴포넌트에서 blogId 가져오기 시도
         */
        tryLoadFromParent() {
            const settingsEl = document.getElementById('blogSettings');
            if (settingsEl && settingsEl._x_dataStack && settingsEl._x_dataStack[0]) {
                const parentData = settingsEl._x_dataStack[0];
                if (parentData.selectedBlog && parentData.selectedBlog.id) {
                    this.blogId = parentData.selectedBlog.id;
                    if (parentData.selectedBlog.platform) {
                        this.platform = String(parentData.selectedBlog.platform).toLowerCase();
                    }
                    console.log('[replaceTabApp] 부모에서 blogId 가져옴:', this.blogId, 'platform:', this.platform);
                    this.load();
                    return true;
                }
            }
            return false;
        },

        /**
         * URL에서 블로그 ID 추출
         */
        getBlogIdFromUrl() {
            const match = window.location.pathname.match(/\/blogs\/(\d+)/);
            return match ? match[1] : null;
        },

        /**
         * 고유 ID 생성
         */
        generateId() {
            return `row_${++this.idCounter}_${Date.now()}`;
        },

        /**
         * 블로그 플랫폼별 본문 스코프 기본 클래스 반환.
         * - 워드프레스: 'entry-content', 구글 블로거: 'post-body'
         * - 그 외/미상: 'post-content' (폴백)
         * 본문 글에만 스타일이 적용되도록 각 콘텐츠 태그에 부여되는 본문 스코프 클래스.
         * @returns {string} 본문 스코프 베이스 클래스
         */
        contentBaseClass() {
            if (this.platform === 'wordpress') return 'entry-content';
            if (this.platform === 'blogger') return 'post-body';
            return 'post-content';
        },

        /**
         * 데이터 로드
         */
        async load() {
            this.loading = true;
            try {
                const response = await fetch(`/api/v1/blogs/${this.blogId}/settings/placeholders`);
                if (response.ok) {
                    const data = await response.json();
                    // 백엔드 응답 형식: { blog_id, placeholders: {...} }
                    this.placeholders = data.placeholders || {
                        html_tags: {},
                        css_classes: {},
                        link_styles: { default_class: '', button_class: 'button-link' },
                        text_replace: []
                    };
                    this.syncToRows();
                }
            } catch (error) {
                console.error('치환자 데이터 로드 실패:', error);
            } finally {
                this.loading = false;
            }
        },

        /**
         * 객체 데이터를 편집용 배열로 변환
         */
        syncToRows() {
            // 텍스트 치환
            this.textReplaceRows = (this.placeholders.text_replace || []).map(item => ({
                id: this.generateId(),
                find: item.find || '',
                replace: item.replace || ''
            }));

            // HTML 태그 치환
            this.htmlTagRows = Object.entries(this.placeholders.html_tags || {}).map(([from, to]) => ({
                id: this.generateId(),
                from,
                to
            }));

            // CSS 클래스 치환: 고정 태그 목록을 항상 전체 렌더
            // 각 태그의 className은 기존 저장값이 있으면 채우고, 없으면 빈 문자열
            // (a / a.button 등 링크 관련 항목은 link_styles에서 별도 관리하므로 css_classes 표시에서 제외됨)
            const savedCssClasses = this.placeholders.css_classes || {};
            // 고정 목록 + 기존 저장된 비표준 태그(예: 헤딩 다운시프트로 생긴 h6)도
            // 함께 표시·보존해 저장 시 데이터 손실을 막는다. (a/a.button은 링크에서 별도 관리)
            const extraTags = Object.keys(savedCssClasses).filter(
                t => t !== 'a' && t !== 'a.button' && !CSS_CLASS_TAGS.includes(t)
            );
            // 빈값이면 플랫폼별 본문 스코프 기본값 '{본문베이스}'만 자동 입력(태그명 제외).
            // (워드프레스→'entry-content', 블로거→'post-body', 그 외→'post-content')
            // 태그는 '태그' 열에 이미 표시되고 생성 CSS의 선택자에서 자동으로 붙으므로
            // 값에는 넣지 않는다(발행 HTML에 불필요한 태그명 클래스가 생기지 않게).
            // 생성 CSS는 '.entry-content h1 {}' 형태가 된다.
            // 저장값이 있으면 그대로 사용.
            const base = this.contentBaseClass();
            this.cssClassRows = [...CSS_CLASS_TAGS, ...extraTags].map(tag => ({
                id: this.generateId(),
                tag,
                className: savedCssClasses[tag] || base
            }));

            // 링크 스타일 동기화
            // 일반 링크·버튼 링크 모두 다른 본문 태그와 동일하게 본문 베이스를 자동 입력.
            // - 일반 링크: '{본문베이스}' (예: 'entry-content' → CSS '.entry-content a')
            // - 버튼 링크: '{본문베이스} button-link' (예: 'entry-content button-link'
            //   → CSS '.entry-content .button-link a'). 'button-link'는 래퍼 구조 클래스.
            const linkStyles = this.placeholders.link_styles || {};
            this.linkStyles = {
                default_class: linkStyles.default_class || base,
                button_class: linkStyles.button_class || `${base} button-link`
            };
        },

        /**
         * 편집용 배열을 객체 데이터로 변환
         */
        syncFromRows() {
            // 텍스트 치환
            this.placeholders.text_replace = this.textReplaceRows
                .filter(row => row.find && row.replace)
                .map(row => ({ find: row.find, replace: row.replace }));

            // HTML 태그 치환
            this.placeholders.html_tags = {};
            this.htmlTagRows
                .filter(row => row.from && row.to)
                .forEach(row => {
                    this.placeholders.html_tags[row.from] = row.to;
                });

            // CSS 클래스 치환: 고정 목록 중 클래스명이 비지 않은 것만 저장
            // (빈칸은 저장하지 않음 → 백엔드가 자동 스킵하여 기본 태그 그대로 발행)
            this.placeholders.css_classes = {};
            this.cssClassRows
                .filter(row => row.tag && row.className && row.className.trim())
                .forEach(row => {
                    this.placeholders.css_classes[row.tag] = row.className.trim();
                });

            // 링크 스타일 동기화
            this.placeholders.link_styles = {
                default_class: this.linkStyles.default_class || '',
                button_class: this.linkStyles.button_class || 'button-link'
            };

            // 순환 매핑 체크
            this.checkCyclicMapping();
        },

        // === 텍스트 치환 행 관리 ===
        addTextRow() {
            this.textReplaceRows.push({ id: this.generateId(), find: '', replace: '' });
        },
        removeTextRow(index) {
            this.textReplaceRows.splice(index, 1);
        },

        // === HTML 태그 치환 행 관리 ===
        addHtmlRow() {
            this.htmlTagRows.push({ id: this.generateId(), from: '', to: '' });
        },
        removeHtmlRow(index) {
            this.htmlTagRows.splice(index, 1);
            this.checkCyclicMapping();
        },

        // === CSS 클래스 치환 ===
        // 고정 태그 목록(CSS_CLASS_TAGS)을 사용하므로 행 추가/삭제/기본태그추가 없음.
        // 각 태그는 항상 표시되며 클래스명만 입력/수정한다.

        /**
         * 순환 매핑 체크
         */
        checkCyclicMapping() {
            const mappings = {};
            this.htmlTagRows.forEach(row => {
                if (row.from && row.to) {
                    mappings[row.from] = row.to;
                }
            });

            // 간단한 순환 감지
            for (const from in mappings) {
                let current = mappings[from];
                const visited = new Set([from]);
                while (current && mappings[current]) {
                    if (visited.has(current)) {
                        this.hasCyclicMapping = true;
                        return;
                    }
                    visited.add(current);
                    current = mappings[current];
                }
            }
            this.hasCyclicMapping = false;
        },

        /**
         * 프리셋 적용 ('추가' 방식)
         *
         * 기본 자동입력값(플랫폼 본문 스코프 클래스, 예: 'entry-content')은 그대로 두고,
         * 프리셋의 태그별 스타일 클래스를 "추가"한다(대체 아님). 값에는 태그명을 넣지 않으며
         * (태그는 선택자에서 자동으로 붙음), 프리셋 클래스도 태그명을 echo하지 않는다.
         * 예) 'entry-content' → 'entry-content wp-block-heading' (CSS: '.entry-content h1.wp-block-heading')
         *     'post-body'     → 'post-body blogger-heading'   (CSS: '.post-body h1.blogger-heading')
         *
         * @param {string} presetName - 'wordpress' | 'blogger'
         */
        applyPreset(presetName) {
            // 프리셋별 태그 스타일 클래스(전체 14개 태그, 태그명을 echo하지 않음)
            // - 워드프레스: 구텐베르크/표 블록 스타일 훅 클래스
            // - 블로거: 의미 기반 스타일 훅 클래스(blogger-h1처럼 태그를 중복하지 않음)
            const PRESET_TAG_CLASSES = {
                wordpress: {
                    h1: 'wp-block-heading', h2: 'wp-block-heading', h3: 'wp-block-heading',
                    h4: 'wp-block-heading', h5: 'wp-block-heading', h6: 'wp-block-heading',
                    p: 'wp-block-paragraph', ul: 'wp-block-list', ol: 'wp-block-list',
                    li: 'wp-block-list-item', table: 'wp-block-table',
                    th: 'wp-block-table-header', td: 'wp-block-table-cell',
                    blockquote: 'wp-block-quote'
                },
                blogger: {
                    h1: 'blogger-heading', h2: 'blogger-heading', h3: 'blogger-heading',
                    h4: 'blogger-heading', h5: 'blogger-heading', h6: 'blogger-heading',
                    p: 'blogger-text', ul: 'blogger-list', ol: 'blogger-list',
                    li: 'blogger-list-item', table: 'blogger-table',
                    th: 'blogger-table-header', td: 'blogger-table-cell',
                    blockquote: 'blogger-quote'
                }
            };
            const PRESET_LINK_CLASS = {
                wordpress: 'wp-block-link',
                blogger: 'blogger-link'
            };
            // 프리셋별 html_tags(병합) — 워드프레스는 H1 하향 정렬
            const PRESET_HTML_TAGS = {
                wordpress: { h1: 'h2', h2: 'h3', h3: 'h4' },
                blogger: {}
            };

            const tagClasses = PRESET_TAG_CLASSES[presetName];
            if (!tagClasses) return;

            // 클래스 문자열에 특정 클래스를 중복 없이 추가(맨 뒤 append) — 링크용
            const addClass = (current, extra) => {
                if (!extra) return current;
                const parts = (current || '').trim().split(/\s+/).filter(Boolean);
                if (!parts.includes(extra)) parts.push(extra);
                return parts.join(' ');
            };

            // 프리셋 클래스를 태그명 '앞'에 삽입(태그명은 항상 맨 뒤 유지) — 태그용
            // → 최종 순서: '기본클래스 + 프리셋클래스 + 태그명'
            //   예) 'entry-content h1' + wp-block-heading → 'entry-content wp-block-heading h1'
            const addClassBeforeTag = (current, extra, tag) => {
                let parts = (current || '').trim().split(/\s+/).filter(Boolean);
                const hasTag = parts.includes(tag);
                parts = parts.filter(p => p !== tag);          // 태그명 분리
                if (extra && !parts.includes(extra)) parts.push(extra); // 프리셋 클래스 추가
                if (hasTag) parts.push(tag);                   // 태그명을 맨 뒤로 재배치
                return parts.join(' ');
            };

            // 기존 행(본문 스코프 + 태그명 자동입력)에 프리셋 클래스를 태그명 앞에 추가
            this.cssClassRows = this.cssClassRows.map(row => ({
                ...row,
                className: addClassBeforeTag(row.className, tagClasses[row.tag], row.tag)
            }));

            // 일반 링크 기본 클래스에도 다른 태그와 동일하게 프리셋 클래스를 'a' 앞에 추가
            // (순서: 본문베이스 + 프리셋 + a). 버튼 클래스는 구조 유지.
            this.linkStyles.default_class = addClassBeforeTag(
                this.linkStyles.default_class, PRESET_LINK_CLASS[presetName], 'a'
            );

            // html_tags 병합(기존 값 보존) — 편집 행(htmlTagRows)에 추가/갱신
            // (syncFromRows가 html_tags를 htmlTagRows에서 재구성하므로 행에 반영해야 보존됨)
            const presetHtml = PRESET_HTML_TAGS[presetName];
            Object.keys(presetHtml).forEach(from => {
                const existing = this.htmlTagRows.find(r => r.from === from);
                if (existing) {
                    existing.to = presetHtml[from];
                } else {
                    this.htmlTagRows.push({ id: this.generateId(), from, to: presetHtml[from] });
                }
            });

            // 편집 배열 → placeholders 반영
            this.syncFromRows();

            if (typeof showSuccessMessage === 'function') {
                showSuccessMessage(`${presetName} 프리셋 클래스가 추가되었습니다.`);
            }
        },

        /**
         * CSS 클래스 치환값 초기화
         *
         * 이미 저장·편집한 CSS 클래스명(프리셋 추가분 포함)을 모두 지우고
         * 플랫폼 본문 스코프 기본값('{본문베이스}')으로 되돌린다. 일반 링크 기본
         * 클래스도 함께 초기화한다. 저장을 눌러야 서버에 반영된다.
         */
        resetCssClasses() {
            if (!confirm('CSS 클래스 치환값을 플랫폼 기본값으로 초기화할까요?\n(저장을 눌러야 반영됩니다)')) {
                return;
            }
            const base = this.contentBaseClass();
            this.cssClassRows = this.cssClassRows.map(row => ({ ...row, className: base }));
            this.linkStyles.default_class = base;
            this.linkStyles.button_class = `${base} button-link`;
            this.syncFromRows();
            if (typeof showSuccessMessage === 'function') {
                showSuccessMessage('기본값으로 초기화되었습니다. 저장을 눌러 반영하세요.');
            }
        },

        /**
         * 저장
         */
        async save() {
            // 부모에서 최신 blogId 동기화
            const settingsEl = document.getElementById('blogSettings');
            if (settingsEl && settingsEl._x_dataStack && settingsEl._x_dataStack[0] && settingsEl._x_dataStack[0].selectedBlog) {
                this.blogId = settingsEl._x_dataStack[0].selectedBlog.id;
            }
            if (!this.blogId || this.blogId === 'null') {
                console.error('저장 실패: 유효한 blog_id가 없습니다.');
                if (typeof showErrorMessage === 'function') {
                    showErrorMessage('블로그 ID를 찾을 수 없습니다. 페이지를 새로고침해주세요.');
                }
                return;
            }

            this.saving = true;
            this.syncFromRows();

            try {
                // 백엔드 스키마에 맞게 { placeholders: {...} } 형식으로 전송
                const response = await fetch(`/api/v1/blogs/${this.blogId}/settings/placeholders`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ placeholders: this.placeholders })
                });

                if (response.ok) {
                    if (typeof showSuccessMessage === 'function') {
                        showSuccessMessage('치환자 설정이 저장되었습니다.');
                    }
                    // 스타일 탭에 치환자 변경 알림 (CSS 재생성용)
                    window.dispatchEvent(new CustomEvent('placeholders-saved', {
                        detail: { blogId: this.blogId, placeholders: this.placeholders }
                    }));
                } else {
                    const errorData = await response.json().catch(() => ({}));
                    console.error('저장 응답 오류:', errorData);
                    throw new Error('저장 실패');
                }
            } catch (error) {
                console.error('저장 실패:', error);
                if (typeof showErrorMessage === 'function') {
                    showErrorMessage('저장에 실패했습니다.');
                }
            } finally {
                this.saving = false;
            }
        },

        /**
         * 미리보기 모달 표시
         */
        async showPreviewModal() {
            this.syncFromRows();
            this.showPreview = true;

            try {
                const response = await fetch(`/api/v1/blogs/${this.blogId}/settings/placeholders/preview`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        placeholders: this.placeholders,
                        sample: this.sampleMarkdown
                    })
                });

                if (response.ok) {
                    const data = await response.json();
                    this.previewHtml = data.html || this.sampleMarkdown;
                } else {
                    // API 실패 시 클라이언트 사이드 간단 변환
                    this.previewHtml = this.simplePreview();
                }
            } catch (error) {
                console.error('미리보기 실패:', error);
                this.previewHtml = this.simplePreview();
            }
        },

        /**
         * 클라이언트 사이드 간단 미리보기
         */
        simplePreview() {
            let html = this.sampleMarkdown;

            // 텍스트 치환
            this.textReplaceRows.forEach(row => {
                if (row.find && row.replace) {
                    html = html.split(row.find).join(row.replace);
                }
            });

            return html.replace(/\n/g, '<br>');
        },

        /**
         * JSON 내보내기
         */
        exportJson() {
            this.syncFromRows();
            const dataStr = JSON.stringify(this.placeholders, null, 2);
            const blob = new Blob([dataStr], { type: 'application/json' });
            const url = URL.createObjectURL(blob);

            const a = document.createElement('a');
            a.href = url;
            a.download = `placeholders_blog_${this.blogId}.json`;
            a.click();
            URL.revokeObjectURL(url);

            if (typeof showSuccessMessage === 'function') {
                showSuccessMessage('JSON 파일이 다운로드되었습니다.');
            }
        },

        /**
         * JSON 가져오기
         */
        importJson(event) {
            const file = event.target.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = (e) => {
                try {
                    const data = JSON.parse(e.target.result);
                    this.placeholders = {
                        html_tags: data.html_tags || {},
                        css_classes: data.css_classes || {},
                        text_replace: data.text_replace || []
                    };
                    this.syncToRows();
                    if (typeof showSuccessMessage === 'function') {
                        showSuccessMessage('JSON 파일을 가져왔습니다.');
                    }
                } catch (error) {
                    console.error('JSON 파싱 실패:', error);
                    if (typeof showErrorMessage === 'function') {
                        showErrorMessage('올바른 JSON 파일이 아닙니다.');
                    }
                }
            };
            reader.readAsText(file);

            // 파일 입력 초기화
            event.target.value = '';
        }
    };
}
