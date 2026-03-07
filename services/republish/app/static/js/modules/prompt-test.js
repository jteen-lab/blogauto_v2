/** 파이프라인 단계별 테스트 - 상태 관리 및 API 호출 메서드 */

function createPromptTestState() {
    return {
        loading: false,
        // 현재 실행 중인 단계 키 (loading 고착 디버깅용)
        loadingKey: null,
        // 탭 패널 상태
        panelOpen: false,
        activeStep: 1,
        // 인라인 테스트 블록 토글 상태
        showSelectTitle: false,
        showRecombine: false,
        showReferences: false,
        showContent: false,
        showInternalLinks: false,
        showImage: false,
        showSubstitution: false,
        showFullPipeline: false,
        // 테스트 블로그 선택
        testBlogId: null,
        // 각 단계 결과 (문자열 키 기반)
        results: {
            selectTitle: null,
            recombine: null,
            references: null,
            content: null,
            internalLinks: null,
            image: null,
            substitution: null,
            fullPipeline: null,
        },
        // Step 입력 필드
        titleText: '',
        searchQuery: '',
        contentTitle: '',
        contentRef: '',
        internalLinksContent: '',
        imageTitle: '',
        dryRun: true,
        // 현재 진행 중인 AbortController (요청 취소용)
        _abortController: null,
    };
}

const promptTestMethods = {
    getTestModuleId() {
        return this.module?.id;
    },
    getTestBlogId() {
        return parseInt(this.promptTest.testBlogId) || null;
    },
    getSelectedBlogOptions() {
        const selected = this.promptModule.selectedBlogs || [];
        const allBlogs = [
            ...(this.promptModule.matchedBlogs || []),
            ...(this.promptModule.unmatchedBlogs || []),
            ...(this.promptModule.blogs || []),
        ];
        const seen = new Set();
        const result = [];
        for (const id of selected) {
            if (seen.has(id)) continue;
            seen.add(id);
            const blog = allBlogs.find(b => b.id === id);
            result.push({ id, name: blog ? blog.name : `블로그 ${id}` });
        }
        return result;
    },

    /**
     * API 호출 헬퍼 (타임아웃 + AbortController 지원)
     * 타임아웃: 90초 (AI API 호출 대기 고려)
     */
    async _testFetch(url, body) {
        // 이전 요청이 있으면 취소
        if (this.promptTest._abortController) {
            this.promptTest._abortController.abort();
        }
        const controller = new AbortController();
        this.promptTest._abortController = controller;

        // 90초 타임아웃
        const timeoutId = setTimeout(() => controller.abort(), 90000);

        try {
            const resp = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(body),
                signal: controller.signal,
            });
            clearTimeout(timeoutId);

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || `HTTP ${resp.status}`);
            }
            return await resp.json();
        } catch (e) {
            clearTimeout(timeoutId);
            if (e.name === 'AbortError') {
                throw new Error('요청이 타임아웃되었거나 취소되었습니다 (90초 초과)');
            }
            throw e;
        } finally {
            this.promptTest._abortController = null;
        }
    },

    // Step: 제목 선택
    async runStepSelectTitle() {
        console.log('[PromptTest] runStepSelectTitle 호출됨');
        const moduleId = this.getTestModuleId();
        const blogId = this.getTestBlogId();
        if (!moduleId || !blogId) return this._setTestError('selectTitle', '모듈 ID와 블로그를 선택하세요');
        this._startTest('selectTitle');
        try {
            const data = await this._testFetch('/api/v1/generation/test/select-title', {
                blog_id: blogId, module_id: moduleId,
            });
            this.promptTest.results.selectTitle = data;
            if (data.success && data.result?.selected_title) {
                const sel = data.result.selected_title;
                this.promptTest.titleText = sel.title || '';
                this.promptTest.searchQuery = sel.title || '';
                this.promptTest.contentTitle = sel.title || '';
                this.promptTest.imageTitle = sel.title || '';
            }
        } catch (e) { this._setTestError('selectTitle', e.message); }
        finally { this._endTest(); }
    },

    // Step: 제목 재조합
    async runStepRecombine() {
        console.log('[PromptTest] runStepRecombine 호출됨', {
            loading: this.promptTest.loading,
            loadingKey: this.promptTest.loadingKey,
            styles: this.promptModule.titleRecombine.selectedStyles,
        });
        const moduleId = this.getTestModuleId();
        if (!moduleId) return this._setTestError('recombine', '모듈 ID가 필요합니다');
        const blogId = this.getTestBlogId();
        if (!blogId) return this._setTestError('recombine', '블로그를 선택하세요');
        const titleText = this.promptTest.titleText?.trim();
        if (!titleText) return this._setTestError('recombine', '제목을 입력하세요');
        this._startTest('recombine');
        try {
            const data = await this._testFetch('/api/v1/generation/test/recombine-title', {
                module_id: moduleId, blog_id: blogId, title_text: titleText,
                styles: this.promptModule.titleRecombine.selectedStyles || [],
            });
            this.promptTest.results.recombine = data;
            if (data.success && data.result?.recombined_title) {
                this.promptTest.searchQuery = data.result.recombined_title;
                this.promptTest.contentTitle = data.result.recombined_title;
                this.promptTest.imageTitle = data.result.recombined_title;
            }
        } catch (e) { this._setTestError('recombine', e.message); }
        finally { this._endTest(); }
    },

    // 스타일 아이콘 매핑
    getStyleIcon(style) {
        const icons = {
            emotional: '\uD83D\uDC96',
            practical: '\uD83D\uDCA1',
            question: '\u2753',
            viral: '\uD83D\uDD25',
            minimal: '\u2728',
        };
        return icons[style] || '\uD83D\uDD04';
    },

    // Step: 참조자료 수집 (UI 참조자료 설정 + 블로그 reference_ai 사용)
    async runStepReferences() {
        console.log('[PromptTest] runStepReferences 호출됨');
        const moduleId = this.getTestModuleId();
        const blogId = this.getTestBlogId();
        const query = this.promptTest.searchQuery?.trim();
        if (!moduleId) return this._setTestError('references', '모듈 ID가 필요합니다');
        if (!blogId) return this._setTestError('references', '블로그를 선택하세요');
        if (!query) return this._setTestError('references', '검색어를 입력하세요');
        this._startTest('references');
        try {
            const ref = this.promptModule.reference || {};
            const data = await this._testFetch('/api/v1/generation/test/collect-references', {
                module_id: moduleId,
                search_query: query,
                blog_id: blogId,
                ref_settings: {
                    max_search: ref.maxSearch || 30,
                    crawl_target: ref.crawlTarget || 10,
                    summary_count: ref.summaryCount || 3,
                    summary_method: ref.summaryMethod || 'ai',
                    summary_style: ref.summaryStyle || 'concise',
                    algorithm_type: ref.algorithmType || 'textrank',
                    max_length: ref.maxLength || 500,
                },
            });
            this.promptTest.results.references = data;
            if (data.success && data.result?.reference_injection) {
                this.promptTest.contentRef = data.result.reference_injection;
            }
        } catch (e) { this._setTestError('references', e.message); }
        finally { this._endTest(); }
    },

    // Step: 글 생성
    async runStepContent() {
        console.log('[PromptTest] runStepContent 호출됨');
        const moduleId = this.getTestModuleId();
        const blogId = this.getTestBlogId();
        const title = this.promptTest.contentTitle?.trim();
        if (!moduleId || !blogId) return this._setTestError('content', '모듈 ID와 블로그를 선택하세요');
        if (!title) return this._setTestError('content', '제목을 입력하세요');
        this._startTest('content');
        try {
            const data = await this._testFetch('/api/v1/generation/test/generate-content', {
                module_id: moduleId, blog_id: blogId,
                title: title, reference_text: this.promptTest.contentRef || null,
            });
            this.promptTest.results.content = data;
            // 글 생성 성공 시 내부링크 테스트용 콘텐츠 저장
            if (data.success && data.result?.content_markdown) {
                this.promptTest.internalLinksContent = data.result.content_markdown;
            }
        } catch (e) { this._setTestError('content', e.message); }
        finally { this._endTest(); }
    },

    // Step: 내부링크 추가
    async runStepInternalLinks() {
        console.log('[PromptTest] runStepInternalLinks 호출됨');
        const moduleId = this.getTestModuleId();
        const blogId = this.getTestBlogId();
        const title = this.promptTest.contentTitle?.trim();
        const content = this.promptTest.internalLinksContent?.trim();
        if (!moduleId || !blogId) return this._setTestError('internalLinks', '모듈 ID와 블로그를 선택하세요');
        if (!content) return this._setTestError('internalLinks', '글 생성 테스트를 먼저 실행하세요');
        this._startTest('internalLinks');
        try {
            const data = await this._testFetch('/api/v1/generation/test/add-internal-links', {
                blog_id: blogId, module_id: moduleId, title: title || '', content: content,
            });
            this.promptTest.results.internalLinks = data;
        } catch (e) { this._setTestError('internalLinks', e.message); }
        finally { this._endTest(); }
    },

    // Step: 이미지 생성
    async runStepImage() {
        console.log('[PromptTest] runStepImage 호출됨');
        const moduleId = this.getTestModuleId();
        const blogId = this.getTestBlogId();
        const title = this.promptTest.imageTitle?.trim();
        if (!moduleId || !blogId) return this._setTestError('image', '모듈 ID와 블로그를 선택하세요');
        if (!title) return this._setTestError('image', '제목을 입력하세요');
        this._startTest('image');
        try {
            const data = await this._testFetch('/api/v1/generation/test/generate-image', {
                module_id: moduleId, blog_id: blogId, title: title,
            });
            this.promptTest.results.image = data;
        } catch (e) { this._setTestError('image', e.message); }
        finally { this._endTest(); }
    },

    // Step: 변환 및 치환 적용
    async runStepSubstitution() {
        console.log('[PromptTest] runStepSubstitution 호출됨');
        const blogId = this.getTestBlogId();
        const content = this.promptTest.internalLinksContent?.trim();
        if (!blogId) return this._setTestError('substitution', '블로그를 선택하세요');
        if (!content) return this._setTestError('substitution', '글 생성 테스트를 먼저 실행하세요');
        this._startTest('substitution');
        try {
            const data = await this._testFetch('/api/v1/generation/test/substitution-html', {
                blog_id: blogId, content: content,
                text_replace_enabled: this.promptModule?.textReplaceEnabled ?? true,
            });
            this.promptTest.results.substitution = data;
        } catch (e) { this._setTestError('substitution', e.message); }
        finally { this._endTest(); }
    },

    // Step: 전체 파이프라인
    async runStepFullPipeline() {
        console.log('[PromptTest] runStepFullPipeline 호출됨');
        const moduleId = this.getTestModuleId();
        const blogId = this.getTestBlogId();
        if (!moduleId || !blogId) return this._setTestError('fullPipeline', '모듈 ID와 블로그를 선택하세요');
        this._startTest('fullPipeline');
        try {
            const data = await this._testFetch('/api/v1/generation/test/full-pipeline', {
                blog_id: blogId, module_id: moduleId, dry_run: this.promptTest.dryRun,
            });
            this.promptTest.results.fullPipeline = data;
        } catch (e) { this._setTestError('fullPipeline', e.message); }
        finally { this._endTest(); }
    },

    /**
     * 테스트 시작 - loading 상태 활성화
     * 이전 요청이 있으면 무조건 취소 (loading 상태와 무관하게)
     */
    _startTest(key) {
        // 이전 AbortController가 남아있으면 무조건 취소 (loading 상태 무관)
        if (this.promptTest._abortController) {
            console.warn('[PromptTest] 이전 요청 취소:', this.promptTest.loadingKey);
            this.promptTest._abortController.abort();
            this.promptTest._abortController = null;
        }
        // loading 상태 초기화 후 재설정 (Alpine.js 반응성 보장)
        this.promptTest.loading = false;
        this.promptTest.loadingKey = null;
        // 이전 결과 제거 (재실행 시 시각적 변화를 위해)
        this.promptTest.results[key] = null;
        // 새 테스트 시작
        this.promptTest.loading = true;
        this.promptTest.loadingKey = key;
    },

    /**
     * 테스트 종료 - loading 상태 해제
     * _abortController가 남아있으면 정리 (안전장치)
     */
    _endTest() {
        this.promptTest.loading = false;
        this.promptTest.loadingKey = null;
        if (this.promptTest._abortController) {
            this.promptTest._abortController = null;
        }
    },

    /**
     * 테스트 에러 설정 - loading도 함께 해제
     */
    _setTestError(key, msg) {
        this.promptTest.results[key] = { success: false, error: msg };
        this.promptTest.loading = false;
        this.promptTest.loadingKey = null;
    },

    clearTestResult(key) {
        this.promptTest.results[key] = null;
    },

    /**
     * 모든 테스트 결과 초기화 + loading 상태 해제
     * 진행 중인 요청도 취소
     */
    clearAllTestResults() {
        // 진행 중인 요청 취소
        if (this.promptTest._abortController) {
            this.promptTest._abortController.abort();
            this.promptTest._abortController = null;
        }
        const keys = Object.keys(this.promptTest.results);
        for (const k of keys) this.promptTest.results[k] = null;
        this.promptTest.loading = false;
        this.promptTest.loadingKey = null;
    },
};

window.createPromptTestState = createPromptTestState;
window.promptTestMethods = promptTestMethods;
