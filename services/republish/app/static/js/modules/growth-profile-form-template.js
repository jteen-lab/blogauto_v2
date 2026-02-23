/**
 * GP 모듈 인라인 폼 전체 템플릿
 * list.js의 getFullFormTemplate()에서 호출
 *
 * 섹션 구성:
 *  1. 워밍업 설정 (이 파일)
 *  2. 프리셋 선택 + 상세 요약 (이 파일)
 *  3. 활성 시간대 schedule_matrix (이 파일)
 *  4. 지터 설정 (이 파일)
 *  5. 성장 구간 (growth-profile-form-template-sections.js)
 */

/** 1. 워밍업 설정 섹션 */
function getGPWarmupSection() {
    return `
        <div id="gp-warmup-section" class="space-y-4 mb-6">
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

/** 2. 프리셋 선택 + 상세 요약 섹션 */
function getGPPresetSection() {
    return `
        <div class="space-y-4 mb-6">
            <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                📋 프로파일 선택
            </h3>
            <p class="text-sm text-gray-500">프로파일을 선택하면 아래 설정이 자동으로 채워집니다. 커스텀을 선택하면 처음부터 직접 설정합니다.</p>
            <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                <template x-for="preset in gpModule.presets" :key="preset.key">
                    <div class="border-2 rounded-lg cursor-pointer transition-all"
                         :class="gpModule.selectedPreset === preset.key
                             ? 'border-blue-500 bg-blue-50'
                             : 'border-gray-200 hover:border-gray-300'"
                         @click="gpModule.loadPreset(preset.key)">
                        <!-- 카드 헤더 -->
                        <div class="p-4 pb-2">
                            <div class="flex items-center justify-between">
                                <div class="font-medium text-gray-900" x-text="preset.name"></div>
                                <!-- 커스텀 프로파일 삭제 버튼 -->
                                <button type="button" x-show="preset.isCustom"
                                        @click.stop="gpModule.removeCustomProfile(preset.key)"
                                        class="p-1 text-red-400 hover:text-red-600" title="삭제">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                                    </svg>
                                </button>
                            </div>
                            <p class="text-xs text-gray-500 mt-1" x-text="preset.description"></p>
                            <div class="mt-2 flex flex-wrap gap-1">
                                <span class="px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-600"
                                      x-text="preset.stageCount + '단계'"></span>
                                <span class="px-2 py-0.5 text-xs rounded-full"
                                      :class="preset.warmupEnabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'"
                                      x-text="preset.warmupEnabled ? '워밍업 ON' : '워밍업 OFF'"></span>
                            </div>
                        </div>
                        <!-- 상세 요약 (getCardData가 있는 모든 프리셋) -->
                        <div x-show="gpModule.getCardData(preset.key)"
                             class="px-4 pb-3 pt-1 border-t border-gray-100 space-y-1.5">
                            <!-- 1. 워밍업 -->
                            <div class="flex items-center justify-between text-xs">
                                <span class="text-gray-500 flex items-center gap-1">
                                    <span>🔥</span>
                                    워밍업 <span x-text="gpModule.getWarmupSummaryText(gpModule.getCardData(preset.key)?.warmup)"></span>
                                </span>
                                <button type="button" @click.stop="gpModule.scrollToSection('gp-warmup-section')"
                                        class="text-blue-500 hover:text-blue-700 text-xs"
                                        x-show="gpModule.selectedPreset === preset.key">이동</button>
                            </div>
                            <!-- 2. 활성 시간대 -->
                            <div class="flex items-center justify-between text-xs">
                                <span class="text-gray-500 flex items-center gap-1">
                                    <span>⏰</span>
                                    <span x-text="gpModule.getScheduleSummaryText(gpModule.getCardData(preset.key)?.schedule_matrix)"></span>
                                </span>
                                <button type="button" @click.stop="gpModule.scrollToSection('gp-schedule-section')"
                                        class="text-blue-500 hover:text-blue-700 text-xs"
                                        x-show="gpModule.selectedPreset === preset.key">이동</button>
                            </div>
                            <!-- 3. 지터 -->
                            <div class="flex items-center justify-between text-xs">
                                <span class="text-gray-500 flex items-center gap-1">
                                    <span>🎲</span>
                                    지터 <span x-text="gpModule.getJitterSummaryText(gpModule.getCardData(preset.key)?.jitter)"></span>
                                </span>
                                <button type="button" @click.stop="gpModule.scrollToSection('gp-jitter-section')"
                                        class="text-blue-500 hover:text-blue-700 text-xs"
                                        x-show="gpModule.selectedPreset === preset.key">이동</button>
                            </div>
                            <!-- 4. 성장 구간 -->
                            <div class="text-xs">
                                <div class="flex items-center justify-between">
                                    <span class="text-gray-500 flex items-center gap-1">
                                        <span>📊</span>
                                        <span x-text="(gpModule.getCardData(preset.key)?.stages?.length || 0) + '구간'"></span>
                                    </span>
                                    <button type="button" @click.stop="gpModule.scrollToSection('gp-stages-section')"
                                            class="text-blue-500 hover:text-blue-700 text-xs"
                                            x-show="gpModule.selectedPreset === preset.key">이동</button>
                                </div>
                                <template x-for="(ss, ssIdx) in gpModule.getStagesSummary(gpModule.getCardData(preset.key)?.stages)" :key="ssIdx">
                                    <div class="ml-4 text-gray-400 truncate" x-text="ss.label + '(' + ss.range + '): ' + ss.modules"></div>
                                </template>
                            </div>
                        </div>
                    </div>
                </template>
                <!-- 새 커스텀 프로파일 추가 카드 -->
                <div class="border-2 border-dashed border-gray-300 rounded-lg cursor-pointer
                            hover:border-blue-400 hover:bg-blue-50 transition-all flex items-center justify-center min-h-[120px]"
                     @click="(() => { const name = prompt('커스텀 프로파일 이름을 입력하세요:'); if(name) gpModule.addCustomProfile(name); })()">
                    <div class="text-center p-4">
                        <div class="text-2xl text-gray-400 mb-1">+</div>
                        <div class="text-sm text-gray-500">새 커스텀 추가</div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

/** 3. 활성 시간대 (schedule_matrix) 섹션 */
function getGPScheduleSection() {
    return `
        <div id="gp-schedule-section" class="space-y-4 mb-6">
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

/** 4. 지터(랜덤 변동) 설정 섹션 */
function getGPJitterSection() {
    return `
        <div id="gp-jitter-section" class="space-y-4 mb-6">
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
        <div x-show="formData.type_code === 'growth_profile'" class="space-y-6"
             x-init="gpModule.loadAllPresetDetails()">
            ${getGPWarmupSection()}
            ${getGPPresetSection()}
            ${getGPScheduleSection()}
            ${getGPJitterSection()}
            ${typeof getGPStagesSection === 'function' ? getGPStagesSection() : ''}
        </div>
    `;
}

// 전역 노출
window.getGrowthProfileFormTemplate = getGrowthProfileFormTemplate;
