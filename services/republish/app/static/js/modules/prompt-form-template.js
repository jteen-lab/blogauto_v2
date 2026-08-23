/**
 * 프롬프트 모듈 폼 HTML 템플릿 - list.js의 getFullFormTemplate()에서 호출
 * 섹션별 함수: prompt-form-template-sections.js (참조자료 + 글 생성)
 */

/** 카테고리 모드 콘텐츠 (카테고리 트리 + 선택 태그) */
function getPromptCategoryModeContent() {
    return `
                                <div x-show="promptModule.linking.linkMode === 'category'" x-transition class="space-y-4">
                                    <div x-show="promptModule.categoriesLoading" class="flex items-center gap-2 text-sm text-gray-500 p-4">⏳ 카테고리 로딩 중...</div>
                                    <div x-show="!promptModule.categoriesLoading && promptModule.topics.length === 0" class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                                        <p class="text-sm text-yellow-800">⚠️ 등록된 카테고리가 없습니다. <a href="/categories" class="text-blue-600 hover:underline">카테고리 관리</a>에서 먼저 카테고리를 추가해주세요.</p>
                                    </div>
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

/** 블로그 기준 모드 콘텐츠 (블로그 선택 + 자동 연결 카테고리) */
function getCategoryBlogModeContent() {
    return `
                                <div x-show="promptModule.linking.linkMode === 'blog'" x-transition class="space-y-4">
                                    <div x-show="promptModule.blogsLoading" class="flex items-center gap-2 text-sm text-gray-500 p-4">⏳ 블로그 로딩 중...</div>
                                    <div x-show="!promptModule.blogsLoading" class="space-y-4">
                                        <div class="flex gap-2 border-b border-gray-200 mb-4">
                                            <button type="button" @click="promptModule.activeBlogTab = 'wordpress'" :class="promptModule.activeBlogTab === 'wordpress' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500'" class="px-4 py-2 text-sm font-medium">🌐 WordPress</button>
                                            <button type="button" @click="promptModule.activeBlogTab = 'blogger'" :class="promptModule.activeBlogTab === 'blogger' ? 'border-b-2 border-orange-500 text-orange-600' : 'text-gray-500'" class="px-4 py-2 text-sm font-medium">📙 Blogger</button>
                                        </div>
                                        <div class="max-h-64 overflow-y-auto space-y-2">
                                            <template x-for="blog in getBlogsByPlatform(promptModule.activeBlogTab)" :key="blog.id">
                                                <div class="flex items-center gap-3 p-3 border rounded-lg cursor-pointer hover:bg-gray-50"
                                                     :class="promptModule.selectedBlogs.includes(blog.id) ? 'ring-2 ring-blue-500 border-blue-500' : 'border-gray-200'"
                                                     @click="onBlogSelectInBlogMode(blog.id)">
                                                    <input type="checkbox" :checked="promptModule.selectedBlogs.includes(blog.id)" @click.stop="onBlogSelectInBlogMode(blog.id)" class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500">
                                                    <div class="flex-1 min-w-0">
                                                        <div class="font-medium text-gray-900 truncate" x-text="blog.name"></div>
                                                        <div class="text-xs text-gray-500 truncate" x-text="blog.url"></div>
                                                    </div>
                                                </div>
                                            </template>
                                            <div x-show="getBlogsByPlatform(promptModule.activeBlogTab).length === 0" class="p-4 text-center text-gray-500 text-sm">해당 플랫폼에 등록된 블로그가 없습니다.</div>
                                        </div>
                                    </div>
                                    <div x-show="promptModule.selectedBlogs.length > 0" class="space-y-3">
                                        <h4 class="text-sm font-medium text-gray-700">자동 연결된 카테고리</h4>
                                        <template x-for="blogId in promptModule.selectedBlogs" :key="blogId">
                                            <div class="p-3 bg-gray-50 rounded-lg space-y-2">
                                                <div class="text-sm font-medium" x-text="getBlogName(blogId)"></div>
                                                <div class="flex flex-wrap gap-1">
                                                    <template x-for="cat in getAutoLinkedCategories(blogId)" :key="cat.topic_id + '-' + (cat.subtopic_id || 'all')">
                                                        <span class="inline-flex items-center px-2 py-0.5 bg-green-100 text-green-800 rounded-full text-xs">
                                                            <span x-text="cat.topic_name + (cat.subtopic_name ? ' > ' + cat.subtopic_name : '')"></span>
                                                        </span>
                                                    </template>
                                                </div>
                                                <template x-for="exc in getExcludedCategoriesForBlog(blogId)" :key="exc.topic_id + '-' + (exc.subtopic_id || 'all')">
                                                    <div class="flex items-center gap-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs">
                                                        <span class="text-amber-700">⚠️ <span x-text="exc.topic_name + (exc.subtopic_name ? ' > ' + exc.subtopic_name : '')"></span> → <span x-text="exc.module_name"></span>에서 사용 중</span>
                                                        <button type="button" @click="showForceLink(blogId, [exc], exc.module_name, exc.module_id)" class="ml-auto px-2 py-1 bg-amber-600 text-white rounded text-xs hover:bg-amber-700">이 모듈에서 사용하기</button>
                                                    </div>
                                                </template>
                                            </div>
                                        </template>
                                    </div>
                                </div>`;
}

/** 1. 카테고리/블로그 연동 탭 섹션 */
function getPromptLinkingSection() {
    return `
                            <div class="space-y-4">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    📂 카테고리 / 블로그 연동
                                    <span class="text-xs font-normal text-gray-500">(연동 방식을 선택하세요)</span>
                                </h3>
                                <div class="flex gap-2 mb-4">
                                    <button type="button" @click="switchLinkMode('category')"
                                            :class="promptModule.linking.linkMode === 'category' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'"
                                            class="px-4 py-2 rounded-lg text-sm font-medium transition-colors">📂 카테고리 기준</button>
                                    <button type="button" @click="switchLinkMode('blog')"
                                            :class="promptModule.linking.linkMode === 'blog' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'"
                                            class="px-4 py-2 rounded-lg text-sm font-medium transition-colors">📝 블로그 기준</button>
                                </div>
${getPromptCategoryModeContent()}
${getCategoryBlogModeContent()}
                            </div>`;
}

/** 1-2. 애드센스 승인용 (F4 니치 강제 + F7 정보이득) — 이 모듈에만 적용 */
function getPromptAdsenseSection() {
    return `
                            <div class="space-y-4 border border-amber-200 bg-amber-50/40 rounded-lg p-4">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    💰 애드센스 승인용 설정
                                    <span class="text-xs font-normal text-gray-500">(선택 · 이 모듈에만 적용)</span>
                                </h3>

                                <!-- 모듈 실행 조건(애드센스 상태 연동) -->
                                <div class="space-y-2 pb-3 border-b border-amber-200">
                                    <label class="block text-sm font-medium text-gray-800">이 모듈을 실행할 시점</label>
                                    <select x-model="promptModule.adsense.role"
                                            class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-500">
                                        <option value="always">항상 실행 (기본)</option>
                                        <option value="adsense_only">애드센스 승인 전에만 실행</option>
                                        <option value="post_approval">애드센스 승인 후에만 실행</option>
                                    </select>
                                    <p class="text-xs text-gray-500">
                                        블로그마다 애드센스 상태가 다르면 <strong>블로그별로</strong> 판정합니다.
                                        예를 들어 '승인 전에만'으로 두면, 이 모듈에 연결된 블로그 중
                                        <strong>아직 승인되지 않은 블로그에만</strong> 글이 생성됩니다.
                                        승인된 블로그는 자동으로 빠지므로 설정을 바꿀 필요가 없습니다.
                                    </p>
                                </div>

                                <!-- F4 니치(주제) 강제 -->
                                <div class="space-y-3">
                                    <label class="flex items-center gap-2 cursor-pointer">
                                        <input type="checkbox" x-model="promptModule.adsense.nicheEnabled" class="w-4 h-4 text-amber-600 rounded focus:ring-amber-500">
                                        <span class="text-sm font-medium text-gray-800">니치(주제) 강제</span>
                                    </label>
                                    <p class="text-xs text-gray-500 pl-6">켜면 이 모듈이 아래 선택한 주제(topic)의 제목만 생성합니다. 애드센스 E-E-A-T 니치 집중용(단일 주제 권장).</p>
                                    <div x-show="promptModule.adsense.nicheEnabled" x-transition class="pl-6 space-y-2">
                                        <div x-show="promptModule.topics.length === 0" class="text-xs text-yellow-700">등록된 주제가 없습니다. <a href="/categories" class="text-blue-600 hover:underline">카테고리 관리</a>에서 추가하세요.</div>
                                        <div x-show="promptModule.topics.length > 0" class="border border-gray-200 rounded-lg max-h-48 overflow-y-auto bg-white">
                                            <template x-for="topic in promptModule.topics" :key="'niche-' + topic.id">
                                                <label class="flex items-center gap-2 p-2 border-b border-gray-100 last:border-b-0 hover:bg-amber-50 cursor-pointer">
                                                    <input type="checkbox" :checked="isNicheTopicSelected(topic.id)" @change="toggleNicheTopic(topic.id)" class="w-4 h-4 text-amber-600 rounded focus:ring-amber-500">
                                                    <span class="text-sm text-gray-700" x-text="topic.name"></span>
                                                </label>
                                            </template>
                                        </div>
                                        <p x-show="promptModule.adsense.nicheTopicIds.length === 0" class="text-xs text-red-500">⚠️ 주제를 1개 이상 선택해야 니치 강제가 동작합니다(미선택 시 무시).</p>
                                    </div>
                                </div>

                                <!-- F7 정보이득 강화 -->
                                <div class="space-y-2 border-t border-amber-200 pt-3">
                                    <label class="flex items-center gap-2 cursor-pointer">
                                        <input type="checkbox" x-model="promptModule.adsense.infoGainEnabled" class="w-4 h-4 text-amber-600 rounded focus:ring-amber-500">
                                        <span class="text-sm font-medium text-gray-800">정보이득(애드센스) 강화</span>
                                    </label>
                                    <p class="text-xs text-gray-500 pl-6">켜면 글 생성 프롬프트에 정보이득 지시문(고유 관점·구체 팁·비교·주의점·출처)을 자동 주입합니다.</p>
                                </div>
                            </div>`;
}

/** 2. 제목 재조합 설정 섹션 */
function getPromptTitleSection() {
    return `
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

/** 5-1. 이미지 섹션 이미지 상세 설정 (하위 콘텐츠) */
function getImageSectionDetailContent() {
    return `
                                    <div class="border-t border-green-200 pt-4 mt-4">
                                        <div class="flex items-center justify-between mb-3">
                                            <h4 class="text-sm font-semibold text-gray-800 flex items-center gap-2">🧩 섹션 이미지 상세 설정</h4>
                                            <label class="flex items-center cursor-pointer">
                                                <input type="checkbox" x-model="promptModule.imageGeneration.sectionCustom" class="w-4 h-4 text-teal-600 rounded focus:ring-teal-500">
                                                <span class="ml-2 text-sm text-gray-600">활성화</span>
                                            </label>
                                        </div>
                                        <div x-show="!promptModule.imageGeneration.sectionCustom" class="p-3 bg-gray-50 border border-gray-200 rounded-lg">
                                            <p class="text-xs text-gray-600">ℹ️ 비활성화 시 대표 이미지 설정 기반 자동 설정 적용 (1:1 비율, standard 품질)</p>
                                        </div>
                                        <div x-show="promptModule.imageGeneration.sectionCustom" x-transition class="space-y-3 p-3 bg-teal-50 border border-teal-200 rounded-lg">
                                            <div>
                                                <label class="block text-sm font-medium text-gray-700 mb-1">섹션 이미지 비율</label>
                                                <select x-model="promptModule.imageGeneration.sectionAspectRatio" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-sm">
                                                    <option value="16:9">16:9 (가로 와이드)</option><option value="4:3">4:3 (가로)</option><option value="1:1">1:1 (정사각형)</option><option value="3:4">3:4 (세로)</option><option value="9:16">9:16 (세로 와이드)</option>
                                                </select>
                                            </div>
                                            <div>
                                                <label class="block text-sm font-medium text-gray-700 mb-1">섹션 이미지 스타일</label>
                                                <select x-model="promptModule.imageGeneration.sectionStyle" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-sm">
                                                    <option value="realistic">사실적 (Realistic)</option><option value="vivid">비비드 (Vivid)</option><option value="artistic">예술적 (Artistic)</option><option value="cartoon">카툰 (Cartoon)</option><option value="minimal">미니멀 (Minimal)</option>
                                                </select>
                                            </div>
                                            <div>
                                                <label class="block text-sm font-medium text-gray-700 mb-1">섹션 이미지 품질</label>
                                                <select x-model="promptModule.imageGeneration.sectionQuality" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-sm">
                                                    <option value="standard">Standard</option><option value="hd">HD</option>
                                                </select>
                                                <p class="text-xs text-gray-400 mt-1">DALL-E 모델 선택 시에만 적용됩니다.</p>
                                            </div>
                                            <div>
                                                <label class="block text-sm font-medium text-gray-700 mb-1">섹션 프롬프트 템플릿 <span class="text-xs text-gray-500">(변수: {title}, {keywords})</span></label>
                                                <textarea x-model="promptModule.imageGeneration.sectionPromptTemplate" rows="2" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-sm" placeholder="{title} 주제의 블로그 섹션 일러스트"></textarea>
                                            </div>
                                            <p class="text-xs text-gray-400">※ 블로그 이미지 모드가 '혼용'이고 섹션 소스가 'AI'일 때 적용됩니다.</p>
                                        </div>
                                    </div>`;
}

/** 5-2. 이미지 모드별 안내 메시지 */
function getImageModeGuides() {
    return `
                                    <div class="p-3 bg-gray-50 border border-gray-200 rounded-lg">
                                        <p class="text-xs text-gray-600">이 설정은 <strong>AI 이미지 생성</strong> 블로그에 적용됩니다. 템플릿 이미지 모드 블로그에서는 블로그 설정의 템플릿이 자동 사용됩니다.</p>
                                    </div>
                                    <div x-show="getSelectedBlogImageMode() === 'template'" class="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                                        <p class="text-xs text-blue-700">현재 연동된 블로그 중 <strong>템플릿 이미지</strong> 모드인 블로그가 있습니다. 해당 블로그에서는 아래 AI 설정 대신 블로그의 템플릿 이미지가 사용됩니다.</p>
                                    </div>
                                    <div x-show="getSelectedBlogImageMode() === 'openai' || getSelectedBlogImageMode() === 'ai'" class="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                                        <p class="text-xs text-blue-700">블로그 이미지 모드: <strong>AI 이미지</strong> - AI로 생성된 이미지가 사용됩니다.</p>
                                    </div>
                                    <div x-show="getSelectedBlogImageMode() === 'both'" class="p-3 bg-purple-50 border border-purple-200 rounded-lg">
                                        <p class="text-xs text-purple-700">블로그 이미지 모드: <strong>AI + 템플릿 병행</strong> - 대표/섹션 이미지 소스를 아래에서 선택하세요.</p>
                                    </div>`;
}

/** 5. 이미지 생성 설정 섹션 */
function getPromptImageSection() {
    return `
                            <div class="space-y-4">
                                <div class="flex items-center justify-between">
                                    <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">🖼️ 이미지 생성 설정</h3>
                                    <span class="text-xs text-gray-500">블로그 이미지 설정에 따라 자동 적용</span>
                                </div>
                                <div x-transition class="space-y-4 p-4 bg-green-50 rounded-lg">
${getImageModeGuides()}
                                    <div>
                                        <label class="flex items-center cursor-pointer gap-2">
                                            <input type="checkbox" x-model="promptModule.imageGeneration.titleOverlay" class="w-4 h-4 text-green-600 rounded focus:ring-green-500">
                                            <span class="text-sm text-gray-700">재조합 제목 오버레이</span>
                                        </label>
                                        <p class="text-xs text-gray-400 mt-1 ml-6">AI 생성 이미지 위에 재조합된 제목을 오버레이합니다.</p>
                                    </div>
                                    <div x-show="getSelectedBlogImageMode() === 'both'" class="p-3 bg-teal-50 border border-teal-200 rounded-lg">
                                        <p class="text-xs text-teal-700">대표/섹션 이미지 소스(AI/템플릿)는 <strong>블로그 설정 > 이미지 탭</strong>에서 블로그별로 설정합니다.</p>
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">이미지 비율</label>
                                        <select x-model="promptModule.imageGeneration.aspectRatio" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 text-sm">
                                            <option value="16:9">16:9 (가로 와이드)</option><option value="4:3">4:3 (가로)</option><option value="1:1">1:1 (정사각형)</option><option value="3:4">3:4 (세로)</option><option value="9:16">9:16 (세로 와이드)</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">이미지 스타일</label>
                                        <select x-model="promptModule.imageGeneration.style" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 text-sm">
                                            <option value="realistic">사실적 (Realistic)</option><option value="vivid">비비드 (Vivid)</option><option value="artistic">예술적 (Artistic)</option><option value="cartoon">카툰 (Cartoon)</option><option value="minimal">미니멀 (Minimal)</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">이미지 품질</label>
                                        <select x-model="promptModule.imageGeneration.quality" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 text-sm">
                                            <option value="standard">Standard</option><option value="hd">HD</option>
                                        </select>
                                        <p class="text-xs text-gray-400 mt-1">DALL-E 모델 선택 시에만 적용됩니다.</p>
                                    </div>
                                    <p class="text-xs text-gray-400">이미지 생성 AI 서비스 및 모델은 블로그 설정 > AI 탭에서 설정합니다.</p>
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">대표 이미지 프롬프트 템플릿 <span class="text-xs text-gray-500">(변수: {title}, {keywords})</span></label>
                                        <textarea x-model="promptModule.imageGeneration.promptTemplate" rows="3" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 text-sm" placeholder="{title} 주제의 블로그 대표 이미지. {keywords} 키워드를 시각적으로 표현."></textarea>
                                    </div>
${getImageSectionDetailContent()}
                                </div>
                            </div>`;
}

/** 6-1. 충돌로 제외된 블로그 경고 (카테고리 모드 하위) */
function getExcludedBlogsWarning() {
    return `
                                    <div x-show="promptModule.linking.excludedBlogs.length > 0" class="mt-3 space-y-2">
                                        <h4 class="text-sm font-medium text-amber-700">⚠️ 다른 모듈에서 사용 중인 블로그</h4>
                                        <template x-for="exc in promptModule.linking.excludedBlogs" :key="exc.blog_id">
                                            <div class="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                                                <div class="flex items-center justify-between">
                                                    <div>
                                                        <span class="text-sm font-medium text-amber-800" x-text="exc.blog_name"></span>
                                                        <div class="text-xs text-amber-600 mt-1">
                                                            <template x-for="conflict in exc.conflicts" :key="conflict.topic_name">
                                                                <span class="mr-2"><span x-text="conflict.topic_name + (conflict.subtopic_name ? ' > ' + conflict.subtopic_name : '')"></span> → <span x-text="conflict.module_name"></span></span>
                                                            </template>
                                                        </div>
                                                    </div>
                                                    <button type="button" @click="showForceLink(exc.blog_id, exc.conflicts.map(c => ({topic_id: c.topic_id, subtopic_id: c.subtopic_id, topic_name: c.topic_name, subtopic_name: c.subtopic_name})), exc.conflicts[0].module_name, exc.conflicts[0].module_id)" class="px-3 py-1 bg-amber-600 text-white rounded-lg text-xs hover:bg-amber-700 whitespace-nowrap">이 모듈에서 사용하기</button>
                                                </div>
                                            </div>
                                        </template>
                                    </div>`;
}

/** 6. 블로그 선택 섹션 (카테고리 모드 전용) */
function getPromptBlogSection() {
    return `
                            <div x-show="promptModule.linking.linkMode === 'category'" class="space-y-4">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    📝 블로그 선택
                                    <span class="text-xs font-normal text-gray-500">(선택한 카테고리가 등록된 블로그)</span>
                                </h3>
                                <div x-show="promptModule.selectedCategories.length === 0" class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                                    <p class="text-sm text-yellow-800">⚠️ 먼저 카테고리를 선택해주세요. 선택한 카테고리가 등록된 블로그가 표시됩니다.</p>
                                </div>
                                <div x-show="promptModule.selectedCategories.length > 0">
                                    <div class="flex gap-2 border-b border-gray-200 mb-4">
                                        <button type="button" @click="promptModule.activeBlogTab = 'wordpress'"
                                                :class="promptModule.activeBlogTab === 'wordpress' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500'"
                                                class="px-4 py-2 text-sm font-medium">🌐 WordPress <span class="text-xs ml-1" x-text="'(' + getMatchedBlogsByPlatform('wordpress').length + ')'"></span></button>
                                        <button type="button" @click="promptModule.activeBlogTab = 'blogger'"
                                                :class="promptModule.activeBlogTab === 'blogger' ? 'border-b-2 border-orange-500 text-orange-600' : 'text-gray-500'"
                                                class="px-4 py-2 text-sm font-medium">📙 Blogger <span class="text-xs ml-1" x-text="'(' + getMatchedBlogsByPlatform('blogger').length + ')'"></span></button>
                                    </div>
                                    <div x-show="promptModule.blogsLoading" class="flex items-center gap-2 text-sm text-gray-500 p-4">
                                        <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                                        블로그 로딩 중...
                                    </div>
                                    <div x-show="!promptModule.blogsLoading" class="max-h-64 overflow-y-auto space-y-2">
                                        <template x-for="blog in getMatchedBlogsByPlatform(promptModule.activeBlogTab)" :key="blog.id">
                                            <div class="flex items-center gap-3 p-3 border rounded-lg cursor-pointer hover:bg-gray-50"
                                                 :class="promptModule.selectedBlogs.includes(blog.id) ? 'ring-2 ring-blue-500 border-blue-500' : 'border-gray-200'"
                                                 @click="toggleBlogSelection(blog.id)">
                                                <input type="checkbox" :checked="promptModule.selectedBlogs.includes(blog.id)" @click.stop="toggleBlogSelection(blog.id)" class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500">
                                                <div class="flex-1 min-w-0">
                                                    <div class="font-medium text-gray-900 truncate" x-text="blog.name"></div>
                                                    <div class="text-xs text-gray-500 truncate" x-text="blog.url"></div>
                                                </div>
                                            </div>
                                        </template>
                                        <div x-show="!promptModule.blogsLoading && getMatchedBlogsByPlatform(promptModule.activeBlogTab).length === 0" class="p-4 text-center text-gray-500 text-sm">해당 플랫폼에 선택한 카테고리가 등록된 블로그가 없습니다.</div>
                                    </div>
                                    <div x-show="!promptModule.blogsLoading && promptModule.matchedBlogs.length === 0" class="p-4 bg-gray-50 border border-gray-200 rounded-lg mt-2">
                                        <p class="text-sm text-gray-600">선택한 카테고리가 등록된 블로그가 없습니다. <a href="/blogs" class="text-blue-600 hover:underline">블로그 관리</a>에서 카테고리를 연결해주세요.</p>
                                    </div>
                                    <div x-show="promptModule.matchedBlogs.length > 0" class="flex items-center justify-between mt-3">
                                        <span class="text-sm text-blue-600"><span x-text="promptModule.selectedBlogs.length"></span>개 블로그 선택됨</span>
                                        <button type="button" @click="selectAllMatchedBlogs()" class="text-sm text-blue-600 hover:text-blue-800 underline">전체 선택 (<span x-text="promptModule.matchedBlogs.length"></span>)</button>
                                    </div>
${getExcludedBlogsWarning()}
                                </div>
                            </div>`;
}

/** 강제 연동 확인 모달 */
function getForceLinkModal() {
    return `
                            <div x-show="promptModule.linking.forceLinkConfirm" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="cancelForceLink()">
                                <div class="bg-white rounded-xl shadow-2xl p-6 max-w-lg mx-4">
                                    <h3 class="text-lg font-bold text-gray-900 mb-3">⚠️ 연동 변경 확인</h3>
                                    <div class="space-y-3">
                                        <p class="text-sm text-gray-700">선택한 카테고리의 블로그 연동을 <strong x-text="promptModule.linking.forceLinkConfirm?.sourceModuleName"></strong>에서 이 모듈로 이동합니다.</p>
                                        <div class="p-3 bg-gray-50 rounded-lg text-sm">
                                            <p class="text-gray-600">변경 내용:</p>
                                            <ul class="mt-1 space-y-1 text-xs text-gray-700">
                                                <li>• 기존 모듈에서 해당 매핑 제거</li>
                                                <li>• 이 모듈에 매핑 추가</li>
                                            </ul>
                                        </div>
                                        <template x-if="promptModule.linking.forceLinkConfirm?.hasWholeTopic && promptModule.linking.forceLinkConfirm?.groupedTopics?.length > 0">
                                            <div class="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                                                <p class="text-xs text-blue-700 mb-2">가져올 카테고리를 선택하세요:</p>
                                                <div class="space-y-1 max-h-48 overflow-y-auto">
                                                    <template x-for="group in promptModule.linking.forceLinkConfirm.groupedTopics" :key="group.topic_id">
                                                        <div>
                                                            <div class="flex items-center gap-2 p-1.5 bg-blue-100/50 rounded cursor-pointer" @click="toggleForceLinkTopicExpand(group.topic_id)">
                                                                <svg class="w-3.5 h-3.5 text-blue-500 transition-transform" :class="promptModule.linking.forceLinkConfirm.expandedTopics?.includes(group.topic_id) ? 'rotate-90' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 5l7 7-7 7"/></svg>
                                                                <input type="checkbox" :checked="isForceLinkTopicSelected(group.topic_id)" @click.stop="toggleForceLinkTopicSelection(group.topic_id)" class="w-3.5 h-3.5 rounded text-blue-600">
                                                                <span class="text-xs font-medium text-blue-900" x-text="group.topic_name"></span>
                                                                <span class="text-xs text-blue-600" x-text="'(' + group.subtopics.length + ')'"></span>
                                                            </div>
                                                            <div x-show="promptModule.linking.forceLinkConfirm.expandedTopics?.includes(group.topic_id)" x-transition class="pl-7 space-y-0.5">
                                                                <template x-for="sub in group.subtopics" :key="sub.subtopic_id">
                                                                    <label class="flex items-center gap-2 p-1 rounded hover:bg-blue-100 cursor-pointer">
                                                                        <input type="checkbox" :checked="isForceLinkSubtopicSelected(group.topic_id, sub.subtopic_id)" @change="toggleForceLinkSubtopicSelection(group.topic_id, sub.subtopic_id)" class="w-3.5 h-3.5 rounded text-blue-600">
                                                                        <span class="text-xs text-gray-700" x-text="sub.subtopic_name"></span>
                                                                    </label>
                                                                </template>
                                                            </div>
                                                        </div>
                                                    </template>
                                                </div>
                                            </div>
                                        </template>
                                    </div>
                                    <div class="flex justify-end gap-3 mt-4">
                                        <button type="button" @click="cancelForceLink()" class="px-4 py-2 text-sm text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200">취소</button>
                                        <button type="button" @click="executeForceLink()" class="px-4 py-2 text-sm text-white bg-amber-600 rounded-lg hover:bg-amber-700">확인</button>
                                    </div>
                                </div>
                            </div>`;
}

/** 전체 프롬프트 모듈 폼 템플릿 (설정-테스트 인터리빙 구조) */
function getPromptModuleFormTemplate() {
    return `
                        <div x-show="formData.type_code === 'prompt'" class="space-y-6">
${getPromptLinkingSection()}
${getPromptAdsenseSection()}
${getPromptBlogSection()}
${getTestBlogAndTitleSection()}
${getTestFullPipelineSection()}
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
${getForceLinkModal()}
                        </div>
`;
}

// 전역 노출
window.getPromptModuleFormTemplate = getPromptModuleFormTemplate;
