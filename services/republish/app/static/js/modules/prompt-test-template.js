/** 파이프라인 테스트 인라인 블록 템플릿 - 각 설정 섹션 아래에 배치 */

// 공통 헬퍼: 스피너 (해당 키가 실행 중일 때만 표시)
function _testSpinner(key) {
    const condition = key
        ? `promptTest.loading && promptTest.loadingKey === '${key}'`
        : `promptTest.loading`;
    return `<span x-show="${condition}" class="flex items-center gap-1">
        <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>실행중...</span>`;
}

// 공통 헬퍼: 실행 버튼 (재실행 항상 가능 - 이전 요청은 자동 취소됨)
function _testBtn(fn, label, key) {
    const showLabel = key
        ? `!(promptTest.loading && promptTest.loadingKey === '${key}')`
        : `!promptTest.loading`;
    // 다른 단계가 로딩 중일 때만 disabled (같은 단계는 재실행 허용)
    const disabledCond = key
        ? `promptTest.loading && promptTest.loadingKey !== '${key}'`
        : `false`;
    return `<button type="button" @click="${fn}()"
        :disabled="${disabledCond}"
        class="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        :class="(promptTest.loading && promptTest.loadingKey === '${key}') ? 'opacity-75 cursor-wait' : ''">
        <span x-show="${showLabel}">${label || '실행'}</span>${_testSpinner(key)}</button>`;
}

// 공통 헬퍼: 에러 표시
function _testError(key) {
    return `<template x-if="promptTest.results.${key} && !promptTest.results.${key}.success">
        <div class="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700" x-text="promptTest.results.${key}.error"></div>
    </template>`;
}

// 공통 헬퍼: 인라인 테스트 블록 래퍼
function _testBlockWrapper(key, title, innerHtml) {
    return `
<div x-show="isEdit" class="mt-3">
    <div class="border border-indigo-200 rounded-lg overflow-hidden">
        <button type="button" @click="promptTest.show${_capitalize(key)} = !promptTest.show${_capitalize(key)}"
                class="w-full flex items-center justify-between px-3 py-2 bg-indigo-50 hover:bg-indigo-100 text-sm">
            <span class="font-medium text-indigo-800">🧪 ${title}</span>
            <svg :class="promptTest.show${_capitalize(key)} ? 'rotate-180' : ''" class="w-4 h-4 text-indigo-600 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
        </button>
        <div x-show="promptTest.show${_capitalize(key)}" x-transition class="p-3 bg-white space-y-2">
            ${innerHtml}
        </div>
    </div>
</div>`;
}

// camelCase 키의 첫 글자를 대문자로 (showXxx 토글용)
function _capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

/** 테스트 블로그 선택 + 제목 선택 테스트 */
function getTestBlogAndTitleSection() {
    const inner = `
            <!-- 테스트 블로그 선택 -->
            <div class="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                <label class="text-sm font-medium text-gray-700 whitespace-nowrap">테스트 블로그:</label>
                <select x-model="promptTest.testBlogId"
                        class="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500">
                    <option value="">-- 블로그 선택 --</option>
                    <template x-for="b in getSelectedBlogOptions()" :key="b.id">
                        <option :value="b.id" x-text="b.name"></option>
                    </template>
                </select>
                <button type="button" @click="clearAllTestResults()"
                        class="px-3 py-1.5 text-xs text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">초기화</button>
            </div>
            <!-- 제목 선택 테스트 -->
            <p class="text-xs text-gray-500">사용 가능한 제목 후보를 조회하고 랜덤으로 하나를 선택합니다.</p>
            ${_testBtn('runStepSelectTitle', '실행', 'selectTitle')}
            <template x-if="promptTest.results.selectTitle"><div class="mt-2">
                <template x-if="promptTest.results.selectTitle.success">
                    <div class="p-3 bg-green-50 border border-green-200 rounded-lg space-y-2 text-sm">
                        <div class="font-medium text-green-800">선택된 제목: <span class="font-normal" x-text="promptTest.results.selectTitle.result?.selected_title?.title"></span></div>
                        <div class="text-green-700">후보 수: <span x-text="promptTest.results.selectTitle.result?.total_candidates"></span>개</div>
                        <details class="text-xs"><summary class="cursor-pointer text-green-600 hover:underline">후보 목록 보기</summary>
                            <ul class="mt-1 space-y-0.5 pl-4 list-disc text-gray-600">
                                <template x-for="c in (promptTest.results.selectTitle.result?.candidates || [])" :key="c.id">
                                    <li><span x-text="c.title"></span> <span class="text-gray-400">(ID: <span x-text="c.id"></span>)</span></li>
                                </template>
                            </ul>
                        </details>
                    </div>
                </template>
                ${_testError('selectTitle')}
            </div></template>`;
    return _testBlockWrapper('selectTitle', '제목 선택 테스트', inner);
}

/** 제목 재조합 테스트 */
function getTestRecombineSection() {
    const inner = `
            <p class="text-xs text-gray-500">AI를 사용하여 선택한 스타일별로 제목을 재조합합니다.</p>
            <div>
                <label class="block text-xs font-medium text-gray-600 mb-1">원본 제목</label>
                <input type="text" x-model="promptTest.titleText" placeholder="제목 선택에서 자동 입력 또는 직접 입력"
                       class="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500">
            </div>
            ${_testBtn('runStepRecombine', '실행', 'recombine')}
            <template x-if="promptTest.results.recombine"><div class="mt-2">
                <template x-if="promptTest.results.recombine.success">
                    <div class="p-3 bg-green-50 border border-green-200 rounded-lg space-y-2 text-sm">
                        <div class="text-green-800">원본: <span class="font-normal" x-text="promptTest.results.recombine.result?.original_title"></span></div>

                        <!-- 스타일별 결과 (style_results 있을 때) -->
                        <template x-if="promptTest.results.recombine.result?.style_results?.length > 0">
                            <div class="space-y-1.5">
                                <div class="text-xs font-medium text-green-700 border-b border-green-200 pb-1">
                                    스타일별 재조합 결과 (<span x-text="promptTest.results.recombine.result?.total_styles"></span>건)
                                </div>
                                <template x-for="(sr, idx) in promptTest.results.recombine.result?.style_results" :key="idx">
                                    <div class="flex items-start gap-2 p-2 bg-white rounded border border-green-100">
                                        <span class="text-base flex-shrink-0" x-text="getStyleIcon(sr.style)"></span>
                                        <div class="flex-1 min-w-0">
                                            <div class="flex items-center gap-1.5">
                                                <span class="text-xs font-medium text-green-700 bg-green-100 px-1.5 py-0.5 rounded" x-text="sr.style_label"></span>
                                                <span x-show="sr.is_modified" class="text-xs text-green-600">변경됨</span>
                                                <span x-show="!sr.is_modified" class="text-xs text-gray-400">변경없음</span>
                                            </div>
                                            <div class="text-sm text-gray-800 mt-0.5" x-text="sr.recombined_title"></div>
                                        </div>
                                    </div>
                                </template>
                            </div>
                        </template>

                        <!-- style_results 없을 때 (하위호환) -->
                        <template x-if="!promptTest.results.recombine.result?.style_results?.length">
                            <div class="text-green-800 font-medium">재조합: <span class="font-normal" x-text="promptTest.results.recombine.result?.recombined_title"></span></div>
                        </template>

                        <!-- AI 호출 실패 상세 (error_details 배열) -->
                        <template x-if="promptTest.results.recombine.result?.error_details?.length > 0">
                            <div class="text-xs text-amber-700 bg-amber-50 p-2 rounded border border-amber-200">
                                <div class="font-medium mb-1">일부 스타일 실패:</div>
                                <template x-for="(ed, edIdx) in promptTest.results.recombine.result.error_details" :key="edIdx">
                                    <div class="text-amber-600" x-text="ed"></div>
                                </template>
                            </div>
                        </template>

                        <div class="text-green-700 text-xs border-t border-green-200 pt-1.5 mt-1.5">
                            AI: <span x-text="promptTest.results.recombine.result?.ai_provider"></span>
                            | Provider 소스: <span x-text="promptTest.results.recombine.result?.settings_used?.provider_source || '-'"></span>
                            | 소요: <span x-text="promptTest.results.recombine.result?.generation_time_seconds"></span>초
                        </div>
                    </div>
                </template>
                ${_testError('recombine')}
            </div></template>`;
    return _testBlockWrapper('recombine', '제목 재조합 테스트', inner);
}

/** 참조자료 수집 테스트 */
function getTestReferenceSection() {
    const inner = `
            <p class="text-xs text-gray-500">검색어로 참조자료를 수집하고 요약합니다.</p>
            <div>
                <label class="block text-xs font-medium text-gray-600 mb-1">검색어</label>
                <input type="text" x-model="promptTest.searchQuery" placeholder="이전 단계에서 자동 입력 또는 직접 입력"
                       class="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500">
            </div>
            ${_testBtn('runStepReferences', '실행', 'references')}
            <template x-if="promptTest.results.references"><div class="mt-2">
                <template x-if="promptTest.results.references.success">
                    <div class="p-3 bg-green-50 border border-green-200 rounded-lg space-y-1 text-sm">
                        <div class="text-green-800">수집된 참조자료: <span x-text="promptTest.results.references.result?.total_collected"></span>건</div>
                        <div class="text-green-700 text-xs">소요: <span x-text="promptTest.results.references.result?.generation_time_seconds"></span>초</div>
                        <!-- 사용된 설정 정보 -->
                        <template x-if="promptTest.results.references.result?.settings_used">
                            <div class="text-xs text-gray-500 flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
                                <span>요약: <span x-text="promptTest.results.references.result.settings_used.summary_method || '-'"></span></span>
                                <span>스타일: <span x-text="promptTest.results.references.result.settings_used.summary_style || '-'"></span></span>
                                <span x-show="promptTest.results.references.result.settings_used.summary_method === 'ai'">AI: <span x-text="promptTest.results.references.result.settings_used.ai_provider || '-'"></span>/<span x-text="promptTest.results.references.result.settings_used.ai_model || '-'"></span></span>
                                <span x-show="promptTest.results.references.result.settings_used.summary_method !== 'ai'">알고리즘: <span x-text="promptTest.results.references.result.settings_used.algorithm_type || '-'"></span></span>
                                <span>최대: <span x-text="promptTest.results.references.result.settings_used.max_length || '-'"></span>자</span>
                            </div>
                        </template>
                        <details class="text-xs mt-1"><summary class="cursor-pointer text-green-600 hover:underline">요약 보기</summary>
                            <div class="mt-1 space-y-1 pl-2">
                                <template x-for="(s, i) in (promptTest.results.references.result?.summaries || [])" :key="i">
                                    <div class="p-2 bg-white rounded border border-green-100">
                                        <div class="text-gray-500 truncate" x-text="s.source_url"></div>
                                        <div class="text-gray-700 mt-0.5 whitespace-pre-wrap max-h-40 overflow-y-auto" x-text="s.summary"></div>
                                        <div class="text-gray-400 text-right mt-0.5" x-text="(s.summary || '').length + '자'"></div>
                                    </div>
                                </template>
                            </div>
                        </details>
                    </div>
                </template>
                ${_testError('references')}
            </div></template>`;
    return _testBlockWrapper('references', '참조자료 수집 테스트', inner);
}

/** 글 생성 테스트 */
function getTestContentSection() {
    const inner = `
            <p class="text-xs text-gray-500">AI로 글을 생성합니다.</p>
            <div class="grid grid-cols-1 gap-2">
                <div><label class="block text-xs font-medium text-gray-600 mb-1">제목</label>
                    <input type="text" x-model="promptTest.contentTitle" placeholder="이전 단계에서 자동 입력 또는 직접 입력"
                           class="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500"></div>
                <div><label class="block text-xs font-medium text-gray-600 mb-1">참조자료 (선택)</label>
                    <textarea x-model="promptTest.contentRef" rows="2" placeholder="참조 수집에서 자동 입력 또는 직접 입력"
                              class="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500"></textarea></div>
            </div>
            ${_testBtn('runStepContent', '실행', 'content')}
            <template x-if="promptTest.results.content"><div class="mt-2">
                <template x-if="promptTest.results.content.success">
                    <div class="p-3 bg-green-50 border border-green-200 rounded-lg space-y-1 text-sm">
                        <div class="text-green-800">글 길이: <span x-text="promptTest.results.content.result?.content_length"></span>자</div>
                        <div class="text-green-700 text-xs">AI: <span x-text="promptTest.results.content.result?.ai_provider"></span>
                            (<span x-text="promptTest.results.content.result?.ai_model"></span>)
                            | 소요: <span x-text="promptTest.results.content.result?.generation_time_seconds"></span>초</div>
                        <details class="text-xs mt-1"><summary class="cursor-pointer text-green-600 hover:underline">마크다운 미리보기</summary>
                            <pre class="mt-1 p-2 bg-white rounded border border-green-100 overflow-x-auto text-gray-700 whitespace-pre-wrap"
                                 x-text="promptTest.results.content.result?.content_markdown"></pre></details>
                        <template x-if="promptTest.results.content.result?.content_html">
                            <details class="text-xs mt-1"><summary class="cursor-pointer text-green-600 hover:underline">HTML 미리보기</summary>
                                <div class="mt-1 p-2 bg-white rounded border border-green-100 prose prose-sm max-w-none"
                                     x-html="promptTest.results.content.result?.content_html"></div></details>
                        </template>
                    </div>
                </template>
                ${_testError('content')}
            </div></template>`;
    return _testBlockWrapper('content', '글 생성 테스트', inner);
}

/** 내부링크 추가 테스트 */
function getTestInternalLinksSection() {
    const inner = `
            <p class="text-xs text-gray-500">생성된 글에 내부링크를 자동 삽입합니다. (글 생성 테스트 후 실행)</p>
            <div>
                <label class="block text-xs font-medium text-gray-600 mb-1">입력 콘텐츠</label>
                <textarea x-model="promptTest.internalLinksContent" rows="3" placeholder="글 생성 결과에서 자동 입력"
                          class="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500"></textarea>
            </div>
            ${_testBtn('runStepInternalLinks', '실행', 'internalLinks')}
            <template x-if="promptTest.results.internalLinks"><div class="mt-2">
                <template x-if="promptTest.results.internalLinks.success">
                    <div class="p-3 bg-green-50 border border-green-200 rounded-lg space-y-1 text-sm">
                        <div class="text-green-800">결과 길이: <span x-text="promptTest.results.internalLinks.result?.content_length || 0"></span>자</div>
                        <div class="text-green-700 text-xs">소요: <span x-text="promptTest.results.internalLinks.result?.generation_time_seconds"></span>초</div>
                        <details class="text-xs mt-1"><summary class="cursor-pointer text-green-600 hover:underline">결과 미리보기</summary>
                            <pre class="mt-1 p-2 bg-white rounded border border-green-100 overflow-x-auto text-gray-700 whitespace-pre-wrap text-xs"
                                 x-text="promptTest.results.internalLinks.result?.content_with_links"></pre></details>
                    </div>
                </template>
                ${_testError('internalLinks')}
            </div></template>`;
    return _testBlockWrapper('internalLinks', '내부링크 추가 테스트', inner);
}

/** 이미지 생성 테스트 */
function getTestImageSection() {
    const inner = `
            <p class="text-xs text-gray-500">블로그 설정에 따라 AI 또는 템플릿 이미지를 생성합니다.</p>
            <!-- 블로그 이미지 모드 안내 -->
            <div x-show="getSelectedBlogImageMode() === 'template'"
                 class="p-2 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-700">
                블로그가 템플릿 이미지 모드입니다. Canvas로 미리보기를 생성합니다.
            </div>
            <div x-show="getSelectedBlogImageMode() === 'both'"
                 class="p-2 bg-purple-50 border border-purple-200 rounded text-xs text-purple-700">
                AI + 템플릿 병행 모드 (소스 설정은 블로그 설정 > 이미지 탭에서 관리)
            </div>
            <div><label class="block text-xs font-medium text-gray-600 mb-1">이미지 제목</label>
                <input type="text" x-model="promptTest.imageTitle" placeholder="이전 단계에서 자동 입력 또는 직접 입력"
                       class="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500"></div>
            ${_testBtn('runStepImage', '실행', 'image')}
            <!-- Canvas: 템플릿 모드 렌더링용 (숨겨진 상태로 항상 존재) -->
            <canvas id="testImageCanvas" style="display:none;"></canvas>
            <template x-if="promptTest.results.image"><div class="mt-2">
                <template x-if="promptTest.results.image.success">
                    <div class="p-3 bg-green-50 border border-green-200 rounded-lg space-y-1 text-sm">
                        <div class="text-green-800">모드: <span x-text="promptTest.results.image.result?.image_mode || '없음'"></span>
                            <span x-show="promptTest.results.image.result?.blog_image_mode"
                                  class="text-xs text-gray-500 ml-1">(블로그: <span x-text="promptTest.results.image.result?.blog_image_mode"></span>)</span>
                        </div>
                        <!-- 템플릿 Canvas 미리보기 -->
                        <template x-if="promptTest.results.image.result?.canvas_rendered">
                            <div class="mt-1 space-y-1">
                                <div class="text-green-600 text-xs">Canvas 렌더링 완료 (서버 호출 없음)</div>
                                <img id="testImagePreview" class="max-w-full rounded border" alt="템플릿 이미지 미리보기"
                                     x-init="$nextTick(() => {
                                         const cvs = document.getElementById('testImageCanvas');
                                         const img = document.getElementById('testImagePreview');
                                         if (cvs && img) img.src = cvs.toDataURL('image/png');
                                     })">
                            </div>
                        </template>
                        <!-- AI 모드: 대표 이미지 URL -->
                        <template x-if="!promptTest.results.image.result?.canvas_rendered">
                            <div>
                                <!-- AI 서비스/모델 정보 -->
                                <div class="text-green-700 text-xs flex flex-wrap gap-x-3 gap-y-0.5 mb-1">
                                    <span>AI 서비스: <span x-text="promptTest.results.image.result?.provider || '-'"></span></span>
                                    <span>모델: <span x-text="promptTest.results.image.result?.ai_model || '-'"></span></span>
                                </div>
                                <div x-show="promptTest.results.image.result?.image_url" class="text-green-700 text-xs">대표 이미지 URL: <span x-text="promptTest.results.image.result?.image_url"></span></div>
                                <div x-show="promptTest.results.image.result?.image_url" class="mt-1">
                                    <img :src="promptTest.results.image.result?.image_url" class="max-w-xs rounded border" alt="대표 이미지"></div>
                                <!-- 섹션 이미지 (section_images 배열) -->
                                <template x-if="promptTest.results.image.result?.section_images?.length > 0">
                                    <div class="space-y-1 mt-2">
                                        <div class="text-xs font-medium text-green-700">섹션 이미지 (<span x-text="promptTest.results.image.result.section_images.length"></span>장):</div>
                                        <template x-for="(sImg, sIdx) in promptTest.results.image.result.section_images" :key="sIdx">
                                            <div class="flex items-center gap-2">
                                                <img :src="sImg.image_url || sImg" class="w-20 h-20 object-cover rounded border" :alt="'섹션 이미지 ' + (sIdx + 1)">
                                                <span class="text-xs text-gray-500" x-text="sImg.image_url || sImg"></span>
                                            </div>
                                        </template>
                                    </div>
                                </template>
                                <div x-show="!promptTest.results.image.result?.image_url && !promptTest.results.image.result?.section_images?.length" class="text-green-600 text-xs">이미지가 생성되지 않았습니다 (비활성화 또는 mode=none)</div>
                            </div>
                        </template>
                        <div class="text-green-700 text-xs">소요: <span x-text="promptTest.results.image.result?.generation_time_seconds"></span>초</div>
                    </div>
                </template>
                ${_testError('image')}
            </div></template>`;
    return _testBlockWrapper('image', '이미지 생성 테스트', inner);
}

/** 변환 및 치환 적용 테스트 */
function getTestSubstitutionSection() {
    const inner = `
            <p class="text-xs text-gray-500">마크다운 → HTML 변환 및 블로그 치환 규칙을 적용합니다.</p>
            ${_testBtn('runStepSubstitution', '실행', 'substitution')}
            <template x-if="promptTest.results.substitution"><div class="mt-2">
                <template x-if="promptTest.results.substitution.success">
                    <div class="p-3 bg-green-50 border border-green-200 rounded-lg space-y-1 text-sm">
                        <div class="text-green-800">변환 완료</div>
                        <div class="text-green-700 text-xs">소요: <span x-text="promptTest.results.substitution.result?.generation_time_seconds"></span>초</div>
                        <details class="text-xs mt-1"><summary class="cursor-pointer text-green-600 hover:underline">HTML 결과 보기</summary>
                            <div class="mt-1 p-2 bg-white rounded border border-green-100 prose prose-sm max-w-none"
                                 x-html="promptTest.results.substitution.result?.final_html"></div></details>
                    </div>
                </template>
                ${_testError('substitution')}
            </div></template>`;
    return _testBlockWrapper('substitution', '변환 및 치환 적용 테스트', inner);
}

/** 전체 파이프라인 테스트 */
function getTestFullPipelineSection() {
    const inner = `
            <p class="text-xs text-gray-500">모든 단계를 순서대로 실행합니다.</p>
            <label class="flex items-center gap-2">
                <input type="checkbox" x-model="promptTest.dryRun" class="rounded text-indigo-600 focus:ring-indigo-500">
                <span class="text-sm text-gray-700">Dry Run (DB 저장 안 함)</span>
            </label>
            ${_testBtn('runStepFullPipeline', '전체 실행', 'fullPipeline')}
            <template x-if="promptTest.results.fullPipeline"><div class="mt-2">
                <template x-if="promptTest.results.fullPipeline.success !== undefined">
                    <div :class="promptTest.results.fullPipeline.success ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'"
                         class="p-3 border rounded-lg space-y-2 text-sm">
                        <div :class="promptTest.results.fullPipeline.success ? 'text-green-800' : 'text-red-800'" class="font-medium">
                            <span x-text="promptTest.results.fullPipeline.success ? '전체 파이프라인 성공' : '파이프라인 실패'"></span>
                            <span class="font-normal text-xs ml-2">(총 <span x-text="promptTest.results.fullPipeline.total_time_seconds"></span>초
                                | dry_run: <span x-text="promptTest.results.fullPipeline.dry_run ? '예' : '아니오'"></span>)</span>
                        </div>
                        <template x-if="promptTest.results.fullPipeline.steps"><div class="space-y-1">
                            <template x-for="(val, key) in promptTest.results.fullPipeline.steps" :key="key">
                                <div class="flex items-center gap-2 text-xs">
                                    <span :class="val.success ? 'text-green-600' : 'text-red-600'" x-text="val.success ? '✅' : '❌'"></span>
                                    <span class="text-gray-700" x-text="key"></span>
                                    <span x-show="val.title" class="text-gray-500 truncate max-w-xs" x-text="val.title"></span>
                                    <span x-show="val.error" class="text-red-500" x-text="val.error"></span>
                                </div>
                            </template>
                        </div></template>
                        <template x-if="promptTest.results.fullPipeline.error && !promptTest.results.fullPipeline.steps">
                            <div class="text-red-700 text-xs" x-text="promptTest.results.fullPipeline.error"></div>
                        </template>
                    </div>
                </template>
            </div></template>`;
    return _testBlockWrapper('fullPipeline', '전체 파이프라인 테스트', inner);
}

// 전역 노출
window.getTestBlogAndTitleSection = getTestBlogAndTitleSection;
window.getTestRecombineSection = getTestRecombineSection;
window.getTestReferenceSection = getTestReferenceSection;
window.getTestContentSection = getTestContentSection;
window.getTestInternalLinksSection = getTestInternalLinksSection;
window.getTestImageSection = getTestImageSection;
window.getTestSubstitutionSection = getTestSubstitutionSection;
window.getTestFullPipelineSection = getTestFullPipelineSection;
