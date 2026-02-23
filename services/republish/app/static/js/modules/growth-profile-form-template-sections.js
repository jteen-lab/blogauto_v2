/**
 * GP 인라인 폼 - 스테이지 섹션
 * growth-profile-form-template.js에서 호출
 */

/** 성장 구간 설정 섹션 */
function getGPStagesSection() {
    return `
        <div id="gp-stages-section" class="space-y-4 mb-6">
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

// 전역 노출
window.getGPStagesSection = getGPStagesSection;
