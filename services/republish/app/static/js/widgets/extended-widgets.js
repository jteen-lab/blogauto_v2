/**
 * 확장 위젯 모음
 *
 * 복잡한 입력이 필요한 경우를 위한 위젯들입니다.
 * - time-picker: 시간 선택 (24시 표기법)
 * - interval-selector: 간격/횟수 설정 (시간 또는 횟수 모드)
 */

// 스핀박스 제거 CSS 삽입
(function() {
    if (!document.getElementById('no-spin-style')) {
        var style = document.createElement('style');
        style.id = 'no-spin-style';
        style.textContent = '.no-spin::-webkit-outer-spin-button,.no-spin::-webkit-inner-spin-button{-webkit-appearance:none;margin:0}.no-spin{-moz-appearance:textfield}';
        document.head.appendChild(style);
    }
})();

// =====================================================
// 액션 스케줄러 Alpine 컴포넌트 (IIFE 외부에서 정의)
// =====================================================
window.actionSchedulerComponent = function() {
    return {
        _mode: 'time_based',
        _interval: '60',
        _count: '10',
        _jitter: '20',
        _activeHours: 14,

        init: function() {
            var self = this;
            if (typeof paramValues !== 'undefined') {
                this._mode = paramValues.interval_mode || 'time_based';
                this._interval = String(paramValues.fixed_interval_minutes || 60);
                this._count = String(paramValues.daily_target_count || 10);
                this._jitter = String(paramValues.jitter_percent !== undefined ? paramValues.jitter_percent : 20);

                var matrix = paramValues.schedule_matrix;
                if (matrix && Array.isArray(matrix)) {
                    var cnt = 0;
                    matrix.forEach(function(day) {
                        if (day) day.forEach(function(h) { if (h) cnt++; });
                    });
                    this._activeHours = Math.round(cnt / 7);
                }

                this.$watch('_mode', function(v) { paramValues.interval_mode = v; });
                this.$watch('_interval', function(v) { paramValues.fixed_interval_minutes = parseInt(v) || 60; });
                this.$watch('_count', function(v) { paramValues.daily_target_count = parseInt(v) || 10; });
                this.$watch('_jitter', function(v) { paramValues.jitter_percent = parseInt(v) || 0; });
            }
        },

        calcDailyCount: function() {
            var interval = parseInt(this._interval) || 60;
            return Math.floor((this._activeHours * 60) / interval);
        },

        calcInterval: function() {
            var count = parseInt(this._count) || 10;
            return Math.max(15, Math.round((this._activeHours * 60) / count));
        }
    };
};

// =====================================================
// 워크플로우 가이드 Alpine 컴포넌트 (IIFE 외부에서 정의)
// =====================================================
window.workflowGuideComponent = function(stepsData) {
    return {
        steps: stepsData || [],
        selectedStep: null,
        stepModules: {},
        showPopup: false,
        availableModules: [],
        loading: false,

        init: function() {
            // 기존 저장된 workflow_guide 데이터 로드
            // window.paramValues는 moduleFormApp에서 전역에 노출됨
            console.log('[WorkflowGuide] init 시작, window.paramValues:', window.paramValues);

            if (window.paramValues && window.paramValues.workflow_guide) {
                var savedGuide = window.paramValues.workflow_guide;
                console.log('[WorkflowGuide] 저장된 데이터 로드:', JSON.stringify(savedGuide));

                if (savedGuide && typeof savedGuide === 'object' && Object.keys(savedGuide).length > 0) {
                    for (var key in savedGuide) {
                        if (savedGuide.hasOwnProperty(key)) {
                            this.stepModules[key] = savedGuide[key];
                            console.log('[WorkflowGuide] stepModules[' + key + '] =', savedGuide[key]);
                        }
                    }
                } else {
                    console.log('[WorkflowGuide] workflow_guide가 비어있음');
                }
            } else {
                console.log('[WorkflowGuide] workflow_guide 데이터 없음');
            }
        },

        selectStep: function(idx) {
            console.log('[WorkflowGuide] selectStep 호출:', idx, this.steps[idx]);
            this.selectedStep = idx;
            this.showPopup = true;
            console.log('[WorkflowGuide] showPopup:', this.showPopup);
            this.loadModules(this.steps[idx].module_type_code);
        },

        loadModules: function(typeCode) {
            var self = this;
            self.loading = true;
            fetch('/api/v1/modules?module_type_code=' + typeCode)
                .then(function(resp) {
                    if (!resp.ok) {
                        throw new Error('HTTP ' + resp.status);
                    }
                    return resp.json();
                })
                .then(function(data) {
                    console.log('[WorkflowGuide] API 응답:', data);
                    self.availableModules = data.modules || data.items || [];
                    console.log('[WorkflowGuide] availableModules:', self.availableModules);
                    self.loading = false;
                })
                .catch(function(e) {
                    console.error('모듈 로드 오류:', e);
                    self.availableModules = [];
                    self.loading = false;
                });
        },

        selectModule: function(moduleId, moduleName) {
            this.stepModules[this.selectedStep] = { id: moduleId, name: moduleName };
            this.showPopup = false;
            // window.paramValues를 통해 부모 컴포넌트의 데이터 업데이트
            if (window.paramValues) {
                window.paramValues.workflow_guide = this.stepModules;
            }
        },

        createNewModule: function() {
            var self = this;
            var stepIdx = this.selectedStep;
            var typeCode = this.steps[stepIdx].module_type_code;

            console.log('[WorkflowGuide] createNewModule 호출:', typeCode, 'stepIdx:', stepIdx);

            if (window.moduleListAppInstance) {
                var moduleType = window.moduleListAppInstance.moduleTypes.find(function(t) { return t.code === typeCode; });
                console.log('[WorkflowGuide] moduleType 찾음:', moduleType);

                if (moduleType) {
                    // 모듈 생성 완료 콜백 등록
                    window._workflowModuleCallback = function(createdModule) {
                        console.log('[WorkflowGuide] 콜백 호출됨:', createdModule);
                        console.log('[WorkflowGuide] self 유효:', !!self, 'stepModules:', self ? self.stepModules : null);

                        if (createdModule && createdModule.module_type && createdModule.module_type.code === typeCode) {
                            // self가 유효하면 직접 업데이트
                            if (self && self.stepModules) {
                                self.stepModules[stepIdx] = { id: createdModule.id, name: createdModule.name };
                                self.showPopup = false;  // 선택 팝업 닫기
                                console.log('[WorkflowGuide] stepModules 업데이트:', self.stepModules);
                            }

                            // window.paramValues도 업데이트
                            if (window.paramValues) {
                                if (!window.paramValues.workflow_guide) {
                                    window.paramValues.workflow_guide = {};
                                }
                                window.paramValues.workflow_guide[stepIdx] = { id: createdModule.id, name: createdModule.name };
                                console.log('[WorkflowGuide] paramValues 업데이트:', window.paramValues.workflow_guide);
                            }

                            console.log('[WorkflowGuide] 모듈 자동 선택 완료:', createdModule.name);
                        }
                        window._workflowModuleCallback = null;
                    };

                    // 중첩 바텀시트를 사용하여 모듈 생성 폼 열기 (기존 템플릿 폼 유지)
                    window.moduleListAppInstance.createNestedModule(moduleType);
                }
            } else {
                alert('모듈 관리 페이지에서만 새 모듈을 생성할 수 있습니다.');
            }
        },

        getStepName: function() {
            if (this.selectedStep !== null && this.steps[this.selectedStep]) {
                return this.steps[this.selectedStep].name + ' 모듈 선택';
            }
            return '모듈 선택';
        }
    };
};

(function() {
    const baseInputClass = 'px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent';

    /**
     * 시간 선택 위젯 (24시 표기법)
     *
     * 사용자가 시:분을 선택하면 내부적으로 크론 표현식으로 변환하여 저장
     * schema.outputFormat: 'cron' | 'time' (기본: 'time')
     * schema.useActiveHours: true인 경우 active_hours 필드 참조하여 활성 시간대만 선택 가능
     */
    WidgetRegistry.register('time-picker', {
        render(key, schema, value, onChange) {
            const useActiveHours = schema.useActiveHours || false;

            // 활성 시간대 연동 기능
            if (useActiveHours) {
                // 초기값 파싱 및 활성 시간대 검증
                const initScript = `
                    if (!paramValues['${key}'] || paramValues['${key}'].includes('*')) {
                        paramValues['${key}'] = '09:00';
                    }
                    // 활성 시간 목록 계산
                    $data._activeHoursList = [];
                    const activeMatrix = paramValues['active_hours'];
                    if (activeMatrix && Array.isArray(activeMatrix)) {
                        const hourSet = new Set();
                        activeMatrix.forEach(day => {
                            if (day) day.forEach((active, hour) => {
                                if (active) hourSet.add(hour);
                            });
                        });
                        $data._activeHoursList = Array.from(hourSet).sort((a, b) => a - b);
                    }
                    // 활성 시간이 없으면 전체 시간 사용
                    if ($data._activeHoursList.length === 0) {
                        $data._activeHoursList = Array.from({length: 24}, (_, i) => i);
                    }
                    // 현재 선택된 시간이 활성 시간대가 아니면 첫 번째 활성 시간으로 변경
                    const currentHour = parseInt(paramValues['${key}']?.split(':')[0] || 9);
                    if (!$data._activeHoursList.includes(currentHour)) {
                        const firstActiveHour = String($data._activeHoursList[0]).padStart(2, '0');
                        paramValues['${key}'] = firstActiveHour + ':00';
                    }
                `;

                return `
                    <div x-init="${initScript}">
                        <div class="flex items-center gap-2">
                            <select x-model="paramValues['${key}']"
                                    class="${baseInputClass} w-40">
                                <template x-for="hour in $data._activeHoursList" :key="hour">
                                    <option :value="String(hour).padStart(2, '0') + ':00'"
                                            x-text="String(hour).padStart(2, '0') + ':00'">
                                    </option>
                                </template>
                            </select>
                            <span class="text-sm text-gray-500">
                                (활성 시간대만 선택 가능)
                            </span>
                        </div>
                        <p class="mt-2 text-xs text-gray-400"
                           x-show="$data._activeHoursList && $data._activeHoursList.length < 24">
                            활성 시간: <span x-text="$data._activeHoursList?.map(h => h + '시').join(', ')"></span>
                        </p>
                    </div>
                `;
            }

            // 기본 time-picker (활성 시간대 연동 없음)
            const initScript = `
                if (!paramValues['${key}'] || paramValues['${key}'].includes('*')) {
                    paramValues['${key}'] = '09:00';
                }
            `;

            return `
                <div x-init="${initScript}">
                    <div class="flex items-center gap-2">
                        <input type="time"
                               x-model="paramValues['${key}']"
                               class="${baseInputClass} w-40">
                        <span class="text-sm text-gray-500">
                            (24시간 표기법)
                        </span>
                    </div>
                    <p class="mt-2 text-xs text-gray-400">
                        예: 09:00 = 오전 9시, 14:30 = 오후 2시 30분
                    </p>
                </div>
            `;
        },

        // 크론 표현식으로 변환
        toCron(timeValue) {
            if (!timeValue) return '0 9 * * *';
            const [hour, minute] = timeValue.split(':').map(Number);
            return `${minute} ${hour} * * *`;
        },

        // 크론 표현식에서 시간으로 변환
        fromCron(cronValue) {
            if (!cronValue || !cronValue.includes(' ')) return '09:00';
            const parts = cronValue.split(' ');
            if (parts.length < 2) return '09:00';
            const minute = parts[0].padStart(2, '0');
            const hour = parts[1].padStart(2, '0');
            return `${hour}:${minute}`;
        }
    });

    /**
     * 간격 설정 위젯
     *
     * 두 가지 모드 지원:
     * - minutes: 분 단위 간격 설정 (예: 30분마다)
     * - daily_count: 하루 목표 횟수 설정 (예: 하루 5회)
     *
     * 저장 형식: { mode: 'minutes'|'daily_count', minutes: number, dailyCount: number }
     */
    WidgetRegistry.register('interval-selector', {
        render(key, schema, value, onChange) {
            // 초기값 설정
            const initScript = `
                if (!paramValues['${key}'] || typeof paramValues['${key}'] !== 'object') {
                    paramValues['${key}'] = {
                        mode: 'minutes',
                        minutes: ${schema.defaultMinutes || 60},
                        dailyCount: ${schema.defaultDailyCount || 5}
                    };
                }
            `;

            return `
                <div x-init="${initScript}" class="space-y-4">
                    <!-- 모드 선택 -->
                    <div class="flex gap-4">
                        <label class="flex items-center cursor-pointer">
                            <input type="radio"
                                   value="minutes"
                                   x-model="paramValues['${key}'].mode"
                                   class="text-blue-600 focus:ring-blue-500 h-4 w-4">
                            <span class="ml-2 text-sm text-gray-700">시간으로 설정</span>
                        </label>
                        <label class="flex items-center cursor-pointer">
                            <input type="radio"
                                   value="daily_count"
                                   x-model="paramValues['${key}'].mode"
                                   class="text-blue-600 focus:ring-blue-500 h-4 w-4">
                            <span class="ml-2 text-sm text-gray-700">횟수로 설정</span>
                        </label>
                    </div>

                    <!-- 시간 모드 -->
                    <div x-show="paramValues['${key}'].mode === 'minutes'"
                         class="p-4 bg-gray-50 rounded-lg">
                        <div class="flex items-center gap-2 flex-wrap">
                            <span class="text-gray-700 text-sm">실행 간격:</span>
                            <input type="text"
                                   inputmode="numeric"
                                   x-model.lazy="paramValues['${key}'].minutes"
                                   class="no-spin ${baseInputClass} w-20 text-center">
                            <span class="text-gray-700 text-sm">분마다</span>
                        </div>
                        <p class="mt-2 text-xs text-gray-500">
                            <span x-text="(() => {
                                const activeMatrix = paramValues['active_hours'];
                                const activeHours = activeMatrix ? activeMatrix.flat().filter(h => h).length / 7 : 24;
                                const dailyCount = Math.round((activeHours * 60) / (paramValues['${key}'].minutes || 60));
                                return '약 ' + dailyCount + '회/일 실행 (활성 ' + Math.round(activeHours) + '시간 기준)';
                            })()"></span>
                        </p>
                    </div>

                    <!-- 횟수 모드 -->
                    <div x-show="paramValues['${key}'].mode === 'daily_count'"
                         class="p-4 bg-gray-50 rounded-lg">
                        <div class="flex items-center gap-2 flex-wrap">
                            <span class="text-gray-700 text-sm">하루 목표:</span>
                            <input type="text"
                                   inputmode="numeric"
                                   x-model.lazy="paramValues['${key}'].dailyCount"
                                   class="no-spin ${baseInputClass} w-20 text-center">
                            <span class="text-gray-700 text-sm">회</span>
                        </div>
                        <p class="mt-2 text-xs text-gray-500">
                            <span x-text="(() => {
                                const activeMatrix = paramValues['active_hours'];
                                const activeHours = activeMatrix ? activeMatrix.flat().filter(h => h).length / 7 : 24;
                                const interval = Math.round((activeHours * 60) / (paramValues['${key}'].dailyCount || 5));
                                return '약 ' + interval + '분 간격으로 실행 (활성 ' + Math.round(activeHours) + '시간 기준)';
                            })()"></span>
                        </p>
                    </div>
                </div>
            `;
        },

        // 분 단위 간격으로 변환
        toMinutes(value) {
            if (!value || typeof value !== 'object') return 60;
            if (value.mode === 'daily_count') {
                return Math.round(1440 / (value.dailyCount || 5));
            }
            return value.minutes || 60;
        }
    });

    /**
     * 다중 시간 선택 위젯 (여러 시간 지정)
     */
    WidgetRegistry.register('multi-time-picker', {
        render(key, schema, value, onChange) {
            const initScript = `
                if (!paramValues['${key}'] || !Array.isArray(paramValues['${key}'])) {
                    paramValues['${key}'] = ['09:00'];
                }
            `;

            return `
                <div x-init="${initScript}" class="space-y-2">
                    <template x-for="(time, index) in paramValues['${key}']" :key="index">
                        <div class="flex items-center gap-2">
                            <input type="time"
                                   x-model="paramValues['${key}'][index]"
                                   class="${baseInputClass} w-40">
                            <button type="button"
                                    @click="paramValues['${key}'].splice(index, 1)"
                                    x-show="paramValues['${key}'].length > 1"
                                    class="text-red-500 hover:text-red-700 p-1">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                </svg>
                            </button>
                        </div>
                    </template>
                    <button type="button"
                            @click="paramValues['${key}'].push('09:00')"
                            x-show="paramValues['${key}'].length < ${schema.maxTimes || 5}"
                            class="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
                        </svg>
                        시간 추가
                    </button>
                </div>
            `;
        }
    });

    /**
     * 스케줄 매트릭스 위젯 (7일 x 24시간)
     *
     * 활성 시간대를 지정하는 그리드 UI
     * - 파란색: 활성 시간대
     * - 회색: 비활성 시간대
     *
     * 저장 형식: Array(7).fill().map(() => Array(24).fill(boolean))
     * [월, 화, 수, 목, 금, 토, 일] x [0시~23시]
     */
    WidgetRegistry.register('schedule-matrix', {
        render(key, schema, value, onChange) {
            const days = ['월', '화', '수', '목', '금', '토', '일'];

            // 초기값 설정 (기본: 평일 9-21시)
            const initScript = `
                if (!paramValues['${key}'] || !Array.isArray(paramValues['${key}']) || paramValues['${key}'].length !== 7) {
                    paramValues['${key}'] = Array(7).fill().map((_, dayIdx) =>
                        Array(24).fill().map((_, hour) =>
                            dayIdx < 5 && hour >= 9 && hour <= 21
                        )
                    );
                }
                // 활성 시간 계산 함수
                $data._calcActiveHours = function() {
                    let count = 0;
                    const matrix = paramValues['${key}'];
                    if (matrix) {
                        matrix.forEach(day => {
                            if (day) day.forEach(h => { if (h) count++; });
                        });
                    }
                    return count;
                };
                $data._scheduleActiveHours = $data._calcActiveHours();
            `;

            // 시간 행 생성 (0~23시)
            let hourRows = '';
            for (let hour = 0; hour < 24; hour++) {
                const hourStr = String(hour).padStart(2, '0');
                let dayCells = '';
                for (let dayIdx = 0; dayIdx < 7; dayIdx++) {
                    dayCells += `
                        <td class="border border-gray-300 p-0">
                            <button type="button"
                                    class="w-full h-6 border-none cursor-pointer transition-colors duration-150"
                                    :class="paramValues['${key}'][${dayIdx}][${hour}] ? 'bg-blue-500 hover:bg-blue-600' : 'bg-gray-100 hover:bg-gray-200'"
                                    @click="paramValues['${key}'][${dayIdx}][${hour}] = !paramValues['${key}'][${dayIdx}][${hour}]; $data._scheduleActiveHours = $data._calcActiveHours()">
                            </button>
                        </td>
                    `;
                }
                hourRows += `
                    <tr>
                        <td class="border border-gray-300 bg-gray-50 p-1 text-center font-medium text-xs">${hourStr}시</td>
                        ${dayCells}
                    </tr>
                `;
            }

            // 요일 헤더
            let dayHeaders = '';
            for (let dayIdx = 0; dayIdx < 7; dayIdx++) {
                dayHeaders += `
                    <th class="border border-gray-300 bg-gray-100 p-1 text-center cursor-pointer hover:bg-gray-200 w-8 text-xs"
                        @click="(() => {
                            const allActive = paramValues['${key}'][${dayIdx}].every(h => h);
                            paramValues['${key}'][${dayIdx}] = paramValues['${key}'][${dayIdx}].map(() => !allActive);
                            $data._scheduleActiveHours = $data._calcActiveHours();
                        })()">${days[dayIdx]}</th>
                `;
            }

            return `
                <div x-init="${initScript}" class="space-y-3">
                    <!-- 빠른 설정 버튼 -->
                    <div class="flex flex-wrap items-center justify-between gap-2">
                        <div class="flex flex-wrap gap-2">
                            <button type="button"
                                    @click="paramValues['${key}'] = Array(7).fill().map(() => Array(24).fill(true)); $data._scheduleActiveHours = $data._calcActiveHours()"
                                    class="px-3 py-1 text-xs bg-blue-100 text-blue-800 rounded-full hover:bg-blue-200">
                                전체 선택
                            </button>
                            <button type="button"
                                    @click="paramValues['${key}'] = Array(7).fill().map(() => Array(24).fill(false)); $data._scheduleActiveHours = $data._calcActiveHours()"
                                    class="px-3 py-1 text-xs bg-gray-100 text-gray-800 rounded-full hover:bg-gray-200">
                                전체 해제
                            </button>
                            <button type="button"
                                    @click="paramValues['${key}'] = Array(7).fill().map((_, d) => Array(24).fill().map((_, h) => d < 5 && h >= 9 && h <= 21)); $data._scheduleActiveHours = $data._calcActiveHours()"
                                    class="px-3 py-1 text-xs bg-green-100 text-green-800 rounded-full hover:bg-green-200">
                                평일 9-21시
                            </button>
                            <button type="button"
                                    @click="paramValues['${key}'] = Array(7).fill().map((_, d) => Array(24).fill().map((_, h) => d >= 5 && h >= 9 && h <= 21)); $data._scheduleActiveHours = $data._calcActiveHours()"
                                    class="px-3 py-1 text-xs bg-purple-100 text-purple-800 rounded-full hover:bg-purple-200">
                                주말만
                            </button>
                            <button type="button"
                                    @click="paramValues['${key}'] = Array(7).fill().map((_, d) => Array(24).fill().map((_, h) => d < 5 && (h >= 22 || h <= 8))); $data._scheduleActiveHours = $data._calcActiveHours()"
                                    class="px-3 py-1 text-xs bg-indigo-100 text-indigo-800 rounded-full hover:bg-indigo-200">
                                평일 22-08시
                            </button>
                        </div>
                        <div class="text-sm text-blue-800 font-medium">
                            활성: <span x-text="$data._scheduleActiveHours || 0"></span>시간/주
                        </div>
                    </div>

                    <p class="text-xs text-gray-500">
                        파란색 = 활성, 회색 = 비활성 | 요일 헤더 클릭으로 해당 요일 전체 선택/해제
                    </p>

                    <!-- 스케줄 테이블 -->
                    <div class="overflow-x-auto">
                        <table class="w-full text-xs border-collapse">
                            <thead>
                                <tr>
                                    <th class="border border-gray-300 bg-gray-100 p-1 text-center w-10">시간</th>
                                    ${dayHeaders}
                                </tr>
                            </thead>
                            <tbody>
                                ${hourRows}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        },

        // 기본값 생성 (평일 9-21시)
        getDefaultValue() {
            return Array(7).fill().map((_, dayIdx) =>
                Array(24).fill().map((_, hour) =>
                    dayIdx < 5 && hour >= 9 && hour <= 21
                )
            );
        },

        // 활성 시간 수 계산
        getActiveHoursCount(matrix) {
            if (!matrix || !Array.isArray(matrix)) return 0;
            let count = 0;
            matrix.forEach(day => {
                if (day) day.forEach(h => { if (h) count++; });
            });
            return count;
        },

        // 특정 요일의 활성 시간 반환
        getDayActiveHours(matrix, dayIdx) {
            if (!matrix || !matrix[dayIdx]) return [];
            return matrix[dayIdx]
                .map((active, hour) => active ? hour : -1)
                .filter(h => h >= 0);
        }
    });

    /**
     * 발행 간격 구간 설정 위젯
     *
     * 누적 포스트 수에 따라 발행 간격을 차등 적용
     * 저장 형식: [{start: number, end: number|null, interval_minutes: number}, ...]
     */
    WidgetRegistry.register('interval-tiers', {
        render(key, schema, value, onChange) {
            // 초기값 설정 (기본: 1개 구간)
            const initScript = `
                if (!paramValues['${key}'] || !Array.isArray(paramValues['${key}']) || paramValues['${key}'].length === 0) {
                    paramValues['${key}'] = [
                        { start: 1, end: 50, interval_minutes: 120 },
                        { start: 51, end: 100, interval_minutes: 90 },
                        { start: 101, end: null, interval_minutes: 60 }
                    ];
                }
            `;

            return `
                <div x-init="${initScript}" class="space-y-4">
                    <!-- 구간 설명 -->
                    <div class="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                        <p class="font-medium mb-1">누적 포스트 수 기준 발행 간격 설정</p>
                        <p class="text-xs">포스트 수가 많을수록 간격을 줄여 발행 빈도를 높일 수 있습니다.</p>
                    </div>

                    <!-- 구간 목록 -->
                    <div class="space-y-3">
                        <template x-for="(tier, index) in paramValues['${key}']" :key="index">
                            <div class="flex flex-wrap items-center gap-2 p-3 bg-gray-50 rounded-lg border border-gray-200">
                                <!-- 구간 번호 -->
                                <span class="text-xs font-medium text-gray-500 w-6"
                                      x-text="'#' + (index + 1)"></span>

                                <!-- 시작 포스트 수 -->
                                <div class="flex items-center gap-1">
                                    <input type="text"
                                           inputmode="numeric"
                                           x-model.lazy="tier.start"
                                           class="no-spin ${baseInputClass} w-20 text-center text-sm"
                                           :disabled="index > 0">
                                    <span class="text-gray-500 text-sm">~</span>
                                </div>

                                <!-- 종료 포스트 수 -->
                                <div class="flex items-center gap-1">
                                    <input type="text"
                                           inputmode="numeric"
                                           x-model.lazy="tier.end"
                                           :placeholder="index === paramValues['${key}'].length - 1 ? '무제한' : ''"
                                           class="no-spin ${baseInputClass} w-20 text-center text-sm">
                                    <span class="text-gray-500 text-sm">개</span>
                                </div>

                                <!-- 화살표 -->
                                <span class="text-gray-400">→</span>

                                <!-- 발행 간격 -->
                                <div class="flex items-center gap-1">
                                    <input type="text"
                                           inputmode="numeric"
                                           x-model.lazy="tier.interval_minutes"
                                           class="no-spin ${baseInputClass} w-20 text-center text-sm">
                                    <span class="text-gray-500 text-sm">분 간격</span>
                                </div>

                                <!-- 일일 예상 횟수 -->
                                <span class="text-xs text-blue-600 ml-auto"
                                      x-text="'약 ' + Math.floor(1440 / (tier.interval_minutes || 60)) + '회/일'">
                                </span>

                                <!-- 삭제 버튼 -->
                                <button type="button"
                                        @click="paramValues['${key}'].splice(index, 1); if (paramValues['${key}'].length > 0 && index > 0) { paramValues['${key}'][index - 1].end = null; }"
                                        x-show="paramValues['${key}'].length > 1"
                                        class="text-red-500 hover:text-red-700 p-1 ml-1">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                    </svg>
                                </button>
                            </div>
                        </template>
                    </div>

                    <!-- 구간 추가 버튼 -->
                    <button type="button"
                            @click="(() => {
                                const tiers = paramValues['${key}'];
                                const lastTier = tiers[tiers.length - 1];
                                const newStart = (lastTier.end || lastTier.start) + 1;
                                // 마지막 구간에 종료값 설정
                                if (!lastTier.end) {
                                    lastTier.end = newStart - 1;
                                }
                                // 새 구간 추가
                                tiers.push({
                                    start: newStart,
                                    end: null,
                                    interval_minutes: Math.max(30, (lastTier.interval_minutes || 60) - 30)
                                });
                            })()"
                            x-show="paramValues['${key}'].length < 5"
                            class="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
                        </svg>
                        구간 추가 (최대 5개)
                    </button>

                    <!-- 안내 메시지 -->
                    <p class="text-xs text-gray-500">
                        마지막 구간의 종료 포스트 수는 비워두면 무제한으로 적용됩니다.
                    </p>
                </div>
            `;
        },

        // 현재 포스트 수에 해당하는 간격 반환
        getIntervalForPostCount(tiers, postCount) {
            if (!tiers || !Array.isArray(tiers)) return 60;

            for (const tier of tiers) {
                if (postCount >= tier.start && (tier.end === null || postCount <= tier.end)) {
                    return tier.interval_minutes || 60;
                }
            }
            // 기본값
            return 60;
        },

        // 기본값 생성
        getDefaultValue() {
            return [
                { start: 1, end: 50, interval_minutes: 120 },
                { start: 51, end: 100, interval_minutes: 90 },
                { start: 101, end: null, interval_minutes: 60 }
            ];
        }
    });

    /**
     * 라디오 버튼 위젯
     *
     * 여러 옵션 중 하나 선택 (열로 표시)
     * schema.enum: 옵션 값 배열
     * schema.enumLabels: 옵션 레이블 객체
     */
    WidgetRegistry.register('radio', {
        render(key, schema, value, onChange) {
            const options = schema.enum || [];
            const labels = schema.enumLabels || {};
            const defaultValue = schema.default || options[0] || '';

            const initScript = `
                if (!paramValues['${key}']) {
                    paramValues['${key}'] = '${defaultValue}';
                }
            `;

            let optionsHtml = '';
            options.forEach((opt, idx) => {
                const label = labels[opt] || opt;
                optionsHtml += `
                    <label class="flex items-center gap-3 p-3 border rounded-lg cursor-pointer transition-colors"
                           :class="paramValues['${key}'] === '${opt}' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'">
                        <input type="radio"
                               name="radio_${key}"
                               value="${opt}"
                               x-model="paramValues['${key}']"
                               class="text-blue-600 focus:ring-blue-500 h-4 w-4">
                        <div>
                            <span class="font-medium text-gray-900">${label}</span>
                        </div>
                    </label>
                `;
            });

            return `
                <div x-init="${initScript}" class="space-y-2">
                    ${optionsHtml}
                </div>
            `;
        }
    });

    /**
     * 템플릿 미리보기 위젯 (레거시 - 단순 표시용)
     */
    WidgetRegistry.register('template-preview', {
        render(key, schema, value, onChange) {
            const workflows = {
                'republish_standard': [
                    { icon: '🔍', name: '조회', desc: '블로그 목록 조회' },
                    { icon: '📊', name: '분류', desc: '상태 분류' },
                    { icon: '⏰', name: '스케줄', desc: '간격 설정' },
                    { icon: '🚀', name: '발행', desc: '재발행 실행' },
                    { icon: '📝', name: '기록', desc: '결과 저장' }
                ]
            };

            const workflowKey = schema.default || 'republish_standard';
            const workflow = workflows[workflowKey] || workflows['republish_standard'];

            let nodesHtml = workflow.map((node, idx) => {
                const arrow = idx < workflow.length - 1 ? `<span class="text-gray-400 mx-1">→</span>` : '';
                return `
                    <div class="flex items-center">
                        <div class="flex flex-col items-center px-2">
                            <span class="text-2xl">${node.icon}</span>
                            <span class="text-xs font-medium text-gray-700">${node.name}</span>
                        </div>
                        ${arrow}
                    </div>
                `;
            }).join('');

            return `
                <div class="p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg border border-blue-200">
                    <div class="flex flex-wrap items-center justify-center gap-1 mb-3">
                        ${nodesHtml}
                    </div>
                    <p class="text-center text-xs text-gray-600">
                        ${schema.description || '이 템플릿을 적용하면 위 5개 모듈이 자동으로 추가됩니다'}
                    </p>
                </div>
            `;
        }
    });

    /**
     * 상태 분류 모듈 전용 위젯
     *
     * 구조:
     * - 재발행 가능 최소 포스트 수: [10]개 이상일 때 재발행 시작
     * - 재발행 적용 구간: 시작[1]~종료[100](비워두면 무제한)
     */
    WidgetRegistry.register('status-classify-settings', {
        render(key, schema, value, onChange) {
            const initScript = `
                if (!paramValues['min_post_count']) paramValues['min_post_count'] = 10;
                if (!paramValues['post_range_from']) paramValues['post_range_from'] = 1;
                if (paramValues['post_range_to'] === undefined) paramValues['post_range_to'] = null;
            `;

            return `
                <div x-init="${initScript}" class="space-y-6">
                    <!-- 재발행 가능 최소 포스트 수 -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">
                            재발행 가능 최소 포스트 수
                        </label>
                        <div class="flex items-center gap-2">
                            <input type="text"
                                   inputmode="numeric"
                                   x-model.lazy="paramValues['min_post_count']"
                                   class="no-spin ${baseInputClass} w-20 text-center">
                            <span class="text-sm text-gray-600">개 이상일 때 재발행 시작</span>
                        </div>
                        <p class="mt-1 text-xs text-gray-500">
                            블로그에 최소 이만큼의 포스트가 누적되어야 재발행이 활성화됩니다
                        </p>
                    </div>

                    <!-- 재발행 적용 구간 -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">
                            재발행 적용 구간 (누적 포스트 수 기준)
                        </label>
                        <div class="flex items-center gap-2 flex-wrap">
                            <span class="text-sm text-gray-600">시작</span>
                            <input type="text"
                                   inputmode="numeric"
                                   x-model.lazy="paramValues['post_range_from']"
                                   class="no-spin ${baseInputClass} w-20 text-center">
                            <span class="text-gray-400">~</span>
                            <span class="text-sm text-gray-600">종료</span>
                            <input type="text"
                                   inputmode="numeric"
                                   x-model.lazy="paramValues['post_range_to']"
                                   placeholder="무제한"
                                   class="no-spin ${baseInputClass} w-24 text-center">
                            <span class="text-xs text-gray-500">(비워두면 무제한)</span>
                        </div>
                        <p class="mt-1 text-xs text-gray-500">
                            블로그에 누적된 포스트 수가 해당 범위일 때만 프로파일이 적용됩니다. 예: 누적 포스트가 1~100인 블로그에만 적용, 초과 시 미적용
                        </p>
                    </div>
                </div>
            `;
        }
    });

    /**
     * 액션 스케줄러 모듈 전용 위젯
     * - 스핀박스 없음 (직접 숫자 입력)
     * - 포커스 유지
     */
    WidgetRegistry.register('action-scheduler-settings', {
        render: function(key, schema, value, onChange) {
            var numInputClass = 'px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-center';

            return '<style>.no-spin::-webkit-outer-spin-button,.no-spin::-webkit-inner-spin-button{-webkit-appearance:none;margin:0}.no-spin{-moz-appearance:textfield}</style>' +
                '<div x-data="actionSchedulerComponent()" class="space-y-4">' +
                '<label class="block text-sm font-medium text-gray-700">액션 간격 설정 (하루 기준)</label>' +

                '<div class="border rounded-lg overflow-hidden" :class="_mode === \'time_based\' ? \'border-blue-500\' : \'border-gray-200\'">' +
                    '<label class="flex items-center gap-3 p-3 cursor-pointer" :class="_mode === \'time_based\' ? \'bg-blue-50\' : \'bg-gray-50\'">' +
                        '<input type="radio" value="time_based" x-model="_mode" class="text-blue-600 focus:ring-blue-500 h-4 w-4">' +
                        '<span class="font-medium text-gray-900">시간으로 설정</span>' +
                    '</label>' +
                    '<div x-show="_mode === \'time_based\'" x-cloak class="p-3 border-t border-l-4 border-l-blue-500 bg-white">' +
                        '<div class="flex items-center gap-2 flex-wrap">' +
                            '<span class="text-sm text-gray-600">액션 간격:</span>' +
                            '<input type="text" inputmode="numeric" x-model.lazy="_interval" class="no-spin ' + numInputClass + ' w-20">' +
                            '<span class="text-sm text-gray-600">분</span>' +
                            '<span class="text-gray-400 mx-1">/</span>' +
                            '<span class="text-sm text-gray-600">하루 최대:</span>' +
                            '<span class="font-semibold text-blue-600" x-text="calcDailyCount() + \'회\'"></span>' +
                        '</div>' +
                        '<p class="mt-2 text-xs text-gray-500">활성 시간대 기준으로 계산됩니다 (오늘 활성 시간: <span x-text="_activeHours"></span>시간)</p>' +
                    '</div>' +
                '</div>' +

                '<div class="border rounded-lg overflow-hidden" :class="_mode === \'count_based\' ? \'border-green-500\' : \'border-gray-200\'">' +
                    '<label class="flex items-center gap-3 p-3 cursor-pointer" :class="_mode === \'count_based\' ? \'bg-green-50\' : \'bg-gray-50\'">' +
                        '<input type="radio" value="count_based" x-model="_mode" class="text-green-600 focus:ring-green-500 h-4 w-4">' +
                        '<span class="font-medium text-gray-900">횟수로 설정</span>' +
                    '</label>' +
                    '<div x-show="_mode === \'count_based\'" x-cloak class="p-3 border-t border-l-4 border-l-green-500 bg-white">' +
                        '<div class="flex items-center gap-2 flex-wrap">' +
                            '<span class="text-sm text-gray-600">하루 목표:</span>' +
                            '<input type="text" inputmode="numeric" x-model.lazy="_count" class="no-spin ' + numInputClass + ' w-16">' +
                            '<span class="text-sm text-gray-600">회</span>' +
                            '<span class="text-gray-400 mx-1">/</span>' +
                            '<span class="text-sm text-gray-600">최소 간격:</span>' +
                            '<span class="font-semibold text-green-600" x-text="calcInterval() + \'분\'"></span>' +
                        '</div>' +
                        '<p class="mt-2 text-xs text-gray-500">활성 시간대 기준으로 간격이 자동 계산됩니다 (오늘 활성 시간: <span x-text="_activeHours"></span>시간)</p>' +
                    '</div>' +
                '</div>' +

                '<div class="border-t pt-4">' +
                    '<label class="block text-sm font-medium text-gray-700 mb-2">변동 범위</label>' +
                    '<div class="flex items-center gap-2">' +
                        '<span class="text-sm text-gray-600">±</span>' +
                        '<input type="text" inputmode="numeric" x-model.lazy="_jitter" class="no-spin ' + numInputClass + ' w-16">' +
                        '<span class="text-sm text-gray-600">%</span>' +
                    '</div>' +
                    '<p class="mt-1 text-xs text-gray-500">설정된 간격에서 ±N% 범위로 랜덤하게 재발행됩니다. 0으로 설정하면 고정 간격 사용.</p>' +
                '</div>' +

                '<div class="border-t pt-4">' +
                    '<label class="block text-sm font-medium text-gray-700 mb-2">활성 시간대 설정</label>' +
                    '<div x-html="(function() { ' +
                        'if (window.WidgetRegistry && window.WidgetRegistry.has(\'schedule-matrix\')) { ' +
                            'var widget = window.WidgetRegistry.get(\'schedule-matrix\'); ' +
                            'return widget.render(\'schedule_matrix\', { title: \'활성 시간대 설정\', description: \'월~일 x 0~24시 활성화 시간대\' }, null, null); ' +
                        '} ' +
                        'return \'<div class=text-gray-500>스케줄 매트릭스 위젯 로딩 중...</div>\'; ' +
                    '})()"></div>' +
                '</div>' +
            '</div>';
        }
    });

    /**
     * 워크플로우 가이드 위젯
     * - 각 모듈 클릭 시 선택/생성 팝업
     */
    WidgetRegistry.register('workflow-guide', {
        render: function(key, schema, value, onChange) {
            var steps = schema.workflow_steps || [];

            // steps 데이터를 글로벌에 저장
            window._workflowSteps = steps;

            // 단계별 HTML 생성
            var stepsHtml = '';
            for (var i = 0; i < steps.length; i++) {
                var step = steps[i];
                var arrow = i < steps.length - 1 ? '<span class="text-gray-400 mx-2 text-lg">&rarr;</span>' : '';

                stepsHtml += '<div class="flex items-center">' +
                    '<div class="flex flex-col items-center p-2 min-w-[70px] rounded-lg cursor-pointer hover:bg-blue-100 transition-colors" ' +
                        '@click="selectStep(' + i + ')" ' +
                        ':class="stepModules[' + i + '] ? \'bg-green-50 ring-2 ring-green-400\' : (selectedStep === ' + i + ' ? \'bg-blue-100 ring-2 ring-blue-400\' : \'\')">' +
                        '<span class="text-2xl mb-1">' + step.icon + '</span>' +
                        '<span class="text-xs font-medium text-gray-800 text-center">' + step.name + '</span>' +
                        '<span x-show="!stepModules[' + i + ']" class="text-[10px] text-gray-500 mt-0.5 text-center">' + step.desc + '</span>' +
                        '<span x-show="stepModules[' + i + ']" class="text-[10px] text-green-600 mt-0.5 text-center font-medium" x-text="stepModules[' + i + '] ? stepModules[' + i + '].name : \'\'"></span>' +
                    '</div>' +
                    arrow +
                '</div>';
            }

            return '<div x-data="workflowGuideComponent(window._workflowSteps)" class="space-y-4">' +
                '<div class="p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg border border-blue-200">' +
                    '<div class="flex flex-wrap items-center justify-center gap-1">' +
                        stepsHtml +
                    '</div>' +
                '</div>' +

                '<div x-show="showPopup" x-transition class="mt-4 border-2 border-blue-300 rounded-xl bg-white shadow-lg overflow-hidden">' +
                    '<div class="p-3 border-b bg-blue-50">' +
                        '<div class="flex items-center justify-between">' +
                            '<h3 class="font-semibold text-gray-800" x-text="getStepName()"></h3>' +
                            '<button type="button" @click="showPopup = false" class="text-gray-400 hover:text-gray-600">' +
                                '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>' +
                            '</button>' +
                        '</div>' +
                    '</div>' +
                    '<div class="p-4 max-h-64 overflow-y-auto">' +
                        '<div x-show="loading" class="text-center py-4">' +
                            '<div class="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 mx-auto"></div>' +
                            '<p class="text-sm text-gray-500 mt-2">모듈 목록 로딩 중...</p>' +
                        '</div>' +
                        '<div x-show="!loading && (!availableModules || availableModules.length === 0)" class="py-4">' +
                            '<p class="text-sm text-gray-500 mb-3 text-center">생성된 모듈이 없습니다</p>' +
                            '<button type="button" @click="createNewModule()" class="w-full px-3 py-2 border-2 border-dashed border-gray-300 text-gray-600 rounded-lg hover:border-blue-400 hover:text-blue-600 text-sm">' +
                                '+ 새 모듈 생성' +
                            '</button>' +
                        '</div>' +
                        '<div x-show="!loading && availableModules && availableModules.length > 0" class="space-y-2">' +
                            '<template x-for="(mod, modIdx) in availableModules" :key="modIdx">' +
                                '<button type="button" @click="selectModule(mod.id, mod.name)" ' +
                                    'class="w-full text-left p-3 rounded-lg border hover:bg-blue-50 hover:border-blue-300 transition-colors" ' +
                                    ':class="stepModules[selectedStep] && stepModules[selectedStep].id === mod.id ? \'bg-blue-50 border-blue-500\' : \'border-gray-200\'">' +
                                    '<div class="font-medium text-gray-800" x-text="mod.name"></div>' +
                                    '<div class="text-xs text-gray-500" x-text="mod.description || \'설명 없음\'"></div>' +
                                '</button>' +
                            '</template>' +
                            '<div class="pt-3 border-t mt-3">' +
                                '<button type="button" @click="createNewModule()" class="w-full px-3 py-2 border-2 border-dashed border-gray-300 text-gray-600 rounded-lg hover:border-blue-400 hover:text-blue-600 text-sm">' +
                                    '+ 새 모듈 생성' +
                                '</button>' +
                            '</div>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
            '</div>';
        }
    });

    console.log('[ExtendedWidgets] 확장 위젯 로드 완료:', WidgetRegistry.list());
})();
