function createPromptModuleLinkingState() {
    return {
        linkMode: 'category',
        blogCategoryMap: [],
        usedMappings: [],
        excludedBlogs: [],
        excludedCategories: [],
        allBlogsForSelect: [],
        blogCategories: {},
        forceLinkConfirm: null
    };
}

const promptModuleLinkingMethods = {
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
                const allBlogs = [...this.promptModule.matchedBlogs, ...this.promptModule.unmatchedBlogs];
                for (const b of allBlogs) {
                    if (b.image_mode) this.promptModule.blogImageModes[b.id] = b.image_mode;
                }
            }
        } catch (e) { console.error('블로그 조회 실패:', e); }
        finally { this.promptModule.blogsLoading = false; }
    },

    getSelectedBlogImageMode() {
        const selectedIds = this.promptModule.selectedBlogs || [];
        if (selectedIds.length === 0) return 'template';
        return this.promptModule.blogImageModes[selectedIds[0]] || 'template';
    },

    toggleBlogSelection(blogId) {
        const idx = this.promptModule.selectedBlogs.indexOf(blogId);
        if (idx !== -1) this.promptModule.selectedBlogs.splice(idx, 1);
        else this.promptModule.selectedBlogs.push(blogId);
        this.buildBlogCategoryMap();
    },

    selectAllMatchedBlogs() {
        this.promptModule.selectedBlogs = this.promptModule.matchedBlogs.map(b => b.id);
        this.buildBlogCategoryMap();
    },

    removeBlog(blogId) {
        const idx = this.promptModule.selectedBlogs.indexOf(blogId);
        if (idx !== -1) {
            this.promptModule.selectedBlogs.splice(idx, 1);
            this.buildBlogCategoryMap();
        }
    },

    getBlogName(blogId) {
        const blog = this.promptModule.matchedBlogs.find(b => b.id === blogId) ||
                     this.promptModule.unmatchedBlogs.find(b => b.id === blogId) ||
                     this.promptModule.blogs.find(b => b.id === blogId);
        return blog ? blog.name : `블로그 ${blogId}`;
    },

    async loadUsedBlogCategories() {
        // in-flight 가드: 같은 폼에서 다중 호출 시 동일 Promise 재사용
        // (이전 회귀에서 fire-and-forget 호출과 init/카테고리 변경이 겹쳐
        //  동시에 2~3개 요청이 발생, 64초 걸리던 백엔드와 connection pool을
        //  다투며 submitForm 응답이 끊겨 SyntaxError 가 났던 패턴 방지)
        if (this.promptModule.linking._usedMappingsInflight) {
            return this.promptModule.linking._usedMappingsInflight;
        }
        const run = async () => {
            try {
                const params = new URLSearchParams();
                if (this.isEdit && this.module?.id) {
                    params.append('exclude_module_id', this.module.id);
                }
                const url = `/api/v1/modules/used-blog-categories?${params.toString()}`;
                const resp = await fetch(url, { credentials: 'include' });
                if (resp.ok) {
                    const data = await resp.json();
                    this.promptModule.linking.usedMappings = data.mappings || [];
                }
            } catch (e) {
                console.error('[연동] 매핑 로드 오류:', e);
            } finally {
                this.promptModule.linking._usedMappingsInflight = null;
            }
        };
        this.promptModule.linking._usedMappingsInflight = run();
        return this.promptModule.linking._usedMappingsInflight;
    },

    async loadBlogCategories(blogId) {
        if (this.promptModule.linking.blogCategories[blogId]) {
            return;
        }
        try {
            const resp = await fetch(`/api/v1/blogs/${blogId}/categories`, {
                credentials: 'include'
            });
            if (resp.ok) {
                const data = await resp.json();
                this.promptModule.linking.blogCategories[blogId] = data.categories || [];
            } else {
                this.promptModule.linking.blogCategories[blogId] = [];
            }
        } catch (e) {
            this.promptModule.linking.blogCategories[blogId] = [];
        }
    },

    _topicsConflict(topicA, subA, topicB, subB) {
        if (topicA !== topicB) return false;
        if (subA == null && subB == null) return true;
        if (subA == null || subB == null) return true;
        return subA === subB;
    },

    checkConflicts() {
        const linking = this.promptModule.linking;
        const used = linking.usedMappings;

        if (linking.linkMode === 'category') {
            this._checkConflictsForCategoryMode(used);
        } else {
            this._checkConflictsForBlogMode(used);
        }
    },

    _checkConflictsForCategoryMode(used) {
        const selectedCats = this.promptModule.selectedCategories;
        const matchedBlogs = this.promptModule.matchedBlogs;
        const excluded = [];

        for (const blog of matchedBlogs) {
            const conflicts = [];
            const seenKeys = new Set();
            for (const cat of selectedCats) {
                const matched = used.filter(m =>
                    m.blog_id === blog.id &&
                    this._topicsConflict(cat.topic_id, cat.subtopic_id, m.topic_id, m.subtopic_id)
                );
                for (const conflict of matched) {
                    const key = `${conflict.topic_id}-${conflict.subtopic_id}-${conflict.module_id}`;
                    if (seenKeys.has(key)) continue;
                    seenKeys.add(key);
                    conflicts.push({
                        topic_id: conflict.topic_id,
                        subtopic_id: conflict.subtopic_id,
                        topic_name: conflict.topic_name || `토픽 ${conflict.topic_id}`,
                        subtopic_name: conflict.subtopic_name || (conflict.subtopic_id == null ? '(전체)' : null),
                        module_name: conflict.module_name || `모듈 ${conflict.module_id}`,
                        module_id: conflict.module_id
                    });
                }
            }
            if (conflicts.length > 0) {
                excluded.push({
                    blog_id: blog.id,
                    blog_name: blog.name || `블로그 ${blog.id}`,
                    conflicts
                });
            }
        }

        this.promptModule.linking.excludedBlogs = excluded;
    },

    _checkConflictsForBlogMode(used) {
        const selectedBlogs = this.promptModule.selectedBlogs;
        const blogCats = this.promptModule.linking.blogCategories;
        const excluded = [];
        const seen = new Set();

        for (const blogId of selectedBlogs) {
            const cats = blogCats[blogId] || [];
            for (const cat of cats) {
                const matched = used.filter(m =>
                    m.blog_id === blogId &&
                    this._topicsConflict(cat.topic_id, cat.subtopic_id, m.topic_id, m.subtopic_id)
                );
                for (const conflict of matched) {
                    const key = `${blogId}-${conflict.topic_id}-${conflict.subtopic_id}-${conflict.module_id}`;
                    if (seen.has(key)) continue;
                    seen.add(key);
                    excluded.push({
                        topic_id: conflict.topic_id,
                        subtopic_id: conflict.subtopic_id,
                        topic_name: cat.topic_name || conflict.topic_name || `토픽 ${cat.topic_id}`,
                        subtopic_name: conflict.subtopic_name || (conflict.subtopic_id == null ? '(전체)' : null),
                        module_name: conflict.module_name || `모듈 ${conflict.module_id}`,
                        module_id: conflict.module_id
                    });
                }
            }
        }

        this.promptModule.linking.excludedCategories = excluded;
    },

    showForceLink(blogId, conflictCategories, sourceModuleName, sourceModuleId) {
        const hasWholeTopic = conflictCategories.some(c => c.subtopic_id == null);
        this.promptModule.linking.forceLinkConfirm = {
            blogId, categories: conflictCategories, sourceModuleName, sourceModuleId,
            hasWholeTopic, groupedTopics: [], expandedTopics: [],
            // selectedCategories: 토픽 전체({topic_id, subtopic_id:null}) 또는 개별 서브토픽
            selectedCategories: [...conflictCategories],
        };
        if (hasWholeTopic) this._loadGroupedTopicsForForceLink(conflictCategories);
    },

    async _loadGroupedTopicsForForceLink(categories) {
        const fc = this.promptModule.linking.forceLinkConfirm;
        if (!fc) return;
        const wholeTopics = categories.filter(c => c.subtopic_id == null);
        const groups = [];
        for (const cat of wholeTopics) {
            await this.loadBlogCategories(fc.blogId);
            const blogCats = this.promptModule.linking.blogCategories[fc.blogId] || [];
            const subs = blogCats.filter(c => c.topic_id === cat.topic_id).map(c => ({
                subtopic_id: c.subtopic_id,
                subtopic_name: c.subtopic_name || `서브토픽 ${c.subtopic_id}`,
            }));
            groups.push({
                topic_id: cat.topic_id,
                topic_name: cat.topic_name || `토픽 ${cat.topic_id}`,
                subtopics: subs,
            });
        }
        fc.groupedTopics = groups;
    },

    toggleForceLinkTopicExpand(topicId) {
        const fc = this.promptModule.linking.forceLinkConfirm;
        if (!fc) return;
        if (!fc.expandedTopics) fc.expandedTopics = [];
        const idx = fc.expandedTopics.indexOf(topicId);
        if (idx === -1) fc.expandedTopics.push(topicId);
        else fc.expandedTopics.splice(idx, 1);
    },

    isForceLinkTopicSelected(topicId) {
        const fc = this.promptModule.linking.forceLinkConfirm;
        if (!fc) return false;
        return fc.selectedCategories.some(c => c.topic_id === topicId);
    },

    toggleForceLinkTopicSelection(topicId) {
        const fc = this.promptModule.linking.forceLinkConfirm;
        if (!fc) return;
        if (this.isForceLinkTopicSelected(topicId)) {
            fc.selectedCategories = fc.selectedCategories.filter(c => c.topic_id !== topicId);
        } else {
            fc.selectedCategories.push({ topic_id: topicId, subtopic_id: null });
        }
    },

    isForceLinkSubtopicSelected(topicId, subtopicId) {
        const cats = this.promptModule.linking.forceLinkConfirm?.selectedCategories || [];
        return cats.some(c => c.topic_id === topicId && (c.subtopic_id == null || c.subtopic_id === subtopicId));
    },

    toggleForceLinkSubtopicSelection(topicId, subtopicId) {
        const fc = this.promptModule.linking.forceLinkConfirm;
        if (!fc) return;
        const wholeIdx = fc.selectedCategories.findIndex(c => c.topic_id === topicId && c.subtopic_id == null);
        if (wholeIdx !== -1) {
            fc.selectedCategories.splice(wholeIdx, 1);
            const group = fc.groupedTopics.find(g => g.topic_id === topicId);
            if (group) {
                for (const sub of group.subtopics) {
                    if (sub.subtopic_id !== subtopicId) {
                        fc.selectedCategories.push({ topic_id: topicId, subtopic_id: sub.subtopic_id });
                    }
                }
            }
            return;
        }
        const idx = fc.selectedCategories.findIndex(c => c.topic_id === topicId && c.subtopic_id === subtopicId);
        if (idx !== -1) {
            fc.selectedCategories.splice(idx, 1);
        } else {
            fc.selectedCategories.push({ topic_id: topicId, subtopic_id: subtopicId });
        }
    },

    async executeForceLink() {
        const fc = this.promptModule.linking.forceLinkConfirm;
        if (!fc) return;

        const categories = fc.selectedCategories.filter(c => c.topic_id != null);

        const moduleId = this.module?.id;
        try {
            let url, bodyData;
            if (moduleId) {
                // 편집 모드: 기존 force-link API (소스 제거 + 타겟 추가)
                url = `/api/v1/modules/${moduleId}/force-link`;
                bodyData = { blog_id: fc.blogId, categories };
            } else {
                // 신규 모드: release API (소스 제거만)
                url = '/api/v1/modules/release-categories';
                bodyData = { blog_id: fc.blogId, categories };
            }

            const resp = await fetch(url, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(bodyData),
            });

            if (resp.ok) {
                await this.loadUsedBlogCategories();
                this.checkConflicts();
                this.buildBlogCategoryMap();
            } else {
                const err = await resp.json().catch(() => ({}));
                if (this.showError) this.showError(err.detail || '강제 연동에 실패했습니다');
            }
        } catch (e) {
            if (this.showError) this.showError('강제 연동 중 오류가 발생했습니다');
        } finally {
            this.promptModule.linking.forceLinkConfirm = null;
        }
    },

    cancelForceLink() {
        this.promptModule.linking.forceLinkConfirm = null;
    },

    buildBlogCategoryMap() {
        const linking = this.promptModule.linking;
        const map = [];

        if (linking.linkMode === 'category') {
            this._buildMapForCategoryMode(map);
        } else {
            this._buildMapForBlogMode(map);
        }

        linking.blogCategoryMap = map;
    },

    _buildMapForCategoryMode(map) {
        const linking = this.promptModule.linking;
        const excludedBlogIds = new Set(linking.excludedBlogs.map(b => b.blog_id));
        const selectedBlogs = this.promptModule.selectedBlogs.filter(id => !excludedBlogIds.has(id));
        const selectedCats = this.promptModule.selectedCategories;

        for (const blogId of selectedBlogs) {
            for (const cat of selectedCats) {
                map.push({
                    blog_id: blogId,
                    topic_id: cat.topic_id,
                    subtopic_id: cat.subtopic_id
                });
            }
        }
    },

    _buildMapForBlogMode(map) {
        const linking = this.promptModule.linking;
        const excCats = linking.excludedCategories;

        for (const blogId of this.promptModule.selectedBlogs) {
            const cats = linking.blogCategories[blogId] || [];
            for (const cat of cats) {
                const isExcluded = excCats.some(ec =>
                    this._topicsConflict(cat.topic_id, cat.subtopic_id, ec.topic_id, ec.subtopic_id)
                );
                if (!isExcluded) {
                    map.push({
                        blog_id: blogId,
                        topic_id: cat.topic_id,
                        subtopic_id: cat.subtopic_id
                    });
                }
            }
        }
    },

    switchLinkMode(mode) {
        if (mode !== 'category' && mode !== 'blog') {
            console.error('[연동] 잘못된 모드:', mode);
            return;
        }

        this.promptModule.linking.linkMode = mode;
        this.promptModule.matchedBlogs = [];
        this.promptModule.unmatchedBlogs = [];
        this.promptModule.selectedBlogs = [];
        this.promptModule.linking.excludedBlogs = [];
        this.promptModule.linking.excludedCategories = [];
        this.promptModule.linking.blogCategoryMap = [];

        if (mode === 'blog') {
            this.promptModule.selectedCategories = [];
            this._loadBlogsForBlogMode();
        }

    },

    async _loadBlogsForBlogMode() {
        try {
            await Promise.all([
                this.loadBlogs(),
                this.loadUsedBlogCategories(),
            ]);
            this.promptModule.linking.allBlogsForSelect = this.promptModule.blogs || [];
        } catch (e) {
            console.error('[연동] 블로그 목록 로드 오류:', e);
        }
    },

    async onBlogSelectInBlogMode(blogId) {
        const idx = this.promptModule.selectedBlogs.indexOf(blogId);

        if (idx === -1) {
            this.promptModule.selectedBlogs.push(blogId);
            const loads = [this.loadBlogCategories(blogId)];
            if (this.promptModule.linking.usedMappings.length === 0) {
                loads.push(this.loadUsedBlogCategories());
            }
            await Promise.all(loads);
        } else {
            this.promptModule.selectedBlogs.splice(idx, 1);
            delete this.promptModule.linking.blogCategories[blogId];
        }

        this.checkConflicts();
        this.buildBlogCategoryMap();
    },

    getAutoLinkedCategories(blogId) {
        const cats = this.promptModule.linking.blogCategories[blogId] || [];
        const excCats = this.promptModule.linking.excludedCategories;
        return cats.filter(c =>
            !excCats.some(ec => this._topicsConflict(c.topic_id, c.subtopic_id, ec.topic_id, ec.subtopic_id))
        );
    },

    getExcludedCategoriesForBlog(blogId) {
        const cats = this.promptModule.linking.blogCategories[blogId] || [];
        return this.promptModule.linking.excludedCategories.filter(
            ec => cats.some(c => this._topicsConflict(c.topic_id, c.subtopic_id, ec.topic_id, ec.subtopic_id))
        );
    },

    async initPromptModuleLinkingFromData() {
        if (!this.isEdit || !this.module?.settings) return;

        const settings = this.module.settings;

        if (settings.link_mode) {
            this.promptModule.linking.linkMode = settings.link_mode;
        }

        if (settings.blog_category_map && Array.isArray(settings.blog_category_map)) {
            this.promptModule.linking.blogCategoryMap = settings.blog_category_map;
        }

        if (this.promptModule.linking.linkMode === 'blog') {
            await this._loadBlogsForBlogMode();
            const blogIds = [...new Set(
                this.promptModule.linking.blogCategoryMap.map(m => m.blog_id)
            )];
            const loadPromises = blogIds.map(id => this.loadBlogCategories(id));
            await Promise.all(loadPromises);
        }

        await this.loadUsedBlogCategories();
        this.checkConflicts();
    },

    preparePromptModuleLinkingData() {
        return {
            link_mode: this.promptModule.linking.linkMode,
            blog_category_map: this.promptModule.linking.blogCategoryMap
        };
    }
};

// 전역 노출
window.createPromptModuleLinkingState = createPromptModuleLinkingState;
window.promptModuleLinkingMethods = promptModuleLinkingMethods;
