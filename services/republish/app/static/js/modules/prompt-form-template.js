/**
 * 프롬프트 모듈 폼 HTML 템플릿 - list.js의 getFullFormTemplate()에서 호출
 * 섹션별 함수: prompt-form-template-sections.js (참조자료 + 글 생성)
 */

/** 1. 카테고리 선택 섹션 */
function getPromptCategorySection() {
    return `
                            <!-- 1. 카테고리 선택 섹션 -->
                            <div class="space-y-4">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    📂 카테고리 연결
                                    <span class="text-xs font-normal text-gray-500">(프롬프트가 적용될 카테고리 선택)</span>
                                </h3>

                                <!-- 카테고리 로딩 -->
                                <div x-show="promptModule.categoriesLoading" class="flex items-center gap-2 text-sm text-gray-500 p-4">⏳ 카테고리 로딩 중...</div>
                                <!-- 카테고리 없음 -->
                                <div x-show="!promptModule.categoriesLoading && promptModule.topics.length === 0" class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                                    <p class="text-sm text-yellow-800">⚠️ 등록된 카테고리가 없습니다. <a href="/categories" class="text-blue-600 hover:underline">카테고리 관리</a>에서 먼저 카테고리를 추가해주세요.</p>
                                </div>

                                <!-- 카테고리 트리 선택 -->
                                <div x-show="!promptModule.categoriesLoading && promptModule.topics.length > 0" class="border border-gray-200 rounded-lg max-h-64 overflow-y-auto">
                                    <template x-for="topic in promptModule.topics" :key="topic.id">
                                        <div class="border-b border-gray-100 last:border-b-0">
                                            <div class="flex items-center gap-2 p-3 bg-gray-50 hover:bg-gray-100 cursor-pointer" @click="toggleTopicExpand(topic.id)">
                                                <svg class="w-4 h-4 text-gray-500 transition-transform" :class="promptModule.expandedTopics.includes(topic.id) ? 'rotate-90' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
                                                <input type="checkbox" :checked="isTopicSelected(topic.id)" @click.stop="toggleTopicSelection(topic.id)" class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500">
                                                <span class="font-medium text-gray-800" x-text="topic.name"></span>
                                                <span class="text-xs text-gray-500" x-text="'(' + (topic.subcategories?.length || 0) + ')'"></span>
                                            </div>
                                            <div x-show="promptModule.expandedTopics.includes(topic.id)" x-transition class="pl-8 bg-white">
                                                <template x-for="subtopic in topic.subcategories" :key="subtopic.id">
                                                    <div class="flex items-center gap-2 p-2 hover:bg-blue-50 cursor-pointer" @click="toggleSubtopicSelection(topic.id, subtopic.id)">
                                                        <input type="checkbox" :checked="isSubtopicSelected(topic.id, subtopic.id)" @click.stop="toggleSubtopicSelection(topic.id, subtopic.id)" class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500">
                                                        <span class="text-sm text-gray-700" x-text="subtopic.name"></span>
                                                    </div>
                                                </template>
                                            </div>
                                        </div>
                                    </template>
                                </div>

                                <!-- 선택된 카테고리 표시 -->
                                <div x-show="promptModule.selectedCategories.length > 0" class="flex flex-wrap gap-2">
                                    <template x-for="cat in promptModule.selectedCategories" :key="cat.topic_id + '-' + (cat.subtopic_id || 'all')">
                                        <span class="inline-flex items-center px-2 py-1 bg-blue-100 text-blue-800 rounded-full text-xs">
                                            <span x-text="getCategoryDisplayName(cat)"></span>
                                            <button type="button" @click="removeCategory(cat)" class="ml-1 hover:text-blue-600"><svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button>
                                        </span>
                                    </template>
                                </div>
                            </div>`;
}

/** 2. 제목 재조합 설정 섹션 */
function getPromptTitleSection() {
    return `
                            <!-- 2. 제목 재조합 프롬프트 섹션 -->
                            <div class="space-y-4">
                                <div class="flex items-center justify-between">
                                    <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">🏷️ 제목 재조합 설정</h3>
                                    <label class="flex items-center cursor-pointer">
                                        <input type="checkbox" x-model="promptModule.titleRecombine.enabled" class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500">
                                        <span class="ml-2 text-sm text-gray-600">활성화</span>
                                    </label>
                                </div>
                                <div x-show="promptModule.titleRecombine.enabled" x-transition class="space-y-4 p-4 bg-gray-50 rounded-lg">
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">제목 스타일 선택</label>
                                        <div class="grid grid-cols-2 md:grid-cols-5 gap-2">
                                            <template x-for="style in promptModule.titleStyles" :key="style.value">
                                                <label class="flex items-center p-2 border rounded-lg cursor-pointer transition-colors" :class="promptModule.titleRecombine.selectedStyles.includes(style.value) ? 'bg-blue-50 border-blue-400' : 'bg-white border-gray-200 hover:border-gray-300'">
                                                    <input type="checkbox" :value="style.value" :checked="promptModule.titleRecombine.selectedStyles.includes(style.value)" @change="toggleTitleStyle(style.value)" class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500">
                                                    <div class="ml-2"><span class="text-sm font-medium" x-text="style.icon + ' ' + style.label"></span></div>
                                                </label>
                                            </template>
                                        </div>
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">추가 지시사항 (선택)</label>
                                        <textarea x-model="promptModule.titleRecombine.customPrompt" rows="2" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm" placeholder="예: 한국 시장에 맞는 표현 사용, 이모지 포함하지 않기"></textarea>
                                        <p class="text-xs text-gray-400 mt-1">기본 재조합 프롬프트에 추가됩니다. 예: "반말체로 작성", "15자 이내로 짧게"</p>
                                    </div>
                                </div>
                            </div>`;
}

/** 5. 이미지 생성 설정 섹션 */
function getPromptImageSection() {
    return `
                            <!-- 5. 이미지 생성 설정 섹션 -->
                            <div class="space-y-4">
                                <div class="flex items-center justify-between">
                                    <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                        🖼️ 이미지 생성 설정
                                    </h3>
                                    <label class="flex items-center cursor-pointer">
                                        <input type="checkbox"
                                               x-model="promptModule.imageGeneration.enabled"
                                               class="w-4 h-4 text-green-600 rounded focus:ring-green-500">
                                        <span class="ml-2 text-sm text-gray-600">활성화</span>
                                    </label>
                                </div>

                                <div x-show="promptModule.imageGeneration.enabled" x-transition class="space-y-4 p-4 bg-green-50 rounded-lg">

                                    <!-- 공통 안내 메시지 -->
                                    <div class="p-3 bg-gray-50 border border-gray-200 rounded-lg">
                                        <p class="text-xs text-gray-600">
                                            이 설정은 <strong>AI 이미지 생성</strong> 블로그에 적용됩니다.
                                            템플릿 이미지 모드 블로그에서는 블로그 설정의 템플릿이 자동 사용됩니다.
                                        </p>
                                    </div>

                                    <!-- 블로그 image_mode 안내 메시지 -->
                                    <div x-show="getSelectedBlogImageMode() === 'template'"
                                         class="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                                        <p class="text-xs text-blue-700">
                                            현재 연동된 블로그 중 <strong>템플릿 이미지</strong> 모드인 블로그가 있습니다.
                                            해당 블로그에서는 아래 AI 설정 대신 블로그의 템플릿 이미지가 사용됩니다.
                                        </p>
                                    </div>

                                    <div x-show="getSelectedBlogImageMode() === 'openai' || getSelectedBlogImageMode() === 'ai'"
                                         class="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                                        <p class="text-xs text-blue-700">블로그 이미지 모드: <strong>AI 이미지</strong> - AI로 생성된 이미지가 사용됩니다.</p>
                                    </div>

                                    <div x-show="getSelectedBlogImageMode() === 'both'"
                                         class="p-3 bg-purple-50 border border-purple-200 rounded-lg">
                                        <p class="text-xs text-purple-700">블로그 이미지 모드: <strong>AI + 템플릿 병행</strong> - 대표/섹션 이미지 소스를 아래에서 선택하세요.</p>
                                    </div>

                                    <!-- 제목 오버레이 옵션 -->
                                    <div>
                                        <label class="flex items-center cursor-pointer gap-2">
                                            <input type="checkbox"
                                                   x-model="promptModule.imageGeneration.titleOverlay"
                                                   class="w-4 h-4 text-green-600 rounded focus:ring-green-500">
                                            <span class="text-sm text-gray-700">재조합 제목 오버레이</span>
                                        </label>
                                        <p class="text-xs text-gray-400 mt-1 ml-6">AI 생성 이미지 위에 재조합된 제목을 오버레이합니다. 블로그 이미지 설정의 폰트/오버레이 설정이 적용됩니다.</p>
                                    </div>

                                    <!-- both 모드 전용: 대표/섹션 이미지 소스 선택 -->
                                    <div x-show="getSelectedBlogImageMode() === 'both'" class="grid grid-cols-2 gap-4">
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">대표 이미지 소스</label>
                                            <select x-model="promptModule.imageGeneration.coverSource"
                                                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 text-sm">
                                                <option value="template">템플릿 이미지</option>
                                                <option value="ai">AI 생성 이미지</option>
                                            </select>
                                            <p class="text-xs text-gray-400 mt-1">글의 대표(썸네일) 이미지</p>
                                        </div>
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">섹션 이미지 소스</label>
                                            <select x-model="promptModule.imageGeneration.sectionSource"
                                                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 text-sm">
                                                <option value="ai">AI 생성 이미지</option>
                                                <option value="template">템플릿 이미지</option>
                                            </select>
                                            <p class="text-xs text-gray-400 mt-1">글 본문 내 섹션 이미지</p>
                                        </div>
                                    </div>

                                    <!-- AI 이미지 상세 설정 -->
                                    <div class="space-y-4">
                                        <!-- 이미지 AI 안내 -->
                                        <p class="text-xs text-gray-400">이미지 생성 AI 서비스 및 모델은 블로그 설정 > AI 탭에서 설정합니다.</p>

                                        <!-- DALL-E 설정 -->
                                        <div x-show="promptModule.imageGeneration.provider === 'dalle'" x-transition class="space-y-4">
                                            <div class="grid grid-cols-2 gap-4">
                                                <div>
                                                    <label class="block text-sm font-medium text-gray-700 mb-2">이미지 크기</label>
                                                    <select x-model="promptModule.imageGeneration.dalle.size"
                                                            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500">
                                                        <option value="1024x1024">1024x1024 (정사각형)</option>
                                                        <option value="1792x1024">1792x1024 (가로)</option>
                                                        <option value="1024x1792">1024x1792 (세로)</option>
                                                    </select>
                                                </div>
                                                <div>
                                                    <label class="block text-sm font-medium text-gray-700 mb-2">품질</label>
                                                    <select x-model="promptModule.imageGeneration.dalle.quality"
                                                            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500">
                                                        <option value="standard">Standard</option>
                                                        <option value="hd">HD (고품질)</option>
                                                    </select>
                                                </div>
                                            </div>
                                            <div>
                                                <label class="block text-sm font-medium text-gray-700 mb-2">스타일</label>
                                                <div class="grid grid-cols-2 gap-2">
                                                    <label class="flex items-center p-2 border rounded-lg cursor-pointer"
                                                           :class="promptModule.imageGeneration.dalle.style === 'vivid' ? 'bg-green-100 border-green-400' : 'bg-white'">
                                                        <input type="radio" value="vivid" x-model="promptModule.imageGeneration.dalle.style"
                                                               class="w-4 h-4 text-green-600">
                                                        <span class="ml-2 text-sm">Vivid (생동감)</span>
                                                    </label>
                                                    <label class="flex items-center p-2 border rounded-lg cursor-pointer"
                                                           :class="promptModule.imageGeneration.dalle.style === 'natural' ? 'bg-green-100 border-green-400' : 'bg-white'">
                                                        <input type="radio" value="natural" x-model="promptModule.imageGeneration.dalle.style"
                                                               class="w-4 h-4 text-green-600">
                                                        <span class="ml-2 text-sm">Natural (자연스러움)</span>
                                                    </label>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- Nano Banana 설정 -->
                                        <div x-show="promptModule.imageGeneration.provider === 'nanobanana'" x-transition class="space-y-4">
                                            <div class="grid grid-cols-2 gap-4">
                                                <div>
                                                    <label class="block text-sm font-medium text-gray-700 mb-2">이미지 비율</label>
                                                    <select x-model="promptModule.imageGeneration.nanobanana.aspectRatio"
                                                            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500">
                                                        <option value="1:1">1:1 (정사각형)</option>
                                                        <option value="16:9">16:9 (가로)</option>
                                                        <option value="9:16">9:16 (세로)</option>
                                                        <option value="4:3">4:3</option>
                                                        <option value="3:4">3:4</option>
                                                    </select>
                                                </div>
                                                <div>
                                                    <label class="block text-sm font-medium text-gray-700 mb-2">스타일</label>
                                                    <select x-model="promptModule.imageGeneration.nanobanana.style"
                                                            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500">
                                                        <option value="realistic">사실적</option>
                                                        <option value="artistic">예술적</option>
                                                        <option value="cartoon">카툰</option>
                                                        <option value="minimal">미니멀</option>
                                                    </select>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- 이미지 프롬프트 템플릿 -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">
                                                이미지 프롬프트 템플릿
                                                <span class="text-xs text-gray-500">(변수: {title}, {keywords})</span>
                                            </label>
                                            <textarea x-model="promptModule.imageGeneration.promptTemplate"
                                                      rows="3"
                                                      class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 text-sm"
                                                      placeholder="{title} 주제의 블로그 대표 이미지. {keywords} 키워드를 시각적으로 표현. 깔끔하고 전문적인 디자인."></textarea>
                                        </div>

                                        <!-- 이미지 개수 -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">글당 생성 이미지 수</label>
                                            <input type="number"
                                                   x-model.number="promptModule.imageGeneration.imagesPerPost"
                                                   min="1" max="5"
                                                   class="w-24 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500">
                                        </div>
                                    </div>
                                </div>
                            </div>`;
}

/** 6. 블로그 선택 섹션 */
function getPromptBlogSection() {
    return `
                            <!-- 6. 블로그 선택 섹션 (카테고리 연동) -->
                            <div class="space-y-4">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    📝 블로그 선택
                                    <span class="text-xs font-normal text-gray-500">(선택한 카테고리가 등록된 블로그)</span>
                                </h3>

                                <!-- 카테고리 미선택 시 안내 -->
                                <div x-show="promptModule.selectedCategories.length === 0"
                                     class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                                    <p class="text-sm text-yellow-800">
                                        ⚠️ 먼저 카테고리를 선택해주세요. 선택한 카테고리가 등록된 블로그가 표시됩니다.
                                    </p>
                                </div>

                                <!-- 카테고리 선택됨: 매칭된 블로그 표시 -->
                                <div x-show="promptModule.selectedCategories.length > 0">
                                    <!-- 플랫폼 탭 -->
                                    <div class="flex gap-2 border-b border-gray-200 mb-4">
                                        <button type="button" @click="promptModule.activeBlogTab = 'wordpress'"
                                                :class="promptModule.activeBlogTab === 'wordpress' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500'"
                                                class="px-4 py-2 text-sm font-medium">
                                            🌐 WordPress
                                            <span class="text-xs ml-1" x-text="'(' + getMatchedBlogsByPlatform('wordpress').length + ')'"></span>
                                        </button>
                                        <button type="button" @click="promptModule.activeBlogTab = 'blogger'"
                                                :class="promptModule.activeBlogTab === 'blogger' ? 'border-b-2 border-orange-500 text-orange-600' : 'text-gray-500'"
                                                class="px-4 py-2 text-sm font-medium">
                                            📙 Blogger
                                            <span class="text-xs ml-1" x-text="'(' + getMatchedBlogsByPlatform('blogger').length + ')'"></span>
                                        </button>
                                    </div>

                                    <!-- 블로그 로딩 -->
                                    <div x-show="promptModule.blogsLoading" class="flex items-center gap-2 text-sm text-gray-500 p-4">
                                        <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                        </svg>
                                        블로그 로딩 중...
                                    </div>

                                    <!-- 블로그 목록 -->
                                    <div x-show="!promptModule.blogsLoading" class="max-h-64 overflow-y-auto space-y-2">
                                        <template x-for="blog in getMatchedBlogsByPlatform(promptModule.activeBlogTab)" :key="blog.id">
                                            <div class="flex items-center gap-3 p-3 border rounded-lg cursor-pointer hover:bg-gray-50"
                                                 :class="promptModule.selectedBlogs.includes(blog.id) ? 'ring-2 ring-blue-500 border-blue-500' : 'border-gray-200'"
                                                 @click="toggleBlogSelection(blog.id)">
                                                <input type="checkbox"
                                                       :checked="promptModule.selectedBlogs.includes(blog.id)"
                                                       @click.stop="toggleBlogSelection(blog.id)"
                                                       class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500">
                                                <div class="flex-1 min-w-0">
                                                    <div class="font-medium text-gray-900 truncate" x-text="blog.name"></div>
                                                    <div class="text-xs text-gray-500 truncate" x-text="blog.url"></div>
                                                </div>
                                            </div>
                                        </template>

                                        <!-- 해당 플랫폼에 매칭된 블로그 없음 -->
                                        <div x-show="!promptModule.blogsLoading && getMatchedBlogsByPlatform(promptModule.activeBlogTab).length === 0"
                                             class="p-4 text-center text-gray-500 text-sm">
                                            해당 플랫폼에 선택한 카테고리가 등록된 블로그가 없습니다.
                                        </div>
                                    </div>

                                    <!-- 전체 매칭 블로그 없음 -->
                                    <div x-show="!promptModule.blogsLoading && promptModule.matchedBlogs.length === 0"
                                         class="p-4 bg-gray-50 border border-gray-200 rounded-lg mt-2">
                                        <p class="text-sm text-gray-600">
                                            선택한 카테고리가 등록된 블로그가 없습니다.
                                            <a href="/blogs" class="text-blue-600 hover:underline">블로그 관리</a>에서 카테고리를 연결해주세요.
                                        </p>
                                    </div>

                                    <!-- 선택 카운트 및 전체 선택 버튼 -->
                                    <div x-show="promptModule.matchedBlogs.length > 0" class="flex items-center justify-between mt-3">
                                        <span class="text-sm text-blue-600">
                                            <span x-text="promptModule.selectedBlogs.length"></span>개 블로그 선택됨
                                        </span>
                                        <button type="button"
                                                @click="selectAllMatchedBlogs()"
                                                class="text-sm text-blue-600 hover:text-blue-800 underline">
                                            전체 선택 (<span x-text="promptModule.matchedBlogs.length"></span>)
                                        </button>
                                    </div>
                                </div>
                            </div>`;
}

/** 전체 프롬프트 모듈 폼 템플릿 (설정-테스트 인터리빙 구조) */
function getPromptModuleFormTemplate() {
    return `
                        <!-- 프롬프트 모듈 설정 -->
                        <div x-show="formData.type_code === 'prompt'" class="space-y-6">
${getPromptCategorySection()}
${getPromptBlogSection()}
${getTestBlogAndTitleSection()}
${getPromptTitleSection()}
${getTestRecombineSection()}
${getPromptReferenceSection()}
${getTestReferenceSection()}
${getPromptContentGenSection()}
${getTestContentSection()}
${getPromptInternalLinksSection()}
${getTestInternalLinksSection()}
${getPromptSubstitutionSection()}
${getPromptImageSection()}
${getTestImageSection()}
${getTestSubstitutionSection()}
${getTestFullPipelineSection()}
                        </div>
`;
}

// 전역 노출
window.getPromptModuleFormTemplate = getPromptModuleFormTemplate;
