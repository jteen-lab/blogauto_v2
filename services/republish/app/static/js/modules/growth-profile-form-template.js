/**
 * GP 모듈 인라인 폼 전체 템플릿
 * list.js의 getFullFormTemplate()에서 호출
 *
 * 섹션 구성:
 *  1. 프리셋 선택 (이 파일)
 *  2. 활성 시간대 schedule_matrix (이 파일)
 *  3. 지터 설정 (이 파일)
 *  4. 성장 구간 (growth-profile-form-template-sections.js)
 *  5. 워밍업 설정 (growth-profile-form-template-sections.js)
 *  6. 블로그 프리뷰 (growth-profile-form-template-sections.js)
 */

/** 1. 프리셋 선택 섹션 */
function getGPPresetSection() {
    return `
        <div class="space-y-4 mb-6">
            <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                📋 기본 프로파일 선택
            </h3>
            <p class="text-sm text-gray-500">프로파일을 선택하면 아래 설정이 자동으로 채워집니다.</p>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <template x-for="preset in gpModule.presets" :key="preset.key">
                    <div class="border-2 rounded-lg p-4 cursor-pointer transition-all"
                         :class="gpModule.selectedPreset === preset.key
                             ? 'border-blue-500 bg-blue-50'
                             : 'border-gray-200 hover:border-gray-300'"
                         @click="gpModule.loadPreset(preset.key)">
                        <div class="font-medium text-gray-900" x-text="preset.name"></div>
                        <p class="text-xs text-gray-500 mt-1" x-text="preset.description"></p>
                        <div class="mt-2 flex flex-wrap gap-1">
                            <span class="px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-600"
                                  x-text="preset.stageCount + '단계'"></span>
                            <span class="px-2 py-0.5 text-xs rounded-full"
                                  :class="preset.warmupEnabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'"
                                  x-text="preset.warmupEnabled ? '워밍업 ON' : '워밍업 OFF'"></span>
                        </div>
                    </div>
                </template>
            </div>
        </div>
    `;
}

/** 2. 활성 시간대 (schedule_matrix) 섹션 */
function getGPScheduleSection() {
    return `
        <div class="space-y-4 mb-6">
            <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">📅 활성 시간대</h3>
            <div class="bg-gray-50 rounded-lg p-4">
                <div class="flex flex-wrap gap-2 mb-4">
                    <button type="button" @click="gpModule.selectAllHours()"
                            class="px-3 py-1 text-xs bg-blue-100 text-blue-800 rounded-full hover:bg-blue-200">
                        전체 선택
                    </button>
                    <button type="button" @click="gpModule.clearAllHours()"
                            class="px-3 py-1 text-xs bg-gray-100 text-gray-800 rounded-full hover:bg-gray-200">
                        전체 해제
                    </button>
                    <button type="button" @click="gpModule.selectWeekdayHours()"
                            class="px-3 py-1 text-xs bg-green-100 text-green-800 rounded-full hover:bg-green-200">
                        평일 6~21시
                    </button>
                    <button type="button" @click="gpModule.selectWeekendHours()"
                            class="px-3 py-1 text-xs bg-purple-100 text-purple-800 rounded-full hover:bg-purple-200">
                        주말 7~20시
                    </button>
                </div>
                <p class="text-xs text-gray-500 mb-3">파란색 = 활성, 회색 = 비활성 | 요일 헤더 클릭으로 전체 선택/해제</p>
                <div class="overflow-x-auto">
                    <table class="w-full text-xs border-collapse">
                        <thead>
                            <tr>
                                <th class="border border-gray-300 bg-gray-100 p-2 text-center w-12">시간</th>
                                <template x-for="(day, dayIdx) in gpModule.days" :key="dayIdx">
                                    <th class="border border-gray-300 bg-gray-100 p-2 text-center cursor-pointer hover:bg-gray-200 w-8"
                                        @click="gpModule.toggleDay(dayIdx)" x-text="day"></th>
                                </template>
                            </tr>
                        </thead>
                        <tbody>
                            <template x-for="hour in 24" :key="hour">
                                <tr>
                                    <td class="border border-gray-300 bg-gray-50 p-1 text-center font-medium"
                                        x-text="String(hour-1).padStart(2, '0') + '시'"></td>
                                    <template x-for="(day, dayIdx) in gpModule.days" :key="dayIdx + '-' + hour">
                                        <td class="border border-gray-300 p-0">
                                            <button type="button"
                                                    class="w-full h-7 border-none cursor-pointer transition-colors duration-150"
                                                    :class="gpModule.schedule_matrix && gpModule.schedule_matrix[dayIdx][hour-1]
                                                        ? 'bg-blue-500 hover:bg-blue-600'
                                                        : 'bg-gray-100 hover:bg-gray-200'"
                                                    @click="gpModule.toggleHour(dayIdx, hour-1)"></button>
                                        </td>
                                    </template>
                                </tr>
                            </template>
                        </tbody>
                    </table>
                </div>
                <div class="mt-4 p-3 bg-blue-50 rounded-lg">
                    <div class="flex items-center justify-between text-sm">
                        <span class="text-blue-800 font-medium">
                            활성 시간: <span x-text="gpModule.activeHoursCount"></span>시간/주
                        </span>
                        <span class="text-blue-600" x-show="gpModule.todayActiveHours > 0">
                            오늘: <span x-text="gpModule.todayActiveHours"></span>시간
                        </span>
                    </div>
                </div>
            </div>
        </div>
    `;
}

/** 3. 지터(랜덤 변동) 설정 섹션 */
function getGPJitterSection() {
    return `
        <div class="space-y-4 mb-6">
            <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">🎲 지터(랜덤 변동) 설정</h3>
            <div class="p-4 bg-gray-50 rounded-lg space-y-3">
                <label class="flex items-center cursor-pointer">
                    <input type="checkbox" x-model="gpModule.jitter.enabled"
                           class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500">
                    <span class="ml-2 text-sm font-medium text-gray-700">지터 활성화</span>
                    <span class="ml-2 text-xs text-gray-500">(간격에 랜덤 변동을 추가하여 자연스러운 패턴 생성)</span>
                </label>
                <div x-show="gpModule.jitter.enabled" x-transition class="grid grid-cols-2 gap-4 ml-6">
                    <div>
                        <label class="block text-xs text-gray-500 mb-1">최소 변동 (%)</label>
                        <input type="number" x-model.number="gpModule.jitter.min_percent"
                               min="-50" max="0"
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm">
                        <p class="mt-0.5 text-xs text-gray-400">-50 ~ 0</p>
                    </div>
                    <div>
                        <label class="block text-xs text-gray-500 mb-1">최대 변동 (%)</label>
                        <input type="number" x-model.number="gpModule.jitter.max_percent"
                               min="0" max="100"
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm">
                        <p class="mt-0.5 text-xs text-gray-400">0 ~ 100</p>
                    </div>
                </div>
                <p x-show="gpModule.jitter.enabled" class="text-xs text-blue-600 ml-6">
                    예: 간격 60분 + 지터(-20%~+30%) = 48~78분 랜덤 간격
                </p>
            </div>
        </div>
    `;
}

/** GP 전체 인라인 폼 템플릿 */
function getGrowthProfileFormTemplate() {
    return `
        <div x-show="formData.type_code === 'growth_profile'" class="space-y-6">
            ${getGPPresetSection()}
            ${getGPScheduleSection()}
            ${getGPJitterSection()}
            ${typeof getGPStagesSection === 'function' ? getGPStagesSection() : ''}
            ${typeof getGPWarmupSection === 'function' ? getGPWarmupSection() : ''}
            ${typeof getGPPreviewSection === 'function' ? getGPPreviewSection() : ''}
        </div>
    `;
}

// 전역 노출
window.getGrowthProfileFormTemplate = getGrowthProfileFormTemplate;
