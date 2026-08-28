/**
 * 프롬프트 빌더 — 모듈 폼 내부 임베드 패널 HTML.
 *
 * 사용 방식:
 *   - list.html 페이지가 <script id="prompt-builder-blocks-data"> 로 데이터 임베드
 *   - prompt-form-template-sections.js 의 user_prompt_template textarea 직후에
 *     `${window.getPromptBuilderEmbeddedHTML()}` 삽입
 *   - Alpine.js 가 createPromptBuilderState({ mode: 'embedded', onApply: ... }) 생성
 *   - "반영" 버튼이 onApply 콜백으로 promptModule.contentGeneration.userPromptTemplate 채움
 */
window.getPromptBuilderEmbeddedHTML = function () {
    return `
    <div class="border-t border-purple-200 pt-4"
         x-data="createPromptBuilderState({
             mode: 'embedded',
             onApply: (text) => { promptModule.contentGeneration.userPromptTemplate = text; },
             onApplyPreset: (p) => { if (p.full_prompt) promptModule.adsense.infoGainEnabled = false; },
             getSelectedCategoryNames: () => {
                 // 프리셋 추천에 넘길 카테고리 이름.
                 // 연결 방식이 두 가지라 둘 다 본다.
                 //   · 카테고리 기준 모드 → promptModule.selectedCategories (id만 있음)
                 //   · 블로그 기준 모드   → linking.blogCategories[blogId] (이름 포함)
                 const topics = [], subs = [];
                 const addTopic = (n) => { if (n && !topics.includes(n)) topics.push(n); };
                 const addSub = (n) => { if (n && !subs.includes(n)) subs.push(n); };

                 (promptModule.selectedCategories || []).forEach((c) => {
                     const t = (promptModule.topics || []).find((x) => x.id === c.topic_id);
                     if (!t) return;
                     addTopic(t.name);
                     if (c.subtopic_id) {
                         const st = (t.subtopics || []).find((x) => x.id === c.subtopic_id);
                         if (st) addSub(st.name);
                     }
                 });

                 const byBlog = (promptModule.linking && promptModule.linking.blogCategories) || {};
                 (promptModule.selectedBlogs || []).forEach((blogId) => {
                     (byBlog[blogId] || []).forEach((c) => {
                         addTopic(c.topic_name);
                         addSub(c.subtopic_name);
                     });
                 });

                 return { topics, subtopics: subs };
             }
         })"
         x-init="init()">

        <button type="button"
                @click="expanded = !expanded"
                class="flex items-center gap-2 text-sm text-purple-600 hover:text-purple-800">
            <svg class="w-4 h-4 transition-transform"
                 :class="expanded ? 'rotate-90' : ''"
                 fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
            </svg>
            <span class="font-semibold">프롬프트 빌더</span>
            <span class="text-xs text-gray-500">— 페르소나·독자 수준·섹션 패턴·시작 톤을 골라 위 템플릿을 자동 채움</span>
        </button>

        <div x-show="expanded" x-transition class="mt-4 space-y-4">

            <!-- F11: 애드센스 승인용 전용 프롬프트 적용 안내 -->
            <div x-show="fullPromptOverride" x-transition
                 class="p-3 text-xs bg-amber-50 border border-amber-300 text-amber-800 rounded-lg flex items-start gap-2">
                <span>🔒</span>
                <span>애드센스 승인용 <strong>전용 프롬프트</strong>가 적용되었습니다. 아래 4축·글자수
                    설정은 무시되며, 이 전용 프롬프트가 그대로 쓰입니다. "반영"을 눌러 위
                    템플릿에 채우세요. 정보이득 강화 토글은 자동으로 꺼집니다(지시 내장).
                    해제하려면 다른 프리셋을 고르거나 "전체 초기화"를 누르세요.</span>
            </div>

            <!-- 빠른 프리셋 -->
            <div class="bg-purple-50/40 rounded-lg p-3">
                <div class="flex items-center justify-between mb-2">
                    <h3 class="text-sm font-semibold text-gray-800">빠른 프리셋</h3>
                    <button type="button" @click="clearAll()"
                            class="text-xs px-2 py-0.5 border border-red-300 text-red-600 rounded hover:bg-red-50">전체 초기화</button>
                </div>
                <p x-show="hasRecommendation" class="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 mb-2">
                    선택한 카테고리에 맞는 프리셋을 위로 올렸습니다. ★ 표시가 하위 주제까지 맞는 것입니다.
                </p>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                    <template x-for="p in sortedPresets" :key="p.code">
                        <div class="relative group">
                            <button type="button" @click="applyPreset(p.code)"
                                    class="w-full text-left p-2 border-2 rounded transition-colors text-xs"
                                    :class="isActivePreset(p) ? 'border-purple-500 bg-purple-50 ring-1 ring-purple-400'
                                            : (presetMatchScore(p) === 2 ? 'border-amber-400 bg-amber-50'
                                            : (presetMatchScore(p) === 1 ? 'border-amber-200 bg-amber-50/40' : 'border-gray-200 hover:bg-white'))">
                                <div class="flex items-center justify-between gap-2">
                                    <span class="font-medium text-gray-800">
                                        <span x-show="presetMatchScore(p) === 2" class="text-amber-600">★</span>
                                        <span x-show="presetMatchScore(p) === 1" class="text-amber-500">☆</span>
                                        <span x-text="p.label"></span>
                                    </span>
                                    <span class="px-1 py-0.5 text-[10px] bg-gray-100 rounded"
                                          x-text="p._custom ? 'CUSTOM' : p.code.toUpperCase()"></span>
                                </div>
                                <div class="text-[11px] text-gray-500 mt-0.5" x-text="'추천: ' + p.categories"></div>
                            </button>
                            <button type="button" x-show="p._custom"
                                    @click.stop="deleteCustomPreset(p.code)"
                                    class="absolute top-1 right-1 text-red-500 hover:text-red-700 text-xs opacity-0 group-hover:opacity-100"
                                    title="삭제">×</button>
                        </div>
                    </template>
                </div>

                <!-- 커스텀 프리셋 저장 (고정 프리셋 적용 중엔 숨김) -->
                <div x-show="!fullPromptOverride" class="mt-3 flex items-center gap-2">
                    <input type="text" x-model="newPresetName"
                           placeholder="현재 조합을 커스텀 프리셋으로 저장할 이름"
                           class="flex-1 px-2 py-1 border border-gray-300 rounded text-xs">
                    <button type="button" @click="saveCustomPreset()"
                            :disabled="!isComplete()"
                            class="px-3 py-1 text-xs bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-40 disabled:cursor-not-allowed">
                        프리셋 저장
                    </button>
                </div>
                <div x-show="presetWarning" x-transition class="mt-2 p-2 text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded"
                     x-text="presetWarning"></div>
            </div>

            <!-- 섹션 수 (표시 전용 — 패턴 본문에서 도출, 조절 불가) -->
            <div class="bg-white border rounded-lg p-3">
                <div class="flex items-center justify-between">
                    <h3 class="text-sm font-semibold text-gray-800">생성 섹션 수</h3>
                    <span class="text-xs font-mono px-2 py-0.5 bg-gray-100 rounded"><span x-text="derivedSectionCount"></span>개</span>
                </div>
                <p class="text-[10px] text-gray-500 mt-1">선택한 섹션 패턴이 정하며, 구조 약속도 이 값과 일치합니다.</p>
            </div>

            <!-- 최소 글자수 -->
            <div class="bg-white border rounded-lg p-3" :class="fullPromptOverride ? 'opacity-50' : ''">
                <h3 class="text-sm font-semibold text-gray-800 mb-2">최소 글자수</h3>
                <div class="grid grid-cols-3 gap-2">
                    <label class="text-[10px] text-gray-600">도입
                        <input type="number" min="0" step="10" x-model.number="introChars" :disabled="fullPromptLocked"
                               class="mt-0.5 w-full px-1.5 py-1 text-xs border border-gray-300 rounded disabled:bg-gray-100"></label>
                    <label class="text-[10px] text-gray-600">섹션당
                        <input type="number" min="0" step="10" x-model.number="sectionChars" :disabled="fullPromptLocked"
                               class="mt-0.5 w-full px-1.5 py-1 text-xs border border-gray-300 rounded disabled:bg-gray-100"></label>
                    <label class="text-[10px] text-gray-600">마치며
                        <input type="number" min="0" step="10" x-model.number="outroChars" :disabled="fullPromptLocked"
                               class="mt-0.5 w-full px-1.5 py-1 text-xs border border-gray-300 rounded disabled:bg-gray-100"></label>
                </div>
            </div>

            <!-- 5축 라디오 + EDIT -->
            ${getBuilderAxisHTML('persona', '페르소나 (어투)', 'personas')}
            ${getBuilderAxisHTML('reader', '독자 수준', 'readers')}
            ${getBuilderAxisHTML('common', '글쓰기 기본 원칙', 'commons')}
            ${getBuilderAxisHTML('pattern', '섹션 패턴', 'patterns')}
            ${getBuilderAxisHTML('tone', '시작 톤', 'tones')}

            <!-- 미리보기 + 반영 -->
            <div class="bg-white border rounded-lg p-3">
                <div class="flex items-center justify-between mb-2">
                    <h3 class="text-sm font-semibold text-gray-800">완성 프롬프트 미리보기</h3>
                    <div class="flex items-center gap-2">
                        <span class="text-xs text-gray-500">
                            <span x-text="charCount"></span>자 · <span x-text="lineCount"></span>줄
                        </span>
                        <button type="button" @click="applyToTemplate()" :disabled="!isComplete()"
                                class="px-3 py-1 text-xs bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-40 disabled:cursor-not-allowed">
                            <span x-show="!justApplied">사용자 프롬프트 템플릿에 반영</span>
                            <span x-show="justApplied">반영됨!</span>
                        </button>
                    </div>
                </div>
                <div x-show="!isComplete()" class="mb-2 p-2 text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded">
                    4개 블록을 모두 선택하면 반영 버튼이 활성화됩니다.
                </div>
                <textarea readonly x-ref="output" x-text="builtPrompt"
                          class="w-full h-72 font-mono text-[11px] p-2 border rounded bg-gray-50 resize-none whitespace-pre-wrap"></textarea>
            </div>
        </div>
    </div>
    `;
};


/** 4축 라디오 그룹 + EDIT 영역 HTML 생성 (재사용용 내부 함수) */
function getBuilderAxisHTML(field, title, listName) {
    return `
    <div class="bg-white border rounded-lg p-3">
        <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-semibold text-gray-800">${title}</h3>
            <div class="flex items-center gap-2">
                <span class="text-xs text-gray-500" x-text="selectedLabel('${field}', ${listName})"></span>
                <button type="button" @click="toggleEdit('${field}')" :disabled="!${field} || fullPromptLocked"
                        class="text-xs px-2 py-0.5 border rounded disabled:opacity-40 disabled:cursor-not-allowed"
                        :class="editing.${field} ? 'bg-purple-600 text-white' : 'hover:bg-gray-50'">
                    <span x-text="editing.${field} ? '닫기' : 'EDIT'"></span>
                </button>
            </div>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2" :class="fullPromptOverride ? 'opacity-50' : ''">
            <template x-for="opt in ${listName}" :key="opt.code">
                <label class="flex items-start gap-2 p-2 border rounded hover:bg-gray-50"
                       :class="(${field} === opt.code ? 'border-purple-500 bg-purple-50' : 'border-gray-200') + (fullPromptOverride ? ' cursor-not-allowed' : ' cursor-pointer')">
                    <input type="radio" name="${field}-pb" :value="opt.code" x-model="${field}" :disabled="fullPromptLocked" class="mt-0.5">
                    <div>
                        <div class="font-medium text-xs" x-text="opt.label"></div>
                        <div class="text-[10px] text-gray-500 mt-0.5">
                            <span x-text="opt.code"></span>
                            <span x-show="opt.cluster" class="ml-1">· <span x-text="opt.cluster"></span></span>
                        </div>
                    </div>
                </label>
            </template>
        </div>
        <div x-show="editing.${field}" x-transition class="mt-2 p-2 bg-amber-50 border border-amber-200 rounded">
            <div class="flex items-center justify-between mb-1 text-[11px]">
                <span class="text-amber-800">옵션 편집 — "영구 저장"으로 이 옵션을 갱신하거나 "새 옵션으로" 추가하세요.</span>
                <button type="button" @click="resetOverride('${field}')"
                        class="text-gray-500 hover:underline">원본으로</button>
            </div>
            <textarea x-model="overrides.${field}"
                      class="w-full h-32 p-2 text-xs border rounded font-mono bg-white"></textarea>
            <div class="flex items-center gap-2 mt-2">
                <button type="button" @click="persistBlock('${field}')" :disabled="blockBusy"
                        class="px-2 py-1 text-[11px] bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-40">영구 저장</button>
                <button type="button" @click="saveAsNewBlock('${field}')" :disabled="blockBusy"
                        class="px-2 py-1 text-[11px] bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-40">새 옵션으로 저장</button>
                <button type="button" @click="deleteSelectedBlock('${field}')" :disabled="blockBusy"
                        class="px-2 py-1 text-[11px] border border-red-300 text-red-600 rounded hover:bg-red-50 disabled:opacity-40">삭제</button>
                <span x-show="blockMsg" x-text="blockMsg" class="text-[11px] text-emerald-700"></span>
            </div>
        </div>
    </div>
    `;
}
