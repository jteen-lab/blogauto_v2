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
            customPrompt: '',
            // 길이는 설정으로 받는다. 프롬프트에 적으면 AI 가 못 지킨다.
            minLength: 0,
            maxLength: 0,
            // 스타일별 지시. 비우면 기본값을 쓴다.
            stylePrompts: {}
        },

        // 스타일 템플릿(서버에서 받는다)
        styleTemplates: [],
        styleTemplate: '',
        styleTemplateHint: '',

        // 서버 기본값(placeholder 로 보여 준다). 분위기가 아니라 형태다 —
        // "따뜻하게" 로는 AI 가 스타일을 구분하지 못한다.
        styleDefaults: {
            emotional: "독자를 '당신'으로 부르고 감정 어휘를 하나 넣을 것. 예: 지금도 손실 중인 당신이 확인해야 할 매매 원칙",
            practical: "숫자나 절차를 넣을 것. 예: 3단계로 끝내는 매매 원칙과 5가지 확인 조건",
            question: "의문사로 시작할 것. 예: 왜 지금 사야 하고 얼마나 나눠 담아야 하는가",
            viral: "역설이나 반전을 넣을 것. 예: 아무도 말하지 않는 오히려 손해인 분할매수 구간",
            minimal: "명사로 끝낼 것. 수식어 금지. 예: 라오어 무한매수법 실전 매매 원칙 총정리"
        },

        // 제목 스타일 옵션
        titleStyles: [
            { value: 'emotional', label: '감성형', icon: '💖' },
            { value: 'practical', label: '실용형', icon: '💡' },
            { value: 'question', label: '질문형', icon: '❓' },
            { value: 'viral', label: '바이럴', icon: '🔥' },
            { value: 'minimal', label: '심플', icon: '✨' }
        ],

        aiProviders: [
            { value: 'openai', label: 'ChatGPT' },
            { value: 'claude', label: 'Claude' },
            { value: 'gemini', label: 'Gemini' }
        ],

        contentGeneration: {
            // 빌더에서 고른 축 코드(복원·강조용). 텍스트만으론 무엇을 골랐는지 알 수 없다.
            builderSelection: null,
            enabled: false,
            provider: 'openai',
            temperature: 0.7,
            maxTokens: 4096,
            topP: 0.9,
            frequencyPenalty: 0,
            presencePenalty: 0,
            topK: 40,
            systemPrompt: '당신은 전문적인 블로그 콘텐츠 작성자입니다. SEO에 최적화된 고품질 블로그 글을 작성해주세요.',
            // {reference_materials} — 검색해 모은 자료가 들어갈 자리.
            // 빠져 있으면 생성기가 프롬프트 끝에 붙이지만, 원하는 위치에
            // 두려면 여기에 적는다.
            userPromptTemplate: '제목: {title}\n\n위 제목으로 블로그 글을 작성해주세요.\n카테고리: {category}\n키워드: {keywords}\n\n아래 자료를 참고해 사실·수치를 반영하되 문장을 그대로 옮기지 마세요.\n{reference_materials}',
            renewalMode: 'inherit',
            renewalText: '',
            showAdvanced: false
        },

        reference: {
            enabled: true,
            maxSearch: 30,
            crawlTarget: 10,
            summaryCount: 3,
            summaryMethod: 'ai',
            aiProvider: 'openai',
            aiModel: 'gpt-4.1-mini',
            summaryStyle: 'concise',
            algorithmType: 'textrank',
            maxLength: 500
        },

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

        textReplaceEnabled: true,
        imageGeneration: {
            enabled: true,
            aspectRatio: '16:9',
            style: 'realistic',
            quality: 'standard',
            promptTemplate: '{title} 주제를 상징하는 전문적인 블로그 대표 배경 이미지, {keywords} 관련 시각 요소, 현대적이고 깔끔한 일러스트 배경',
            titleOverlay: false,
            sectionCustom: false,
            sectionPromptTemplate: '{title} 주제의 블로그 섹션 일러스트, 심플하고 집중적인 디자인',
            sectionAspectRatio: '1:1',
            sectionStyle: 'minimal',
            sectionQuality: 'standard'
        },

        blogImageModes: {},

        // 애드센스 승인용 (F4 니치 강제 + F7 정보이득) — 이 모듈에만 적용
        adsense: {
            nicheEnabled: false,
            // 승인 전에만 사용할 프리셋 코드(2026-08-30 재설계).
            // 비어 있으면 항상 '사용자 프롬프트 템플릿'(평소 프롬프트)을 쓴다.
            // 승인되면 지정이 있어도 무시되어 평소 프롬프트로 자동 복귀한다.
            approvalPreset: '',
            approvalPresetOptions: [],
            nicheTopicIds: [],   // 허용 topic_id 배열
            infoGainEnabled: false,
            // 블로그의 애드센스 상태에 따라 이 모듈을 실행할지 결정
            // always | adsense_only | post_approval
            role: 'always',
            // 형제 블로그(같은 도메인·같은 모듈)가 쓴 제목을 후보에서 제외
            excludeSiblingTitles: true,   // 새 모듈 기본값 — 형제 사이트 주제 중복 방지
            // AI 답변 인용 대비(AEO/GEO) 지시문 주입
            aeoEnabled: false,
            // 블로그의 애드센스 상태에 따라 니치·정보이득을 자동 전환
            autoSwitch: false
        }
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

    // 애드센스 승인 전에만 쓸 프리셋 목록(빌더 목록에는 없다)
    async loadApprovalPresets() {
        try {
            const resp = await fetch('/api/v1/prompt-builder/blocks/approval-presets', {
                credentials: 'include',
            });
            if (resp.ok) {
                const data = await resp.json();
                this.promptModule.adsense.approvalPresetOptions = data.presets || [];
            }
        } catch (e) { console.error('승인용 프리셋 로드 실패:', e); }
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
                customPrompt: settings.title_recombine.custom_prompt || '',
                minLength: settings.title_recombine.min_length || 0,
                maxLength: settings.title_recombine.max_length || 0,
                stylePrompts: settings.title_recombine.style_prompts || {}
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
                builderSelection: cg.builder_selection || null,
                renewalMode: (cg.renewal_prompt && cg.renewal_prompt.mode) || 'inherit',
                renewalText: (cg.renewal_prompt && cg.renewal_prompt.text) || '',
                showAdvanced: false
            };
        }

        // 이미지 생성 설정 (통합 파라미터 + 레거시 마이그레이션)
        if (settings.image_generation) {
            const ig = settings.image_generation;
            // 레거시 dalle{}/nanobanana{} → 통합 키 마이그레이션
            let aspectRatio = ig.aspect_ratio || '16:9';
            let style = ig.style || 'realistic';
            let quality = ig.quality || 'standard';
            if (!ig.aspect_ratio && (ig.dalle || ig.nanobanana)) {
                if (ig.nanobanana?.aspectRatio) {
                    aspectRatio = ig.nanobanana.aspectRatio;
                } else if (ig.dalle?.size) {
                    const sizeMap = {'1792x1024': '16:9', '1024x1792': '9:16', '1024x1024': '1:1'};
                    aspectRatio = sizeMap[ig.dalle.size] || '16:9';
                }
                if (ig.nanobanana?.style) {
                    style = ig.nanobanana.style;
                } else if (ig.dalle?.style) {
                    const styleMap = {'natural': 'realistic', 'vivid': 'vivid'};
                    style = styleMap[ig.dalle.style] || 'realistic';
                }
                if (ig.dalle?.quality) quality = ig.dalle.quality;
            }
            this.promptModule.imageGeneration = {
                enabled: ig.enabled ?? true,
                aspectRatio: aspectRatio,
                style: style,
                quality: quality,
                promptTemplate: ig.prompt_template || '{title} 주제를 상징하는 전문적인 블로그 대표 배경 이미지, {keywords} 관련 시각 요소, 현대적이고 깔끔한 일러스트 배경',
                titleOverlay: ig.title_overlay ?? false,
                sectionCustom: ig.section_custom ?? false,
                sectionPromptTemplate: ig.section_prompt_template || '{title} 주제의 블로그 섹션 일러스트, 심플하고 집중적인 디자인',
                sectionAspectRatio: ig.section_aspect_ratio || '1:1',
                sectionStyle: ig.section_style || 'minimal',
                sectionQuality: ig.section_quality || 'standard'
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
            // 카테고리 모드일 때만 블로그 로드
            if (!settings.link_mode || settings.link_mode === 'category') {
                this.loadBlogsByCategories();
            }
        }

        // 선택된 블로그 (편집 모드)
        if (settings.blogs && settings.blogs.length > 0) {
            this.promptModule.selectedBlogs = settings.blogs.map(b => b.id || b);
        }

        // 애드센스 승인용 설정 복원 (F4 니치 + F7 정보이득)
        // ⚠️ 객체를 통째로 바꾸면 별도로 불러온 approvalPresetOptions 가 사라져
        //    승인용 프리셋 셀렉트가 빈 채로 뜬다(= 저장했는데 리셋된 것처럼 보임).
        //    기존 값을 펼쳐 유지한 뒤 저장값만 덮는다.
        this.promptModule.adsense = {
            ...this.promptModule.adsense,
            role: settings.adsense_role || 'always',
            excludeSiblingTitles: settings.exclude_sibling_titles ?? true,  // 기본 켜짐 — 형제 사이트 주제 중복 방지
            aeoEnabled: settings.aeo_enabled ?? false,
            autoSwitch: settings.adsense_auto ?? false,
            approvalPreset: settings.adsense_approval_preset ?? '',
            nicheEnabled: settings.niche_enabled ?? false,
            nicheTopicIds: Array.isArray(settings.niche_topic_ids) ? settings.niche_topic_ids.slice() : [],
            infoGainEnabled: settings.info_gain_enabled ?? false
        };

        // 양방향 연동 데이터 복원
        if (this.initPromptModuleLinkingFromData) {
            this.initPromptModuleLinkingFromData();
        }
    },

    // 애드센스 니치 topic 토글 (F4)
    isNicheTopicSelected(topicId) {
        return this.promptModule.adsense.nicheTopicIds.includes(topicId);
    },
    toggleNicheTopic(topicId) {
        const ids = this.promptModule.adsense.nicheTopicIds;
        const idx = ids.indexOf(topicId);
        if (idx !== -1) ids.splice(idx, 1);
        else ids.push(topicId);
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
        if (this.promptModule.selectedCategories.length > 0) {
            // usedMappings가 아직 로드되지 않았으면 병렬 로드
            const loads = [this.loadBlogsByCategories()];
            if (this.loadUsedBlogCategories && this.promptModule.linking.usedMappings.length === 0) {
                loads.push(this.loadUsedBlogCategories());
            }
            Promise.all(loads).then(() => {
                if (this.checkConflicts) this.checkConflicts();
                if (this.buildBlogCategoryMap) this.buildBlogCategoryMap();
            });
        } else {
            this.promptModule.matchedBlogs = [];
            this.promptModule.unmatchedBlogs = [];
            if (this.promptModule.linking) {
                this.promptModule.linking.excludedBlogs = [];
                this.promptModule.linking.blogCategoryMap = [];
            }
        }
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
    toggleTitleStyle(styleValue) {
        const idx = this.promptModule.titleRecombine.selectedStyles.indexOf(styleValue);
        if (idx !== -1) this.promptModule.titleRecombine.selectedStyles.splice(idx, 1);
        else this.promptModule.titleRecombine.selectedStyles.push(styleValue);
    },
    /** 템플릿 목록을 서버에서 받는다. 정의를 한 곳에서 관리한다. */
    async loadStyleTemplates() {
        if (this.promptModule.styleTemplates.length) return;
        try {
            const r = await fetch('/api/v1/recombine-templates',
                                  { credentials: 'include' });
            if (!r.ok) return;
            const d = await r.json();
            this.promptModule.styleTemplates = d.templates || [];
        } catch (e) { /* 목록이 없어도 직접 입력은 된다 */ }
    },

    /** 고른 템플릿으로 다섯 칸을 채운다. 채운 뒤 개별 수정할 수 있다. */
    applyStyleTemplate() {
        const code = this.promptModule.styleTemplate;
        if (!code) return;
        const found = (this.promptModule.styleTemplates || [])
            .find(t => t.code === code);
        if (!found) return;
        this.promptModule.titleRecombine.stylePrompts = { ...found.prompts };
        this.promptModule.styleTemplateHint = `${found.label} 적용됨`;
    },

    /** 모듈이 고른 블로그의 니치로 템플릿을 고른다.
     *
     *  금융 블로그에 맛집용 지시가 들어가면 제목이 어긋난다. 맞는 것이
     *  없으면 고르지 않는다 — 짐작하면 엉뚱한 지시가 들어간다.
     */
    async recommendStyleTemplate() {
        const blogs = this.promptModule.selectedBlogs || [];
        if (!blogs.length) {
            this.promptModule.styleTemplateHint = '블로그를 먼저 고르세요';
            return;
        }
        await this.loadStyleTemplates();
        try {
            const r = await fetch(
                `/api/v1/recombine-templates/recommend?blog_ids=${blogs.join(',')}`,
                { credentials: 'include' });
            if (!r.ok) return;
            const d = await r.json();
            if (!d.code) {
                this.promptModule.styleTemplateHint = d.reason || '';
                return;
            }
            this.promptModule.styleTemplate = d.code;
            this.promptModule.titleRecombine.stylePrompts = { ...d.prompts };
            this.promptModule.styleTemplateHint = d.reason || '';
        } catch (e) {
            this.promptModule.styleTemplateHint = '추천을 받지 못했습니다';
        }
    },

    // 프롬프트 모듈 유효성 검증
    validatePromptModule() {
        const linkMode = this.promptModule.linking?.linkMode || 'category';

        // 카테고리 모드: 카테고리 필수
        if (linkMode === 'category' && this.promptModule.selectedCategories.length === 0) {
            this.showError('최소 1개 이상의 카테고리를 선택해주세요');
            return false;
        }

        // 블로그 모드: 블로그 필수
        if (linkMode === 'blog' && this.promptModule.selectedBlogs.length === 0) {
            this.showError('최소 1개 이상의 블로그를 선택해주세요');
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
        // 저장 전 blogCategoryMap 갱신
        if (this.buildBlogCategoryMap) {
            this.buildBlogCategoryMap();
        }

        // 양방향 연동 데이터
        const linkingData = this.preparePromptModuleLinkingData
            ? this.preparePromptModuleLinkingData()
            : {};

        return {
            // 양방향 연동 설정
            ...linkingData,
            // 애드센스 승인용 (F4 니치 강제 + F7 정보이득)
            adsense_role: this.promptModule.adsense.role || 'always',
            exclude_sibling_titles: !!this.promptModule.adsense.excludeSiblingTitles,
            aeo_enabled: !!this.promptModule.adsense.aeoEnabled,
            adsense_auto: !!this.promptModule.adsense.autoSwitch,
            adsense_approval_preset: this.promptModule.adsense.approvalPreset || '',
            niche_enabled: this.promptModule.adsense.nicheEnabled,
            niche_topic_ids: this.promptModule.adsense.nicheTopicIds,
            info_gain_enabled: this.promptModule.adsense.infoGainEnabled,
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
                custom_prompt: this.promptModule.titleRecombine.customPrompt,
                min_length: this.promptModule.titleRecombine.minLength || 0,
                max_length: this.promptModule.titleRecombine.maxLength || 0,
                // 빈 값은 보내지 않는다 — 저장해 두면 기본값으로 못 돌아간다
                style_prompts: Object.fromEntries(
                    Object.entries(this.promptModule.titleRecombine.stylePrompts || {})
                        .filter(([, v]) => v && String(v).trim())
                        .map(([k, v]) => [k, String(v).trim()]))
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
                user_prompt_template: this.promptModule.contentGeneration.userPromptTemplate,
                // 어떤 프리셋·항목을 골랐는지 함께 저장한다(다시 열었을 때 강조 복원).
                builder_selection: this.promptModule.contentGeneration.builderSelection || null,
                // 재발행 리뉴얼 프롬프트 (mode: inherit|new|additional)
                renewal_prompt: {
                    mode: this.promptModule.contentGeneration.renewalMode || 'inherit',
                    text: this.promptModule.contentGeneration.renewalText || ''
                }
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
            // 이미지 생성 설정 (통합 파라미터, provider는 블로그 설정에서 결정)
            // cover_source/section_source는 블로그 설정 이미지 탭에서 관리
            image_generation: {
                enabled: this.promptModule.imageGeneration.enabled,
                aspect_ratio: this.promptModule.imageGeneration.aspectRatio,
                style: this.promptModule.imageGeneration.style,
                quality: this.promptModule.imageGeneration.quality,
                prompt_template: this.promptModule.imageGeneration.promptTemplate,
                title_overlay: this.promptModule.imageGeneration.titleOverlay,
                section_custom: this.promptModule.imageGeneration.sectionCustom,
                section_prompt_template: this.promptModule.imageGeneration.sectionPromptTemplate,
                section_aspect_ratio: this.promptModule.imageGeneration.sectionAspectRatio,
                section_style: this.promptModule.imageGeneration.sectionStyle,
                section_quality: this.promptModule.imageGeneration.sectionQuality
            }
        };
    }
};

// 전역 노출
window.createPromptModuleState = createPromptModuleState;
window.promptModuleMethods = promptModuleMethods;
