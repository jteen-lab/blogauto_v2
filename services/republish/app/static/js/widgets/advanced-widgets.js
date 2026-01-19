/**
 * 고급 위젯 모음
 *
 * 복잡한 데이터 입력을 위한 고급 위젯들입니다.
 * - tag-input: 태그 입력 (쉼표/엔터로 구분)
 * - module-selector: 플로우 내 다른 모듈 선택
 * - text-replace-rules: 텍스트 치환 규칙 목록
 * - prompt-structure: 프롬프트 구조 설정
 * - prompt-advanced: 프롬프트 고급 설정
 * - newsletter-source-list: 뉴스레터 소스 목록
 */

(function() {
    const baseInputClass = 'px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent';

    /**
     * 태그 입력 위젯
     *
     * 쉼표 또는 엔터로 구분된 태그를 입력
     * 저장 형식: string[]
     */
    WidgetRegistry.register('tag-input', {
        render(key, schema, value, onChange) {
            const maxTags = schema.maxTags || 20;
            const placeholder = schema.placeholder || '태그 입력 후 Enter';

            const initScript = `
                if (!paramValues['${key}'] || !Array.isArray(paramValues['${key}'])) {
                    paramValues['${key}'] = [];
                }
                $data._tagInput_${key} = '';
            `;

            return `
                <div x-init="${initScript}" class="space-y-2">
                    <!-- 입력 필드 -->
                    <div class="flex gap-2">
                        <input type="text"
                               x-model="$data._tagInput_${key}"
                               @keydown.enter.prevent="if ($data._tagInput_${key}.trim() && paramValues['${key}'].length < ${maxTags}) { paramValues['${key}'].push($data._tagInput_${key}.trim()); $data._tagInput_${key} = ''; }"
                               @keydown.comma.prevent="if ($data._tagInput_${key}.trim() && paramValues['${key}'].length < ${maxTags}) { paramValues['${key}'].push($data._tagInput_${key}.trim()); $data._tagInput_${key} = ''; }"
                               placeholder="${placeholder}"
                               class="${baseInputClass} flex-1">
                        <button type="button"
                                @click="if ($data._tagInput_${key}.trim() && paramValues['${key}'].length < ${maxTags}) { paramValues['${key}'].push($data._tagInput_${key}.trim()); $data._tagInput_${key} = ''; }"
                                class="px-3 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-sm">
                            추가
                        </button>
                    </div>

                    <!-- 태그 목록 -->
                    <div class="flex flex-wrap gap-2" x-show="paramValues['${key}'].length > 0">
                        <template x-for="(tag, index) in paramValues['${key}']" :key="index">
                            <span class="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm">
                                <span x-text="tag"></span>
                                <button type="button"
                                        @click="paramValues['${key}'].splice(index, 1)"
                                        class="hover:text-blue-600">
                                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                    </svg>
                                </button>
                            </span>
                        </template>
                    </div>

                    <p class="text-xs text-gray-500"
                       x-text="paramValues['${key}'].length + '/${maxTags}개'"></p>
                </div>
            `;
        }
    });

    /**
     * 모듈 선택 위젯
     *
     * 현재 플로우의 다른 모듈 중 특정 조건에 맞는 모듈 선택
     * filter: {category: string, code: string}
     */
    WidgetRegistry.register('module-selector', {
        render(key, schema, value, onChange) {
            const filter = schema.filter || {};
            const filterCategory = filter.category || '';
            const filterCode = filter.code || '';

            const initScript = `
                $data._filteredModules_${key} = [];
                // 모듈 체인에서 필터된 모듈 목록 가져오기
                if (window._moduleChainInstance) {
                    const allModules = window._moduleChainInstance.modules || [];
                    $data._filteredModules_${key} = allModules.filter(m => {
                        const mt = m.moduleType || {};
                        let match = true;
                        if ('${filterCategory}') match = match && mt.category === '${filterCategory}';
                        if ('${filterCode}') match = match && mt.code === '${filterCode}';
                        return match;
                    });
                }
            `;

            return `
                <div x-init="${initScript}">
                    <select x-model="paramValues['${key}']"
                            class="${baseInputClass} w-full">
                        <option value="">-- 모듈 선택 --</option>
                        <template x-for="mod in $data._filteredModules_${key}" :key="mod.id || mod.tempId">
                            <option :value="mod.id || mod.tempId"
                                    x-text="mod.name || mod.moduleType?.name || '모듈'">
                            </option>
                        </template>
                    </select>
                    <p class="mt-1 text-xs text-gray-500"
                       x-show="$data._filteredModules_${key}.length === 0">
                        조건에 맞는 모듈이 없습니다. 먼저 ${filterCode || filterCategory || '해당'} 모듈을 추가하세요.
                    </p>
                </div>
            `;
        }
    });

    /**
     * 텍스트 치환 규칙 위젯
     *
     * 원본 텍스트 → 대체 텍스트 규칙 목록
     * 저장 형식: [{from: string, to: string, useRegex: boolean}, ...]
     */
    WidgetRegistry.register('text-replace-rules', {
        render(key, schema, value, onChange) {
            const initScript = `
                if (!paramValues['${key}'] || !Array.isArray(paramValues['${key}'])) {
                    paramValues['${key}'] = [];
                }
            `;

            return `
                <div x-init="${initScript}" class="space-y-3">
                    <!-- 규칙 목록 -->
                    <template x-for="(rule, index) in paramValues['${key}']" :key="index">
                        <div class="flex flex-wrap items-center gap-2 p-3 bg-gray-50 rounded-lg">
                            <input type="text"
                                   x-model="rule.from"
                                   placeholder="원본 텍스트"
                                   class="${baseInputClass} w-32 text-sm">
                            <span class="text-gray-400">→</span>
                            <input type="text"
                                   x-model="rule.to"
                                   placeholder="대체 텍스트"
                                   class="${baseInputClass} w-32 text-sm">
                            <label class="flex items-center gap-1 text-xs text-gray-600 cursor-pointer">
                                <input type="checkbox"
                                       x-model="rule.useRegex"
                                       class="rounded text-blue-500">
                                정규식
                            </label>
                            <button type="button"
                                    @click="paramValues['${key}'].splice(index, 1)"
                                    class="text-red-500 hover:text-red-700 ml-auto">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                </svg>
                            </button>
                        </div>
                    </template>

                    <!-- 규칙 추가 버튼 -->
                    <button type="button"
                            @click="paramValues['${key}'].push({from: '', to: '', useRegex: false})"
                            x-show="paramValues['${key}'].length < 20"
                            class="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
                        </svg>
                        치환 규칙 추가
                    </button>

                    <p class="text-xs text-gray-500" x-show="paramValues['${key}'].length === 0">
                        치환 규칙을 추가하세요. 예: "글쎄요" → "음..."
                    </p>
                </div>
            `;
        }
    });

    /**
     * 프롬프트 구조 설정 위젯
     *
     * 글 구조별 세부 프롬프트 설정
     * 저장 형식: {sections: {...}, features: {...}}
     */
    WidgetRegistry.register('prompt-structure', {
        render(key, schema, value, onChange) {
            const initScript = `
                if (!paramValues['${key}'] || typeof paramValues['${key}'] !== 'object') {
                    paramValues['${key}'] = {
                        sections: {
                            introduction: { enabled: true, prompt: '', min_words: 100 },
                            body: { enabled: true, prompt: '', min_words: 500, paragraphs: 3 },
                            conclusion: { enabled: true, prompt: '', min_words: 100 }
                        },
                        features: {
                            include_images: false,
                            image_count: 2,
                            internal_links: false,
                            link_count: 3
                        }
                    };
                }
            `;

            return `
                <div x-init="${initScript}" class="space-y-4">
                    <!-- 섹션 설정 -->
                    <div class="border rounded-lg overflow-hidden">
                        <div class="bg-gray-100 px-4 py-2 font-medium text-sm">글 구조 섹션</div>

                        <!-- 서론 -->
                        <div class="p-4 border-b">
                            <label class="flex items-center gap-2 mb-2">
                                <input type="checkbox"
                                       x-model="paramValues['${key}'].sections.introduction.enabled"
                                       class="rounded text-blue-500">
                                <span class="font-medium">서론</span>
                            </label>
                            <div x-show="paramValues['${key}'].sections.introduction.enabled" class="space-y-2 ml-6">
                                <textarea x-model="paramValues['${key}'].sections.introduction.prompt"
                                          placeholder="서론 작성 지시사항..."
                                          rows="2"
                                          class="${baseInputClass} w-full text-sm"></textarea>
                                <div class="flex items-center gap-2">
                                    <span class="text-xs text-gray-500">최소 단어 수:</span>
                                    <input type="number"
                                           x-model.number="paramValues['${key}'].sections.introduction.min_words"
                                           min="50" max="500"
                                           class="${baseInputClass} w-20 text-sm">
                                </div>
                            </div>
                        </div>

                        <!-- 본문 -->
                        <div class="p-4 border-b">
                            <label class="flex items-center gap-2 mb-2">
                                <input type="checkbox"
                                       x-model="paramValues['${key}'].sections.body.enabled"
                                       class="rounded text-blue-500">
                                <span class="font-medium">본문</span>
                            </label>
                            <div x-show="paramValues['${key}'].sections.body.enabled" class="space-y-2 ml-6">
                                <textarea x-model="paramValues['${key}'].sections.body.prompt"
                                          placeholder="본문 작성 지시사항..."
                                          rows="3"
                                          class="${baseInputClass} w-full text-sm"></textarea>
                                <div class="flex flex-wrap items-center gap-4">
                                    <div class="flex items-center gap-2">
                                        <span class="text-xs text-gray-500">최소 단어 수:</span>
                                        <input type="number"
                                               x-model.number="paramValues['${key}'].sections.body.min_words"
                                               min="100" max="5000"
                                               class="${baseInputClass} w-20 text-sm">
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <span class="text-xs text-gray-500">문단 수:</span>
                                        <input type="number"
                                               x-model.number="paramValues['${key}'].sections.body.paragraphs"
                                               min="1" max="10"
                                               class="${baseInputClass} w-16 text-sm">
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- 결론 -->
                        <div class="p-4">
                            <label class="flex items-center gap-2 mb-2">
                                <input type="checkbox"
                                       x-model="paramValues['${key}'].sections.conclusion.enabled"
                                       class="rounded text-blue-500">
                                <span class="font-medium">결론</span>
                            </label>
                            <div x-show="paramValues['${key}'].sections.conclusion.enabled" class="space-y-2 ml-6">
                                <textarea x-model="paramValues['${key}'].sections.conclusion.prompt"
                                          placeholder="결론 작성 지시사항..."
                                          rows="2"
                                          class="${baseInputClass} w-full text-sm"></textarea>
                                <div class="flex items-center gap-2">
                                    <span class="text-xs text-gray-500">최소 단어 수:</span>
                                    <input type="number"
                                           x-model.number="paramValues['${key}'].sections.conclusion.min_words"
                                           min="50" max="500"
                                           class="${baseInputClass} w-20 text-sm">
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- 추가 기능 -->
                    <div class="border rounded-lg overflow-hidden">
                        <div class="bg-gray-100 px-4 py-2 font-medium text-sm">추가 기능</div>
                        <div class="p-4 space-y-3">
                            <!-- 이미지 포함 -->
                            <div>
                                <label class="flex items-center gap-2">
                                    <input type="checkbox"
                                           x-model="paramValues['${key}'].features.include_images"
                                           class="rounded text-blue-500">
                                    <span>이미지 포함</span>
                                </label>
                                <div x-show="paramValues['${key}'].features.include_images" class="ml-6 mt-2">
                                    <div class="flex items-center gap-2">
                                        <span class="text-xs text-gray-500">이미지 수:</span>
                                        <input type="number"
                                               x-model.number="paramValues['${key}'].features.image_count"
                                               min="1" max="10"
                                               class="${baseInputClass} w-16 text-sm">
                                    </div>
                                </div>
                            </div>

                            <!-- 내부 링크 -->
                            <div>
                                <label class="flex items-center gap-2">
                                    <input type="checkbox"
                                           x-model="paramValues['${key}'].features.internal_links"
                                           class="rounded text-blue-500">
                                    <span>내부 링크 자동 생성</span>
                                </label>
                                <div x-show="paramValues['${key}'].features.internal_links" class="ml-6 mt-2">
                                    <div class="flex items-center gap-2">
                                        <span class="text-xs text-gray-500">링크 수:</span>
                                        <input type="number"
                                               x-model.number="paramValues['${key}'].features.link_count"
                                               min="1" max="10"
                                               class="${baseInputClass} w-16 text-sm">
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }
    });

    /**
     * 프롬프트 고급 설정 위젯
     *
     * 글쓰기 스타일, 말투, 단어 수 등 고급 설정
     */
    WidgetRegistry.register('prompt-advanced', {
        render(key, schema, value, onChange) {
            const initScript = `
                if (!paramValues['${key}'] || typeof paramValues['${key}'] !== 'object') {
                    paramValues['${key}'] = {
                        writing_style: 'professional',
                        speech_style: 'formal',
                        word_count: 1500,
                        seo_focus: false
                    };
                }
            `;

            return `
                <div x-init="${initScript}" class="space-y-4 p-4 bg-gray-50 rounded-lg">
                    <!-- 글쓰기 스타일 -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">글쓰기 스타일</label>
                        <div class="flex flex-wrap gap-2">
                            <label class="flex items-center gap-2 px-3 py-2 border rounded-lg cursor-pointer"
                                   :class="paramValues['${key}'].writing_style === 'professional' ? 'border-blue-500 bg-blue-50' : 'border-gray-200'">
                                <input type="radio" value="professional"
                                       x-model="paramValues['${key}'].writing_style"
                                       class="sr-only">
                                <span>전문적</span>
                            </label>
                            <label class="flex items-center gap-2 px-3 py-2 border rounded-lg cursor-pointer"
                                   :class="paramValues['${key}'].writing_style === 'casual' ? 'border-blue-500 bg-blue-50' : 'border-gray-200'">
                                <input type="radio" value="casual"
                                       x-model="paramValues['${key}'].writing_style"
                                       class="sr-only">
                                <span>캐주얼</span>
                            </label>
                            <label class="flex items-center gap-2 px-3 py-2 border rounded-lg cursor-pointer"
                                   :class="paramValues['${key}'].writing_style === 'friendly' ? 'border-blue-500 bg-blue-50' : 'border-gray-200'">
                                <input type="radio" value="friendly"
                                       x-model="paramValues['${key}'].writing_style"
                                       class="sr-only">
                                <span>친근한</span>
                            </label>
                        </div>
                    </div>

                    <!-- 말투 -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">말투</label>
                        <div class="flex flex-wrap gap-2">
                            <label class="flex items-center gap-2 px-3 py-2 border rounded-lg cursor-pointer"
                                   :class="paramValues['${key}'].speech_style === 'formal' ? 'border-blue-500 bg-blue-50' : 'border-gray-200'">
                                <input type="radio" value="formal"
                                       x-model="paramValues['${key}'].speech_style"
                                       class="sr-only">
                                <span>존댓말 (~합니다)</span>
                            </label>
                            <label class="flex items-center gap-2 px-3 py-2 border rounded-lg cursor-pointer"
                                   :class="paramValues['${key}'].speech_style === 'informal' ? 'border-blue-500 bg-blue-50' : 'border-gray-200'">
                                <input type="radio" value="informal"
                                       x-model="paramValues['${key}'].speech_style"
                                       class="sr-only">
                                <span>반말 (~해요)</span>
                            </label>
                        </div>
                    </div>

                    <!-- 목표 단어 수 -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">목표 단어 수</label>
                        <div class="flex items-center gap-2">
                            <input type="range"
                                   x-model.number="paramValues['${key}'].word_count"
                                   min="500" max="5000" step="100"
                                   class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer">
                            <span class="text-sm font-medium w-20 text-right"
                                  x-text="paramValues['${key}'].word_count + '자'"></span>
                        </div>
                        <div class="flex justify-between text-xs text-gray-400 mt-1">
                            <span>500자</span>
                            <span>5000자</span>
                        </div>
                    </div>

                    <!-- SEO 최적화 -->
                    <div>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox"
                                   x-model="paramValues['${key}'].seo_focus"
                                   class="rounded text-blue-500">
                            <span class="font-medium">SEO 최적화 적용</span>
                        </label>
                        <p class="text-xs text-gray-500 ml-6 mt-1">
                            키워드 밀도, 헤딩 구조, 메타 설명 등 SEO 요소를 고려하여 글을 작성합니다.
                        </p>
                    </div>
                </div>
            `;
        }
    });

    /**
     * 뉴스레터 소스 목록 위젯
     *
     * 뉴스레터 URL 또는 이메일 주소 목록
     * 저장 형식: [{type: 'url'|'email', value: string, name: string}, ...]
     */
    WidgetRegistry.register('newsletter-source-list', {
        render(key, schema, value, onChange) {
            const initScript = `
                if (!paramValues['${key}'] || !Array.isArray(paramValues['${key}'])) {
                    paramValues['${key}'] = [];
                }
            `;

            return `
                <div x-init="${initScript}" class="space-y-3">
                    <!-- 소스 목록 -->
                    <template x-for="(source, index) in paramValues['${key}']" :key="index">
                        <div class="flex flex-wrap items-center gap-2 p-3 bg-gray-50 rounded-lg">
                            <select x-model="source.type"
                                    class="${baseInputClass} w-24 text-sm">
                                <option value="url">URL</option>
                                <option value="email">이메일</option>
                            </select>
                            <input type="text"
                                   x-model="source.value"
                                   :placeholder="source.type === 'url' ? 'https://...' : 'newsletter@example.com'"
                                   class="${baseInputClass} flex-1 text-sm">
                            <input type="text"
                                   x-model="source.name"
                                   placeholder="별칭 (선택)"
                                   class="${baseInputClass} w-24 text-sm">
                            <button type="button"
                                    @click="paramValues['${key}'].splice(index, 1)"
                                    class="text-red-500 hover:text-red-700">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                </svg>
                            </button>
                        </div>
                    </template>

                    <!-- 소스 추가 버튼 -->
                    <button type="button"
                            @click="paramValues['${key}'].push({type: 'url', value: '', name: ''})"
                            x-show="paramValues['${key}'].length < 10"
                            class="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
                        </svg>
                        뉴스레터 소스 추가
                    </button>

                    <p class="text-xs text-gray-500" x-show="paramValues['${key}'].length === 0">
                        수집할 뉴스레터 URL 또는 이메일 주소를 추가하세요.
                    </p>
                </div>
            `;
        }
    });

    console.log('[AdvancedWidgets] 고급 위젯 로드 완료:', WidgetRegistry.list());
})();
