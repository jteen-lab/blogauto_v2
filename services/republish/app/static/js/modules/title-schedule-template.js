/**
 * 제목 모듈 스케줄 UI — 키워드 모듈과 **같은 방식**.
 *
 * 분 단위 숫자 하나로 받던 것을 다른 모듈과 같은 형태(고정 시간 /
 * 간격 + 활성 시간대)로 맞춘다. 모듈마다 스케줄 UI 가 다르면 사용자가
 * 매번 다시 익혀야 한다.
 *
 * 계획서: docs/plans/title_tab_workplan.md §1
 */
window.getTitleScheduleTemplate = function () {
    return `
    <div class="border border-gray-200 rounded-lg p-3 space-y-4">
        <div class="text-sm font-semibold text-gray-800">🕐 실행 스케줄</div>

        <div class="flex gap-4">
            <label class="flex items-center cursor-pointer">
                <input type="radio" x-model="formData.title.schedule_mode" value="fixed_time"
                       class="text-amber-600 focus:ring-amber-500">
                <span class="ml-2 text-sm">고정 시간 (권장)</span>
            </label>
            <label class="flex items-center cursor-pointer">
                <input type="radio" x-model="formData.title.schedule_mode" value="interval"
                       class="text-amber-600 focus:ring-amber-500">
                <span class="ml-2 text-sm">간격 기반</span>
            </label>
        </div>

        <!-- 고정 시간 -->
        <div x-show="formData.title.schedule_mode === 'fixed_time'" class="p-3 bg-amber-50 rounded-lg">
            <label class="block text-sm font-medium text-gray-700 mb-2">실행 시간</label>
            <div class="flex flex-wrap gap-2 mb-3">
                <template x-for="(time, idx) in formData.title.fixed_times" :key="idx">
                    <span class="inline-flex items-center px-3 py-1 bg-amber-200 text-amber-900 rounded-full text-sm">
                        <span x-text="time"></span>
                        <button type="button" @click="removeTitleTime(time)"
                                class="ml-2 text-amber-700 hover:text-amber-900">×</button>
                    </span>
                </template>
                <span x-show="!formData.title.fixed_times.length" class="text-xs text-gray-500 py-1">
                    아직 없습니다 — 시간을 추가하세요
                </span>
            </div>
            <div class="flex items-center gap-2">
                <input type="time" x-model="newFixedTime"
                       class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500">
                <button type="button" @click="addTitleTime()"
                        class="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 text-sm">추가</button>
            </div>
            <p class="mt-2 text-xs text-gray-500">매일 지정한 시간에 실행합니다</p>
        </div>

        <!-- 간격 -->
        <div x-show="formData.title.schedule_mode === 'interval'" class="p-3 bg-amber-50 rounded-lg">
            <div class="flex items-center gap-2">
                <span class="text-gray-700 text-sm">실행 간격:</span>
                <input type="number" x-model.number="formData.title.interval_hours" min="1" max="24"
                       class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500">
                <span class="text-gray-500 text-sm">시간마다</span>
            </div>
            <p class="mt-2 text-xs text-gray-500">아래 활성 시간대 안에서만 실행합니다</p>
        </div>

        <!-- 활성 시간대 -->
        <div x-show="formData.title.schedule_mode === 'interval'">
            <label class="block text-sm font-medium text-gray-700 mb-2">활성 시간대</label>
            <div class="bg-gray-50 rounded-lg p-3">
                <div class="flex flex-wrap gap-2 mb-3">
                    <button type="button" @click="selectAllHours()"
                            class="px-3 py-1 text-xs bg-amber-100 text-amber-800 rounded-full hover:bg-amber-200">
                        전체 선택 (24시간)
                    </button>
                    <button type="button" @click="clearAllHours()"
                            class="px-3 py-1 text-xs bg-gray-100 text-gray-800 rounded-full hover:bg-gray-200">
                        전체 해제
                    </button>
                    <button type="button" @click="selectWorkingHours()"
                            class="px-3 py-1 text-xs bg-green-100 text-green-800 rounded-full hover:bg-green-200">
                        업무 시간 (평일 9-21시)
                    </button>
                </div>
                <p class="text-xs text-gray-500 mb-2">주황 = 활성, 회색 = 비활성</p>
                <div class="overflow-x-auto">
                    <table class="w-full text-xs border-collapse">
                        <thead>
                            <tr>
                                <th class="border border-gray-300 bg-gray-100 p-2 text-center w-12">시간</th>
                                <template x-for="(day, dayIdx) in days" :key="dayIdx">
                                    <th class="border border-gray-300 bg-gray-100 p-2 text-center cursor-pointer hover:bg-gray-200 w-8"
                                        @click="toggleDay(dayIdx)" x-text="day"></th>
                                </template>
                            </tr>
                        </thead>
                        <tbody>
                            <template x-for="hour in 24" :key="hour">
                                <tr>
                                    <td class="border border-gray-300 bg-gray-50 p-1 text-center font-medium"
                                        x-text="String(hour-1).padStart(2, '0') + '시'"></td>
                                    <template x-for="(day, dayIdx) in days" :key="dayIdx + '-' + hour">
                                        <td class="border border-gray-300 p-0">
                                            <button type="button"
                                                    class="w-full h-6 border-none cursor-pointer transition-colors duration-150"
                                                    :class="schedule[dayIdx] && schedule[dayIdx][hour-1] ? 'bg-amber-500 hover:bg-amber-600' : 'bg-gray-100 hover:bg-gray-200'"
                                                    @click="toggleHour(dayIdx, hour-1)"></button>
                                        </td>
                                    </template>
                                </tr>
                            </template>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    `;
};
