/**
 * GP 인라인 폼 - 스테이지/워밍업/프리뷰 섹션
 * growth-profile-form-template.js에서 호출
 */

/** 성장 구간 설정 섹션 */
function getGPStagesSection() {
    return `
        <div class="space-y-4 mb-6">
            <div class="flex items-center justify-between">
                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">📈 성장 구간 설정</h3>
                <button type="button" @click="gpModule.addStage()"
                        class="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                    + 구간 추가
                </button>
            </div>

            <div x-show="gpModule.validationError" x-transition
                 class="p-3 bg-red-50 border border-red-200 rounded-lg">
                <p class="text-sm text-red-700" x-text="gpModule.validationError"></p>
            </div>

            <div x-show="gpModule.stages.length === 0" class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p class="text-sm text-yellow-800">구간이 없습니다. 프리셋을 선택하거나 "구간 추가" 버튼을 눌러 성장 구간을 설정하세요.</p>
            </div>

            <template x-for="(stage, stageIdx) in gpModule.stages" :key="stageIdx">
                <div class="border border-gray-200 rounded-lg overflow-hidden">
                    <div class="flex items-center justify-between p-3 bg-gray-50 border-b border-gray-200">
                        <div class="flex items-center gap-3 flex-1">
                            <span class="text-sm font-bold text-blue-600" x-text="'#' + (stageIdx + 1)"></span>
                            <input type="text" x-model="stage.label"
                                   class="flex-1 max-w-xs px-2 py-1 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-500"
                                   placeholder="구간 이름 (예: 초기 성장)">
                        </div>
                        <button type="button" @click="gpModule.removeStage(stageIdx)"
                                class="p-1 text-red-400 hover:text-red-600" title="구간 삭제">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                            </svg>
                        </button>
                    </div>

                    <div class="p-4 space-y-4">
                        <div class="flex items-center gap-3">
                            <label class="text-xs text-gray-500 w-20 shrink-0">내부 이름</label>
                            <input type="text" x-model="stage.name"
                                   class="flex-1 px-2 py-1 border border-gray-300 rounded text-sm font-mono focus:ring-2 focus:ring-blue-500"
                                   placeholder="stage_1 (영문)">
                        </div>

                        <div class="flex items-center gap-2 flex-wrap">
                            <label class="text-xs text-gray-500 w-20 shrink-0">적용 구간</label>
                            <span class="text-xs text-gray-600">발행글</span>
                            <input type="number" x-model.number="stage.post_count_min" min="0"
                                   class="w-20 px-2 py-1 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-500">
                            <span class="text-gray-400">~</span>
                            <template x-if="stageIdx < gpModule.stages.length - 1">
                                <input type="number" x-model.number="stage.post_count_max" min="1"
                                       @change="gpModule.onMaxChanged(stageIdx)"
                                       class="w-20 px-2 py-1 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-500">
                            </template>
                            <template x-if="stageIdx === gpModule.stages.length - 1">
                                <span class="text-xs text-gray-500 italic px-2 py-1">무제한</span>
                            </template>
                            <span class="text-xs text-gray-500">개</span>
                        </div>

                        <div class="flex items-start gap-3">
                            <label class="text-xs text-gray-500 w-20 shrink-0 pt-1">설명</label>
                            <input type="text" x-model="stage.description"
                                   class="flex-1 px-2 py-1 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-500"
                                   placeholder="이 구간의 설명 (선택)">
                        </div>

                        ${getGPModuleIntervalBlock('generate', '생성 (Generate)', 'blue')}
                        ${getGPModuleIntervalBlock('publish', '발행 (Publish)', 'blue')}
                        ${getGPModuleIntervalBlock('republish', '재발행 (Republish)', 'purple')}
                    </div>
                </div>
            </template>
        </div>
    `;
}

/** 모듈 간격 설정 블록 (generate/publish/republish 공통) */
function getGPModuleIntervalBlock(moduleKey, label, color) {
    const showInventory = moduleKey === 'generate';
    return `
                        <div class="border border-${color}-200 rounded-lg overflow-hidden">
                            <div class="flex items-center p-2.5 bg-${color}-50 border-b border-${color}-200 cursor-pointer"
                                 @click="stage.${moduleKey}.enabled = !stage.${moduleKey}.enabled">
                                <input type="checkbox" :checked="stage.${moduleKey}.enabled"
                                       class="w-4 h-4 text-${color}-600 rounded focus:ring-${color}-500 pointer-events-none">
                                <span class="ml-2 text-sm font-medium text-${color}-800">${label}</span>
                            </div>
                            <div x-show="stage.${moduleKey}.enabled" x-transition class="p-3 space-y-2">
                                ${showInventory ? `
                                <div class="flex items-center gap-2">
                                    <span class="text-xs text-gray-600">최소 재고:</span>
                                    <input type="number" x-model.number="stage.${moduleKey}.min_inventory"
                                           min="1" max="100"
                                           class="w-16 px-2 py-1 border border-gray-300 rounded text-sm">
                                    <span class="text-xs text-gray-500">개 미만이면 생성</span>
                                </div>` : ''}
                                <div class="flex gap-4">
                                    <label class="flex items-center cursor-pointer">
                                        <input type="radio" :name="'interval_' + stageIdx + '_${moduleKey}'"
                                               :checked="stage.${moduleKey}.interval_mode === 'manual'"
                                               @change="stage.${moduleKey}.interval_mode = 'manual'"
                                               class="text-${color}-600 h-3 w-3">
                                        <span class="ml-1.5 text-xs text-gray-600">시간으로 설정</span>
                                    </label>
                                    <label class="flex items-center cursor-pointer">
                                        <input type="radio" :name="'interval_' + stageIdx + '_${moduleKey}'"
                                               :checked="stage.${moduleKey}.interval_mode === 'auto'"
                                               @change="stage.${moduleKey}.interval_mode = 'auto'"
                                               class="text-${color}-600 h-3 w-3">
                                        <span class="ml-1.5 text-xs text-gray-600">횟수로 설정</span>
                                    </label>
                                </div>
                                <div x-show="stage.${moduleKey}.interval_mode === 'manual'" class="flex items-center gap-2">
                                    <input type="number" x-model.number="stage.${moduleKey}.interval_minutes"
                                           min="15" max="1440"
                                           class="w-20 px-2 py-1 border border-gray-300 rounded text-sm">
                                    <span class="text-xs text-gray-500">분 간격</span>
                                    <span class="text-xs text-${color}-600">
                                        (하루 약 <span x-text="gpModule.calcDailyFromMinutes(stage.${moduleKey}.interval_minutes)"></span>회)
                                    </span>
                                </div>
                                <div x-show="stage.${moduleKey}.interval_mode === 'auto'" class="flex items-center gap-2">
                                    <span class="text-xs text-gray-600">하루</span>
                                    <input type="number" x-model.number="stage.${moduleKey}.daily_count"
                                           min="1" max="100"
                                           class="w-16 px-2 py-1 border border-gray-300 rounded text-sm">
                                    <span class="text-xs text-gray-500">회</span>
                                    <span class="text-xs text-${color}-600">
                                        (약 <span x-text="gpModule.calcMinutesFromDaily(stage.${moduleKey}.daily_count)"></span>분 간격)
                                    </span>
                                </div>
                            </div>
                        </div>
    `;
}

/** 워밍업 설정 섹션 */
function getGPWarmupSection() {
    return `
        <div class="space-y-4 mb-6">
            <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">🔥 워밍업 설정</h3>
            <div class="p-4 bg-gray-50 rounded-lg space-y-4">
                <label class="flex items-center cursor-pointer">
                    <input type="checkbox" x-model="gpModule.warmup.enabled"
                           class="w-4 h-4 text-orange-600 rounded focus:ring-orange-500">
                    <span class="ml-2 text-sm font-medium text-gray-700">워밍업 활성화</span>
                    <span class="ml-2 text-xs text-gray-500">(새 블로그 초기 발행량 점진적 증가)</span>
                </label>

                <div x-show="gpModule.warmup.enabled" x-transition class="space-y-4 ml-6">
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div>
                            <label class="block text-xs text-gray-500 mb-1">워밍업 기간</label>
                            <div class="flex items-center gap-1">
                                <input type="number" x-model.number="gpModule.warmup.warmup_days"
                                       min="1" max="90"
                                       class="w-full px-2 py-1.5 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-orange-500">
                                <span class="text-xs text-gray-500">일</span>
                            </div>
                        </div>
                        <div>
                            <label class="block text-xs text-gray-500 mb-1">초기 일일 발행</label>
                            <div class="flex items-center gap-1">
                                <input type="number" x-model.number="gpModule.warmup.initial_daily_posts"
                                       min="1" max="10"
                                       class="w-full px-2 py-1.5 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-orange-500">
                                <span class="text-xs text-gray-500">회</span>
                            </div>
                        </div>
                        <div>
                            <label class="block text-xs text-gray-500 mb-1">최대 일일 발행</label>
                            <div class="flex items-center gap-1">
                                <input type="number" x-model.number="gpModule.warmup.max_daily_posts"
                                       min="1" max="50"
                                       class="w-full px-2 py-1.5 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-orange-500">
                                <span class="text-xs text-gray-500">회</span>
                            </div>
                        </div>
                        <div>
                            <label class="block text-xs text-gray-500 mb-1">증가 속도</label>
                            <div class="flex items-center gap-1">
                                <input type="number" x-model.number="gpModule.warmup.ramp_rate"
                                       min="0.1" max="5" step="0.1"
                                       class="w-full px-2 py-1.5 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-orange-500">
                                <span class="text-xs text-gray-500">/일</span>
                            </div>
                        </div>
                    </div>

                    <div x-show="gpModule.warmupSimulation.length > 0" class="p-3 bg-orange-50 rounded-lg">
                        <p class="text-xs font-medium text-orange-800 mb-2">워밍업 시뮬레이션:</p>
                        <div class="flex flex-wrap gap-2">
                            <template x-for="sim in gpModule.warmupSimulation" :key="sim.day">
                                <span class="px-2 py-1 bg-white border border-orange-200 rounded text-xs text-orange-700">
                                    Day <span x-text="sim.day"></span>:
                                    <span x-text="sim.daily"></span>회/일
                                    (<span x-text="sim.interval"></span>분)
                                </span>
                            </template>
                        </div>
                    </div>

                    <p class="text-xs text-orange-600">워밍업은 발행(Publish)에만 적용됩니다. 생성과 재발행은 구간 설정을 따릅니다.</p>
                </div>
            </div>
        </div>
    `;
}

/** 블로그별 적용 프리뷰 섹션 */
function getGPPreviewSection() {
    return `
        <div class="space-y-4 mb-6">
            <div class="flex items-center justify-between">
                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">👀 블로그별 적용 프리뷰</h3>
                <button type="button" @click="gpModule.loadPreview()"
                        :disabled="gpModule.previewLoading"
                        class="px-3 py-1.5 text-xs bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50">
                    <span x-show="!gpModule.previewLoading">새로고침</span>
                    <span x-show="gpModule.previewLoading" class="flex items-center gap-1">
                        <svg class="animate-spin h-3 w-3" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        로딩 중...
                    </span>
                </button>
            </div>

            <div x-show="gpModule.previewLoading" class="p-4 text-center text-sm text-gray-500">
                프리뷰 로딩 중...
            </div>

            <div x-show="!gpModule.previewLoading && gpModule.previewBlogs.length === 0"
                 class="p-4 bg-gray-50 rounded-lg text-center">
                <p class="text-sm text-gray-500">"새로고침" 버튼을 눌러 블로그별 적용 결과를 미리 확인하세요.</p>
            </div>

            <div x-show="!gpModule.previewLoading && gpModule.previewBlogs.length > 0"
                 class="border border-gray-200 rounded-lg max-h-64 overflow-y-auto">
                <template x-for="blog in gpModule.previewBlogs" :key="blog.id || blog.name">
                    <div class="flex items-center justify-between p-3 border-b border-gray-100 last:border-b-0 hover:bg-gray-50">
                        <div class="flex items-center gap-2">
                            <span class="text-sm font-medium text-gray-900" x-text="blog.name"></span>
                            <span class="text-xs text-gray-500" x-text="'(' + (blog.postCount || 0) + '개)'"></span>
                        </div>
                        <div class="flex items-center gap-2">
                            <span class="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700"
                                  x-text="blog.stageName || '해당 없음'"></span>
                            <span x-show="blog.generate" class="px-1.5 py-0.5 text-xs rounded bg-green-100 text-green-700">생성</span>
                            <span x-show="blog.publish" class="px-1.5 py-0.5 text-xs rounded bg-blue-100 text-blue-700">발행</span>
                            <span x-show="blog.republish" class="px-1.5 py-0.5 text-xs rounded bg-purple-100 text-purple-700">재발행</span>
                        </div>
                    </div>
                </template>
            </div>
        </div>
    `;
}

// 전역 노출
window.getGPStagesSection = getGPStagesSection;
window.getGPWarmupSection = getGPWarmupSection;
window.getGPPreviewSection = getGPPreviewSection;
