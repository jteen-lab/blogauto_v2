/**
 * 프롬프트 모듈 폼 전용 JavaScript
 * Alpine.js 기반 프롬프트 모듈 상태 관리
 *
 * @description HTML 템플릿은 prompt-form-template.js에 분리됨 (500줄 제한 준수)
 */

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
            provider: 'openai',
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

        // 이미지 생성 설정
        imageGeneration: {
            enabled: false,
            provider: 'dalle',
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
            }
        }
    };
}

// 프롬프트 모듈 메서드 믹스인
const promptModuleMethods = {
    // 카테고리 로드
    async loadCategories() {
        this.promptModule.categoriesLoading = true;
        try {
            const response = await fetch('/api/v1/categories', {
                credentials: 'include'
            });
            if (response.ok) {
                const data = await response.json();
                // API 응답: { categories: [{ id, name, subcategories: [...] }] }
                this.promptModule.topics = data.categories || [];
                console.log('[loadCategories] 카테고리 로드 완료:', this.promptModule.topics.length);
            }
        } catch (error) {
            console.error('카테고리 로드 실패:', error);
        } finally {
            this.promptModule.categoriesLoading = false;
        }
    },

    // 전체 블로그 로드 (플랫폼별 필터링용)
    async loadBlogs() {
        this.promptModule.blogsLoading = true;
        try {
            const response = await fetch('/api/v1/blogs', {
                credentials: 'include'
            });
            if (response.ok) {
                const data = await response.json();
                this.promptModule.blogs = data.blogs || data || [];
                console.log('[loadBlogs] 전체 블로그 로드 완료:', this.promptModule.blogs.length);
            }
        } catch (error) {
            console.error('블로그 로드 실패:', error);
        } finally {
            this.promptModule.blogsLoading = false;
        }
    },

    // 플랫폼별 블로그 필터링 (전체 블로그에서)
    getBlogsByPlatform(platform) {
        return this.promptModule.blogs.filter(b => b.platform === platform);
    },

    // 매칭된 블로그에서 플랫폼별 필터링 (카테고리 연동)
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
                nanobanana: ig.nanobanana || { aspectRatio: '16:9', style: 'realistic' }
            };
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

    // Topic 펼치기/접기
    toggleTopicExpand(topicId) {
        const idx = this.promptModule.expandedTopics.indexOf(topicId);
        if (idx === -1) {
            this.promptModule.expandedTopics.push(topicId);
        } else {
            this.promptModule.expandedTopics.splice(idx, 1);
        }
    },

    // Topic 선택 (전체 subtopics 포함 또는 topic만)
    isTopicSelected(topicId) {
        return this.promptModule.selectedCategories.some(c => c.topic_id === topicId);
    },

    toggleTopicSelection(topicId) {
        if (this.isTopicSelected(topicId)) {
            // 해당 topic의 모든 카테고리 제거
            this.promptModule.selectedCategories = this.promptModule.selectedCategories.filter(c => c.topic_id !== topicId);
        } else {
            // topic만 추가 (subtopic_id: null)
            this.promptModule.selectedCategories.push({ topic_id: topicId, subtopic_id: null });
        }
        this.onCategoryChange();
    },

    // SubTopic 선택
    isSubtopicSelected(topicId, subtopicId) {
        return this.promptModule.selectedCategories.some(
            c => c.topic_id === topicId && c.subtopic_id === subtopicId
        );
    },

    toggleSubtopicSelection(topicId, subtopicId) {
        const idx = this.promptModule.selectedCategories.findIndex(
            c => c.topic_id === topicId && c.subtopic_id === subtopicId
        );
        if (idx !== -1) {
            this.promptModule.selectedCategories.splice(idx, 1);
        } else {
            // 기존에 topic만 선택되어 있었다면 제거
            const topicOnlyIdx = this.promptModule.selectedCategories.findIndex(
                c => c.topic_id === topicId && c.subtopic_id === null
            );
            if (topicOnlyIdx !== -1) {
                this.promptModule.selectedCategories.splice(topicOnlyIdx, 1);
            }
            this.promptModule.selectedCategories.push({ topic_id: topicId, subtopic_id: subtopicId });
        }
        this.onCategoryChange();
    },

    // 카테고리 변경 시 블로그 재조회
    onCategoryChange() {
        if (this.promptModule.selectedCategories.length > 0) {
            this.loadBlogsByCategories();
        } else {
            this.promptModule.matchedBlogs = [];
            this.promptModule.unmatchedBlogs = [];
        }
    },

    // 카테고리 표시 이름 반환
    getCategoryDisplayName(cat) {
        const topic = this.promptModule.topics.find(t => t.id === cat.topic_id);
        if (!topic) return `카테고리 ${cat.topic_id}`;

        if (cat.subtopic_id) {
            // subcategories로 변경 (API 응답 구조에 맞춤)
            const subtopic = topic.subcategories?.find(s => s.id === cat.subtopic_id);
            return subtopic ? `${topic.name} > ${subtopic.name}` : topic.name;
        }
        return topic.name + ' (전체)';
    },

    // 카테고리 제거
    removeCategory(cat) {
        const idx = this.promptModule.selectedCategories.findIndex(
            c => c.topic_id === cat.topic_id && c.subtopic_id === cat.subtopic_id
        );
        if (idx !== -1) {
            this.promptModule.selectedCategories.splice(idx, 1);
            this.onCategoryChange();
        }
    },

    // 카테고리 기반 블로그 조회
    async loadBlogsByCategories() {
        this.promptModule.blogsLoading = true;
        try {
            const topicIds = [...new Set(this.promptModule.selectedCategories.map(c => c.topic_id))];
            const subtopicIds = this.promptModule.selectedCategories
                .filter(c => c.subtopic_id)
                .map(c => c.subtopic_id);

            const params = new URLSearchParams();
            if (topicIds.length > 0) params.append('topic_ids', topicIds.join(','));
            if (subtopicIds.length > 0) params.append('subtopic_ids', subtopicIds.join(','));

            const response = await fetch(`/api/v1/blogs/by-categories?${params.toString()}`, {
                credentials: 'include'
            });

            if (response.ok) {
                const data = await response.json();
                this.promptModule.matchedBlogs = data.matched_blogs || [];
                this.promptModule.unmatchedBlogs = data.unmatched_blogs || [];
                console.log('[loadBlogsByCategories] 매칭:', this.promptModule.matchedBlogs.length,
                    '미매칭:', this.promptModule.unmatchedBlogs.length);
            }
        } catch (error) {
            console.error('블로그 조회 실패:', error);
        } finally {
            this.promptModule.blogsLoading = false;
        }
    },

    // 제목 스타일 토글
    toggleTitleStyle(styleValue) {
        const idx = this.promptModule.titleRecombine.selectedStyles.indexOf(styleValue);
        if (idx !== -1) {
            this.promptModule.titleRecombine.selectedStyles.splice(idx, 1);
        } else {
            this.promptModule.titleRecombine.selectedStyles.push(styleValue);
        }
    },

    // 블로그 선택 토글
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
            // 이미지 생성 설정
            image_generation: {
                enabled: this.promptModule.imageGeneration.enabled,
                provider: this.promptModule.imageGeneration.provider,
                prompt_template: this.promptModule.imageGeneration.promptTemplate,
                images_per_post: this.promptModule.imageGeneration.imagesPerPost,
                dalle: this.promptModule.imageGeneration.dalle,
                nanobanana: this.promptModule.imageGeneration.nanobanana
            }
        };
    }
};

// 전역 노출
window.createPromptModuleState = createPromptModuleState;
window.promptModuleMethods = promptModuleMethods;
