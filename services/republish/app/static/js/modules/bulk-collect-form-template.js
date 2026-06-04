/**
 * 대량 수집(bulk_collect) 모듈 인라인 폼 전체 템플릿.
 *
 * list.js 의 getDefaultFormHTML() 안에서 호출되어
 * 모듈 폼 영역에 동적으로 끼워 넣는다.
 *
 * 섹션:
 *   2. URL 소스
 *   3. 8개 파라미터
 *   4. 스케줄(matrix + interval + jitter)
 *
 * Alpine 상태는 상위 moduleFormApp 의 bcModule 객체
 * (createBulkCollectState()) 를 그대로 참조한다.
 *
 * NOTE: _bulk_collect_form.html (Jinja2 include 용) 의 마크업과 동일하다.
 *       양쪽을 동시에 수정해야 한다.
 */

/** 섹션 2: 수집 대상 URL (URL탭에서 블로그 가져오기) */
function getBCUrlSourceSection() {
    return `
        <div id="bc-url-source-section" class="space-y-4 mb-6">
            <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                📥 수집 대상 URL
            </h3>
            <p class="text-xs text-gray-500 -mt-2">
                데이터 관리 → <strong>URL탭</strong>(수집 모듈이 모은 블로그 주소)에서 가져옵니다.
            </p>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div class="p-3 bg-gray-50 rounded-lg">
                    <label class="block text-xs font-medium text-gray-700 mb-1">
                        사이클당 블로그 수
                    </label>
                    <input type="number"
                           x-model.number="bcModule.from_collect.max_urls"
                           min="1" max="100"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg
                                  focus:ring-2 focus:ring-purple-500 text-sm">
                    <p class="mt-1 text-xs text-gray-500">
                        한 번 실행에 URL탭에서 가져올 블로그 수 · 기본값: 3
                    </p>
                </div>

                <div class="p-3 bg-gray-50 rounded-lg">
                    <label class="block text-xs font-medium text-gray-700 mb-1">
                        가져오는 순서
                    </label>
                    <div class="flex gap-4 mt-2">
                        <label class="flex items-center cursor-pointer">
                            <input type="radio" x-model="bcModule.from_collect.order_mode"
                                   value="stored"
                                   class="text-purple-600 focus:ring-purple-500 h-4 w-4">
                            <span class="ml-2 text-sm text-gray-700">저장 순서</span>
                        </label>
                        <label class="flex items-center cursor-pointer">
                            <input type="radio" x-model="bcModule.from_collect.order_mode"
                                   value="random"
                                   class="text-purple-600 focus:ring-purple-500 h-4 w-4">
                            <span class="ml-2 text-sm text-gray-700">랜덤</span>
                        </label>
                    </div>
                </div>
            </div>

            <div class="p-3 bg-purple-50 rounded-lg">
                <p class="text-xs text-purple-800">
                    📌 선택한 블로그의 <strong>사이트맵을 크롤링</strong>해 글 주소를 모으고,
                    각 글에서 제목을 추출해 <strong>임시제목탭</strong>에 저장합니다.
                    재실행 시 이미 모은 글은 건너뛰고 새 글만 추가합니다(증분).
                </p>
            </div>
        </div>
    `;
}

/** 섹션 3: 대량 수집 파라미터 (확정 옵션 3종 + 자동 전역 동시) */
function getBCParamsSection() {
    return `
        <div id="bc-params-section" class="space-y-4 mb-6">
            <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                ⚙️ 대량 수집 파라미터
            </h3>
            <p class="text-xs text-gray-500 -mt-2">
                각 항목은 한 번의 실행이 어떻게 동작할지를 결정합니다.
            </p>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div class="p-3 bg-gray-50 rounded-lg">
                    <label class="block text-xs font-medium text-gray-700 mb-1">
                        사이클 최대 시간 (초)
                    </label>
                    <input type="number"
                           x-model.number="bcModule.bulk_params.cycle_max_duration_sec"
                           min="30" max="3600"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg
                                  focus:ring-2 focus:ring-blue-500 text-sm">
                    <p class="mt-1 text-xs text-gray-500">
                        이 시간이 지나면 멈추고 남은 작업은 다음 실행에서 이어서 합니다.
                        예: 300초 = 5분 · 기본값: 300
                    </p>
                </div>

                <div class="p-3 bg-gray-50 rounded-lg">
                    <label class="block text-xs font-medium text-gray-700 mb-1">
                        블로그당 가져올 글 수
                    </label>
                    <input type="number"
                           x-model.number="bcModule.bulk_params.chunk_size_initial"
                           min="1" max="10000"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg
                                  focus:ring-2 focus:ring-blue-500 text-sm">
                    <p class="mt-1 text-xs text-gray-500">
                        각 블로그 사이트맵에서 한 번에 가져올 <strong>새 글 주소</strong> 수 · 기본값: 100
                    </p>
                </div>

                <div class="p-3 bg-gray-50 rounded-lg">
                    <label class="block text-xs font-medium text-gray-700 mb-1">
                        같은 블로그 동시 요청 수
                    </label>
                    <input type="number"
                           x-model.number="bcModule.bulk_params.domain_concurrency"
                           min="1" max="20"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg
                                  focus:ring-2 focus:ring-blue-500 text-sm">
                    <p class="mt-1 text-xs text-gray-500">
                        한 블로그에 동시에 보낼 요청 수. 많으면 차단될 수 있습니다.
                        1~3 권장 · 기본값: 2
                    </p>
                </div>
            </div>

            <div class="p-3 bg-blue-50 rounded-lg">
                <p class="text-xs text-blue-800">
                    💡 전체 동시 요청 수는
                    <strong>(사이클당 블로그 수 × 같은 블로그 동시 요청 수)</strong> 로
                    자동 계산됩니다. 예: 블로그 3 × 동시 2 = 전체 6.
                </p>
            </div>

            <div class="space-y-2">
                <label class="flex items-start p-3 bg-gray-50 rounded-lg cursor-pointer
                              hover:bg-gray-100 transition-colors">
                    <input type="checkbox"
                           x-model="bcModule.bulk_params.pause_on_callback_backlog"
                           class="w-4 h-4 mt-0.5 text-blue-600 rounded focus:ring-blue-500">
                    <div class="ml-3">
                        <span class="text-sm font-medium text-gray-700">
                            다른 작업이 밀려있으면 건너뛰기
                        </span>
                        <p class="text-xs text-gray-500 mt-0.5">
                            발행이나 글 생성 등 다른 작업이 많이 쌓여있으면
                            이번 회는 쉽니다 (서버 보호).
                        </p>
                    </div>
                </label>
            </div>
        </div>
    `;
}

/** 섹션 4: 스케줄 */
function getBCScheduleSection() {
    return `
        <div id="bc-schedule-section" class="space-y-4 mb-6">
            <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                ⏰ 수집 스케줄
            </h3>
            <p class="text-xs text-gray-500 -mt-2">사이클이 실행될 시간대와 간격을 설정합니다.</p>

            <div class="bg-gray-50 rounded-lg p-4">
                <div class="flex flex-wrap gap-2 mb-4">
                    <button type="button" @click="bcModule.selectAllHours()"
                            class="px-3 py-1 text-xs bg-blue-100 text-blue-800 rounded-full hover:bg-blue-200">
                        전체 선택
                    </button>
                    <button type="button" @click="bcModule.clearAllHours()"
                            class="px-3 py-1 text-xs bg-gray-100 text-gray-800 rounded-full hover:bg-gray-200">
                        전체 해제
                    </button>
                    <button type="button" @click="bcModule.selectWeekdayHours()"
                            class="px-3 py-1 text-xs bg-green-100 text-green-800 rounded-full hover:bg-green-200">
                        평일 6~21시
                    </button>
                </div>
                <p class="text-xs text-gray-500 mb-3">
                    파란색 = 활성, 회색 = 비활성 | 요일 헤더 클릭으로 전체 선택/해제
                </p>
                <div class="overflow-x-auto">
                    <table class="w-full text-xs border-collapse">
                        <thead>
                            <tr>
                                <th class="border border-gray-300 bg-gray-100 p-2 text-center w-12">시간</th>
                                <template x-for="(day, dayIdx) in bcModule.days" :key="dayIdx">
                                    <th class="border border-gray-300 bg-gray-100 p-2 text-center
                                               cursor-pointer hover:bg-gray-200 w-8"
                                        @click="bcModule.toggleDay(dayIdx)" x-text="day"></th>
                                </template>
                            </tr>
                        </thead>
                        <tbody>
                            <template x-for="hour in 24" :key="hour">
                                <tr>
                                    <td class="border border-gray-300 bg-gray-50 p-1 text-center font-medium"
                                        x-text="String(hour-1).padStart(2, '0') + '시'"></td>
                                    <template x-for="(day, dayIdx) in bcModule.days" :key="dayIdx + '-' + hour">
                                        <td class="border border-gray-300 p-0">
                                            <button type="button"
                                                    class="w-full h-7 border-none cursor-pointer
                                                           transition-colors duration-150"
                                                    :class="bcModule.schedule_matrix &&
                                                            bcModule.schedule_matrix[dayIdx][hour-1]
                                                        ? 'bg-blue-500 hover:bg-blue-600'
                                                        : 'bg-gray-100 hover:bg-gray-200'"
                                                    @click="bcModule.toggleHour(dayIdx, hour-1)"></button>
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
                            활성 시간: <span x-text="bcModule.activeHoursCount"></span>시간/주
                        </span>
                        <span class="text-blue-600" x-show="bcModule.todayActiveHours > 0">
                            오늘: <span x-text="bcModule.todayActiveHours"></span>시간
                        </span>
                    </div>
                </div>
            </div>

            <div class="p-3 bg-gray-50 rounded-lg">
                <label class="block text-xs font-medium text-gray-700 mb-1">실행 간격 (분)</label>
                <input type="number" x-model.number="bcModule.interval_minutes"
                       min="1" max="1440"
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg
                              focus:ring-2 focus:ring-blue-500 text-sm">
                <p class="mt-1 text-xs text-gray-400">기본 60분 (사이클 사이의 베이스 간격)</p>
            </div>

            <!-- 지터(랜덤 변동) — GP 폼과 동일한 ±% 구조 -->
            <div class="p-4 bg-gray-50 rounded-lg space-y-3">
                <label class="flex items-center cursor-pointer">
                    <input type="checkbox" x-model="bcModule.schedule_jitter.enabled"
                           class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500">
                    <span class="ml-2 text-sm font-medium text-gray-700">지터(랜덤 변동) 사용</span>
                </label>
                <p class="text-xs text-gray-500 ml-6">
                    간격에 무작위 변동을 더해 실행 시각을 분산시킵니다 (서버 부하 분산용)
                </p>

                <div x-show="bcModule.schedule_jitter.enabled" x-transition
                     class="space-y-3 ml-6">
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs text-gray-600 mb-1">최소 변동 (%)</label>
                            <input type="number"
                                   x-model.number="bcModule.schedule_jitter.min_percent"
                                   min="-50" max="0" step="5"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg
                                          focus:ring-2 focus:ring-blue-500 text-sm">
                            <p class="mt-1 text-xs text-gray-500">기본 -20%</p>
                        </div>
                        <div>
                            <label class="block text-xs text-gray-600 mb-1">최대 변동 (%)</label>
                            <input type="number"
                                   x-model.number="bcModule.schedule_jitter.max_percent"
                                   min="0" max="100" step="5"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg
                                          focus:ring-2 focus:ring-blue-500 text-sm">
                            <p class="mt-1 text-xs text-gray-500">기본 +30%</p>
                        </div>
                    </div>
                    <p class="text-xs text-gray-500">
                        예: 간격 60분 + 지터(-20%~+30%) = <strong>48~78분 랜덤</strong>
                    </p>
                </div>
            </div>
        </div>
    `;
}

/** bulk_collect 전체 인라인 폼 템플릿 */
function getBulkCollectFormTemplate() {
    return `
        <div x-show="formData.type_code === 'bulk_collect'" class="space-y-6">
            ${getBCUrlSourceSection()}
            ${getBCParamsSection()}
            ${getBCScheduleSection()}

            <div x-show="bcModule.validationError"
                 class="p-3 bg-red-50 border border-red-200 rounded-lg">
                <p class="text-sm text-red-700 flex items-start gap-2">
                    <span>⚠️</span>
                    <span x-text="bcModule.validationError"></span>
                </p>
            </div>
        </div>
    `;
}

// 전역 노출
window.getBulkCollectFormTemplate = getBulkCollectFormTemplate;
