/** 프롬프트 모듈 폼 - 상태 관리 및 메서드 (템플릿: prompt-form-template*.js) */

// 프롬프트 모듈 초기 상태 생성
function createPromptModuleState() {
    return {
        // 카테고리 관련
        topics: [],
        expandedTopics: [],
        selectedCategories: [], // [{topic_id, subtopic_id}]
        categoriesLoading: false,

        // 블로그 관련
        blogs: [],              // 전체 블로그 목록 (플랫폼별 필터용)
        activeBlogTab: 'wordpress',  // 현재 선택된 플랫폼 탭
        matchedBlogs: [],
        unmatchedBlogs: [],
        selectedBlogs: [],
        blogsLoading: false,
        showUnmatchedBlogs: false,

        // 제목 재조합 설정
        titleRecombine: {
            enabled: true,
            selectedStyles: ['emotional', 'practical'],
            countPerStyle: 3,
            customPrompt: ''
        },

        // 제목 스타일 옵션
        titleStyles: [
            { value: 'emotional', label: '감성형', icon: '💖' },
            { value: 'practical', label: '실용형', icon: '💡' },
            { value: 'question', label: '질문형', icon: '❓' },
            { value: 'viral', label: '바이럴', icon: '🔥' },
            { value: 'minimal', label: '심플', icon: '✨' }
        ],

        // AI 프로바이더 옵션
        aiProviders: [
            { value: 'openai', label: 'ChatGPT' },
            { value: 'claude', label: 'Claude' },
            { value: 'gemini', label: 'Gemini' }
        ],

        // 글 생성 설정
        contentGeneration: {
            enabled: false,
            provider: 'openai',   // 폴백용 기본값 (블로그 AI 설정에서 덮어씀)
            temperature: 0.7,
            maxTokens: 4096,
            topP: 0.9,
            frequencyPenalty: 0,
            presencePenalty: 0,
            topK: 40,
            systemPrompt: '당신은 전문적인 블로그 콘텐츠 작성자입니다. SEO에 최적화된 고품질 블로그 글을 작성해주세요.',
            userPromptTemplate: '제목: {title}\n\n위 제목으로 블로그 글을 작성해주세요.\n카테고리: {category}\n키워드: {keywords}',
            showAdvanced: false
        },

        // 참조자료 수집 설정 (필수 - 항상 활성화)
        reference: {
            enabled: true,
            maxSearch: 30,
            crawlTarget: 10,
            summaryCount: 3,
            summaryMethod: 'ai',
            aiProvider: 'openai',   // 폴백용 기본값 (블로그 AI 설정에서 덮어씀)
            aiModel: 'gpt-4.1-mini', // 폴백용 기본값 (블로그 AI 설정에서 덮어씀)
            summaryStyle: 'concise',
            algorithmType: 'textrank',
            maxLength: 500
        },

        // 내부링크 설정
        internalLinks: {
            enabled: false,
            similarityThreshold: 75,
            introCount: 3,
            introLinkType: 'button',
            bodyCount: 1,
            bodyLinkType: 'quote',
            conclusionCount: 3,
            conclusionListStyle: 'dash'
        },

        // 텍스트 치환 활성화
        textReplaceEnabled: true,

        // 이미지 생성 설정
        imageGeneration: {
            enabled: false,
            provider: 'dalle',    // 폴백용 기본값 (블로그 AI 설정에서 덮어씀)
            promptTemplate: '{title}에 대한 전문적인 블로그 헤더 이미지, {keywords} 포함, 현대적인 디자인, 깔끔한 구성',
            imagesPerPost: 1,
            dalle: {
                size: '1024x1024',
                quality: 'standard',
                style: 'vivid'
            },
            nanobanana: {
                aspectRatio: '16:9',
                style: 'realistic'
            },
            titleOverlay: false,        // AI 이미지에 제목 오버레이
            coverSource: 'template',    // both 모드: 대표이미지 소스
            sectionSource: 'ai'         // both 모드: 섹션이미지 소스
        },

        // 블로그별 이미지 모드 캐시 (blog_id → image_mode)
        blogImageModes: {}
    };
}

// 프롬프트 모듈 메서드 믹스인
const promptModuleMethods = {
    async loadCategories() {
        this.promptModule.categoriesLoading = true;
        try {
            const resp = await fetch('/api/v1/categories', { credentials: 'include' });
            if (resp.ok) {
                const data = await resp.json();
                this.promptModule.topics = data.categories || [];
            }
        } catch (e) { console.error('카테고리 로드 실패:', e); }
        finally { this.promptModule.categoriesLoading = false; }
    },

    async loadBlogs() {
        this.promptModule.blogsLoading = true;
        try {
            const resp = await fetch('/api/v1/blogs', { credentials: 'include' });
            if (resp.ok) {
                const data = await resp.json();
                this.promptModule.blogs = data.blogs || data || [];
            }
        } catch (e) { console.error('블로그 로드 실패:', e); }
        finally { this.promptModule.blogsLoading = false; }
    },

    getBlogsByPlatform(platform) {
        return this.promptModule.blogs.filter(b => b.platform === platform);
    },
    getMatchedBlogsByPlatform(platform) {
        return this.promptModule.matchedBlogs.filter(b => b.platform === platform);
    },

    // 편집 모드일 때 기존 데이터로 프롬프트 모듈 초기화
    initPromptModuleFromData() {
        if (!this.isEdit || !this.module?.settings) return;

        const settings = this.module.settings;

        // 제목 재조합 설정
        if (settings.title_recombine) {
            this.promptModule.titleRecombine = {
                enabled: settings.title_recombine.enabled ?? true,
                selectedStyles: settings.title_recombine.styles || ['emotional', 'practical'],
                countPerStyle: settings.title_recombine.count_per_style || 3,
                customPrompt: settings.title_recombine.custom_prompt || ''
            };
        }

        // 참조자료 수집 설정
        if (settings.reference) {
            const ref = settings.reference;
            this.promptModule.reference = {
                enabled: true,
                maxSearch: ref.max_search ?? 30,
                crawlTarget: ref.crawl_target ?? 10,
                summaryCount: ref.summary_count ?? 3,
                summaryMethod: ref.summary_method || 'ai',
                aiProvider: ref.ai_provider || 'openai',
                aiModel: ref.ai_model || 'gpt-4.1-mini',
                summaryStyle: ref.summary_style || 'concise',
                algorithmType: ref.algorithm_type || 'textrank',
                maxLength: ref.max_length ?? 500
            };
        }

        // 글 생성 설정
        if (settings.content_generation) {
            const cg = settings.content_generation;
            this.promptModule.contentGeneration = {
                enabled: cg.enabled ?? false,
                provider: cg.provider || 'openai',
                temperature: cg.temperature ?? 0.7,
                maxTokens: cg.max_tokens || 4096,
                topP: cg.top_p ?? 0.9,
                frequencyPenalty: cg.frequency_penalty ?? 0,
                presencePenalty: cg.presence_penalty ?? 0,
                topK: cg.top_k ?? 40,
                systemPrompt: cg.system_prompt || '',
                userPromptTemplate: cg.user_prompt_template || '',
                showAdvanced: false
            };
        }

        // 이미지 생성 설정
        if (settings.image_generation) {
            const ig = settings.image_generation;
            this.promptModule.imageGeneration = {
                enabled: ig.enabled ?? false,
                provider: ig.provider || 'dalle',
                promptTemplate: ig.prompt_template || '',
                imagesPerPost: ig.images_per_post || 1,
                dalle: ig.dalle || { size: '1024x1024', quality: 'standard', style: 'vivid' },
                nanobanana: ig.nanobanana || { aspectRatio: '16:9', style: 'realistic' },
                titleOverlay: ig.title_overlay ?? false,
                coverSource: ig.cover_source || 'template',
                sectionSource: ig.section_source || 'ai'
            };
        }

        // 내부링크 설정
        if (settings.internal_links) {
            const il = settings.internal_links;
            this.promptModule.internalLinks = {
                enabled: il.enabled ?? false,
                similarityThreshold: il.similarity_threshold ?? 75,
                introCount: il.intro_count ?? 3,
                introLinkType: il.intro_link_type || 'button',
                bodyCount: il.body_count ?? 1,
                bodyLinkType: il.body_link_type || 'quote',
                conclusionCount: il.conclusion_count ?? 3,
                conclusionListStyle: il.conclusion_list_style || 'dash'
            };
        }

        // 텍스트 치환 활성화
        if (settings.text_replace_enabled !== undefined) {
            this.promptModule.textReplaceEnabled = settings.text_replace_enabled;
        }

        // 선택된 카테고리 (편집 모드)
        if (settings.categories && settings.categories.length > 0) {
            this.promptModule.selectedCategories = settings.categories.map(c => ({
                topic_id: c.topic_id,
                subtopic_id: c.subtopic_id || null
            }));
            // 블로그 로드
            this.loadBlogsByCategories();
        }

        // 선택된 블로그 (편집 모드)
        if (settings.blogs && settings.blogs.length > 0) {
            this.promptModule.selectedBlogs = settings.blogs.map(b => b.id || b);
        }
    },

    toggleTopicExpand(topicId) {
        const idx = this.promptModule.expandedTopics.indexOf(topicId);
        if (idx === -1) this.promptModule.expandedTopics.push(topicId);
        else this.promptModule.expandedTopics.splice(idx, 1);
    },
    isTopicSelected(topicId) {
        return this.promptModule.selectedCategories.some(c => c.topic_id === topicId);
    },
    toggleTopicSelection(topicId) {
        if (this.isTopicSelected(topicId)) {
            this.promptModule.selectedCategories = this.promptModule.selectedCategories.filter(c => c.topic_id !== topicId);
        } else {
            this.promptModule.selectedCategories.push({ topic_id: topicId, subtopic_id: null });
        }
        this.onCategoryChange();
    },
    isSubtopicSelected(topicId, subtopicId) {
        return this.promptModule.selectedCategories.some(c => c.topic_id === topicId && c.subtopic_id === subtopicId);
    },
    toggleSubtopicSelection(topicId, subtopicId) {
        const idx = this.promptModule.selectedCategories.findIndex(c => c.topic_id === topicId && c.subtopic_id === subtopicId);
        if (idx !== -1) {
            this.promptModule.selectedCategories.splice(idx, 1);
        } else {
            const topicOnlyIdx = this.promptModule.selectedCategories.findIndex(c => c.topic_id === topicId && c.subtopic_id === null);
            if (topicOnlyIdx !== -1) this.promptModule.selectedCategories.splice(topicOnlyIdx, 1);
            this.promptModule.selectedCategories.push({ topic_id: topicId, subtopic_id: subtopicId });
        }
        this.onCategoryChange();
    },
    onCategoryChange() {
        if (this.promptModule.selectedCategories.length > 0) this.loadBlogsByCategories();
        else { this.promptModule.matchedBlogs = []; this.promptModule.unmatchedBlogs = []; }
    },
    getCategoryDisplayName(cat) {
        const topic = this.promptModule.topics.find(t => t.id === cat.topic_id);
        if (!topic) return `카테고리 ${cat.topic_id}`;
        if (cat.subtopic_id) {
            const sub = topic.subcategories?.find(s => s.id === cat.subtopic_id);
            return sub ? `${topic.name} > ${sub.name}` : topic.name;
        }
        return topic.name + ' (전체)';
    },
    removeCategory(cat) {
        const idx = this.promptModule.selectedCategories.findIndex(c => c.topic_id === cat.topic_id && c.subtopic_id === cat.subtopic_id);
        if (idx !== -1) { this.promptModule.selectedCategories.splice(idx, 1); this.onCategoryChange(); }
    },
    async loadBlogsByCategories() {
        this.promptModule.blogsLoading = true;
        try {
            const topicIds = [...new Set(this.promptModule.selectedCategories.map(c => c.topic_id))];
            const subtopicIds = this.promptModule.selectedCategories.filter(c => c.subtopic_id).map(c => c.subtopic_id);
            const params = new URLSearchParams();
            if (topicIds.length > 0) params.append('topic_ids', topicIds.join(','));
            if (subtopicIds.length > 0) params.append('subtopic_ids', subtopicIds.join(','));
            const resp = await fetch(`/api/v1/blogs/by-categories?${params.toString()}`, { credentials: 'include' });
            if (resp.ok) {
                const data = await resp.json();
                this.promptModule.matchedBlogs = data.matched_blogs || [];
                this.promptModule.unmatchedBlogs = data.unmatched_blogs || [];
                // 블로그별 image_mode 캐시 업데이트
                const allBlogs = [...this.promptModule.matchedBlogs, ...this.promptModule.unmatchedBlogs];
                for (const b of allBlogs) {
                    if (b.image_mode) this.promptModule.blogImageModes[b.id] = b.image_mode;
                }
            }
        } catch (e) { console.error('블로그 조회 실패:', e); }
        finally { this.promptModule.blogsLoading = false; }
    },

    // 선택된 블로그들의 대표 image_mode 반환 (첫 번째 블로그 기준, 없으면 'template')
    getSelectedBlogImageMode() {
        const selectedIds = this.promptModule.selectedBlogs || [];
        if (selectedIds.length === 0) return 'template';
        const firstId = selectedIds[0];
        return this.promptModule.blogImageModes[firstId] || 'template';
    },
    toggleTitleStyle(styleValue) {
        const idx = this.promptModule.titleRecombine.selectedStyles.indexOf(styleValue);
        if (idx !== -1) this.promptModule.titleRecombine.selectedStyles.splice(idx, 1);
        else this.promptModule.titleRecombine.selectedStyles.push(styleValue);
    },
    toggleBlogSelection(blogId) {
        const idx = this.promptModule.selectedBlogs.indexOf(blogId);
        if (idx !== -1) {
            this.promptModule.selectedBlogs.splice(idx, 1);
        } else {
            this.promptModule.selectedBlogs.push(blogId);
        }
    },

    // 매칭된 블로그 전체 선택
    selectAllMatchedBlogs() {
        this.promptModule.selectedBlogs = this.promptModule.matchedBlogs.map(b => b.id);
    },

    // 블로그 제거
    removeBlog(blogId) {
        const idx = this.promptModule.selectedBlogs.indexOf(blogId);
        if (idx !== -1) {
            this.promptModule.selectedBlogs.splice(idx, 1);
        }
    },

    // 블로그 이름 반환
    getBlogName(blogId) {
        const blog = this.promptModule.matchedBlogs.find(b => b.id === blogId) ||
                     this.promptModule.unmatchedBlogs.find(b => b.id === blogId);
        return blog ? blog.name : `블로그 ${blogId}`;
    },

    // 프롬프트 모듈 유효성 검증
    validatePromptModule() {
        // 카테고리 선택 검증
        if (this.promptModule.selectedCategories.length === 0) {
            this.showError('최소 1개 이상의 카테고리를 선택해주세요');
            return false;
        }

        // 제목 재조합 활성화 시 검증
        if (this.promptModule.titleRecombine.enabled) {
            if (this.promptModule.titleRecombine.selectedStyles.length === 0) {
                this.showError('최소 1개 이상의 제목 스타일을 선택해주세요');
                return false;
            }
            if (this.promptModule.titleRecombine.countPerStyle < 1 ||
                this.promptModule.titleRecombine.countPerStyle > 10) {
                this.showError('스타일당 생성 개수는 1~10개 사이여야 합니다');
                return false;
            }
        }

        // 참조자료 수집 검증 (필수) - 범위 검증 헬퍼
        const ref = this.promptModule.reference;
        const refChecks = [
            [ref.maxSearch < 10 || ref.maxSearch > 100, '최대 검색 수는 10~100 범위여야 합니다'],
            [ref.crawlTarget < 3 || ref.crawlTarget > 30, '크롤링 목표는 3~30 범위여야 합니다'],
            [ref.summaryCount < 1 || ref.summaryCount > 10, '요약 선택 수는 1~10 범위여야 합니다'],
            [ref.summaryCount > ref.crawlTarget, '요약 선택 수는 크롤링 목표 이하여야 합니다'],
            [ref.maxLength < 200 || ref.maxLength > 2000, '요약 최대 글자수는 200~2000 범위여야 합니다'],
        ];
        for (const [cond, msg] of refChecks) {
            if (cond) { this.showError(msg); return false; }
        }

        // 글 생성 활성화 시 검증
        if (this.promptModule.contentGeneration.enabled) {
            if (!this.promptModule.contentGeneration.provider) {
                this.showError('AI 모델을 선택해주세요');
                return false;
            }
        }

        // 이미지 생성 활성화 시 검증
        if (this.promptModule.imageGeneration.enabled) {
            if (!this.promptModule.imageGeneration.provider) {
                this.showError('이미지 AI를 선택해주세요');
                return false;
            }
        }

        // 최소 1개 기능 활성화 검증
        if (!this.promptModule.titleRecombine.enabled &&
            !this.promptModule.contentGeneration.enabled &&
            !this.promptModule.imageGeneration.enabled) {
            this.showError('최소 1개 이상의 기능(제목 재조합, 글 생성, 이미지 생성)을 활성화해주세요');
            return false;
        }

        return true;
    },

    // 프롬프트 모듈 요청 데이터 준비
    preparePromptModuleData() {
        return {
            // 카테고리 연결
            categories: this.promptModule.selectedCategories.map(c => ({
                topic_id: c.topic_id,
                subtopic_id: c.subtopic_id
            })),
            // 블로그 연결
            blogs: this.promptModule.selectedBlogs,
            // 참조자료 수집 설정 (필수 - 항상 활성화)
            reference: {
                enabled: true,
                max_search: this.promptModule.reference.maxSearch,
                crawl_target: this.promptModule.reference.crawlTarget,
                summary_count: this.promptModule.reference.summaryCount,
                summary_method: this.promptModule.reference.summaryMethod,
                ai_provider: this.promptModule.reference.aiProvider,
                ai_model: this.promptModule.reference.aiModel,
                summary_style: this.promptModule.reference.summaryStyle,
                algorithm_type: this.promptModule.reference.algorithmType,
                max_length: this.promptModule.reference.maxLength
            },
            // 제목 재조합 설정
            title_recombine: {
                enabled: this.promptModule.titleRecombine.enabled,
                styles: this.promptModule.titleRecombine.selectedStyles,
                count_per_style: this.promptModule.titleRecombine.countPerStyle,
                custom_prompt: this.promptModule.titleRecombine.customPrompt
            },
            // 글 생성 설정
            content_generation: {
                enabled: this.promptModule.contentGeneration.enabled,
                provider: this.promptModule.contentGeneration.provider,
                temperature: this.promptModule.contentGeneration.temperature,
                max_tokens: this.promptModule.contentGeneration.maxTokens,
                top_p: this.promptModule.contentGeneration.topP,
                frequency_penalty: this.promptModule.contentGeneration.frequencyPenalty,
                presence_penalty: this.promptModule.contentGeneration.presencePenalty,
                top_k: this.promptModule.contentGeneration.topK,
                system_prompt: this.promptModule.contentGeneration.systemPrompt,
                user_prompt_template: this.promptModule.contentGeneration.userPromptTemplate
            },
            // 내부링크 설정
            internal_links: {
                enabled: this.promptModule.internalLinks.enabled,
                similarity_threshold: this.promptModule.internalLinks.similarityThreshold,
                intro_count: this.promptModule.internalLinks.introCount,
                intro_link_type: this.promptModule.internalLinks.introLinkType,
                body_count: this.promptModule.internalLinks.bodyCount,
                body_link_type: this.promptModule.internalLinks.bodyLinkType,
                conclusion_count: this.promptModule.internalLinks.conclusionCount,
                conclusion_list_style: this.promptModule.internalLinks.conclusionListStyle
            },
            // 텍스트 치환
            text_replace_enabled: this.promptModule.textReplaceEnabled,
            // 이미지 생성 설정
            image_generation: {
                enabled: this.promptModule.imageGeneration.enabled,
                provider: this.promptModule.imageGeneration.provider,
                prompt_template: this.promptModule.imageGeneration.promptTemplate,
                images_per_post: this.promptModule.imageGeneration.imagesPerPost,
                dalle: this.promptModule.imageGeneration.dalle,
                nanobanana: this.promptModule.imageGeneration.nanobanana,
                title_overlay: this.promptModule.imageGeneration.titleOverlay,
                cover_source: this.promptModule.imageGeneration.coverSource,
                section_source: this.promptModule.imageGeneration.sectionSource
            }
        };
    }
};

// 전역 노출
window.createPromptModuleState = createPromptModuleState;
window.promptModuleMethods = promptModuleMethods;
