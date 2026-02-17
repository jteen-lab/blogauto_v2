/** 생성 모듈 폼 HTML 템플릿 - list.js의 getFullFormTemplate()에서 호출 */
function getGenerateModuleFormTemplate() {
    return `
                        <!-- 생성 모듈 설정: 스케줄러 + 내부링크 + 재고 -->
                        <div x-show="formData.type_code === 'generate'" class="space-y-6">
                            <!-- 생성 간격 설정 -->
                            <div class="space-y-4">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    &#9201;&#65039; 생성 간격 설정
                                </h3>

                                <!-- 간격 설정 모드 선택 -->
                                <div class="flex gap-4 mb-4">
                                    <label class="flex items-center cursor-pointer">
                                        <input type="radio"
                                               x-model="formData.interval_mode"
                                               value="manual"
                                               class="text-blue-600 focus:ring-blue-500 h-4 w-4">
                                        <span class="ml-2 text-sm text-gray-700">시간으로 설정</span>
                                    </label>
                                    <label class="flex items-center cursor-pointer">
                                        <input type="radio"
                                               x-model="formData.interval_mode"
                                               value="auto"
                                               class="text-blue-600 focus:ring-blue-500 h-4 w-4">
                                        <span class="ml-2 text-sm text-gray-700">횟수로 설정</span>
                                    </label>
                                </div>

                                <!-- Manual 모드 -->
                                <div x-show="formData.interval_mode === 'manual'" class="p-4 bg-gray-50 rounded-lg">
                                    <div class="flex items-center gap-2 flex-wrap">
                                        <span class="text-gray-700 text-sm">생성 간격:</span>
                                        <input type="number"
                                               x-model.number="formData.manual_interval_minutes"
                                               min="15" max="1440"
                                               class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                               @input="calculateFromInterval()">
                                        <span class="text-gray-500 text-sm">분</span>
                                        <span class="text-gray-400">/</span>
                                        <span class="text-gray-500 text-sm">하루 최대:</span>
                                        <span class="font-semibold text-blue-600" x-text="calculatedDailyCount + '회'"></span>
                                    </div>
                                    <p class="mt-2 text-xs text-gray-500">활성 시간대 기준 (오늘: <span x-text="todayActiveHours"></span>시간)</p>
                                </div>

                                <!-- Auto 모드 -->
                                <div x-show="formData.interval_mode === 'auto'" class="p-4 bg-gray-50 rounded-lg">
                                    <div class="flex items-center gap-2 flex-wrap">
                                        <span class="text-gray-700 text-sm">하루 목표:</span>
                                        <input type="number"
                                               x-model.number="formData.auto_daily_count"
                                               min="1" max="100"
                                               class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                               @input="calculateFromDailyCount()">
                                        <span class="text-gray-500 text-sm">회</span>
                                        <span class="text-gray-400">/</span>
                                        <span class="text-gray-500 text-sm">최소 간격:</span>
                                        <span class="font-semibold text-blue-600" x-text="calculatedInterval + '분'"></span>
                                    </div>
                                    <p class="mt-2 text-xs text-gray-500">활성 시간대 기준 (오늘: <span x-text="todayActiveHours"></span>시간)</p>
                                </div>

                                <div class="flex items-center gap-2 text-xs text-blue-600">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                                    </svg>
                                    <span>최소 15분 이상 간격이 유지되도록 설정됩니다</span>
                                </div>
                            </div>

                            <!-- 활성 시간대 스케줄 -->
                            <div class="space-y-4">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    &#128197; 활성 시간대
                                </h3>
                                <div class="bg-gray-50 rounded-lg p-4">
                                    <div class="flex flex-wrap gap-2 mb-4">
                                        <button type="button" @click="selectAllHours()"
                                                class="px-3 py-1 text-xs bg-blue-100 text-blue-800 rounded-full hover:bg-blue-200">
                                            전체 선택
                                        </button>
                                        <button type="button" @click="clearAllHours()"
                                                class="px-3 py-1 text-xs bg-gray-100 text-gray-800 rounded-full hover:bg-gray-200">
                                            전체 해제
                                        </button>
                                        <button type="button" @click="selectWorkingHours()"
                                                class="px-3 py-1 text-xs bg-green-100 text-green-800 rounded-full hover:bg-green-200">
                                            평일 9-21시
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
                                                                        class="w-full h-7 border-none cursor-pointer transition-colors duration-150"
                                                                        :class="schedule[dayIdx][hour-1] ? 'bg-blue-500 hover:bg-blue-600' : 'bg-gray-100 hover:bg-gray-200'"
                                                                        @click="toggleHour(dayIdx, hour-1)"></button>
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
                                                활성 시간: <span x-text="activeHoursCount"></span>시간/주
                                            </span>
                                            <span class="text-blue-600" x-show="todayActiveHours > 0">
                                                오늘: <span x-text="todayActiveHours"></span>시간
                                            </span>
                                        </div>
                                        <p class="text-xs text-blue-600 mt-1" x-show="expectedDailyPosts > 0">
                                            예상 일일 생성: 약 <span x-text="expectedDailyPosts"></span>회
                                        </p>
                                    </div>
                                </div>
                            </div>

                            <!-- 내부링크 설정 -->
                            <div class="space-y-4">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    내부링크 설정
                                </h3>

                                <div class="border border-green-200 rounded-lg overflow-hidden">
                                    <!-- 활성화 토글 -->
                                    <div class="flex items-center p-3 bg-green-50 border-b border-green-200 cursor-pointer"
                                         @click="formData.il_enabled = !formData.il_enabled">
                                        <input type="checkbox"
                                               :checked="formData.il_enabled"
                                               class="text-green-600 focus:ring-green-500 h-4 w-4 rounded pointer-events-none">
                                        <span class="ml-3 text-sm font-medium text-gray-700">내부링크 자동 삽입</span>
                                    </div>

                                    <!-- 상세 설정 (활성화 시) -->
                                    <div x-show="formData.il_enabled" x-transition class="p-4 space-y-4">
                                        <div class="p-3 bg-green-50 rounded-lg">
                                            <p class="text-sm text-green-800 font-medium mb-2">내부링크 삽입 프로세스:</p>
                                            <ol class="text-xs text-green-700 space-y-1 list-decimal list-inside">
                                                <li>대상 블로그의 기존 발행글 목록을 조회</li>
                                                <li>유사 제목 글을 서론 뒤에 삽입 (버튼/일반 선택)</li>
                                                <li>각 본론 섹션 제목과 유사한 글을 섹션 뒤에 삽입</li>
                                                <li>랜덤 글을 결론 뒤에 목록 형태로 삽입</li>
                                            </ol>
                                        </div>

                                        <!-- 유사도 임계값 -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">유사도 임계값</label>
                                            <div class="flex items-center gap-3">
                                                <input type="range"
                                                       x-model.number="formData.il_similarity_threshold"
                                                       min="50" max="100" step="5"
                                                       class="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-green-600">
                                                <span class="w-14 text-center text-sm font-medium text-green-700 bg-green-50 rounded px-2 py-1"
                                                      x-text="formData.il_similarity_threshold + '%'"></span>
                                            </div>
                                            <p class="mt-1 text-xs text-gray-500">권장: 75%</p>
                                        </div>

                                        <!-- 서론 링크 -->
                                        <div class="border border-gray-200 rounded-lg p-3 space-y-3">
                                            <span class="text-sm font-medium text-gray-800">서론 뒤 링크</span>
                                            <div class="grid grid-cols-2 gap-3">
                                                <div>
                                                    <label class="block text-xs text-gray-500 mb-1">링크 수</label>
                                                    <input type="number"
                                                           x-model.number="formData.il_intro_count"
                                                           min="1" max="5"
                                                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent text-sm">
                                                    <p class="mt-0.5 text-xs text-gray-400">1~5개</p>
                                                </div>
                                                <div>
                                                    <label class="block text-xs text-gray-500 mb-1">링크 타입</label>
                                                    <select x-model="formData.il_intro_link_type"
                                                            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent text-sm">
                                                        <option value="button">버튼 링크</option>
                                                        <option value="normal">일반 링크</option>
                                                    </select>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- 본론 섹션 안내 -->
                                        <div class="border border-gray-200 rounded-lg p-3">
                                            <span class="text-sm font-medium text-gray-800">본론 섹션 링크</span>
                                            <p class="mt-1 text-xs text-gray-500">
                                                각 본문 섹션 제목과 유사한 기존 글이 있을 경우 자동 삽입 (섹션당 1개)
                                            </p>
                                        </div>

                                        <!-- 결론 링크 -->
                                        <div class="border border-gray-200 rounded-lg p-3 space-y-3">
                                            <span class="text-sm font-medium text-gray-800">결론 뒤 링크</span>
                                            <div class="grid grid-cols-2 gap-3">
                                                <div>
                                                    <label class="block text-xs text-gray-500 mb-1">링크 수</label>
                                                    <input type="number"
                                                           x-model.number="formData.il_conclusion_count"
                                                           min="1" max="10"
                                                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent text-sm">
                                                    <p class="mt-0.5 text-xs text-gray-400">1~10개</p>
                                                </div>
                                                <div>
                                                    <label class="block text-xs text-gray-500 mb-1">리스트 스타일</label>
                                                    <select x-model="formData.il_conclusion_list_style"
                                                            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent text-sm">
                                                        <option value="dash">기호 리스트 (- )</option>
                                                        <option value="number">번호 리스트 (1. )</option>
                                                        <option value="none">리스트 없음</option>
                                                    </select>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- 재고 관리 설정 -->
                            <div class="space-y-4">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    재고 관리 설정
                                </h3>

                                <div class="border border-indigo-200 rounded-lg p-4 space-y-5">
                                    <div class="p-3 bg-indigo-50 rounded-lg">
                                        <p class="text-sm text-indigo-800">
                                            블로그 성장 단계에 따라 글 재고(미발행 생성글) 유지량을 설정합니다.
                                            재고가 기준 이하로 떨어지면 자동으로 글을 생성합니다.
                                        </p>
                                    </div>

                                    <!-- 급성장기 -->
                                    <div class="border border-gray-200 rounded-lg p-3 space-y-3">
                                        <div class="flex items-center gap-2">
                                            <span class="text-sm font-medium text-gray-800">급성장기</span>
                                            <span class="text-xs text-gray-500">발행글 수가 적은 초기 블로그</span>
                                        </div>
                                        <div class="grid grid-cols-2 gap-3">
                                            <div>
                                                <label class="block text-xs text-gray-500 mb-1">기준 발행글 수 (이하)</label>
                                                <input type="number"
                                                       x-model.number="formData.inv_rapid_growth_threshold"
                                                       min="10" max="200"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent text-sm">
                                            </div>
                                            <div>
                                                <label class="block text-xs text-gray-500 mb-1">재고 유지량</label>
                                                <input type="number"
                                                       x-model.number="formData.inv_rapid_growth_inventory"
                                                       min="1" max="30"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent text-sm">
                                                <p class="mt-0.5 text-xs text-gray-400">이 수 이하 시 자동 생성</p>
                                            </div>
                                        </div>
                                    </div>

                                    <!-- 성장기 -->
                                    <div class="border border-gray-200 rounded-lg p-3 space-y-3">
                                        <div class="flex items-center gap-2">
                                            <span class="text-sm font-medium text-gray-800">성장기</span>
                                            <span class="text-xs text-gray-500">콘텐츠가 쌓이기 시작한 블로그</span>
                                        </div>
                                        <div class="grid grid-cols-2 gap-3">
                                            <div>
                                                <label class="block text-xs text-gray-500 mb-1">기준 발행글 수 (이하)</label>
                                                <input type="number"
                                                       x-model.number="formData.inv_growth_threshold"
                                                       min="50" max="500"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent text-sm">
                                            </div>
                                            <div>
                                                <label class="block text-xs text-gray-500 mb-1">재고 유지량</label>
                                                <input type="number"
                                                       x-model.number="formData.inv_growth_inventory"
                                                       min="1" max="20"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent text-sm">
                                                <p class="mt-0.5 text-xs text-gray-400">이 수 이하 시 자동 생성</p>
                                            </div>
                                        </div>
                                    </div>

                                    <!-- 안정기 -->
                                    <div class="border border-gray-200 rounded-lg p-3 space-y-3">
                                        <div class="flex items-center gap-2">
                                            <span class="text-sm font-medium text-gray-800">안정기</span>
                                            <span class="text-xs text-gray-500">충분한 콘텐츠를 보유한 블로그</span>
                                        </div>
                                        <div>
                                            <label class="block text-xs text-gray-500 mb-1">재고 유지량</label>
                                            <input type="number"
                                                   x-model.number="formData.inv_stable_inventory"
                                                   min="1" max="10"
                                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent text-sm">
                                            <p class="mt-0.5 text-xs text-gray-400">성장기 기준 초과 시 적용</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
`;
}

// 전역 노출
window.getGenerateModuleFormTemplate = getGenerateModuleFormTemplate;
